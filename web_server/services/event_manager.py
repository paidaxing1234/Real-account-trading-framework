"""
SSE事件管理器
实现低延迟事件推送（3-10ms）
"""
import asyncio
import time
from typing import Set, Dict, Any, Optional
from loguru import logger
import json

class SSEManager:
    """
    SSE连接管理器
    管理所有活跃的SSE连接，实现低延迟事件广播
    """
    
    def __init__(self):
        self.connections: Set[asyncio.Queue] = set()
        self.event_count = 0
        self.broadcast_count = 0
        
    async def connect(self, queue: asyncio.Queue):
        """添加新的SSE连接"""
        self.connections.add(queue)
        logger.info(f"新SSE连接，当前连接数: {len(self.connections)}")
        
    async def disconnect(self, queue: asyncio.Queue):
        """移除SSE连接"""
        self.connections.discard(queue)
        logger.info(f"SSE连接断开，当前连接数: {len(self.connections)}")
    
    async def broadcast(self, event_type: str, data: Dict[Any, Any]):
        """
        广播事件给所有连接
        延迟：<1ms（内存操作）
        """
        if not self.connections:
            return
        
        start_time = time.perf_counter()
        
        # 构造事件消息
        message = {
            'event': event_type,
            'data': data,
            'timestamp': time.time() * 1000  # 毫秒时间戳
        }
        
        # 立即推送给所有连接（非阻塞）
        dead_connections = []
        success_count = 0
        
        for queue in self.connections:
            try:
                queue.put_nowait(message)  # 非阻塞，延迟<0.1ms
                success_count += 1
            except asyncio.QueueFull:
                logger.warning(f"连接队列已满，丢弃事件: {event_type}")
            except Exception as e:
                logger.error(f"推送事件失败: {e}")
                dead_connections.append(queue)
        
        # 清理死连接
        for queue in dead_connections:
            self.connections.discard(queue)
        
        elapsed = (time.perf_counter() - start_time) * 1000
        self.broadcast_count += 1
        
        if self.broadcast_count % 100 == 0:
            logger.debug(f"广播事件 [{event_type}] 给 {success_count} 个连接，耗时: {elapsed:.3f}ms")
    
    def get_queue_size(self) -> int:
        """获取所有队列的总大小"""
        total_size = sum(queue.qsize() for queue in self.connections)
        return total_size
    
    # ============================================
    # 事件回调方法（对接EventEngine）
    # ============================================
    
    def on_order_event(self, order_data: Dict):
        """
        订单事件回调
        从EventEngine接收订单事件，立即推送给前端
        """
        asyncio.create_task(
            self.broadcast('order', order_data)
        )
        self.event_count += 1
    
    def on_ticker_event(self, ticker_data: Dict):
        """行情事件回调"""
        asyncio.create_task(
            self.broadcast('ticker', ticker_data)
        )
        self.event_count += 1
    
    def on_position_event(self, position_data: Dict):
        """持仓事件回调"""
        asyncio.create_task(
            self.broadcast('position', position_data)
        )
        self.event_count += 1
    
    def on_account_event(self, account_data: Dict):
        """账户事件回调"""
        asyncio.create_task(
            self.broadcast('account', account_data)
        )
        self.event_count += 1
    
    def on_strategy_event(self, strategy_data: Dict):
        """策略事件回调"""
        asyncio.create_task(
            self.broadcast('strategy', strategy_data)
        )
        self.event_count += 1
    
    def on_system_event(self, system_data: Dict):
        """系统事件回调"""
        asyncio.create_task(
            self.broadcast('system', system_data)
        )
        self.event_count += 1
    
    # ============================================
    # 统计方法
    # ============================================
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'connections': len(self.connections),
            'total_events': self.event_count,
            'total_broadcasts': self.broadcast_count,
            'avg_events_per_broadcast': self.event_count / max(1, self.broadcast_count)
        }

# 全局SSE管理器实例
sse_manager = SSEManager()

