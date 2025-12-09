"""
策略管理API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from loguru import logger
from datetime import datetime

from api.auth import get_current_user, UserInfo
from services.event_manager import sse_manager

router = APIRouter()

# ============================================
# 数据模型
# ============================================

class Strategy(BaseModel):
    """策略模型"""
    id: int
    name: str
    type: str
    account: str
    status: str
    pnl: float = 0.0
    returnRate: float = 0.0
    trades: int = 0
    runTime: str = "-"
    pythonFile: Optional[str] = None
    parameters: Optional[Dict] = None
    createdAt: Optional[datetime] = None

class StrategyCreate(BaseModel):
    """创建策略请求"""
    name: str
    type: str
    accountId: int
    symbol: str
    pythonFile: str
    parameters: Optional[Dict] = {}
    description: Optional[str] = ""
    autoStart: bool = False

# ============================================
# Mock数据（临时）
# ============================================

MOCK_STRATEGIES = [
    Strategy(
        id=1,
        name='网格交易策略A',
        type='grid',
        account='OKX账户1',
        status='running',
        pnl=1250.50,
        returnRate=12.5,
        trades=145,
        runTime='3天12小时'
    ),
    Strategy(
        id=2,
        name='趋势跟踪策略B',
        type='trend',
        account='OKX账户2',
        status='running',
        pnl=680.30,
        returnRate=6.8,
        trades=89,
        runTime='2天8小时'
    ),
    Strategy(
        id=3,
        name='套利策略C',
        type='arbitrage',
        account='OKX账户1',
        status='stopped',
        pnl=-120.40,
        returnRate=-1.2,
        trades=56,
        runTime='1天6小时'
    )
]

# ============================================
# API端点
# ============================================

@router.get("", response_model=List[Strategy])
async def get_strategies(
    current_user: UserInfo = Depends(get_current_user)
):
    """获取策略列表"""
    logger.info(f"用户 {current_user.username} 查询策略列表")
    
    # TODO: 从数据库查询
    return MOCK_STRATEGIES

@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """获取策略详情"""
    strategy = next((s for s in MOCK_STRATEGIES if s.id == strategy_id), None)
    
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    
    return {"code": 200, "data": strategy}

@router.post("")
async def create_strategy(
    strategy: StrategyCreate,
    current_user: UserInfo = Depends(get_current_user)
):
    """创建策略"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限创建策略")
    
    logger.info(f"用户 {current_user.username} 创建策略: {strategy.name}")
    
    # TODO: 保存到数据库
    new_strategy = Strategy(
        id=len(MOCK_STRATEGIES) + 1,
        name=strategy.name,
        type=strategy.type,
        account=f"账户{strategy.accountId}",
        status='pending' if not strategy.autoStart else 'running',
        pnl=0.0,
        returnRate=0.0,
        trades=0,
        runTime='-'
    )
    
    MOCK_STRATEGIES.append(new_strategy)
    
    # 推送事件给前端
    await sse_manager.broadcast('strategy', {
        'action': 'created',
        'data': new_strategy.dict()
    })
    
    return {"code": 200, "message": "策略创建成功", "data": new_strategy}

@router.post("/{strategy_id}/start")
async def start_strategy(
    strategy_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """启动策略"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限启动策略")
    
    strategy = next((s for s in MOCK_STRATEGIES if s.id == strategy_id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    
    logger.info(f"启动策略: {strategy.name}")
    
    # 发送命令给C++框架
    from services.cpp_bridge import cpp_bridge
    result = await cpp_bridge.start_strategy(strategy_id, {})
    
    if result.get('success'):
        strategy.status = 'running'
        
        # 实时推送给前端（延迟<10ms）
        await sse_manager.broadcast('strategy', {
            'action': 'started',
            'data': strategy.dict()
        })
        
        return {"code": 200, "message": "策略启动成功"}
    else:
        raise HTTPException(status_code=500, detail="策略启动失败")

@router.post("/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """停止策略"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限停止策略")
    
    strategy = next((s for s in MOCK_STRATEGIES if s.id == strategy_id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    
    logger.info(f"停止策略: {strategy.name}")
    
    # TODO: 实际停止策略
    strategy.status = 'stopped'
    
    # 实时推送给前端
    await sse_manager.broadcast('strategy', {
        'action': 'stopped',
        'data': strategy.dict()
    })
    
    return {"code": 200, "message": "策略停止成功"}

@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """删除策略"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限删除策略")
    
    global MOCK_STRATEGIES
    MOCK_STRATEGIES = [s for s in MOCK_STRATEGIES if s.id != strategy_id]
    
    logger.info(f"删除策略: {strategy_id}")
    
    # 推送删除事件
    await sse_manager.broadcast('strategy', {
        'action': 'deleted',
        'data': {'id': strategy_id}
    })
    
    return {"code": 200, "message": "策略删除成功"}

@router.get("/{strategy_id}/performance")
async def get_strategy_performance(
    strategy_id: int,
    timeRange: str = '7d',
    current_user: UserInfo = Depends(get_current_user)
):
    """获取策略性能数据"""
    # TODO: 从ClickHouse查询
    return {
        "code": 200,
        "data": {
            "pnl": 1250.50,
            "returnRate": 12.5,
            "trades": 145,
            "winRate": 65.2
        }
    }

