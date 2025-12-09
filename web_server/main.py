"""
FastAPI主应用
实盘交易管理系统Web服务
"""
import asyncio
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
from loguru import logger

from config import settings
from api import auth, strategy, account, order, events, command
from services.event_manager import sse_manager
from services.cpp_bridge import cpp_bridge

# 使用uvloop提升性能（仅Linux/macOS）
if sys.platform != 'win32':
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("✅ 使用uvloop事件循环")
    except ImportError:
        logger.warning("⚠️ uvloop未安装，使用默认事件循环")
else:
    logger.info("ℹ️ Windows平台，使用默认事件循环")

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level=settings.LOG_LEVEL
)
logger.add(
    settings.LOG_FILE,
    rotation="500 MB",
    retention="10 days",
    level="INFO"
)

# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的操作"""
    logger.info("🚀 启动实盘交易管理系统...")
    
    # 启动时初始化
    try:
        # 1. 连接数据库
        from database.clickhouse import ch_client
        from database.redis_client import redis_client
        
        try:
            ch_client.connect()
        except Exception as e:
            logger.warning(f"ClickHouse连接失败: {e}，将使用Mock模式")
        
        try:
            redis_client.connect()
        except Exception as e:
            logger.warning(f"Redis连接失败: {e}，将使用内存缓存")
        
        # 2. 连接C++实盘框架
        from services.cpp_bridge import cpp_bridge
        await cpp_bridge.start()
        
    except Exception as e:
        logger.error(f"初始化失败: {e}")
    
    logger.info("✅ 系统启动完成")
    logger.info("=" * 60)
    logger.info("📍 API服务: http://localhost:8000")
    logger.info("📖 API文档: http://localhost:8000/docs")
    logger.info("⚡ SSE事件流: http://localhost:8000/events/stream")
    logger.info("=" * 60)
    
    yield
    
    # 关闭时清理
    logger.info("🛑 正在关闭系统...")
    
    try:
        from database.clickhouse import ch_client
        from database.redis_client import redis_client
        from services.cpp_bridge import cpp_bridge
        
        await cpp_bridge.stop()
        ch_client.disconnect()
        redis_client.disconnect()
        
    except Exception as e:
        logger.error(f"清理资源失败: {e}")
    
    logger.info("✅ 系统已关闭")

# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="高性能实盘交易管理系统API",
    lifespan=lifespan
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip压缩
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 注册路由
app.include_router(auth.router, prefix="/auth", tags=["认证"])
app.include_router(strategy.router, prefix="/strategies", tags=["策略管理"])
app.include_router(account.router, prefix="/accounts", tags=["账户管理"])
app.include_router(order.router, prefix="/orders", tags=["订单管理"])
app.include_router(events.router, prefix="/events", tags=["事件流"])
app.include_router(command.router, prefix="/command", tags=["命令"])

# 根路径
@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }

# 健康检查
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "sse_connections": len(sse_manager.connections),
        "timestamp": asyncio.get_event_loop().time()
    }

# 性能指标
@app.get("/metrics")
async def metrics():
    """性能指标（用于监控）"""
    return {
        "sse_connections": len(sse_manager.connections),
        "event_queue_size": sse_manager.get_queue_size(),
        "uptime": asyncio.get_event_loop().time()
    }

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {settings.HOST}:{settings.PORT}")
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        loop="uvloop",  # 使用uvloop
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True
    )

