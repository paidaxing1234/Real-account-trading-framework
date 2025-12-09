"""
命令API
接收前端发送的命令（启动策略、下单等）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from loguru import logger

from services.cpp_bridge import cpp_bridge

router = APIRouter()

class CommandRequest(BaseModel):
    """命令请求模型"""
    action: str
    data: Dict[str, Any]

class CommandResponse(BaseModel):
    """命令响应模型"""
    code: int
    message: str
    data: Any = None

@router.post("")
async def execute_command(request: CommandRequest):
    """
    执行命令
    
    支持的命令：
    - start_strategy: 启动策略
    - stop_strategy: 停止策略
    - place_order: 手动下单
    - cancel_order: 取消订单
    等等
    """
    try:
        logger.info(f"收到命令: {request.action}, 数据: {request.data}")
        
        # 根据action分发到不同的处理器
        if request.action == 'start_strategy':
            result = await handle_start_strategy(request.data)
        elif request.action == 'stop_strategy':
            result = await handle_stop_strategy(request.data)
        elif request.action == 'place_order':
            result = await handle_place_order(request.data)
        elif request.action == 'cancel_order':
            result = await handle_cancel_order(request.data)
        else:
            raise HTTPException(status_code=400, detail=f"未知命令: {request.action}")
        
        return CommandResponse(
            code=200,
            message="命令执行成功",
            data=result
        )
        
    except Exception as e:
        logger.error(f"命令执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# 命令处理函数
# ============================================

async def handle_start_strategy(data: Dict) -> Dict:
    """启动策略"""
    strategy_id = data.get('id')
    logger.info(f"启动策略: {strategy_id}")
    
    # 通过C++桥接启动策略
    success = await cpp_bridge.start_strategy(strategy_id, data)
    
    return {
        'success': success,
        'strategy_id': strategy_id,
        'status': 'running' if success else 'error'
    }

async def handle_stop_strategy(data: Dict) -> Dict:
    """停止策略"""
    strategy_id = data.get('id')
    logger.info(f"停止策略: {strategy_id}")
    
    # 通过C++桥接停止策略
    success = await cpp_bridge.stop_strategy(strategy_id)
    
    return {
        'success': success,
        'strategy_id': strategy_id,
        'status': 'stopped' if success else 'error'
    }

async def handle_place_order(data: Dict) -> Dict:
    """手动下单"""
    logger.info(f"手动下单: {data}")
    
    # 通过C++桥接下单
    result = await cpp_bridge.place_order(data)
    
    return {
        'success': True,
        'order_id': result['order_id'],
        'state': result['state']
    }

async def handle_cancel_order(data: Dict) -> Dict:
    """取消订单"""
    order_id = data.get('id')
    logger.info(f"取消订单: {order_id}")
    
    # 通过C++桥接取消订单
    success = await cpp_bridge.cancel_order(order_id)
    
    return {
        'success': success,
        'order_id': order_id,
        'state': 'CANCELLED' if success else 'error'
    }

