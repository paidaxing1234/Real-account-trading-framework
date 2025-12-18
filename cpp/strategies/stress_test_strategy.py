#!/usr/bin/env python3
"""
压力测试策略 - 测试多币种批量下单

功能：
1. 订阅20个合约的K线数据（1分钟K线）
2. 每1分钟同时下单20个币种的合约（交替买入/卖出）
3. 测试在高负载情况下系统的稳定性
4. 详细日志记录（失败单独记录，成功批量记录）

使用方法：
    python3 stress_test_strategy.py [--interval 60] [--testnet]

依赖：
    pip install pyzmq

@author Sequence Team
@date 2025-12
"""

import zmq
import json
import time
import signal
import sys
import os
import logging
import argparse
from datetime import datetime
from typing import Optional, Dict, List
from collections import defaultdict

# ============================================================
# 日志配置
# ============================================================

def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """
    设置日志系统
    
    Args:
        log_dir: 日志目录
    
    Returns:
        Logger 实例
    """
    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    
    # 创建日志文件名（包含日期时间）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"stress_test_{timestamp}.log")
    
    # 创建 logger
    logger = logging.getLogger("StressTest")
    logger.setLevel(logging.DEBUG)
    
    # 文件处理器 - 记录所有级别
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 控制台处理器 - 只记录 INFO 及以上
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"日志文件: {log_file}")
    return logger


# ============================================================
# IPC 地址配置
# ============================================================

class IpcAddresses:
    """IPC 通道地址"""
    MARKET_DATA = "ipc:///tmp/trading_md.ipc"
    ORDER = "ipc:///tmp/trading_order.ipc"
    REPORT = "ipc:///tmp/trading_report.ipc"
    SUBSCRIBE = "ipc:///tmp/trading_sub.ipc"  # 订阅管理通道


# ============================================================
# 支持的合约列表（20个主流合约）
# ============================================================

SWAP_SYMBOLS = [
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SOL-USDT-SWAP",
    "XRP-USDT-SWAP",
    "DOGE-USDT-SWAP",
    "ADA-USDT-SWAP",
    "AVAX-USDT-SWAP",
    "DOT-USDT-SWAP",
    "MATIC-USDT-SWAP",
    "LINK-USDT-SWAP",
    "UNI-USDT-SWAP",
    "ATOM-USDT-SWAP",
    "LTC-USDT-SWAP",
    "BCH-USDT-SWAP",
    "ETC-USDT-SWAP",
    "FIL-USDT-SWAP",
    "APT-USDT-SWAP",
    "ARB-USDT-SWAP",
    "OP-USDT-SWAP",
    "NEAR-USDT-SWAP",
]


# ============================================================
# 压力测试策略
# ============================================================

