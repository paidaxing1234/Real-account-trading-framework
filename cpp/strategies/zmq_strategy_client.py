#!/usr/bin/env python3
"""
ZeroMQ 策略客户端示例

功能：
1. 订阅实盘服务器推送的 trades 数据
2. 每分钟自动下一笔测试订单
3. 接收并显示订单回报

架构：
    Trading Server (C++)
         │
         │ IPC (ZeroMQ)
         ▼
    ┌─────────────────┐
    │ Strategy Client │
    │                 │
    │ - SUB trades    │
    │ - PUSH orders   │
    │ - SUB reports   │
    └─────────────────┘

使用方法：
    python3 zmq_strategy_client.py

依赖：
    pip install pyzmq

@author Sequence Team
@date 2025-12
"""

import zmq
import json
import time
import threading
import signal
import sys
import os
import argparse
from datetime import datetime
from typing import Optional, Callable

# ============================================================
# CPU 亲和性配置（低延迟关键）
# ============================================================

def set_cpu_affinity(cpu_id: int) -> bool:
    """
    将当前进程绑定到指定 CPU 核心
    
    Args:
        cpu_id: CPU 核心 ID
    
    Returns:
        bool: 成功返回 True
    """
    try:
        os.sched_setaffinity(0, {cpu_id})
        print(f"[绑核] 进程已绑定到 CPU {cpu_id}")
        return True
    except (AttributeError, OSError) as e:
        print(f"[绑核] 绑定失败: {e}")
        return False


def set_realtime_priority(priority: int = 50) -> bool:
    """
    设置进程为实时调度优先级（需要 root 权限）
    
    Args:
        priority: 优先级 (1-99)
    
    Returns:
        bool: 成功返回 True
    """
    try:
        # SCHED_FIFO = 1
        param = os.sched_param(priority)
        os.sched_setscheduler(0, 1, param)  # SCHED_FIFO
        print(f"[调度] 已设置为 SCHED_FIFO，优先级 {priority}")
        return True
    except (AttributeError, PermissionError, OSError) as e:
        print(f"[调度] 设置失败 (需要 sudo): {e}")
        return False


# NUMA Node 0 的策略 CPU 分配
# 与 C++ 服务器保持一致
class CpuConfig:
    """CPU 亲和性配置"""
    # 策略进程使用的 CPU 范围（同一 NUMA 节点）
    STRATEGY_START_CPU = 4
    STRATEGY_END_CPU = 11
    
    @classmethod
    def get_strategy_cpu(cls, strategy_index: int) -> int:
        """根据策略编号获取 CPU ID"""
        cpu = cls.STRATEGY_START_CPU + strategy_index
        if cpu > cls.STRATEGY_END_CPU:
            cpu = cls.STRATEGY_START_CPU + (strategy_index % (cls.STRATEGY_END_CPU - cls.STRATEGY_START_CPU + 1))
        return cpu


# ============================================================
# IPC 地址配置（必须与 C++ 服务端一致）
# ============================================================

class IpcAddresses:
    """IPC 通道地址"""
    MARKET_DATA = "ipc:///tmp/trading_md.ipc"
    ORDER = "ipc:///tmp/trading_order.ipc"
    REPORT = "ipc:///tmp/trading_report.ipc"


# ============================================================
# ZeroMQ 策略客户端
# ============================================================

