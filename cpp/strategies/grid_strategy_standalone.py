#!/usr/bin/env python3
"""
独立网格交易策略 - 不依赖zmq_strategy_client

直接使用ZMQ进行通信，参数完全符合OKX API规范

使用方法:
    python3 grid_strategy_standalone.py --symbol BTC-USDT-SWAP --grid-num 20
"""

import zmq
import json
import time
import signal
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque

# ============================================================
# 配置
# ============================================================

class Config:
    """配置常量"""
    # IPC地址
    MARKET_DATA_IPC = "ipc:///tmp/trading_md.ipc"
    ORDER_IPC = "ipc:///tmp/trading_order.ipc"
    REPORT_IPC = "ipc:///tmp/trading_report.ipc"
    SUBSCRIBE_IPC = "ipc:///tmp/trading_sub.ipc"  # 订阅通道


# ============================================================
# 独立网格策略
# ============================================================

class GridStrategy:
    """
    独立网格交易策略
    
    直接使用ZMQ通信，不依赖其他库
    """
    
    def __init__(self,
                 strategy_id: str,
                 symbol: str,
                 grid_num: int,
                 grid_spread: float,
                 order_amount: float,
                 api_key: str = "",
                 secret_key: str = "",
                 passphrase: str = "",
                 is_testnet: bool = True):
        """
        初始化
        
        Args:
            strategy_id: 策略ID
            symbol: 交易对（如 BTC-USDT-SWAP）
            grid_num: 单边网格数量
            grid_spread: 网格间距比例
            order_amount: 单次下单金额（USDT）
            api_key: OKX API Key
            secret_key: OKX Secret Key
            passphrase: OKX Passphrase
            is_testnet: 是否模拟盘
        """
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.grid_num = grid_num
        self.grid_spread = grid_spread
        self.order_amount = order_amount
        
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
        self.subscribe_push = None  # 订阅通道
        self.running = False
        
        # 价格追踪
        self.current_price = 0.0
        self.base_price = 0.0
        
        # 网格
        self.buy_levels: List[float] = []
        self.sell_levels: List[float] = []
        self.triggered: Dict[float, bool] = {}
        
        # 统计
        self.trade_count = 0
        self.order_count = 0
        self.report_count = 0
        self.buy_count = 0
        self.sell_count = 0
        self.start_time = 0
        
        # 判断是否为合约
        self.is_swap = "SWAP" in symbol.upper()
        
        print(f"[策略启动] {symbol} | 网格:{grid_num}x2 | 间距:{grid_spread*100:.3f}% | 金额:{order_amount}U")
    
    def connect(self) -> bool:
        """连接到服务器"""
        try:
            # 行情订阅 (SUB)
            self.market_sub = self.context.socket(zmq.SUB)
            self.market_sub.connect(Config.MARKET_DATA_IPC)
            self.market_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self.market_sub.setsockopt(zmq.RCVTIMEO, 100)
            # 订单发送 (PUSH)
            self.order_push = self.context.socket(zmq.PUSH)
            self.order_push.connect(Config.ORDER_IPC)
            
            # 回报订阅 (SUB)
            self.report_sub = self.context.socket(zmq.SUB)
            self.report_sub.connect(Config.REPORT_IPC)
            self.report_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self.report_sub.setsockopt(zmq.RCVTIMEO, 100)
            
            # 订阅管理 (PUSH)
            self.subscribe_push = self.context.socket(zmq.PUSH)
            self.subscribe_push.connect(Config.SUBSCRIBE_IPC)
            print(f"[连接] 订阅通道: {Config.SUBSCRIBE_IPC}")
            
            self.running = True
            print("[连接完成]\n")
            return True
            
        except Exception as e:
            print(f"[错误] 连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        self.running = False
        
        # 取消订阅
        self.unsubscribe_trades(self.symbol)
        
        # 注销账户
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
        print("\n[断开] 已断开连接")
    
    def subscribe_trades(self, symbol: str) -> bool:
        """
        向服务器订阅 trades 行情
        
        Args:
            symbol: 交易对（如 BTC-USDT-SWAP）
        """
        if not self.subscribe_push:
            print("[错误] 订阅通道未连接")
            return False
        
        request = {
            "action": "subscribe",
            "channel": "trades",
            "symbol": symbol
        }
        
        try:
            self.subscribe_push.send_string(json.dumps(request))
            print(f"[订阅] 已请求订阅 trades: {symbol}")
            return True
        except Exception as e:
            print(f"[错误] 订阅请求失败: {e}")
            return False
    
    def unsubscribe_trades(self, symbol: str) -> bool:
        """取消订阅 trades 行情"""
        if not self.subscribe_push:
            return False
        
        request = {
            "action": "unsubscribe",
            "channel": "trades",
            "symbol": symbol
        }
        
        try:
            self.subscribe_push.send_string(json.dumps(request))
            print(f"[取消订阅] trades: {symbol}")
            return True
        except Exception as e:
            print(f"[错误] 取消订阅失败: {e}")
            return False
    
    def register_account(self) -> bool:
        """
        向实盘服务器注册账户
        
        Returns:
            bool: 发送成功返回 True
        """
        if not self.order_push:
            print("[错误] 订单通道未连接")
            return False
        
        if not self.api_key or not self.secret_key or not self.passphrase:
            print("[警告] 未提供账户信息，将使用服务器默认账户")
            return False
        
        # 清理策略ID中的特殊字符（OKX要求只能字母数字）
        clean_strategy_id = ''.join(c for c in self.strategy_id if c.isalnum())
        
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
    
    def recv_trade(self) -> Optional[dict]:
        """接收行情（非阻塞）"""
        try:
            msg = self.market_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            self.trade_count += 1
            return data
        except zmq.Again:
            return None
        except Exception as e:
            return None
    
    def recv_report(self) -> Optional[dict]:
        """接收回报（非阻塞）"""
        try:
            msg = self.report_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            self.report_count += 1

            # 打印回报时间戳
            recv_timestamp = time.time_ns()
            status = data.get("status", "")
            client_id = data.get("client_order_id", "")
            print(f"[策略收到回报] 时间戳: {recv_timestamp} ns | 订单ID: {client_id} | 状态: {status}")
            
            return data
        except zmq.Again:
            return None
        except Exception as e:
            return None
    
    def send_order(self, side: str, quantity: float, price: float = 0.0) -> str:
        """
        发送订单（完全符合OKX API规范）
        
        Args:
            side: "buy" 或 "sell"
            quantity: 数量（合约用张数，现货用币数）
            price: 价格（限价单用，市价单传0）
        """
        
        # 生成客户端订单ID（只能包含字母和数字，不能有下划线）
        # 使用简短前缀，像example一样
        prefix = "py"  # 简短前缀
        client_order_id = f"{prefix}{int(time.time()*1000) % 1000000000}"

        
        # 构造订单请求（完全符合OKX API）
        if self.is_swap:
            # 合约订单 - 支持双向持仓模式
            # 买入开多用 long，卖出开空用 short
            pos_side = "long" if side == "buy" else "short"
            
            order = {
                "type": "order_request",
                "strategy_id": self.strategy_id,
                "client_order_id": "",
                "symbol": self.symbol,           # instId
                "side": side,                    # buy/sell
                "order_type": "market",          # ordType: market
                "quantity": int(quantity),       # sz: 张数（整数）
                "price": 0,                      # px: 市价单不需要
                "td_mode": "cross",              # tdMode: cross全仓
                "pos_side": pos_side,            # posSide: long开多/short开空（双向持仓）
                "tgt_ccy": "",                   # tgtCcy: 合约不需要
                "timestamp": int(time.time() * 1000)
            }
        else:
            # 现货订单
            order = {
                "type": "order_request",
                "strategy_id": self.strategy_id,
                "client_order_id": client_order_id,
                "symbol": self.symbol,
                "side": side,
                "order_type": "market",
                "quantity": quantity,             # sz: BTC数量
                "price": 0,
                "td_mode": "cash",               # tdMode: cash现货
                "tgt_ccy": "",
                "timestamp": int(time.time() * 1000)
            }
        
        # 打印时间戳追踪
        send_timestamp = time.time_ns()
        print(f"[策略发送] 时间戳: {send_timestamp} ns | 订单ID: {client_order_id} | {side.upper()} {quantity}{'张' if self.is_swap else 'BTC'}")
        
        try:
            self.order_push.send_string(json.dumps(order))
            self.order_count += 1
            return client_order_id
        except Exception as e:
            print(f"[错误] 发送订单失败: {e}")
            return ""
    
    def init_grids(self):
        """初始化网格"""
        self.buy_levels = []
        self.sell_levels = []
        self.triggered = {}
        
        # 买入网格（低价）
        for i in range(1, self.grid_num + 1):
            level = self.base_price * (1 - self.grid_spread * i)
            self.buy_levels.append(level)
            self.triggered[level] = False
        
        # 卖出网格（高价）
        for i in range(1, self.grid_num + 1):
            level = self.base_price * (1 + self.grid_spread * i)
            self.sell_levels.append(level)
            self.triggered[level] = False
        
        self.buy_levels.sort(reverse=True)
        self.sell_levels.sort()
        
        print(f"[网格初始化] 基准: {self.base_price:.2f} | 买入:{self.buy_levels[-1]:.2f}~{self.buy_levels[0]:.2f} | 卖出:{self.sell_levels[0]:.2f}~{self.sell_levels[-1]:.2f}\n")
    
    def check_grid_triggers(self):
        """检查网格触发"""
        # 检查买入网格
        for level in self.buy_levels:
            if self.triggered[level]:
                continue
            
            if self.current_price <= level:
                self.trigger_buy(level)
                break
        
        # 检查卖出网格
        for level in self.sell_levels:
            if self.triggered[level]:
                continue
            
            if self.current_price >= level:
                self.trigger_sell(level)
                break
        
        # 重置触发状态
        for level in self.buy_levels:
            if self.triggered[level] and self.current_price > level * 1.002:
                self.triggered[level] = False
        
        for level in self.sell_levels:
            if self.triggered[level] and self.current_price < level * 0.998:
                self.triggered[level] = False
    
    def trigger_buy(self, level: float):
        """触发买入"""
        self.triggered[level] = True
        
        if self.is_swap:
            # 合约：计算张数（1张=0.01BTC=0.01*价格 USDT）
            contracts = int(self.order_amount / (self.current_price * 0.01))
            if contracts < 1:
                contracts = 1
            
            # print(f"\n[触发] 买入开多 {contracts}张 @ {self.current_price:.2f}")
            
            self.send_order("buy", contracts)
        else:
            # 现货：计算BTC数量
            quantity = self.order_amount / self.current_price
            
            # print(f"\n[触发] 买入 {quantity:.6f}BTC @ {self.current_price:.2f}")
            
            self.send_order("buy", quantity)
    
    def trigger_sell(self, level: float):
        """触发卖出"""
        self.triggered[level] = True
        
        if self.is_swap:
            # 合约：计算张数
            contracts = int(self.order_amount / (self.current_price * 0.01))
            if contracts < 1:
                contracts = 1
            
            # print(f"\n[触发] 卖出开空 {contracts}张 @ {self.current_price:.2f}")
            
            self.send_order("sell", contracts)
        else:
            # 现货：计算BTC数量
            quantity = self.order_amount / self.current_price
            
            # print(f"\n[触发] 卖出 {quantity:.6f}BTC @ {self.current_price:.2f}")
            
            self.send_order("sell", quantity)
    
    def on_trade(self, trade: dict):
        """处理行情推送"""
        # 过滤只处理自己关注的交易对
        symbol = trade.get("symbol", "")
        if symbol != self.symbol:
            return
        
        # 提取价格
        price = trade.get("price", 0)
        if price <= 0:
            return
        
        self.current_price = price
        
        # 初始化网格
        if self.base_price == 0:
            self.base_price = price
            self.init_grids()
            return
        
        # 检查触发
        self.check_grid_triggers()
    
    def on_report(self, report: dict):
        """处理订单回报"""
        report_type = report.get("type", "")
        status = report.get("status", "")
        
        # 处理账户注册回报
        if report_type == "register_report":
            if status == "registered":
                self.account_registered = True
                print(f"\n[账户注册] ✓ 注册成功！")
            else:
                print(f"\n[账户注册] ✗ 注册失败: {report.get('error_msg', '')}")
            return
        
        # 处理账户注销回报
        if report_type == "unregister_report":
            if status == "unregistered":
                self.account_registered = False
                print(f"\n[账户注销] ✓ 已注销")
            return
        
        # 处理订单回报
        if status == "filled":
            side = report.get("side", "")
            if side == "buy":
                self.buy_count += 1
            elif side == "sell":
                self.sell_count += 1
    
    def run(self):
        """主循环"""
        if not self.connect():
            return
        
        # 注册账户
        if self.api_key and self.secret_key and self.passphrase:
            self.register_account()
            # 等待注册回报
            time.sleep(0.5)
            # 处理注册回报
            for _ in range(10):
                report = self.recv_report()
                if report and report.get("type") == "register_report":
                    break
                time.sleep(0.1)
        else:
            print("[账户] 未提供账户信息，将使用服务器默认账户")
        
        # 订阅行情
        print(f"\n[订阅] 正在订阅 {self.symbol} 行情...")
        self.subscribe_trades(self.symbol)
        time.sleep(1)  # 等待订阅生效
        
        # 信号处理
        def signal_handler(signum, frame):
            print("\n[信号] 收到停止信号...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print("\n策略运行中... 等待行情数据 (按 Ctrl+C 停止)\n")
        self.start_time = time.time()
        
        try:
            while self.running:
                # 接收行情
                trade = self.recv_trade()
                if trade:
                    self.on_trade(trade)
                
                # 接收回报
                report = self.recv_report()
                if report:
                    self.on_report(report)
                
                # 短暂休眠
                time.sleep(0.0001)
        
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
        
        print("\n" + "=" * 70)
        print("              策略运行总结")
        print("=" * 70)
        print(f"  运行时间:     {elapsed:.1f} 秒")
        print(f"  接收行情:     {self.trade_count} 条")
        print(f"  发送订单:     {self.order_count} 个")
        print(f"  收到回报:     {self.report_count} 个")
        print(f"  买入成交:     {self.buy_count} 笔")
        print(f"  卖出成交:     {self.sell_count} 笔")
        if elapsed > 0:
            print(f"  行情速率:     {self.trade_count / elapsed:.1f} 条/秒")
        print("=" * 70)


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='独立网格交易策略')
    parser.add_argument('--strategy-id', type=str, default='grid_standalone',
                       help='策略ID')
    parser.add_argument('--symbol', type=str, default='BTC-USDT-SWAP',
                       help='交易对 (默认: BTC-USDT-SWAP 合约)')
    parser.add_argument('--grid-num', type=int, default=20,
                       help='单边网格数量')
    parser.add_argument('--grid-spread', type=float, default=0.001,
                       help='网格间距 (0.001 = 0.1%%)')
    parser.add_argument('--order-amount', type=float, default=100.0,
                       help='单次下单金额 USDT')
    
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
    
    # 确定是否使用模拟盘
    is_testnet = not args.live
    
    # 创建策略
    strategy = GridStrategy(
        strategy_id=args.strategy_id,
        symbol=args.symbol,
        grid_num=args.grid_num,
        grid_spread=args.grid_spread,
        order_amount=args.order_amount,
        api_key=args.api_key,
        secret_key=args.secret_key,
        passphrase=args.passphrase,
        is_testnet=is_testnet
    )
    
    # 运行
    strategy.run()


if __name__ == "__main__":
    main()

