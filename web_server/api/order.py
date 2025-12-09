"""
订单管理API
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

class Order(BaseModel):
    """订单模型"""
    id: int
    exchangeOrderId: Optional[str] = None
    symbol: str
    side: str
    type: str
    price: Optional[float] = None
    quantity: float
    filledQuantity: float = 0.0
    filledPrice: Optional[float] = None
    state: str
    fee: float = 0.0
    timestamp: datetime
    updateTime: datetime
    trades: List = []

class OrderCreate(BaseModel):
    """下单请求"""
    accountId: int
    symbol: str
    side: str
    type: str
    price: Optional[float] = None
    quantity: float

class Position(BaseModel):
    """持仓模型"""
    id: int
    symbol: str
    side: str
    quantity: float
    avgPrice: float
    currentPrice: float
    notionalValue: float
    unrealizedPnl: float
    returnRate: float
    leverage: int
    liquidationPrice: float

# ============================================
# Mock数据
# ============================================

MOCK_ORDERS = [
    Order(
        id=1001,
        exchangeOrderId='123456789',
        symbol='BTC-USDT-SWAP',
        side='BUY',
        type='LIMIT',
        price=42500.0,
        quantity=0.1,
        filledQuantity=0.1,
        filledPrice=42500.0,
        state='FILLED',
        fee=4.25,
        timestamp=datetime.now(),
        updateTime=datetime.now()
    )
]

MOCK_POSITIONS = [
    Position(
        id=1,
        symbol='BTC-USDT-SWAP',
        side='long',
        quantity=0.5,
        avgPrice=42000.0,
        currentPrice=42500.0,
        notionalValue=21250.0,
        unrealizedPnl=250.0,
        returnRate=1.19,
        leverage=5,
        liquidationPrice=38000.0
    )
]

# ============================================
# API端点
# ============================================

@router.get("", response_model=List[Order])
async def get_orders(
    symbol: Optional[str] = None,
    state: Optional[str] = None,
    current_user: UserInfo = Depends(get_current_user)
):
    """获取订单列表"""
    orders = MOCK_ORDERS
    
    if symbol:
        orders = [o for o in orders if o.symbol == symbol]
    if state:
        orders = [o for o in orders if o.state == state]
    
    return orders

@router.post("")
async def place_order(
    order: OrderCreate,
    current_user: UserInfo = Depends(get_current_user)
):
    """手动下单"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限下单")
    
    logger.info(f"手动下单: {order.symbol} {order.side} {order.quantity}")
    
    # 发送下单命令给C++框架
    from services.cpp_bridge import cpp_bridge
    result = await cpp_bridge.place_order({
        'symbol': order.symbol,
        'side': order.side,
        'type': order.type,
        'price': order.price,
        'quantity': order.quantity,
        'account_id': order.accountId
    })
    
    if result.get('success'):
        # 创建订单记录
        new_order = Order(
            id=result.get('order_id', len(MOCK_ORDERS) + 1001),
            exchangeOrderId=result.get('exchange_order_id'),
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            price=order.price,
            quantity=order.quantity,
            filledQuantity=0.0,
            state='SUBMITTED',
            timestamp=datetime.now(),
            updateTime=datetime.now()
        )
        
        MOCK_ORDERS.insert(0, new_order)
        
        # 实时推送订单（延迟<5ms）
        await sse_manager.broadcast('order', {
            'action': 'created',
            'data': new_order.dict()
        })
        
        return {"code": 200, "message": "订单提交成功", "data": new_order}
    else:
        raise HTTPException(status_code=500, detail=f"下单失败: {result.get('error')}")

@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    current_user: UserInfo = Depends(get_current_user)
):
    """取消订单"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限取消订单")
    
    order = next((o for o in MOCK_ORDERS if o.id == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    
    logger.info(f"取消订单: {order_id}")
    
    # TODO: 调用交易所API取消
    order.state = 'CANCELLED'
    order.updateTime = datetime.now()
    
    # 实时推送（延迟<5ms）
    await sse_manager.broadcast('order', {
        'action': 'cancelled',
        'data': order.dict()
    })
    
    return {"code": 200, "message": "订单取消成功"}

@router.get("/positions", response_model=List[Position])
async def get_positions(
    current_user: UserInfo = Depends(get_current_user)
):
    """获取持仓列表"""
    return MOCK_POSITIONS

@router.post("/batch-cancel")
async def batch_cancel_orders(
    ids: List[int],
    current_user: UserInfo = Depends(get_current_user)
):
    """批量取消订单"""
    if current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限取消订单")
    
    logger.info(f"批量取消订单: {ids}")
    
    for order_id in ids:
        order = next((o for o in MOCK_ORDERS if o.id == order_id), None)
        if order:
            order.state = 'CANCELLED'
            order.updateTime = datetime.now()
            
            # 逐个推送
            await sse_manager.broadcast('order', {
                'action': 'cancelled',
                'data': order.dict()
            })
    
    return {"code": 200, "message": f"成功取消{len(ids)}个订单"}

