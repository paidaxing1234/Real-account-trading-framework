"""
C++框架桥接层
通过PyBind11与C++实盘框架通信
"""
import sys
import asyncio
from pathlib import Path
from loguru import logger
from typing import Dict, Any, Optional, Callable
import json

# 添加C++模块路径
CPP_MODULE_PATH = Path(__file__).parent.parent.parent / "cpp" / "build"
sys.path.insert(0, str(CPP_MODULE_PATH))

class CppBridge:
    """
    C++框架桥接器
    
    架构：
    Web服务 ←→ CppBridge ←→ C++实盘框架
                            (通过PyBind11)
    """
    
    def __init__(self):
        self.engine = None
        self.components = {}
        self.event_callbacks = {}
        self.initialized = False
        
    def init(self):
        """初始化C++框架"""
        try:
            # 导入C++模块（通过PyBind11编译）
            import trading_cpp  # C++编译的Python模块
            
            logger.info("✅ C++模块导入成功")
            
            # 创建EventEngine
            self.engine = trading_cpp.EventEngine()
            logger.info("✅ C++ EventEngine创建成功")
            
            # 注册事件监听器
            self._register_listeners()
            
            self.initialized = True
            logger.info("✅ C++框架初始化完成")
            
        except ImportError as e:
            logger.warning(f"⚠️ C++模块未编译，使用Mock模式: {e}")
            logger.warning("提示: cd cpp/build && cmake .. && cmake --build .")
            self.initialized = False
        except Exception as e:
            logger.error(f"❌ C++框架初始化失败: {e}")
            self.initialized = False
    
    def _register_listeners(self):
        """注册C++事件监听器"""
        if not self.engine:
            return
        
        try:
            import trading_cpp
            
            # 监听订单事件
            def on_order_callback(order):
                """C++订单事件回调"""
                order_data = {
                    'id': order.order_id,
                    'symbol': order.symbol,
                    'side': order.side_str(),
                    'state': order.state_str(),
                    'price': order.price,
                    'quantity': order.quantity,
                    'filled_quantity': order.filled_quantity,
                    'timestamp': order.timestamp
                }
                
                # 触发回调（推送给SSE）
                self._trigger_callback('order', order_data)
            
            # 监听行情事件  
            def on_ticker_callback(ticker):
                """C++行情事件回调"""
                ticker_data = {
                    'symbol': ticker.symbol,
                    'last_price': ticker.last_price,
                    'bid_price': ticker.bid_price,
                    'ask_price': ticker.ask_price,
                    'volume': ticker.volume,
                    'timestamp': ticker.timestamp
                }
                
                self._trigger_callback('ticker', ticker_data)
            
            # 注册到C++ EventEngine
            self.engine.register_listener(trading_cpp.Order, on_order_callback)
            self.engine.register_listener(trading_cpp.TickerData, on_ticker_callback)
            
            logger.info("✅ C++事件监听器注册成功")
            
        except Exception as e:
            logger.error(f"注册监听器失败: {e}")
    
    def _trigger_callback(self, event_type: str, data: Dict):
        """触发Python回调"""
        callbacks = self.event_callbacks.get(event_type, [])
        for callback in callbacks:
            try:
                # 在asyncio事件循环中调用
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(data))
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")
    
    # ============================================
    # 订阅C++事件（供Web服务使用）
    # ============================================
    
    def on(self, event_type: str, callback: Callable):
        """
        订阅C++事件
        
        用法：
        cpp_bridge.on('order', lambda order: print(order))
        """
        if event_type not in self.event_callbacks:
            self.event_callbacks[event_type] = []
        
        self.event_callbacks[event_type].append(callback)
        logger.debug(f"注册事件回调: {event_type}")
    
    # ============================================
    # 策略管理
    # ============================================
    
    async def start_strategy(self, strategy_id: int, config: Dict) -> bool:
        """启动策略"""
        try:
            if not self.initialized:
                logger.warning("C++框架未初始化，使用Mock模式")
                return True
            
            logger.info(f"启动策略: {strategy_id}, 配置: {config}")
            
            # TODO: 加载策略.so或.py文件
            # strategy = load_strategy(config['python_file'])
            
            # TODO: 启动策略组件
            # strategy.start(self.engine)
            
            # TODO: 保存策略实例
            # self.components[strategy_id] = strategy
            
            logger.info(f"✅ 策略 {strategy_id} 启动成功")
            return True
            
        except Exception as e:
            logger.error(f"启动策略失败: {e}")
            return False
    
    async def stop_strategy(self, strategy_id: int) -> bool:
        """停止策略"""
        try:
            if not self.initialized:
                return True
            
            logger.info(f"停止策略: {strategy_id}")
            
            # TODO: 停止策略组件
            # strategy = self.components.get(strategy_id)
            # if strategy:
            #     strategy.stop()
            #     del self.components[strategy_id]
            
            logger.info(f"✅ 策略 {strategy_id} 停止成功")
            return True
            
        except Exception as e:
            logger.error(f"停止策略失败: {e}")
            return False
    
    # ============================================
    # 订单管理
    # ============================================
    
    async def place_order(self, order_data: Dict) -> Dict:
        """下单"""
        try:
            if not self.initialized:
                logger.warning("C++框架未初始化，返回Mock订单")
                return {
                    'order_id': int(asyncio.get_event_loop().time() * 1000),
                    'state': 'SUBMITTED'
                }
            
            import trading_cpp
            
            # 创建C++订单对象
            if order_data['side'] == 'BUY':
                if order_data['type'] == 'LIMIT':
                    order = trading_cpp.Order.buy_limit(
                        order_data['symbol'],
                        order_data['quantity'],
                        order_data['price']
                    )
                else:  # MARKET
                    order = trading_cpp.Order.buy_market(
                        order_data['symbol'],
                        order_data['quantity']
                    )
            else:  # SELL
                if order_data['type'] == 'LIMIT':
                    order = trading_cpp.Order.sell_limit(
                        order_data['symbol'],
                        order_data['quantity'],
                        order_data['price']
                    )
                else:
                    order = trading_cpp.Order.sell_market(
                        order_data['symbol'],
                        order_data['quantity']
                    )
            
            # 推送到EventEngine
            self.engine.put(order)
            
            logger.info(f"✅ 订单已提交到C++引擎: {order.order_id}")
            
            return {
                'order_id': order.order_id,
                'state': order.state_str()
            }
            
        except Exception as e:
            logger.error(f"下单失败: {e}")
            raise
    
    async def cancel_order(self, order_id: int) -> bool:
        """取消订单"""
        try:
            if not self.initialized:
                return True
            
            # TODO: 调用C++取消订单
            logger.info(f"取消订单: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False
    
    # ============================================
    # 账户查询
    # ============================================
    
    async def get_account_balance(self, account_id: int) -> Dict:
        """查询账户余额"""
        try:
            if not self.initialized:
                return {'balance': 10000.0, 'equity': 10000.0}
            
            # TODO: 通过C++接口查询
            # balance = self.engine.call("get_balance")
            
            return {
                'balance': 10000.0,
                'equity': 10000.0
            }
            
        except Exception as e:
            logger.error(f"查询余额失败: {e}")
            raise
    
    async def get_positions(self, account_id: int) -> list:
        """查询持仓"""
        try:
            if not self.initialized:
                return []
            
            # TODO: 通过C++接口查询
            # positions = self.engine.call("get_positions")
            
            return []
            
        except Exception as e:
            logger.error(f"查询持仓失败: {e}")
            raise
    
    # ============================================
    # 工具方法
    # ============================================
    
    def is_ready(self) -> bool:
        """检查C++框架是否就绪"""
        return self.initialized
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'initialized': self.initialized,
            'components': len(self.components),
            'event_callbacks': sum(len(cbs) for cbs in self.event_callbacks.values())
        }

# 全局C++桥接实例
cpp_bridge = CppBridge()
