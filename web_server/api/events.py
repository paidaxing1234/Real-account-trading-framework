"""
SSE事件流API
实现低延迟实时数据推送（3-10ms）
"""
import asyncio
import json
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from services.event_manager import sse_manager

router = APIRouter()

@router.get("/stream")
async def event_stream(request: Request):
    """
    SSE事件流端点
    
    前端通过EventSource连接此端点，接收实时事件推送
    延迟：3-10ms
    """
    
    async def event_generator():
        # 创建客户端专属队列
        queue = asyncio.Queue(maxsize=1000)
        await sse_manager.connect(queue)
        
        try:
            # 发送连接确认
            yield {
                'event': 'connected',
                'data': json.dumps({
                    'timestamp': asyncio.get_event_loop().time() * 1000,
                    'message': 'SSE连接已建立'
                })
            }
            
            logger.info(f"SSE客户端已连接: {request.client.host}")
            
            # 持续推送事件
            while True:
                # 检查客户端是否断开
                if await request.is_disconnected():
                    logger.info(f"SSE客户端断开: {request.client.host}")
                    break
                
                try:
                    # 等待事件（超时1秒发送心跳）
                    message = await asyncio.wait_for(
                        queue.get(),
                        timeout=30.0
                    )
                    
                    # 立即发送给前端（延迟<1ms）
                    yield {
                        'event': message['event'],
                        'data': json.dumps(message['data']),
                        'id': str(int(message['timestamp']))
                    }
                    
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    yield {
                        'event': 'heartbeat',
                        'data': json.dumps({
                            'timestamp': asyncio.get_event_loop().time() * 1000
                        })
                    }
                    
        except asyncio.CancelledError:
            logger.info(f"SSE连接取消: {request.client.host}")
            raise
        except Exception as e:
            logger.error(f"SSE流错误: {e}")
            raise
        finally:
            # 清理连接
            await sse_manager.disconnect(queue)
    
    return EventSourceResponse(
        event_generator(),
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # 禁用Nginx缓冲，降低延迟
            'Connection': 'keep-alive'
        },
        ping=15  # 每15秒发送ping保持连接
    )

@router.post("/test-push")
async def test_push(event_type: str, data: dict):
    """
    测试推送端点
    用于测试SSE推送功能
    """
    await sse_manager.broadcast(event_type, data)
    return {
        "code": 200,
        "message": "事件已推送",
        "connections": len(sse_manager.connections)
    }

