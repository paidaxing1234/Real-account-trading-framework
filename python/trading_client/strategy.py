"""
策略基类

提供策略开发的基础框架：
- 行情回调 on_ticker()
- 订单回报回调 on_order()
- 下单便捷方法 buy_limit(), sell_limit() 等

使用方法：
    class MyStrategy(Strategy):
        def on_ticker(self, data: TickerData):
            # 处理行情
            pass
        
        def on_order(self, report: OrderReport):
            # 处理订单回报
            pass

作者: Sequence Team
日期: 2024-12
"""

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING
import logging

from .models import TickerData, OrderReport, OrderRequest

# 避免循环导入
if TYPE_CHECKING:
    from .client import TradingClient

# 日志配置
logger = logging.getLogger(__name__)


class Strategy(ABC):
    """
    策略基类
    
    所有策略都应该继承这个类，并实现 on_ticker() 方法。
    
    属性：
        strategy_id: 策略唯一ID，用于识别订单来源
        client: 交易客户端引用（由 TradingClient 注入）
        position: 当前持仓（需要策略自己维护）
    
    生命周期方法：
        on_start(): 策略启动时调用
        on_stop(): 策略停止时调用
        on_ticker(): 收到行情时调用（必须实现）
        on_order(): 收到订单回报时调用
    
    下单方法：
        buy_limit(): 限价买入
        sell_limit(): 限价卖出
        buy_market(): 市价买入
        sell_market(): 市价卖出
        send_order(): 发送自定义订单
    
    示例：
        class MomentumStrategy(Strategy):
            def __init__(self):
                super().__init__()
                self.high_price = 0.0
                
            def on_ticker(self, data: TickerData):
                # 更新最高价
                if data.last_price > self.high_price:
                    self.high_price = data.last_price
                
                # 价格突破时买入
                if data.last_price > self.high_price * 0.99:
                    self.buy_limit(data.symbol, 0.001, data.bid_price)
                    
            def on_order(self, report: OrderReport):
                if report.is_success():
                    self.log(f"订单成功: {report.exchange_order_id}")
    """
    
    def __init__(self):
        """
        初始化策略
        
        子类应该调用 super().__init__() 并在之后初始化自己的状态
        """
        # 策略ID（由 TradingClient 设置）
        self.strategy_id: str = ""
        
        # 交易客户端引用（由 TradingClient 注入）
        self._client: Optional["TradingClient"] = None
        
        # 持仓跟踪（需要策略自己维护）
        self.position: float = 0.0
        
        # 统计数据
        self._tick_count: int = 0
        self._order_count: int = 0
    
    # ========================================
    # 生命周期方法（可选重写）
    # ========================================
    
    def on_start(self):
        """
        策略启动回调
        
        在策略开始接收数据之前调用。
        适合做初始化工作，如：
        - 加载历史数据
        - 初始化指标
        - 恢复状态
        
        子类可以重写这个方法
        """
        self.log("策略启动")
    
    def on_stop(self):
        """
        策略停止回调
        
        在策略停止时调用。
        适合做清理工作，如：
        - 保存状态
        - 平仓
        - 输出统计
        
        子类可以重写这个方法
        """
        self.log(f"策略停止 | 收到行情: {self._tick_count} | 发送订单: {self._order_count}")
    
    @abstractmethod
    def on_ticker(self, data: TickerData):
        """
        行情回调（必须实现）
        
        每收到一条行情数据都会调用这个方法。
        这是策略的核心逻辑所在。
        
        注意：
        - 这个方法应该尽快返回（< 1ms）
        - 不要在这里做阻塞操作（如网络请求、文件IO）
        - 耗时计算应该放在其他线程
        
        参数：
            data: TickerData 对象，包含最新行情
        
        示例：
            def on_ticker(self, data: TickerData):
                # 简单均值回归策略
                if data.last_price < self.avg_price * 0.99:
                    self.buy_limit(data.symbol, 0.001, data.bid_price)
                elif data.last_price > self.avg_price * 1.01:
                    self.sell_limit(data.symbol, 0.001, data.ask_price)
        """
        pass
    
    def on_order(self, report: OrderReport):
        """
        订单回报回调
        
        收到订单执行结果时调用。
        可以用来：
        - 更新持仓
        - 记录交易
        - 处理错误
        
        参数：
            report: OrderReport 对象，包含订单执行结果
        
        示例：
            def on_order(self, report: OrderReport):
                if report.is_filled():
                    # 更新持仓
                    if "buy" in report.client_order_id:
                        self.position += report.filled_quantity
                    else:
                        self.position -= report.filled_quantity
                    
                    self.log(f"成交 | 持仓: {self.position}")
                    
                elif report.is_rejected():
                    self.log(f"订单被拒: {report.error_msg}")
        """
        # 默认实现：打印日志
        if report.is_success():
            self.log(f"订单成功 | ID: {report.exchange_order_id} | 状态: {report.status}")
        else:
            self.log(f"订单失败 | 错误: {report.error_msg}")
    
    # ========================================
    # 下单方法
    # ========================================
    
    def buy_limit(self, symbol: str, quantity: float, price: float) -> Optional[str]:
        """
        限价买入
        
        参数：
            symbol: 交易对，如 "BTC-USDT"
            quantity: 买入数量
            price: 买入价格
            
        返回：
            订单ID（client_order_id），如果失败返回 None
        
        示例：
            # 以 43000 买入 0.001 BTC
            order_id = self.buy_limit("BTC-USDT", 0.001, 43000.0)
        """
        return self._send_order(symbol, "buy", "limit", quantity, price)
    
    def sell_limit(self, symbol: str, quantity: float, price: float) -> Optional[str]:
        """
        限价卖出
        
        参数：
            symbol: 交易对
            quantity: 卖出数量
            price: 卖出价格
            
        返回：
            订单ID，如果失败返回 None
        """
        return self._send_order(symbol, "sell", "limit", quantity, price)
    
    def buy_market(self, symbol: str, quantity: float) -> Optional[str]:
        """
        市价买入
        
        参数：
            symbol: 交易对
            quantity: 买入数量
            
        返回：
            订单ID，如果失败返回 None
        
        注意：市价单会立即成交，价格可能不理想
        """
        return self._send_order(symbol, "buy", "market", quantity, 0.0)
    
    def sell_market(self, symbol: str, quantity: float) -> Optional[str]:
        """
        市价卖出
        
        参数：
            symbol: 交易对
            quantity: 卖出数量
            
        返回：
            订单ID，如果失败返回 None
        """
        return self._send_order(symbol, "sell", "market", quantity, 0.0)
    
    def send_order(self, order: OrderRequest) -> Optional[str]:
        """
        发送自定义订单
        
        参数：
            order: OrderRequest 对象
            
        返回：
            订单ID，如果失败返回 None
        
        示例：
            order = OrderRequest(
                strategy_id=self.strategy_id,
                symbol="BTC-USDT",
                side="buy",
                order_type="post_only",  # 只做 Maker
                price=43000.0,
                quantity=0.001
            )
            self.send_order(order)
        """
        if self._client is None:
            self.log("错误: 客户端未连接")
            return None
        
        # 确保订单有正确的策略ID
        order.strategy_id = self.strategy_id
        
        try:
            self._client.send_order(order)
            self._order_count += 1
            return order.client_order_id
        except Exception as e:
            self.log(f"发送订单失败: {e}")
            return None
    
    def _send_order(
        self, 
        symbol: str, 
        side: str, 
        order_type: str, 
        quantity: float, 
        price: float
    ) -> Optional[str]:
        """内部下单方法"""
        order = OrderRequest(
            strategy_id=self.strategy_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity
        )
        return self.send_order(order)
    
    # ========================================
    # 辅助方法
    # ========================================
    
    def log(self, message: str):
        """
        打印日志
        
        带策略ID前缀的日志输出
        
        参数：
            message: 日志内容
        """
        print(f"[{self.strategy_id}] {message}")
    
    def _set_client(self, client: "TradingClient"):
        """内部方法：设置客户端引用"""
        self._client = client
    
    def _set_strategy_id(self, strategy_id: str):
        """内部方法：设置策略ID"""
        self.strategy_id = strategy_id
    
    def _on_tick_internal(self, data: TickerData):
        """内部方法：处理行情（带统计）"""
        self._tick_count += 1
        self.on_ticker(data)
    
    def _on_order_internal(self, report: OrderReport):
        """内部方法：处理回报（带过滤）"""
        # 只处理属于本策略的回报
        if report.strategy_id == self.strategy_id:
            self.on_order(report)

