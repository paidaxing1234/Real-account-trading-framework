#!/usr/bin/env python3
"""
KlineManager 实盘测试程序

按照现有框架模式实现：
1. 连接实盘服务器
2. 注册账户
3. 订阅多币种 1s K线数据
4. 接收实盘数据并存入 KlineManager
5. 每秒检测数据是否完整连续

使用方法:
    python3 test_kline_manager.py

@author Sequence Team
@date 2025-12
"""

import zmq
import json
import time
import signal
import argparse
from datetime import datetime
from typing import Optional, Dict

from kline_manager import KlineManager


# ============================================================
# 配置
# ============================================================

class Config:
    """配置常量"""
    # IPC地址（与实盘服务器一致）
    MARKET_DATA_IPC = "ipc:///tmp/trading_md.ipc"
    ORDER_IPC = "ipc:///tmp/trading_order.ipc"
    REPORT_IPC = "ipc:///tmp/trading_report.ipc"
    SUBSCRIBE_IPC = "ipc:///tmp/trading_sub.ipc"


# 测试币种列表
SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOGE-USDT",
    "ADA-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT", "MATIC-USDT",
]

# K线周期
INTERVAL = "1s"

# 保留的K线数量
MAX_BARS = 120  # 2分钟的数据


# ============================================================
# 测试策略
# ============================================================

