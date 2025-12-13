"""
交易客户端

连接 C++ 交易服务器，接收行情、发送订单、接收回报。
通过 ZeroMQ IPC 通信，延迟约 30-100μs。

架构：
    ┌──────────────────┐
    │  Trading Server  │  (C++ 进程)
    │  ┌────────────┐  │
    │  │ PUB 行情   │──┼──────┐
    │  │ PULL 订单  │◄─┼──────┤
    │  │ PUB 回报   │──┼──────┤
    │  └────────────┘  │      │
    └──────────────────┘      │
                              │ IPC (Unix Socket)
    ┌──────────────────┐      │
    │  TradingClient   │  (Python 进程)
    │  ┌────────────┐  │      │
    │  │ SUB 行情   │◄─┼──────┤
    │  │ PUSH 订单  │──┼──────┤
    │  │ SUB 回报   │◄─┼──────┘
    │  └────────────┘  │
    │        │         │
    │        ▼         │
    │  ┌────────────┐  │
    │  │  Strategy  │  │
    │  └────────────┘  │
    └──────────────────┘

作者: Sequence Team
日期: 2024-12
"""

import zmq
import json
import time
import signal
import threading
from typing import Optional, Callable
import logging

from .models import TickerData, OrderReport, OrderRequest
from .strategy import Strategy

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class IpcAddresses:
    """
    IPC 地址配置
    
    必须与 C++ 服务端的地址一致！
    """
    MARKET_DATA = "ipc:///tmp/trading_md.ipc"    # 行情通道
    ORDER = "ipc:///tmp/trading_order.ipc"        # 订单通道
    REPORT = "ipc:///tmp/trading_report.ipc"      # 回报通道


