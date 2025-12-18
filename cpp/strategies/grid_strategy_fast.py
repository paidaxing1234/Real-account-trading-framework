#!/usr/bin/env python3
"""
超高频网格交易策略 (ZMQ版本)

特点：
- 使用ZMQ直接通信，延迟更低
- 简化网格逻辑，响应速度更快
- 适合模拟盘快速测试
- 交易频率可达毫秒级

策略类型：
- 固定网格：预设价格网格，触发即交易
- 动态调整：根据波动率自动调整网格间距

使用方法:
    python3 grid_strategy_fast.py --grid-num 20 --grid-spread 0.001 --fast-mode

@author Sequence Team  
@date 2025-12
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

# 导入ZMQ客户端
from zmq_strategy_client import ZmqStrategyClient, IpcAddresses, CpuConfig, set_cpu_affinity


class FastGridStrategy:
    """
    超高频网格交易策略
    
    核心特点：
    1. 极简逻辑 - 减少计算开销
    2. 快速判断 - 毫秒级响应
    3. 批量下单 - 提高吞吐量
    """
    
    def __init__(self,
                 client: ZmqStrategyClient,
                 symbol: str = "BTC-USDT",
                 grid_num: int = 20,
                 grid_spread: float = 0.001,
                 order_amount: float = 3.0,
                 fast_mode: bool = True):
        """
        初始化超高频网格策略
        
        Args:
            client: ZMQ策略客户端
            symbol: 交易对
            grid_num: 单边网格数量
            grid_spread: 网格间距 (0.001 = 0.1%)
            order_amount: 单次下单金额（USDT）
            fast_mode: 快速模式（减少日志输出）
        """
        self.client = client
        self.symbol = symbol
        self.grid_num = grid_num
        self.grid_spread = grid_spread
        self.order_amount = order_amount
        self.fast_mode = fast_mode
        
        # 价格追踪
        self.current_price = 0.0
        self.base_price = 0.0
        self.price_history = deque(maxlen=100)  # 保留最近100个价格
        
        # 网格
        self.buy_levels: List[float] = []
        self.sell_levels: List[float] = []
        self.triggered: Dict[float, bool] = {}
        
        # 订单管理（简化）
        self.pending_buy_orders = 0
        self.pending_sell_orders = 0
        self.max_pending_per_side = 5  # 每侧最多挂单数
        
        # 统计
        self.buy_executions = 0
        self.sell_executions = 0
        self.total_volume = 0.0
        self.start_time = time.time()
        self.last_print_time = 0
        
        # 性能追踪
        self.process_times = deque(maxlen=1000)
        
        print("=" * 70)
        print("              超高频网格交易策略 (ZMQ)")
        print("=" * 70)
        print(f"  交易对:         {self.symbol}")
        print(f"  网格数量:       {self.grid_num} x 2 = {self.grid_num * 2} 个网格")
        print(f"  网格间距:       {self.grid_spread * 100:.3f}%")
        print(f"  单次金额:       {self.order_amount} USDT")
        print(f"  快速模式:       {'启用' if self.fast_mode else '禁用'}")
        print("=" * 70)
        print()
    
    def on_trade(self, trade: dict):
        """处理行情数据 - 核心逻辑"""
        start_ns = time.time_ns()
        
        # 更新价格
        self.current_price = trade.get("price", 0)
        if self.current_price <= 0:
            return
        
        self.price_history.append(self.current_price)
        
        # 首次初始化网格
        if self.base_price == 0:
            self.base_price = self.current_price
            self._setup_grids()
            if not self.fast_mode:
                print(f"[初始化] 基准价格: {self.base_price:.2f}")
                self._print_grids()
            return
        
        # 快速检查网格触发（核心逻辑）
        self._fast_check_grids()
        
        # 记录处理时间
        elapsed_ns = time.time_ns() - start_ns
        self.process_times.append(elapsed_ns)
        
        # 定期打印状态（快速模式下减少输出）
        if not self.fast_mode:
            current_time = time.time()
            if current_time - self.last_print_time >= 3:
                self.last_print_time = current_time
                self._print_status()
    
    def on_report(self, report: dict):
        """处理订单回报"""
        status = report.get("status", "")
        side = report.get("side", "")
        
        # 更新挂单计数
        if status in ["filled", "rejected", "cancelled"]:
            if side == "buy":
                self.pending_buy_orders = max(0, self.pending_buy_orders - 1)
            elif side == "sell":
                self.pending_sell_orders = max(0, self.pending_sell_orders - 1)
        
        # 成交统计
        if status == "filled":
            if side == "buy":
                self.buy_executions += 1
            elif side == "sell":
                self.sell_executions += 1
            
            filled_qty = report.get("filled_quantity", 0)
            filled_price = report.get("filled_price", 0)
            self.total_volume += filled_qty * filled_price
            
            if not self.fast_mode:
                print(f"[成交] {side.upper()} @ {filled_price:.2f} | "
                      f"数量: {filled_qty:.6f}")
        
        elif status == "rejected":
            error_msg = report.get("error_msg", "")
            if not self.fast_mode:
                print(f"[拒单] {side} | {error_msg}")
    
    def _setup_grids(self):
        """设置网格"""
        self.buy_levels = []
        self.sell_levels = []
        self.triggered = {}
        
        # 买入网格（基准价下方）
        for i in range(1, self.grid_num + 1):
            level = self.base_price * (1 - self.grid_spread * i)
            self.buy_levels.append(level)
            self.triggered[level] = False
        
        # 卖出网格（基准价上方）
        for i in range(1, self.grid_num + 1):
            level = self.base_price * (1 + self.grid_spread * i)
            self.sell_levels.append(level)
            self.triggered[level] = False
        
        self.buy_levels.sort(reverse=True)
        self.sell_levels.sort()
    
    def _fast_check_grids(self):
        """快速检查网格触发（优化版）"""
        price = self.current_price
        
        # 检查买入网格（价格下跌）
        if self.pending_buy_orders < self.max_pending_per_side:
            for level in self.buy_levels:
                if self.triggered[level]:
                    continue
                
                if price <= level:
                    # 触发买入
                    self._fast_buy(level)
                    break  # 一次只触发一个
        
        # 检查卖出网格（价格上涨）
        if self.pending_sell_orders < self.max_pending_per_side:
            for level in self.sell_levels:
                if self.triggered[level]:
                    continue
                
                if price >= level:
                    # 触发卖出
                    self._fast_sell(level)
                    break  # 一次只触发一个
        
        # 自动重置已触发的网格（价格回归）
        self._auto_reset_triggers()
    
    def _fast_buy(self, level: float):
        """快速买入"""
        self.triggered[level] = True
        self.pending_buy_orders += 1
        
        # 下市价单
        order_id = self.client.send_order(
            symbol=self.symbol,
            side="buy",
            order_type="market",
            quantity=self.order_amount,
            td_mode="cash",
            tgt_ccy="quote_ccy"
        )
        
        if not self.fast_mode:
            print(f"[BUY]  网格: {level:.2f} | 市价: {self.current_price:.2f}")
    
    def _fast_sell(self, level: float):
        """快速卖出"""
        self.triggered[level] = True
        self.pending_sell_orders += 1
        
        # 计算数量
        quantity = self.order_amount / self.current_price
        
        # 下市价单
        order_id = self.client.send_order(
            symbol=self.symbol,
            side="sell",
            order_type="market",
            quantity=quantity,
            td_mode="cash",
            tgt_ccy="base_ccy"
        )
        
        if not self.fast_mode:
            print(f"[SELL] 网格: {level:.2f} | 市价: {self.current_price:.2f}")
    
    def _auto_reset_triggers(self):
        """自动重置已触发的网格"""
        # 买入网格重置：当价格回升到网格上方
        for level in self.buy_levels:
            if self.triggered[level] and self.current_price > level * 1.001:
                self.triggered[level] = False
        
        # 卖出网格重置：当价格回落到网格下方
        for level in self.sell_levels:
            if self.triggered[level] and self.current_price < level * 0.999:
                self.triggered[level] = False
    
    def _print_grids(self):
        """打印网格信息"""
        print("\n" + "-" * 70)
        print("网格配置:")
        print(f"  卖出区间: {self.sell_levels[0]:.2f} ~ {self.sell_levels[-1]:.2f}")
        print(f"  基准价格: {self.base_price:.2f}")
        print(f"  买入区间: {self.buy_levels[-1]:.2f} ~ {self.buy_levels[0]:.2f}")
        print("-" * 70)
    
    def _print_status(self):
        """打印运行状态"""
        elapsed = time.time() - self.start_time
        trades_per_sec = self.client.trade_count / elapsed if elapsed > 0 else 0
        
        # 计算平均处理时间
        avg_process_ns = sum(self.process_times) / len(self.process_times) if self.process_times else 0
        avg_process_us = avg_process_ns / 1000
        
        print(f"\n[状态] 价格: {self.current_price:.2f} | "
              f"买: {self.buy_executions} | 卖: {self.sell_executions} | "
              f"挂单: B{self.pending_buy_orders}/S{self.pending_sell_orders}")
        print(f"       行情: {self.client.trade_count} ({trades_per_sec:.1f}/s) | "
              f"处理: {avg_process_us:.2f}μs | "
              f"成交量: {self.total_volume:.2f} USDT")
    
    def print_summary(self):
        """打印策略总结"""
        elapsed = time.time() - self.start_time
        
        print("\n" + "=" * 70)
        print("              策略运行总结")
        print("=" * 70)
        print(f"  运行时间:       {elapsed:.1f} 秒")
        print(f"  接收行情:       {self.client.trade_count} 条 ({self.client.trade_count/elapsed:.1f}/s)")
        print(f"  买入成交:       {self.buy_executions} 笔")
        print(f"  卖出成交:       {self.sell_executions} 笔")
        print(f"  总成交量:       {self.total_volume:.2f} USDT")
        print(f"  发送订单:       {self.client.order_count} 个")
        print(f"  收到回报:       {self.client.report_count} 个")
        
        if self.process_times:
            avg_process_ns = sum(self.process_times) / len(self.process_times)
            min_process_ns = min(self.process_times)
            max_process_ns = max(self.process_times)
            
            print(f"\n  处理延迟 (微秒):")
            print(f"    平均:         {avg_process_ns/1000:.2f} μs")
            print(f"    最小:         {min_process_ns/1000:.2f} μs")
            print(f"    最大:         {max_process_ns/1000:.2f} μs")
        
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='超高频网格交易策略 (ZMQ)')
    parser.add_argument('--symbol', type=str, default='BTC-USDT',
                       help='交易对')
    parser.add_argument('--grid-num', type=int, default=20,
                       help='单边网格数量 (默认: 20)')
    parser.add_argument('--grid-spread', type=float, default=0.001,
                       help='网格间距 (默认: 0.001 即 0.1%%)')
    parser.add_argument('--order-amount', type=float, default=3.0,
                       help='单次下单金额 (默认: 3.0 USDT)')
    parser.add_argument('--fast-mode', action='store_true',
                       help='快速模式：减少日志输出')
    parser.add_argument('--cpu', type=int, default=-1,
                       help='绑定CPU核心')
    parser.add_argument('--strategy-index', type=int, default=0,
                       help='策略编号')
    
    # API认证参数
    parser.add_argument('--api-key', type=str, default='',
                       help='OKX API Key')
    parser.add_argument('--secret-key', type=str, default='',
                       help='OKX Secret Key')
    parser.add_argument('--passphrase', type=str, default='',
                       help='OKX Passphrase')
    parser.add_argument('--testnet', action='store_true', default=True,
                       help='使用模拟盘 (默认: True)')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("          超高频网格交易策略启动")
    print("=" * 70)
    print()
    
    # 检查API凭证
    if not args.api_key or not args.secret_key or not args.passphrase:
        print("[警告] 未提供API凭证，使用默认模拟盘账户")
        print()
        args.api_key = "5dee6507-e02d-4bfd-9558-d81783d84cb7"
        args.secret_key = "9B0E54A9843943331EFD0C40547179C8"
        args.passphrase = "Wbl20041209.."
        args.testnet = True
    
    print(f"[配置] 交易模式: {'模拟盘' if args.testnet else '实盘'}")
    print(f"[配置] API Key: {args.api_key[:8]}...")
    print()
    
    # CPU绑定
    if args.cpu >= 0:
        set_cpu_affinity(args.cpu)
    else:
        cpu_id = CpuConfig.get_strategy_cpu(args.strategy_index)
        set_cpu_affinity(cpu_id)
    
    # 创建ZMQ客户端
    strategy_id = f"grid_fast_{args.strategy_index}"
    client = ZmqStrategyClient(strategy_id=strategy_id)
    
    if not client.connect():
        print("[错误] 无法连接到服务器")
        sys.exit(1)
    
    # 发送认证请求（可选，用于 trading_server_full）
    print("[认证] 发送API凭证到服务器...")
    auth_msg = {
        "type": "auth_request",
        "strategy_id": strategy_id,
        "api_key": args.api_key,
        "secret_key": args.secret_key,
        "passphrase": args.passphrase,
        "is_testnet": args.testnet,
        "timestamp": int(time.time() * 1000)
    }
    
    try:
        client.order_push.send_string(json.dumps(auth_msg))
    except Exception as e:
        print(f"[警告] 发送认证请求失败: {e}")
        print("[信息] 将使用服务器默认账户")
        print()
    
    # 等待认证响应（3秒超时，超时则假设服务器不支持认证）
    print("[认证] 等待服务器响应（3秒）...")
    auth_success = False
    timeout = time.time() + 3  # 3秒超时
    
    while time.time() < timeout:
        report = client.recv_report()
        if report and report.get("type") == "auth_response":
            if report.get("success"):
                print("[认证] ✓ 认证成功")
                print()
                auth_success = True
                break
            else:
                error_msg = report.get("error_msg", "未知错误")
                print(f"[认证] ✗ 认证失败: {error_msg}")
                sys.exit(1)
        time.sleep(0.05)
    
    if not auth_success:
        print("[认证] ⚠ 服务器未响应认证请求")
        print("[信息] 可能是使用 trading_server (简化版)")
        print("[信息] 将使用服务器默认账户继续运行")
        print()
    
    # 创建策略
    strategy = FastGridStrategy(
        client=client,
        symbol=args.symbol,
        grid_num=args.grid_num,
        grid_spread=args.grid_spread,
        order_amount=args.order_amount,
        fast_mode=args.fast_mode
    )
    
    # 信号处理
    def signal_handler(signum, frame):
        print("\n[信号] 收到停止信号...")
        client.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("\n策略运行中... (按 Ctrl+C 停止)\n")
    
    # 主循环
    try:
        while client.running:
            # 接收行情
            trade = client.recv_trade()
            if trade:
                strategy.on_trade(trade)
            
            # 接收回报
            report = client.recv_report()
            if report:
                strategy.on_report(report)
            
            # 极短休眠（高频模式）
            time.sleep(0.0001)  # 100微秒
    
    except Exception as e:
        print(f"\n[异常] {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        strategy.print_summary()
        client.disconnect()


if __name__ == "__main__":
    main()