class KlineManagerTest:
    """
    KlineManager 实盘测试
    
    按照 grid_strategy_standalone.py 的模式实现
    """
    
    def __init__(self,
                 strategy_id: str,
                 symbols: list,
                 interval: str = "1s",
                 max_bars: int = 120,
                 api_key: str = "",
                 secret_key: str = "",
                 passphrase: str = "",
                 is_testnet: bool = True):
        """
        初始化
        
        Args:
            strategy_id: 策略ID
            symbols: 订阅的币种列表
            interval: K线周期
            max_bars: 保留的K线数量
            api_key: OKX API Key
            secret_key: OKX Secret Key
            passphrase: OKX Passphrase
            is_testnet: 是否模拟盘
        """
        self.strategy_id = strategy_id
        self.symbols = symbols
        self.interval = interval
        self.max_bars = max_bars
        
        # 账户信息
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_testnet = is_testnet
        self.account_registered = False
        
        # ZMQ context
        self.context = zmq.Context()
        self.market_sub = None
        self.order_push = None
        self.report_sub = None
        self.subscribe_push = None
        self.running = False
        
        # K线管理器
        self.kline_manager = KlineManager(max_bars=max_bars, interval=interval)
        
        # 统计
        self.kline_count = 0
        self.report_count = 0
        self.start_time = 0
        self.last_check_time = 0
        
        print(f"[初始化] 策略ID: {strategy_id}")
        print(f"[初始化] 订阅币种: {len(symbols)} 个")
        print(f"[初始化] K线周期: {interval}")
        print(f"[初始化] 保留数量: {max_bars} 根/币种")
    
    def connect(self) -> bool:
        """连接到实盘服务器"""
        try:
            # 行情订阅 (SUB)
            self.market_sub = self.context.socket(zmq.SUB)
            self.market_sub.connect(Config.MARKET_DATA_IPC)
            self.market_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self.market_sub.setsockopt(zmq.RCVTIMEO, 100)
            print(f"[连接] 行情通道: {Config.MARKET_DATA_IPC}")
            
            # 订单发送 (PUSH) - 用于注册账户
            self.order_push = self.context.socket(zmq.PUSH)
            self.order_push.connect(Config.ORDER_IPC)
            print(f"[连接] 订单通道: {Config.ORDER_IPC}")
            
            # 回报订阅 (SUB)
            self.report_sub = self.context.socket(zmq.SUB)
            self.report_sub.connect(Config.REPORT_IPC)
            self.report_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self.report_sub.setsockopt(zmq.RCVTIMEO, 100)
            print(f"[连接] 回报通道: {Config.REPORT_IPC}")
            
            # 订阅管理 (PUSH)
            self.subscribe_push = self.context.socket(zmq.PUSH)
            self.subscribe_push.connect(Config.SUBSCRIBE_IPC)
            print(f"[连接] 订阅通道: {Config.SUBSCRIBE_IPC}")
            
            self.running = True
            print("[连接] ✓ 所有通道连接成功\n")
            return True
            
        except Exception as e:
            print(f"[错误] 连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        self.running = False
        
        # 取消订阅
        for symbol in self.symbols:
            self.unsubscribe_kline(symbol, self.interval)
        
        # 注销账户
        if self.account_registered:
            self.unregister_account()
        
        # 关闭 socket
        if self.market_sub:
            self.market_sub.close()
        if self.order_push:
            self.order_push.close()
        if self.report_sub:
            self.report_sub.close()
        if self.subscribe_push:
            self.subscribe_push.close()
        
        print("\n[断开] 已断开所有连接")
    
    def register_account(self) -> bool:
        """向实盘服务器注册账户"""
        if not self.order_push:
            print("[错误] 订单通道未连接")
            return False
        
        if not self.api_key or not self.secret_key or not self.passphrase:
            print("[警告] 未提供账户信息，将使用服务器默认账户")
            return False
        
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
            print(f"\n[账户注册] 已发送注册请求")
            print(f"           策略ID: {self.strategy_id}")
            print(f"           API Key: {self.api_key[:8]}...")
            print(f"           模式: {'模拟盘' if self.is_testnet else '实盘'}")
            return True
        except Exception as e:
            print(f"[错误] 发送注册请求失败: {e}")
            return False
    
    def unregister_account(self) -> bool:
        """注销策略账户"""
        if not self.order_push:
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
        except Exception as e:
            print(f"[错误] 发送注销请求失败: {e}")
            return False
    
    def subscribe_kline(self, symbol: str, interval: str) -> bool:
        """订阅K线数据"""
        if not self.subscribe_push:
            print("[错误] 订阅通道未连接")
            return False
        
        request = {
            "action": "subscribe",
            "channel": "kline",
            "symbol": symbol,
            "interval": interval,
            "strategy_id": self.strategy_id,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self.subscribe_push.send_string(json.dumps(request))
            return True
        except Exception as e:
            print(f"[错误] 订阅请求失败: {e}")
            return False
    
    def unsubscribe_kline(self, symbol: str, interval: str) -> bool:
        """取消订阅K线数据"""
        if not self.subscribe_push:
            return False
        
        request = {
            "action": "unsubscribe",
            "channel": "kline",
            "symbol": symbol,
            "interval": interval,
            "strategy_id": self.strategy_id,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self.subscribe_push.send_string(json.dumps(request))
            return True
        except Exception as e:
            return False
    
    def recv_market(self) -> Optional[dict]:
        """接收行情数据（非阻塞）"""
        try:
            msg = self.market_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            return data
        except zmq.Again:
            return None
        except Exception:
            return None
    
    def recv_report(self) -> Optional[dict]:
        """接收回报数据（非阻塞）"""
        try:
            msg = self.report_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            self.report_count += 1
            return data
        except zmq.Again:
            return None
        except Exception:
            return None
    
    def on_kline(self, data: dict):
        """
        处理K线数据
        
        Args:
            data: K线数据，格式如:
                {
                    "type": "kline",
                    "symbol": "BTC-USDT",
                    "interval": "1s",
                    "open": 100000.0,
                    "high": 100100.0,
                    "low": 99900.0,
                    "close": 100050.0,
                    "volume": 1234.5,
                    "timestamp": 1703001234000
                }
        """
        symbol = data.get("symbol", "")
        
        # 只处理订阅的币种
        if symbol not in self.symbols:
            return
        
        # 只处理目标周期
        if data.get("interval") != self.interval:
            return
        
        # 存入 KlineManager
        is_new = self.kline_manager.update(
            symbol,
            int(data.get("timestamp", 0)),
            float(data.get("open", 0)),
            float(data.get("high", 0)),
            float(data.get("low", 0)),
            float(data.get("close", 0)),
            float(data.get("volume", 0))
        )
        
        if is_new:
            self.kline_count += 1
    
    def on_report(self, report: dict):
        """处理回报消息"""
        report_type = report.get("type", "")
        status = report.get("status", "")
        
        # 处理账户注册回报
        if report_type == "register_report":
            if status == "registered":
                self.account_registered = True
                print(f"[账户注册] ✓ 注册成功！")
            else:
                print(f"[账户注册] ✗ 注册失败: {report.get('error_msg', '')}")
            return
        
        # 处理账户注销回报
        if report_type == "unregister_report":
            if status == "unregistered":
                self.account_registered = False
                print(f"[账户注销] ✓ 已注销")
            return
    
    def check_continuity(self):
        """检查数据连续性"""
        current_time = time.time()
        
        # 每秒检查一次
        if current_time - self.last_check_time < 1.0:
            return
        
        self.last_check_time = current_time
        
        # 统计
        total_symbols = len(self.symbols)
        continuous_count = 0
        discontinuous_symbols = []
        
        for symbol in self.symbols:
            bar_count = self.kline_manager.get_bar_count(symbol)
            
            if bar_count >= 2:
                is_cont, missing = self.kline_manager.is_continuous(symbol)
                if is_cont:
                    continuous_count += 1
                else:
                    discontinuous_symbols.append((symbol, len(missing), bar_count))
            elif bar_count > 0:
                continuous_count += 1  # 只有1根，视为连续
        
        # 打印状态
        ts_str = datetime.now().strftime("%H:%M:%S")
        stats = self.kline_manager.get_stats()
        
        status = "✓" if continuous_count == total_symbols else "✗"
        
        # 计算有数据的币种数
        symbols_with_data = len([s for s in self.symbols if self.kline_manager.get_bar_count(s) > 0])
        
        print(f"[{ts_str}] K线: {self.kline_count:5d} | "
              f"币种: {symbols_with_data}/{total_symbols} | "
              f"连续: {continuous_count}/{symbols_with_data} {status} | "
              f"内存: {stats['memory_kb']:.1f}KB")
        
        # 打印不连续的币种
        if discontinuous_symbols:
            for sym, miss_count, bar_count in discontinuous_symbols[:3]:
                print(f"         └─ {sym}: 缺失 {miss_count} 根 (已有 {bar_count} 根)")
    
    def run(self):
        """主循环"""
        if not self.connect():
            return
        
        # 注册账户
        if self.api_key and self.secret_key and self.passphrase:
            self.register_account()
            time.sleep(0.5)
            
            # 处理注册回报
            for _ in range(10):
                report = self.recv_report()
                if report and report.get("type") == "register_report":
                    self.on_report(report)
                    break
                time.sleep(0.1)
        else:
            print("[账户] 未提供账户信息，将使用服务器默认账户")
        
        # 订阅K线数据
        print(f"\n[订阅] 正在订阅 {len(self.symbols)} 个币种的 {self.interval} K线...")
        for symbol in self.symbols:
            self.subscribe_kline(symbol, self.interval)
            print(f"  ✓ {symbol}")
        
        time.sleep(1)  # 等待订阅生效
        
        # 信号处理
        def signal_handler(signum, frame):
            print("\n\n[信号] 收到停止信号...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print("\n" + "=" * 60)
        print("  测试运行中...")
        print("  - 接收实盘 K 线数据并存入 KlineManager")
        print("  - 每秒检测数据连续性")
        print("  按 Ctrl+C 停止")
        print("=" * 60 + "\n")
        
        self.start_time = time.time()
        self.last_check_time = time.time()
        
        try:
            while self.running:
                # 接收行情
                data = self.recv_market()
                if data:
                    msg_type = data.get("type", "")
                    if msg_type == "kline":
                        self.on_kline(data)
                
                # 接收回报
                report = self.recv_report()
                if report:
                    self.on_report(report)
                
                # 检查连续性
                self.check_continuity()
                
                # 短暂休眠
                time.sleep(0.001)
        
        except Exception as e:
            print(f"\n[异常] {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.print_summary()
            self.disconnect()
    
    def print_summary(self):
        """打印总结"""
        elapsed = time.time() - self.start_time
        stats = self.kline_manager.get_stats()
        
        print("\n" + "=" * 60)
        print("                    测试总结")
        print("=" * 60)
        print(f"  运行时间:      {elapsed:.1f} 秒")
        print(f"  接收K线:       {self.kline_count} 根")
        print(f"  币种数量:      {stats['symbol_count']}")
        print(f"  总K线存储:     {stats['total_bars']} 根")
        print(f"  内存占用:      {stats['memory_kb']:.2f} KB")
        
        # 每个币种的状态
        print(f"\n  各币种详情:")
        for symbol in self.symbols:
            bar_count = self.kline_manager.get_bar_count(symbol)
            if bar_count > 0:
                is_cont, missing = self.kline_manager.is_continuous(symbol)
                status = "✓ 连续" if is_cont else f"✗ 缺失{len(missing)}根"
                last = self.kline_manager.get_last(symbol)
                last_price = f"{last['close']:.2f}" if last is not None else "N/A"
                print(f"    {symbol:15s}: {bar_count:3d} 根 | {status:10s} | 最新: {last_price}")
            else:
                print(f"    {symbol:15s}: 无数据")
        
        print("=" * 60)


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='KlineManager 实盘测试')
    parser.add_argument('--strategy-id', type=str, default='kline_test',
                        help='策略ID (默认: kline_test)')
    parser.add_argument('--interval', type=str, default='1s',
                        help='K线周期 (默认: 1s)')
    parser.add_argument('--max-bars', type=int, default=120,
                        help='保留K线数量 (默认: 120)')
    
    # 账户参数
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
                        help='使用实盘')
    
    args = parser.parse_args()
    
    # 确定是否使用模拟盘
    is_testnet = not args.live
    
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + "  KlineManager 实盘测试程序".center(50) + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # 创建测试实例
    test = KlineManagerTest(
        strategy_id=args.strategy_id,
        symbols=SYMBOLS,
        interval=args.interval,
        max_bars=args.max_bars,
        api_key=args.api_key,
        secret_key=args.secret_key,
        passphrase=args.passphrase,
        is_testnet=is_testnet
    )
    
    # 运行
    test.run()


if __name__ == "__main__":
    main()