class StressTestStrategy:
    """
    压力测试策略
    
    功能：
    1. 订阅20个合约的K线数据
    2. 每分钟批量下单20个合约
    3. 记录成功/失败日志
    """
    
    def __init__(self, 
                 strategy_id: str = "stress_test",
                 symbols: List[str] = None,
                 order_interval: int = 60,
                 order_size: float = 1.0,
                 api_key: str = "",
                 secret_key: str = "",
                 passphrase: str = "",
                 is_testnet: bool = True,
                 logger: logging.Logger = None):
        """
        初始化压力测试策略
        
        Args:
            strategy_id: 策略ID
            symbols: 要交易的合约列表
            order_interval: 下单间隔（秒）
            order_size: 下单数量（张）
            api_key: OKX API Key
            secret_key: OKX Secret Key
            passphrase: OKX Passphrase
            is_testnet: 是否模拟盘
            logger: 日志记录器
        """
        self.strategy_id = strategy_id
        self.symbols = symbols or SWAP_SYMBOLS
        self.order_interval = order_interval
        self.order_size = order_size
        
        # 账户信息
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_testnet = is_testnet
        self.account_registered = False
        
        # ZeroMQ
        self.context = zmq.Context()
        self.market_sub: Optional[zmq.Socket] = None
        self.order_push: Optional[zmq.Socket] = None
        self.report_sub: Optional[zmq.Socket] = None
        self.subscribe_push: Optional[zmq.Socket] = None  # 订阅管理通道
        
        # 状态
        self.running = False
        self.last_order_time = 0
        self.order_round = 0  # 下单轮次（交替买卖）
        
        # 日志
        self.logger = logger or logging.getLogger("StressTest")
        
        # 统计
        self.stats = {
            "kline_count": 0,
            "order_sent": 0,
            "order_success": 0,
            "order_failed": 0,
            "pending_orders": {},  # client_order_id -> order_info
        }
        
        # 最新价格缓存（用于日志）
        self.latest_prices: Dict[str, float] = {}
        
        # 批次统计
        self.batch_results: Dict[int, Dict] = {}  # batch_id -> {sent, success, failed, orders}
        self.current_batch_id = 0
        
        self.logger.info(f"策略初始化: {strategy_id}")
        self.logger.info(f"交易合约数: {len(self.symbols)}")
        self.logger.info(f"下单间隔: {order_interval} 秒")
        self.logger.info(f"下单数量: {order_size} 张/合约")
    
    def connect(self) -> bool:
        """连接到交易服务器"""
        try:
            # 行情订阅
            self.market_sub = self.context.socket(zmq.SUB)
            self.market_sub.connect(IpcAddresses.MARKET_DATA)
            self.market_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self.market_sub.setsockopt(zmq.RCVTIMEO, 100)
            self.logger.info(f"行情通道: {IpcAddresses.MARKET_DATA}")
            
            # 订单发送
            self.order_push = self.context.socket(zmq.PUSH)
            self.order_push.connect(IpcAddresses.ORDER)
            self.logger.info(f"订单通道: {IpcAddresses.ORDER}")
            
            # 回报订阅
            self.report_sub = self.context.socket(zmq.SUB)
            self.report_sub.connect(IpcAddresses.REPORT)
            self.report_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self.report_sub.setsockopt(zmq.RCVTIMEO, 100)
            self.logger.info(f"回报通道: {IpcAddresses.REPORT}")
            
            # 订阅管理
            self.subscribe_push = self.context.socket(zmq.PUSH)
            self.subscribe_push.connect(IpcAddresses.SUBSCRIBE)
            self.logger.info(f"订阅通道: {IpcAddresses.SUBSCRIBE}")
            
            self.running = True
            self.logger.info("✓ 所有通道连接成功")
            return True
            
        except zmq.ZMQError as e:
            self.logger.error(f"连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        self.running = False
        
        if self.account_registered:
            self.unregister_account()
        
        if self.market_sub:
            self.market_sub.close()
        if self.order_push:
            self.order_push.close()
        if self.report_sub:
            self.report_sub.close()
        if self.subscribe_push:
            self.subscribe_push.close()
        
        self.logger.info("已断开所有连接")
    
    def register_account(self) -> bool:
        """注册账户到服务器"""
        if not self.order_push:
            self.logger.error("订单通道未连接")
            return False
        
        if not self.api_key or not self.secret_key or not self.passphrase:
            self.logger.warning("未提供账户信息，使用服务器默认账户")
            return True
        
        request = {
            "type": "register_account",
            "strategy_id": self.strategy_id,
            "api_key": self.api_key,
            "secret_key": self.secret_key,
            "passphrase": self.passphrase,
            "is_testnet": self.is_testnet,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self.order_push.send_string(json.dumps(request))
            self.logger.info(f"账户注册请求已发送 | API Key: {self.api_key[:8]}... | "
                           f"{'模拟盘' if self.is_testnet else '实盘'}")
            return True
        except zmq.ZMQError as e:
            self.logger.error(f"发送注册请求失败: {e}")
            return False
    
    def unregister_account(self) -> bool:
        """注销账户"""
        if not self.order_push:
            return False
        
        request = {
            "type": "unregister_account",
            "strategy_id": self.strategy_id,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self.order_push.send_string(json.dumps(request))
            self.logger.info("账户注销请求已发送")
            self.account_registered = False
            return True
        except zmq.ZMQError as e:
            self.logger.error(f"发送注销请求失败: {e}")
            return False
    
    def subscribe_klines(self):
        """订阅所有合约的K线数据"""
        if not self.subscribe_push:
            self.logger.error("订阅通道未连接")
            return
        
        self.logger.info(f"开始订阅 {len(self.symbols)} 个合约的K线...")
        
        for symbol in self.symbols:
            request = {
                "action": "subscribe",
                "channel": "kline",
                "symbol": symbol,
                "interval": "1m"
            }
            try:
                self.subscribe_push.send_string(json.dumps(request))
                self.logger.debug(f"订阅K线: {symbol}")
            except zmq.ZMQError as e:
                self.logger.error(f"订阅失败 {symbol}: {e}")
            
            # 避免发送过快
            time.sleep(0.05)
        
        self.logger.info(f"K线订阅请求发送完成")
    
    def unsubscribe_klines(self):
        """取消订阅K线"""
        if not self.subscribe_push:
            return
        
        for symbol in self.symbols:
            request = {
                "action": "unsubscribe",
                "channel": "kline",
                "symbol": symbol,
                "interval": "1m"
            }
            try:
                self.subscribe_push.send_string(json.dumps(request))
            except zmq.ZMQError:
                pass
            time.sleep(0.01)
        
        self.logger.info("K线订阅已取消")
    
    def send_batch_orders(self):
        """
        批量发送订单（20个合约同时下单）
        """
        if not self.order_push:
            return
        
        self.current_batch_id += 1
        batch_id = self.current_batch_id
        
        # 确定本轮买卖方向（交替）
        base_side = "buy" if self.order_round % 2 == 0 else "sell"
        self.order_round += 1
        
        self.logger.info("=" * 60)
        self.logger.info(f"[批次 {batch_id}] 开始批量下单 | 基准方向: {base_side.upper()}")
        self.logger.info("=" * 60)
        
        # 初始化批次统计
        self.batch_results[batch_id] = {
            "sent": 0,
            "success": 0,
            "failed": 0,
            "start_time": time.time(),
            "orders": {},
            "errors": []
        }
        
        # 记录发送开始时间
        send_start = time.time()
        
        for i, symbol in enumerate(self.symbols):
            # 交替买卖（奇偶数合约方向相反）
            side = base_side if i % 2 == 0 else ("sell" if base_side == "buy" else "buy")
            
            # 生成订单ID（只包含字母数字）
            clean_strategy_id = ''.join(c for c in self.strategy_id if c.isalnum())
            client_order_id = f"{clean_strategy_id}{batch_id:04d}{i:02d}{int(time.time()*1000) % 100000}"
            
            order = {
                "type": "order_request",
                "strategy_id": self.strategy_id,
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "order_type": "market",
                "quantity": self.order_size,
                "price": 0,
                "td_mode": "cross",  # 全仓模式
                "pos_side": "net",   # 净头寸
                "timestamp": int(time.time() * 1000)
            }
            
            try:
                self.order_push.send_string(json.dumps(order))
                self.stats["order_sent"] += 1
                self.batch_results[batch_id]["sent"] += 1
                self.batch_results[batch_id]["orders"][client_order_id] = {
                    "symbol": symbol,
                    "side": side,
                    "status": "pending",
                    "send_time": time.time()
                }
                self.stats["pending_orders"][client_order_id] = {
                    "batch_id": batch_id,
                    "symbol": symbol,
                    "side": side,
                    "send_time": time.time()
                }
                
                self.logger.debug(f"  发送: {side.upper():4s} {symbol} | ID: {client_order_id}")
                
            except zmq.ZMQError as e:
                self.logger.error(f"  发送失败: {symbol} | 错误: {e}")
                self.batch_results[batch_id]["errors"].append({
                    "symbol": symbol,
                    "side": side,
                    "error": str(e),
                    "type": "send_error"
                })
        
        send_duration = time.time() - send_start
        
        self.logger.info(f"[批次 {batch_id}] 发送完成 | "
                        f"数量: {self.batch_results[batch_id]['sent']} | "
                        f"耗时: {send_duration*1000:.1f}ms")
    
    def on_kline(self, data: dict):
        """处理K线数据"""
        self.stats["kline_count"] += 1
        
        symbol = data.get("symbol", "")
        close_price = float(data.get("close", 0) or data.get("c", 0) or 0)
        
        if symbol and close_price > 0:
            self.latest_prices[symbol] = close_price
        
        # 每100条K线打印一次状态
        if self.stats["kline_count"] % 100 == 0:
            self.logger.debug(f"K线数据: {self.stats['kline_count']} 条")
    
    def on_report(self, report: dict):
        """处理订单回报"""
        report_type = report.get("type", "order_report")
        status = report.get("status", "unknown")
        client_order_id = report.get("client_order_id", "")
        exchange_order_id = report.get("exchange_order_id", "")
        error_msg = report.get("error_msg", "")
        
        # 处理账户注册回报
        if report_type == "register_report":
            if status == "registered":
                self.account_registered = True
                self.logger.info("✓ 账户注册成功")
            else:
                self.logger.error(f"✗ 账户注册失败: {error_msg}")
            return
        
        # 处理账户注销回报
        if report_type == "unregister_report":
            if status == "unregistered":
                self.account_registered = False
                self.logger.info("✓ 账户已注销")
            else:
                self.logger.error(f"✗ 账户注销失败: {error_msg}")
            return
        
        # 处理订单回报
        if client_order_id in self.stats["pending_orders"]:
            order_info = self.stats["pending_orders"].pop(client_order_id)
            batch_id = order_info.get("batch_id", 0)
            symbol = order_info.get("symbol", "")
            side = order_info.get("side", "")
            send_time = order_info.get("send_time", 0)
            latency = (time.time() - send_time) * 1000 if send_time else 0
            
            if batch_id in self.batch_results:
                batch = self.batch_results[batch_id]
                
                if status in ["submitted", "filled", "partially_filled", "live"]:
                    self.stats["order_success"] += 1
                    batch["success"] += 1
                    batch["orders"][client_order_id]["status"] = "success"
                    self.logger.debug(f"  ✓ {side.upper():4s} {symbol} | "
                                    f"交易所ID: {exchange_order_id} | 延迟: {latency:.1f}ms")
                else:
                    self.stats["order_failed"] += 1
                    batch["failed"] += 1
                    batch["orders"][client_order_id]["status"] = "failed"
                    batch["errors"].append({
                        "symbol": symbol,
                        "side": side,
                        "status": status,
                        "error": error_msg,
                        "type": "order_error"
                    })
                    # 失败单独记录到日志
                    self.logger.error(f"  ✗ 下单失败 | {symbol} {side.upper()} | "
                                     f"状态: {status} | 错误: {error_msg}")
                
                # 检查批次是否完成
                self._check_batch_complete(batch_id)
    
    def _check_batch_complete(self, batch_id: int):
        """检查批次是否完成并记录汇总"""
        if batch_id not in self.batch_results:
            return
        
        batch = self.batch_results[batch_id]
        total_responded = batch["success"] + batch["failed"]
        
        if total_responded >= batch["sent"]:
            # 批次完成
            duration = time.time() - batch["start_time"]
            
            self.logger.info("-" * 60)
            self.logger.info(f"[批次 {batch_id}] 完成汇总")
            self.logger.info(f"  发送: {batch['sent']} | 成功: {batch['success']} | "
                           f"失败: {batch['failed']} | 耗时: {duration:.2f}s")
            
            if batch["success"] > 0:
                self.logger.info(f"  成功率: {batch['success']/batch['sent']*100:.1f}%")
            
            # 记录所有错误
            if batch["errors"]:
                self.logger.warning(f"  错误详情 ({len(batch['errors'])} 个):")
                for err in batch["errors"]:
                    self.logger.warning(f"    - {err.get('symbol', '')} {err.get('side', '')} | "
                                       f"{err.get('type', '')}: {err.get('error', '')}")
            
            self.logger.info("-" * 60)
    
    def check_order_timer(self):
        """检查是否需要批量下单"""
        current_time = time.time()
        
        if current_time - self.last_order_time >= self.order_interval:
            self.last_order_time = current_time
            self.send_batch_orders()
    
    def print_summary(self):
        """打印运行总结"""
        self.logger.info("=" * 60)
        self.logger.info("运行总结")
        self.logger.info("=" * 60)
        self.logger.info(f"  K线数据: {self.stats['kline_count']} 条")
        self.logger.info(f"  发送订单: {self.stats['order_sent']}")
        self.logger.info(f"  成功订单: {self.stats['order_success']}")
        self.logger.info(f"  失败订单: {self.stats['order_failed']}")
        if self.stats['order_sent'] > 0:
            success_rate = self.stats['order_success'] / self.stats['order_sent'] * 100
            self.logger.info(f"  成功率: {success_rate:.1f}%")
        self.logger.info(f"  下单批次: {self.current_batch_id}")
        self.logger.info("=" * 60)
    
    def run(self):
        """运行策略"""
        if not self.connect():
            return
        
        # 信号处理
        def signal_handler(signum, frame):
            self.logger.info("\n收到停止信号...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 注册账户
        if self.api_key and self.secret_key and self.passphrase:
            self.register_account()
            time.sleep(0.5)
        
        # 订阅K线
        self.subscribe_klines()
        
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("  压力测试策略启动！")
        self.logger.info(f"  - 策略ID: {self.strategy_id}")
        self.logger.info(f"  - 交易合约: {len(self.symbols)} 个")
        self.logger.info(f"  - 下单间隔: {self.order_interval} 秒")
        self.logger.info(f"  - 每笔数量: {self.order_size} 张")
        self.logger.info(f"  - 账户状态: {'已注册' if self.account_registered else '使用默认账户'}")
        self.logger.info(f"  - 交易模式: {'模拟盘' if self.is_testnet else '实盘'}")
        self.logger.info("  按 Ctrl+C 停止")
        self.logger.info("=" * 60)
        self.logger.info("")
        
        # 主循环
        try:
            while self.running:
                # 接收K线数据
                try:
                    if self.market_sub:
                        msg = self.market_sub.recv_string(zmq.NOBLOCK)
                        data = json.loads(msg)
                        msg_type = data.get("type", "")
                        if msg_type == "kline":
                            self.on_kline(data)
                except zmq.Again:
                    pass
                except json.JSONDecodeError:
                    pass
                
                # 接收回报
                try:
                    if self.report_sub:
                        msg = self.report_sub.recv_string(zmq.NOBLOCK)
                        report = json.loads(msg)
                        self.on_report(report)
                except zmq.Again:
                    pass
                except json.JSONDecodeError:
                    pass
                
                # 检查下单定时器
                self.check_order_timer()
                
                # 短暂休眠
                time.sleep(0.001)
                
        except Exception as e:
            self.logger.error(f"异常: {e}")
        
        finally:
            self.unsubscribe_klines()
            self.print_summary()
            self.disconnect()


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='压力测试策略 - 多币种批量下单测试')
    
    parser.add_argument('--strategy-id', type=str, default='stress_test',
                        help='策略ID (默认: stress_test)')
    parser.add_argument('--interval', type=int, default=60,
                        help='下单间隔秒数 (默认: 60)')
    parser.add_argument('--size', type=float, default=1.0,
                        help='每笔下单数量/张 (默认: 1.0)')
    parser.add_argument('--symbols', type=int, default=20,
                        help='交易合约数量 (默认: 20，最多20)')
    
    # 账户参数（默认使用模拟盘账户）
    parser.add_argument('--api-key', type=str,
                        default='25fc280c-9f3a-4d65-a23d-59d42eeb7d7e',
                        help='OKX API Key')
    parser.add_argument('--secret-key', type=str,
                        default='888CC77C745F1B49E75A992F38929992',
                        help='OKX Secret Key')
    parser.add_argument('--passphrase', type=str,
                        default='Sequence2025.',
                        help='OKX Passphrase')
    parser.add_argument('--testnet', action='store_true', default=True,
                        help='使用模拟盘 (默认: True)')
    parser.add_argument('--live', action='store_true',
                        help='使用实盘 (覆盖 --testnet)')
    
    parser.add_argument('--log-dir', type=str, default='logs',
                        help='日志目录 (默认: logs)')
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logging(args.log_dir)
    
    print("=" * 60)
    print("    Sequence 压力测试策略")
    print("    测试多币种批量下单性能")
    print("=" * 60)
    print()
    
    # 限制合约数量
    num_symbols = min(args.symbols, len(SWAP_SYMBOLS))
    symbols = SWAP_SYMBOLS[:num_symbols]
    
    # 确定是否使用模拟盘
    is_testnet = not args.live
    
    # 创建策略
    strategy = StressTestStrategy(
        strategy_id=args.strategy_id,
        symbols=symbols,
        order_interval=args.interval,
        order_size=args.size,
        api_key=args.api_key,
        secret_key=args.secret_key,
        passphrase=args.passphrase,
        is_testnet=is_testnet,
        logger=logger
    )
    
    # 运行
    strategy.run()


if __name__ == "__main__":
    main()