class ZmqStrategyClient:
    """
    ZeroMQ 策略客户端
    
    提供：
    - 订阅行情/trades 数据
    - 发送订单请求
    - 订阅订单回报
    - 注册策略账户
    """
    
    def __init__(self, strategy_id: str = "test_strategy",
                 api_key: str = "",
                 secret_key: str = "",
                 passphrase: str = "",
                 is_testnet: bool = True):
        """
        初始化策略客户端
        
        Args:
            strategy_id: 策略唯一标识
            api_key: OKX API Key（可选，连接后注册）
            secret_key: OKX Secret Key
            passphrase: OKX Passphrase
            is_testnet: 是否模拟盘
        """
        self.strategy_id = strategy_id
        self.context = zmq.Context()
        
        # 账户信息
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_testnet = is_testnet
        self.account_registered = False
        
        # 行情订阅 socket (SUB)
        self.market_sub: Optional[zmq.Socket] = None
        
        # 订单发送 socket (PUSH)
        self.order_push: Optional[zmq.Socket] = None
        
        # 回报订阅 socket (SUB)
        self.report_sub: Optional[zmq.Socket] = None
        
        # 运行状态
        self.running = False
        
        # 统计
        self.trade_count = 0
        self.order_count = 0
        self.report_count = 0
        
        print(f"[Strategy] ID: {self.strategy_id}")
        if api_key:
            print(f"[Strategy] API Key: {api_key[:8]}...")
    
    def connect(self) -> bool:
        """连接到交易服务器"""
        try:
            # ========================================
            # 行情订阅
            # ========================================
            self.market_sub = self.context.socket(zmq.SUB)
            self.market_sub.connect(IpcAddresses.MARKET_DATA)
            # 订阅所有消息（空字符串表示订阅全部）
            self.market_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            # 设置接收超时（毫秒）
            self.market_sub.setsockopt(zmq.RCVTIMEO, 100)
            print(f"[连接] 行情通道: {IpcAddresses.MARKET_DATA}")
            
            # ========================================
            # 订单发送
            # ========================================
            self.order_push = self.context.socket(zmq.PUSH)
            self.order_push.connect(IpcAddresses.ORDER)
            print(f"[连接] 订单通道: {IpcAddresses.ORDER}")
            
            # ========================================
            # 回报订阅
            # ========================================
            self.report_sub = self.context.socket(zmq.SUB)
            self.report_sub.connect(IpcAddresses.REPORT)
            self.report_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self.report_sub.setsockopt(zmq.RCVTIMEO, 100)
            print(f"[连接] 回报通道: {IpcAddresses.REPORT}")
            
            self.running = True
            print("[连接] ✓ 所有通道连接成功")
            return True
            
        except zmq.ZMQError as e:
            print(f"[错误] 连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        self.running = False
        
        # 注销账户
        if self.account_registered:
            self.unregister_account()
        
        if self.market_sub:
            self.market_sub.close()
        if self.order_push:
            self.order_push.close()
        if self.report_sub:
            self.report_sub.close()
        
        print("[断开] 已断开所有连接")
    
    def register_account(self, api_key: str = None, secret_key: str = None, 
                         passphrase: str = None, is_testnet: bool = None) -> bool:
        """
        向实盘服务器注册账户
        
        Args:
            api_key: OKX API Key（如果不提供则使用初始化时的值）
            secret_key: OKX Secret Key
            passphrase: OKX Passphrase
            is_testnet: 是否模拟盘
        
        Returns:
            bool: 发送成功返回 True
        """
        if not self.order_push:
            print("[错误] 订单通道未连接")
            return False
        
        # 使用提供的参数或初始化时的值
        api_key = api_key or self.api_key
        secret_key = secret_key or self.secret_key
        passphrase = passphrase or self.passphrase
        is_testnet = is_testnet if is_testnet is not None else self.is_testnet
        
        if not api_key or not secret_key or not passphrase:
            print("[错误] 缺少账户信息 (api_key, secret_key, passphrase)")
            return False
        
        request = {
            "type": "register_account",
            "strategy_id": self.strategy_id,
            "api_key": api_key,
            "secret_key": secret_key,
            "passphrase": passphrase,
            "is_testnet": is_testnet,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self.order_push.send_string(json.dumps(request))
            print(f"\n[账户注册] 已发送注册请求")
            print(f"           策略ID: {self.strategy_id}")
            print(f"           API Key: {api_key[:8]}...")
            print(f"           模式: {'模拟盘' if is_testnet else '实盘'}")
            
            # 更新本地状态
            self.api_key = api_key
            self.secret_key = secret_key
            self.passphrase = passphrase
            self.is_testnet = is_testnet
            
            return True
        except zmq.ZMQError as e:
            print(f"[错误] 发送注册请求失败: {e}")
            return False
    
    def unregister_account(self) -> bool:
        """
        注销策略账户
        
        Returns:
            bool: 发送成功返回 True
        """
        if not self.order_push:
            print("[错误] 订单通道未连接")
            return False
        
        request = {
            "type": "unregister_account",
            "strategy_id": self.strategy_id,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self.order_push.send_string(json.dumps(request))
            print(f"[账户注销] 已发送注销请求")
            self.account_registered = False
            return True
        except zmq.ZMQError as e:
            print(f"[错误] 发送注销请求失败: {e}")
            return False
    
    def recv_trade(self) -> Optional[dict]:
        """
        接收 trade 数据（非阻塞）
        
        Returns:
            dict: trade 数据，如果没有数据返回 None
        """
        if not self.market_sub:
            return None
        
        try:
            msg = self.market_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            self.trade_count += 1
            return data
        except zmq.Again:
            return None
        except json.JSONDecodeError as e:
            print(f"[警告] JSON 解析错误: {e}")
            return None
    
    def recv_report(self) -> Optional[dict]:
        """
        接收订单回报（非阻塞）
        
        Returns:
            dict: 回报数据，如果没有数据返回 None
        """
        if not self.report_sub:
            return None
        
        try:
            msg = self.report_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            self.report_count += 1
            return data
        except zmq.Again:
            return None
        except json.JSONDecodeError as e:
            print(f"[警告] JSON 解析错误: {e}")
            return None
    
    def send_order(self, 
                   symbol: str,
                   side: str,
                   order_type: str,
                   quantity: float,
                   price: float = 0.0,
                   td_mode: str = "cash",
                   tgt_ccy: str = "quote_ccy") -> str:
        """
        发送订单
        
        Args:
            symbol: 交易对，如 "BTC-USDT"
            side: "buy" 或 "sell"
            order_type: "market" 或 "limit"
            quantity: 数量（市价单以 tgt_ccy 指定单位）
            price: 价格（限价单必填）
            td_mode: 交易模式，"cash" 现货，"cross" 全仓
            tgt_ccy: 目标货币，"quote_ccy" 以计价货币（如USDT）计量
        
        Returns:
            str: 客户端订单ID
        """
        if not self.order_push:
            print("[错误] 订单通道未连接")
            return ""
        
        # 生成唯一订单ID（OKX要求只能包含字母和数字，不能有下划线等特殊字符）
        clean_strategy_id = ''.join(c for c in self.strategy_id if c.isalnum())
        client_order_id = f"{clean_strategy_id}{int(time.time()*1000) % 100000000}"
        
        order = {
            "type": "order_request",
            "strategy_id": self.strategy_id,
            "client_order_id": client_order_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "td_mode": td_mode,
            "tgt_ccy": tgt_ccy,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self.order_push.send_string(json.dumps(order))
            self.order_count += 1
            print(f"\n[订单] 已发送: {side} {symbol} {order_type}")
            print(f"       数量: {quantity}, 价格: {price if order_type == 'limit' else 'market'}")
            print(f"       订单ID: {client_order_id}")
            return client_order_id
        except zmq.ZMQError as e:
            print(f"[错误] 发送订单失败: {e}")
            return ""


# ============================================================
# 简单测试策略
# ============================================================

class SimpleTestStrategy:
    """
    简单测试策略
    
    功能：
    1. 打印接收到的 trades 数据
    2. 定时下单（用于测试联动）
    """
    
    def __init__(self, client: ZmqStrategyClient, order_interval: int = 10):
        self.client = client
        self.last_order_time = 0
        self.order_interval = order_interval  # 默认10秒下一笔单
        self.last_trade = None
        self.last_price = 0.0  # 记录最新价格
        
    def on_trade(self, trade: dict):
        """处理 trade 数据"""
        self.last_trade = trade
        
        # 更新最新价格
        price = trade.get("price", 0)
        if price > 0:
            self.last_price = price
        
        # 每 50 条打印一次
        if self.client.trade_count % 50 == 0:
            symbol = trade.get("symbol", "?")
            side = trade.get("side", "?")
            qty = trade.get("quantity", 0)
            
            print(f"\n[Trade #{self.client.trade_count}] {symbol}")
            print(f"  方向: {side} | 价格: {price:.2f} | 数量: {qty}")
    
    def on_report(self, report: dict):
        """处理回报消息"""
        report_type = report.get("type", "order_report")
        status = report.get("status", "unknown")
        error_msg = report.get("error_msg", "")
        
        # 处理账户注册回报
        if report_type == "register_report":
            print(f"\n{'='*50}")
            print(f"[账户注册回报] 状态: {status}")
            if status == "registered":
                self.client.account_registered = True
                print(f"               ✓ 账户注册成功！")
            else:
                print(f"               ✗ 注册失败: {error_msg}")
            print(f"{'='*50}")
            return
        
        # 处理账户注销回报
        if report_type == "unregister_report":
            print(f"\n{'='*50}")
            print(f"[账户注销回报] 状态: {status}")
            if status == "unregistered":
                self.client.account_registered = False
                print(f"               ✓ 账户已注销")
            else:
                print(f"               ✗ 注销失败: {error_msg}")
            print(f"{'='*50}")
            return
        
        # 处理订单回报
        client_order_id = report.get("client_order_id", "")
        exchange_order_id = report.get("exchange_order_id", "")
        
        print(f"\n{'='*50}")
        print(f"[回报] 类型: {report_type} | 状态: {status}")
        if client_order_id:
            print(f"       客户端ID: {client_order_id}")
        if exchange_order_id:
            print(f"       交易所ID: {exchange_order_id}")
        if error_msg:
            print(f"       错误信息: {error_msg}")
        print(f"{'='*50}")
    
    def check_order_timer(self):
        """检查是否需要下单"""
        current_time = time.time()
        
        # 按配置的间隔下单
        if current_time - self.last_order_time >= self.order_interval:
            self.last_order_time = current_time
            
            # 下一笔市价买单（1 USDT）
            print(f"\n{'*'*50}")
            print(f"[定时下单] {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'*'*50}")
            
            self.client.send_order(
                symbol="BTC-USDT",
                side="buy",
                order_type="market",
                quantity=1,  # 1 USDT
                td_mode="cash",
                tgt_ccy="quote_ccy"
            )


# ============================================================
# 主函数
# ============================================================

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='ZeroMQ 策略客户端')
    parser.add_argument('--cpu', type=int, default=-1,
                        help='绑定到指定 CPU 核心 (默认: 自动分配)')
    parser.add_argument('--strategy-id', type=str, default='test',
                        help='策略 ID (默认: test)')
    parser.add_argument('--strategy-index', type=int, default=0,
                        help='策略编号，用于自动分配 CPU (默认: 0)')
    parser.add_argument('--order-interval', type=int, default=10,
                        help='下单间隔秒数 (默认: 10)')
    parser.add_argument('--realtime', action='store_true',
                        help='启用实时调度优先级 (需要 sudo)')
    parser.add_argument('--no-bindcpu', action='store_true',
                        help='禁用 CPU 绑定')
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
    args = parser.parse_args()
    
    print("=" * 60)
    print("    Sequence ZeroMQ 策略客户端")
    print("    交易所 -> 实盘 -> 策略 联动测试")
    print("=" * 60)
    print()
    
    # ========================================
    # CPU 亲和性配置
    # ========================================
    print(f"[配置] 策略 ID: {args.strategy_id}")
    print(f"[配置] 策略编号: {args.strategy_index}")
    print(f"[配置] 下单间隔: {args.order_interval} 秒")
    
    if not args.no_bindcpu:
        cpu_id = args.cpu
        if cpu_id < 0:
            # 根据策略编号自动分配 CPU
            cpu_id = CpuConfig.get_strategy_cpu(args.strategy_index)
        
        print(f"[配置] 目标 CPU: {cpu_id}")
        print()
        
        # 绑定 CPU
        set_cpu_affinity(cpu_id)
    else:
        print("[配置] CPU 绑定: 禁用")
        print()
    
    # 设置实时优先级（可选）
    if args.realtime:
        set_realtime_priority(48)  # 略低于服务器
    
    # 确定是否使用模拟盘
    is_testnet = not args.live
    
    # 创建客户端
    client = ZmqStrategyClient(
        strategy_id=args.strategy_id,
        api_key=args.api_key,
        secret_key=args.secret_key,
        passphrase=args.passphrase,
        is_testnet=is_testnet
    )
    
    # 连接
    if not client.connect():
        print("[错误] 无法连接到交易服务器")
        print("       请确保 trading_server_full 已启动")
        sys.exit(1)
    
    # 如果提供了账户信息，自动注册
    if args.api_key and args.secret_key and args.passphrase:
        print("\n[账户] 注册账户到实盘服务器...")
        client.register_account()
        # 等待注册回报
        time.sleep(0.5)
    else:
        print("\n[账户] 未提供账户信息，将使用服务器默认账户")
        print("       可通过 --api-key, --secret-key, --passphrase 参数指定账户")
    
    # 创建策略
    strategy = SimpleTestStrategy(client, order_interval=args.order_interval)
    
    # 信号处理
    def signal_handler(signum, frame):
        print("\n\n[信号] 收到停止信号...")
        client.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print()
    print("=" * 60)
    print("  策略启动！")
    print(f"  - 策略ID: {client.strategy_id}")
    print(f"  - 账户状态: {'已注册' if client.account_registered else '使用默认账户'}")
    print(f"  - 交易模式: {'模拟盘' if client.is_testnet else '实盘'}")
    print("  - 接收 trades 数据")
    print(f"  - 每 {strategy.order_interval} 秒自动下单")
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    print()
    
    # 主循环
    start_time = time.time()
    
    try:
        while client.running:
            # 接收 trades
            trade = client.recv_trade()
            if trade:
                strategy.on_trade(trade)
            
            # 接收回报
            report = client.recv_report()
            if report:
                strategy.on_report(report)
            
            # 检查定时下单
            strategy.check_order_timer()
            
            # 短暂休眠
            time.sleep(0.001)  # 1ms
            
    except Exception as e:
        print(f"\n[异常] {e}")
    
    finally:
        # 统计
        elapsed = time.time() - start_time
        print()
        print("=" * 60)
        print("  策略停止")
        print("=" * 60)
        print(f"  运行时间: {elapsed:.1f} 秒")
        print(f"  收到 Trades: {client.trade_count}")
        print(f"  发送订单: {client.order_count}")
        print(f"  收到回报: {client.report_count}")
        if elapsed > 0:
            print(f"  平均 Trades/秒: {client.trade_count / elapsed:.2f}")
        print("=" * 60)
        
        client.disconnect()


if __name__ == "__main__":
    main()

