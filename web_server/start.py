#!/usr/bin/env python3
"""
启动脚本
"""
import sys
import uvicorn
from config import settings
from loguru import logger

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 启动实盘交易管理系统Web服务")
    logger.info("=" * 50)
    logger.info(f"📍 地址: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"📊 SSE事件流: http://{settings.HOST}:{settings.PORT}/events/stream")
    logger.info(f"📖 API文档: http://{settings.HOST}:{settings.PORT}/docs")
    logger.info(f"🔧 调试模式: {settings.DEBUG}")
    logger.info(f"🖥️ 操作系统: {sys.platform}")
    logger.info("=" * 50)
    logger.info("")
    
    # 根据操作系统选择事件循环
    loop_config = "uvloop" if sys.platform != 'win32' else "auto"
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,  # Windows环境禁用reload避免多进程问题
        loop=loop_config,  # Windows使用auto，Linux/macOS使用uvloop
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True
    )

