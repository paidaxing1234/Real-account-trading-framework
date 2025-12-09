"""
ClickHouse数据库操作
"""
from clickhouse_driver import Client
from loguru import logger
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from config import settings

class ClickHouseClient:
    """ClickHouse客户端封装"""
    
    def __init__(self):
        self.client = None
        
    def connect(self):
        """连接ClickHouse"""
        try:
            self.client = Client(
                host=settings.CLICKHOUSE_HOST,
                port=settings.CLICKHOUSE_PORT,
                database=settings.CLICKHOUSE_DATABASE,
                user=settings.CLICKHOUSE_USER,
                password=settings.CLICKHOUSE_PASSWORD
            )
            
            # 测试连接
            self.client.execute('SELECT 1')
            logger.info(f"✅ ClickHouse连接成功: {settings.CLICKHOUSE_HOST}:{settings.CLICKHOUSE_PORT}")
            
        except Exception as e:
            logger.error(f"❌ ClickHouse连接失败: {e}")
            raise
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.disconnect()
            logger.info("ClickHouse连接已关闭")
    
    # ============================================
    # 账户相关查询
    # ============================================
    
    def get_equity_curve(self, account_id: int, days: int = 30) -> List[Dict]:
        """
        查询账户净值曲线
        高性能查询，毫秒级响应
        """
        query = """
        SELECT 
            timestamp,
            equity,
            unrealized_pnl,
            realized_pnl
        FROM account_snapshots
        WHERE account_id = %(account_id)s
          AND timestamp >= now() - INTERVAL %(days)s DAY
        ORDER BY timestamp
        """
        
        result = self.client.execute(
            query,
            {'account_id': account_id, 'days': days}
        )
        
        return [
            {
                'timestamp': row[0].timestamp() * 1000,
                'equity': float(row[1]),
                'unrealizedPnl': float(row[2]),
                'realizedPnl': float(row[3])
            }
            for row in result
        ]
    
    def save_account_snapshot(self, snapshot: Dict):
        """保存账户快照"""
        self.client.execute(
            """
            INSERT INTO account_snapshots 
            (timestamp, account_id, account_name, balance, equity, 
             unrealized_pnl, realized_pnl)
            VALUES
            """,
            [snapshot]
        )
    
    # ============================================
    # 订单相关查询
    # ============================================
    
    def get_orders(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        state: Optional[str] = None,
        start_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """查询订单列表"""
        conditions = []
        params = {}
        
        if account_id:
            conditions.append("account_id = %(account_id)s")
            params['account_id'] = account_id
        
        if symbol:
            conditions.append("symbol = %(symbol)s")
            params['symbol'] = symbol
        
        if state:
            conditions.append("state = %(state)s")
            params['state'] = state
        
        if start_date:
            conditions.append("created_at >= %(start_date)s")
            params['start_date'] = start_date
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
        SELECT *
        FROM orders
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """
        
        params['limit'] = limit
        
        result = self.client.execute(query, params)
        return self._parse_orders(result)
    
    def save_order(self, order: Dict):
        """保存订单"""
        self.client.execute(
            """
            INSERT INTO orders 
            (id, exchange_order_id, account_id, strategy_id, symbol, 
             side, type, price, quantity, filled_quantity, state, fee, created_at)
            VALUES
            """,
            [order]
        )
    
    # ============================================
    # 策略相关查询
    # ============================================
    
    def get_strategy_performance(
        self,
        strategy_id: int,
        days: int = 30
    ) -> Dict:
        """查询策略性能"""
        query = """
        SELECT 
            sum(pnl) as total_pnl,
            avg(return_rate) as avg_return,
            sum(trades_count) as total_trades,
            avg(win_rate) as avg_win_rate
        FROM strategy_performance
        WHERE strategy_id = %(strategy_id)s
          AND date >= today() - %(days)s
        """
        
        result = self.client.execute(
            query,
            {'strategy_id': strategy_id, 'days': days}
        )
        
        if result:
            row = result[0]
            return {
                'totalPnl': float(row[0]) if row[0] else 0.0,
                'avgReturn': float(row[1]) if row[1] else 0.0,
                'totalTrades': int(row[2]) if row[2] else 0,
                'avgWinRate': float(row[3]) if row[3] else 0.0
            }
        
        return {}
    
    # ============================================
    # 工具方法
    # ============================================
    
    def _parse_orders(self, result) -> List[Dict]:
        """解析订单查询结果"""
        # TODO: 实现解析逻辑
        return []
    
    def execute_query(self, query: str, params: Dict = None) -> List:
        """执行自定义查询"""
        return self.client.execute(query, params or {})

# 全局ClickHouse客户端
ch_client = ClickHouseClient()

