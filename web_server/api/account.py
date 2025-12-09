"""
账户管理API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from loguru import logger
from datetime import datetime

from api.auth import get_current_user, UserInfo
from services.event_manager import sse_manager

router = APIRouter()

# ============================================
# 数据模型
# ============================================

class Account(BaseModel):
    """账户模型"""
    id: int
    name: str
    apiKey: str
    balance: float
    availableBalance: float
    frozenBalance: float
    equity: float
    unrealizedPnl: float
    realizedPnl: float
    returnRate: float
    status: str
    accountType: str = 'unified'
    lastSyncTime: Optional[datetime] = None
    createdAt: Optional[datetime] = None

class AccountCreate(BaseModel):
    """创建账户请求"""
    name: str
    apiKey: str
    secretKey: str
    passphrase: str
    accountType: str = 'unified'
    isDemo: bool = False

# ============================================
# Mock数据
# ============================================

MOCK_ACCOUNTS = [
    Account(
        id=1,
        name='OKX账户1',
        apiKey='abc***xyz',
        balance=15000,
        availableBalance=12000,
        frozenBalance=3000,
        equity=16250,
        unrealizedPnl=1250,
        realizedPnl=500,
        returnRate=8.33,
        status='active',
        lastSyncTime=datetime.now(),
        createdAt=datetime(2024, 1, 1)
    ),
    Account(
        id=2,
        name='OKX账户2',
        apiKey='def***uvw',
        balance=8000,
        availableBalance=7200,
        frozenBalance=800,
        equity=8680,
        unrealizedPnl=680,
        realizedPnl=320,
        returnRate=12.5,
        status='active',
        lastSyncTime=datetime.now(),
        createdAt=datetime(2024, 1, 15)
    )
]

# ============================================
# API端点
# ============================================

@router.get("", response_model=List[Account])
async def get_accounts(
    current_user: UserInfo = Depends(get_current_user)
):
    """获取账户列表"""
    logger.info(f"用户 {current_user.username} 查询账户列表")
    return MOCK_ACCOUNTS

@router.get("/{account_id}")
async def get_account(
    account_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """获取账户详情"""
    account = next((a for a in MOCK_ACCOUNTS if a.id == account_id), None)
    
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    return {"code": 200, "data": account}

@router.post("")
async def create_account(
    account: AccountCreate,
    current_user: UserInfo = Depends(get_current_user)
):
    """添加账户"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限添加账户")
    
    logger.info(f"用户 {current_user.username} 添加账户: {account.name}")
    
    # TODO: 保存到数据库，加密存储API Key
    new_account = Account(
        id=len(MOCK_ACCOUNTS) + 1,
        name=account.name,
        apiKey=account.apiKey[:4] + '***' + account.apiKey[-4:],
        balance=10000.0,
        availableBalance=10000.0,
        frozenBalance=0.0,
        equity=10000.0,
        unrealizedPnl=0.0,
        realizedPnl=0.0,
        returnRate=0.0,
        status='active',
        accountType=account.accountType,
        lastSyncTime=datetime.now(),
        createdAt=datetime.now()
    )
    
    MOCK_ACCOUNTS.append(new_account)
    
    # 推送事件
    await sse_manager.broadcast('account', {
        'action': 'created',
        'data': new_account.dict()
    })
    
    return {"code": 200, "message": "账户添加成功", "data": new_account}

@router.post("/{account_id}/sync")
async def sync_account(
    account_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """同步账户数据"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限同步账户")
    
    account = next((a for a in MOCK_ACCOUNTS if a.id == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    logger.info(f"同步账户: {account.name}")
    
    # TODO: 调用OKX API同步数据
    import random
    account.balance += random.uniform(-100, 100)
    account.equity = account.balance + account.unrealizedPnl
    account.lastSyncTime = datetime.now()
    
    # 实时推送更新（延迟<5ms）
    await sse_manager.broadcast('account', {
        'action': 'synced',
        'data': account.dict()
    })
    
    return {"code": 200, "message": "同步成功", "data": account}

@router.get("/{account_id}/balance")
async def get_account_balance(
    account_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """获取账户余额"""
    account = next((a for a in MOCK_ACCOUNTS if a.id == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    return {
        "code": 200,
        "data": {
            "balance": account.balance,
            "availableBalance": account.availableBalance,
            "frozenBalance": account.frozenBalance
        }
    }

@router.get("/{account_id}/equity-curve")
async def get_equity_curve(
    account_id: int,
    timeRange: str = '7d',
    current_user: UserInfo = Depends(get_current_user)
):
    """获取净值曲线"""
    # TODO: 从ClickHouse查询
    import time
    
    # 生成模拟数据
    data = []
    days = {'1d': 1, '7d': 7, '30d': 30, '90d': 90}.get(timeRange, 7)
    
    value = 10000
    for i in range(days, -1, -1):
        timestamp = (time.time() - i * 86400) * 1000
        value += (random.uniform(0, 1) - 0.45) * 200
        data.append({
            'timestamp': timestamp,
            'equity': round(value, 2)
        })
    
    return {
        "code": 200,
        "data": {
            "data": data,
            "statistics": {
                "initialEquity": 10000,
                "currentEquity": round(value, 2),
                "totalReturn": round(value - 10000, 2),
                "returnRate": round((value - 10000) / 10000 * 100, 2)
            }
        }
    }

@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """删除账户"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限删除账户")
    
    global MOCK_ACCOUNTS
    MOCK_ACCOUNTS = [a for a in MOCK_ACCOUNTS if a.id != account_id]
    
    logger.info(f"删除账户: {account_id}")
    
    await sse_manager.broadcast('account', {
        'action': 'deleted',
        'data': {'id': account_id}
    })
    
    return {"code": 200, "message": "账户删除成功"}