class TradingClient:
    """
    交易客户端
    
    负责：
    1. 连接 C++ 交易服务器
    2. 接收行情数据并分发给策略
    3. 发送策略的订单请求
    4. 接收订单回报并分发给策略
    
    使用方法：
        # 方法1：简单用法
        client = TradingClient(strategy_id="my_strategy")
        client.run(MyStrategy())
        
        # 方法2：手动控制
        client = TradingClient(strategy_id="my_strategy")
        client.start()
        
        while client.is_running():
            ticker = client.recv_ticker()
            if ticker:
                # 处理行情
                pass
        
        client.stop()
    
    属性：
        strategy_id: 策略唯一ID
        is_connected: 是否已连接
    """
    
    def __init__(
        self, 
        strategy_id: str = "default",
        market_addr: str = IpcAddresses.MARKET_DATA,
        order_addr: str = IpcAddresses.ORDER,
        report_addr: str = IpcAddresses.REPORT
    ):
        """
        初始化客户端
        
        参数：
            strategy_id: 策略唯一ID，用于识别订单来源
            market_addr: 行情通道地址（默认使用 IPC）
            order_addr: 订单通道地址
            report_addr: 回报通道地址
        """
        self.strategy_id = strategy_id
        
        # ZeroMQ 地址
        self._market_addr = market_addr
        self._order_addr = order_addr
        self._report_addr = report_addr
        
        # ZeroMQ 上下文和 socket
        self._context: Optional[zmq.Context] = None
        self._market_sub: Optional[zmq.Socket] = None    # 行情订阅
        self._order_push: Optional[zmq.Socket] = None    # 订单发送
        self._report_sub: Optional[zmq.Socket] = None    # 回报订阅
        
        # 运行状态
        self._running = False
        self._connected = False
        
        # 策略引用
        self._strategy: Optional[Strategy] = None
        
        # 统计数据
        self._tick_count = 0
        self._order_count = 0
        self._report_count = 0
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理：优雅退出"""
        logger.info(f"收到信号 {signum}，正在停止...")
        self._running = False
    
    # ========================================
    # 连接管理
    # ========================================
    
    def start(self) -> bool:
        """
        启动客户端
        
        创建 ZeroMQ socket 并连接到服务器。
        
        返回：
            True 如果连接成功
        """
        if self._connected:
            logger.warning("客户端已连接")
            return True
        
        try:
            # 创建 ZeroMQ 上下文
            # 使用 1 个 I/O 线程，对于大多数场景足够
            self._context = zmq.Context(1)
            
            # ========================================
            # 创建行情订阅 socket (SUB)
            # ========================================
            # SUB socket 用于接收 PUB 发布的消息
            self._market_sub = self._context.socket(zmq.SUB)
            
            # 设置订阅过滤器
            # 空字符串表示订阅所有消息
            self._market_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            
            # 设置接收超时（毫秒）
            # 非阻塞模式下，100ms 后返回
            self._market_sub.setsockopt(zmq.RCVTIMEO, 100)
            
            # 连接到服务器
            self._market_sub.connect(self._market_addr)
            logger.info(f"行情通道已连接: {self._market_addr}")
            
            # ========================================
            # 创建订单发送 socket (PUSH)
            # ========================================
            # PUSH socket 用于发送消息到 PULL
            self._order_push = self._context.socket(zmq.PUSH)
            
            # 设置发送超时
            self._order_push.setsockopt(zmq.SNDTIMEO, 1000)
            
            # 连接到服务器
            self._order_push.connect(self._order_addr)
            logger.info(f"订单通道已连接: {self._order_addr}")
            
            # ========================================
            # 创建回报订阅 socket (SUB)
            # ========================================
            self._report_sub = self._context.socket(zmq.SUB)
            self._report_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self._report_sub.setsockopt(zmq.RCVTIMEO, 100)
            self._report_sub.connect(self._report_addr)
            logger.info(f"回报通道已连接: {self._report_addr}")
            
            self._connected = True
            self._running = True
            
            logger.info("客户端启动成功")
            return True
            
        except zmq.ZMQError as e:
            logger.error(f"连接失败: {e}")
            self.stop()
            return False
    
    def stop(self):
        """
        停止客户端
        
        关闭所有 socket 和 context
        """
        self._running = False
        
        # 关闭 socket
        if self._market_sub:
            self._market_sub.close()
            self._market_sub = None
        
        if self._order_push:
            self._order_push.close()
            self._order_push = None
        
        if self._report_sub:
            self._report_sub.close()
            self._report_sub = None
        
        # 关闭 context
        if self._context:
            self._context.term()
            self._context = None
        
        self._connected = False
        
        logger.info(f"客户端已停止 | 行情: {self._tick_count} | 订单: {self._order_count} | 回报: {self._report_count}")
    
    def is_running(self) -> bool:
        """检查是否在运行"""
        return self._running
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected
    
    # ========================================
    # 行情接收
    # ========================================
    
    def recv_ticker(self) -> Optional[TickerData]:
        """
        接收行情数据（非阻塞）
        
        如果没有数据，返回 None
        
        返回：
            TickerData 对象，或 None
        """
        if not self._connected or not self._market_sub:
            return None
        
        try:
            # 接收消息（有超时）
            msg = self._market_sub.recv_string(flags=zmq.NOBLOCK)
            
            # 解析 JSON
            data = json.loads(msg)
            
            # 只处理 ticker 类型
            if data.get("type") != "ticker":
                return None
            
            self._tick_count += 1
            return TickerData.from_dict(data)
            
        except zmq.Again:
            # 没有消息
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"接收行情失败: {e}")
            return None
    
    # ========================================
    # 订单发送
    # ========================================
    
    def send_order(self, order: OrderRequest) -> bool:
        """
        发送订单请求
        
        参数：
            order: OrderRequest 对象
            
        返回：
            True 如果发送成功
        """
        if not self._connected or not self._order_push:
            logger.error("客户端未连接，无法发送订单")
            return False
        
        try:
            # 序列化为 JSON
            msg = json.dumps(order.to_dict())
            
            # 发送
            self._order_push.send_string(msg)
            
            self._order_count += 1
            logger.debug(f"订单已发送: {order.client_order_id}")
            return True
            
        except zmq.ZMQError as e:
            logger.error(f"发送订单失败: {e}")
            return False
    
    # ========================================
    # 回报接收
    # ========================================
    
    def recv_report(self) -> Optional[OrderReport]:
        """
        接收订单回报（非阻塞）
        
        返回：
            OrderReport 对象，或 None
        """
        if not self._connected or not self._report_sub:
            return None
        
        try:
            msg = self._report_sub.recv_string(flags=zmq.NOBLOCK)
            data = json.loads(msg)
            
            if data.get("type") != "order_report":
                return None
            
            self._report_count += 1
            return OrderReport.from_dict(data)
            
        except zmq.Again:
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"接收回报失败: {e}")
            return None
    
    def recv_report_for_strategy(self, strategy_id: str) -> Optional[OrderReport]:
        """
        接收指定策略的回报
        
        参数：
            strategy_id: 策略ID
            
        返回：
            属于该策略的 OrderReport，或 None
        """
        report = self.recv_report()
        if report and report.strategy_id == strategy_id:
            return report
        return None
    
    # ========================================
    # 运行策略
    # ========================================
    
    def run(self, strategy: Strategy, log_interval: int = 10):
        """
        运行策略
        
        启动客户端，持续接收行情并分发给策略。
        按 Ctrl+C 停止。
        
        参数：
            strategy: Strategy 对象
            log_interval: 日志打印间隔（秒）
        
        示例：
            client = TradingClient(strategy_id="my_strategy")
            client.run(MyStrategy())
        """
        # 设置策略
        self._strategy = strategy
        strategy._set_client(self)
        strategy._set_strategy_id(self.strategy_id)
        
        # 启动连接
        if not self.start():
            logger.error("启动失败")
            return
        
        # 调用策略的 on_start
        try:
            strategy.on_start()
        except Exception as e:
            logger.error(f"策略 on_start 失败: {e}")
        
        logger.info("=" * 50)
        logger.info(f"  策略 [{self.strategy_id}] 开始运行")
        logger.info("  按 Ctrl+C 停止")
        logger.info("=" * 50)
        
        last_log_time = time.time()
        
        # 主循环
        while self._running:
            try:
                # 1. 接收并处理行情
                ticker = self.recv_ticker()
                if ticker:
                    try:
                        strategy._on_tick_internal(ticker)
                    except Exception as e:
                        logger.error(f"策略 on_ticker 异常: {e}")
                
                # 2. 接收并处理回报
                report = self.recv_report()
                if report:
                    try:
                        strategy._on_order_internal(report)
                    except Exception as e:
                        logger.error(f"策略 on_order 异常: {e}")
                
                # 3. 定期打印统计
                now = time.time()
                if now - last_log_time >= log_interval:
                    logger.info(
                        f"[统计] 行情: {self._tick_count} | "
                        f"订单: {self._order_count} | "
                        f"回报: {self._report_count}"
                    )
                    last_log_time = now
                
                # 4. 短暂休眠（避免空转）
                # 这里用很短的睡眠，因为 recv 已经有超时
                time.sleep(0.0001)  # 100μs
                
            except KeyboardInterrupt:
                logger.info("收到中断信号")
                break
            except Exception as e:
                logger.error(f"主循环异常: {e}")
        
        # 调用策略的 on_stop
        try:
            strategy.on_stop()
        except Exception as e:
            logger.error(f"策略 on_stop 失败: {e}")
        
        # 停止
        self.stop()
        
        logger.info("=" * 50)
        logger.info(f"  策略 [{self.strategy_id}] 已停止")
        logger.info("=" * 50)

