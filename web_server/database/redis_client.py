"""
Redis客户端
用于缓存和实时数据
"""
import redis
from loguru import logger
import json
from typing import Optional, Any

from config import settings

class RedisClient:
    """Redis客户端封装"""
    
    def __init__(self):
        self.client = None
        
    def connect(self):
        """连接Redis"""
        try:
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5
            )
            
            # 测试连接
            self.client.ping()
            logger.info(f"✅ Redis连接成功: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            
        except Exception as e:
            logger.warning(f"⚠️ Redis连接失败: {e}，将使用内存缓存")
            self.client = None
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.close()
            logger.info("Redis连接已关闭")
    
    # ============================================
    # 缓存操作
    # ============================================
    
    def set(self, key: str, value: Any, expire: Optional[int] = None):
        """设置缓存"""
        if not self.client:
            return
        
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            self.client.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Redis set失败: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if not self.client:
            return None
        
        try:
            value = self.client.get(key)
            if value:
                try:
                    return json.loads(value)
                except:
                    return value
            return None
        except Exception as e:
            logger.error(f"Redis get失败: {e}")
            return None
    
    def delete(self, key: str):
        """删除缓存"""
        if not self.client:
            return
        
        try:
            self.client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete失败: {e}")
    
    # ============================================
    # 实时数据缓存
    # ============================================
    
    def cache_ticker(self, symbol: str, ticker_data: Dict):
        """缓存最新行情"""
        key = f"ticker:{symbol}"
        self.set(key, ticker_data, expire=10)  # 10秒过期
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """获取最新行情"""
        key = f"ticker:{symbol}"
        return self.get(key)
    
    def cache_account(self, account_id: int, account_data: Dict):
        """缓存账户数据"""
        key = f"account:{account_id}"
        self.set(key, account_data, expire=60)  # 1分钟过期
    
    def get_account(self, account_id: int) -> Optional[Dict]:
        """获取账户数据"""
        key = f"account:{account_id}"
        return self.get(key)
    
    # ============================================
    # 会话管理
    # ============================================
    
    def save_session(self, token: str, user_data: Dict, expire: int = 86400):
        """保存用户会话"""
        key = f"session:{token}"
        self.set(key, user_data, expire=expire)
    
    def get_session(self, token: str) -> Optional[Dict]:
        """获取用户会话"""
        key = f"session:{token}"
        return self.get(key)
    
    def delete_session(self, token: str):
        """删除会话"""
        key = f"session:{token}"
        self.delete(key)

# 全局Redis客户端
redis_client = RedisClient()

