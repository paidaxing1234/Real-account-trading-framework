#!/usr/bin/env python3
"""
Sequence 策略模板代码

本模板展示如何使用 strategy_client 库实现策略，包括：
- 接收行情数据（trades）
- 下单（市价单/限价单）
- 撤单
- 接收订单回报
- 查询账户/持仓信息

使用方法:
    1. 启动实盘服务器:
       ./trading_server_live
    
    2. 运行策略:
       python3 strategy_template.py

@author Sequence Team
@date 2025-12
"""

import time
import signal
import sys
from datetime import datetime
from typing import Dict, Optional

# 导入策略客户端库
from strategy_client import (
    StrategyClient, 
    BaseStrategy,
    TradeData, 
    OrderReport,
    OrderRequest,
    run_strategy
)


# ============================================================
# 策略模板 1: 使用客户端类（灵活方式）
# ============================================================

def example_using_client():
    """
    使用 StrategyClient 类的示例
    
    适合需要完全控制循环的场景
    """
    print("=" * 60)
    print("  策略模板 - 使用 StrategyClient")
    print("=" * 60)
    
    # 1. 创建客户端
    client = StrategyClient(strategy_id="template_demo")
    
    # 2. 连接到实盘服务器
    if not client.connect():
        print("[错误] 无法连接到实盘服务器")
        print("       请确保 trading_server_live 已启动")
        return
    
    print("[连接] 已连接到实盘服务器")
    print()
    
    # 3. 信号处理
    running = True
    def signal_handler(signum, frame):
        nonlocal running
        print("\n[信号] 收到停止信号...")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 4. 变量
    trade_count = 0
    last_price = 0.0
    last_order_time = 0
    pending_orders: Dict[str, dict] = {}  # 跟踪未完成订单
    
    # 5. 主循环
    print("[策略] 开始运行...")
    print("       按 Ctrl+C 停止")
    print()
    
    while running:
        # ========================================
        # 接收行情数据
        # ========================================
        trade = client.recv_trade()
        if trade:
            trade_count += 1
            last_price = trade.price
            
            # 每 100 条打印一次
            if trade_count % 100 == 0:
                print(f"[行情] #{trade_count} | {trade.symbol} | "
                      f"{trade.side} | 价格: {trade.price:.2f} | "
                      f"数量: {trade.quantity}")
        
        # ========================================
        # 接收订单回报
        # ========================================
        report = client.recv_report()
        if report:
            print(f"\n[回报] 订单状态: {report.status}")
            print(f"       客户端ID: {report.client_order_id}")
            print(f"       交易所ID: {report.exchange_order_id}")
            
            if report.is_rejected():
                print(f"       错误: {report.error_msg}")
            
            # 从 pending_orders 中移除
            if report.client_order_id in pending_orders:
                del pending_orders[report.client_order_id]
            
            print()
        
        # ========================================
        # 策略逻辑：每 30 秒下一笔测试订单
        # ========================================
        current_time = time.time()
        if current_time - last_order_time >= 30:
            last_order_time = current_time
            
            print(f"\n{'*' * 50}")
            print(f"[下单] {datetime.now().strftime('%H:%M:%S')}")
            
            # 市价买入 1 USDT 的 BTC
            order_id = client.buy_market("BTC-USDT", 1)
            
            if order_id:
                print(f"       订单已发送: {order_id}")
                pending_orders[order_id] = {
                    "symbol": "BTC-USDT",
                    "side": "buy",
                    "time": current_time
                }
            else:
                print("       ✗ 发送失败")
            
            print(f"{'*' * 50}\n")
        
        # 短暂休眠
        time.sleep(0.001)
    
    # 6. 停止
    print()
    print("=" * 60)
    print("  策略停止")
    print("=" * 60)
    print(f"  收到行情: {trade_count} 条")
    print(f"  发送订单: {client.order_count} 笔")
    print(f"  收到回报: {client.report_count} 个")
    print("=" * 60)
    
    client.disconnect()


# ============================================================
# 策略模板 2: 继承 BaseStrategy（推荐方式）
# ============================================================

class MyStrategy(BaseStrategy):
    """
    自定义策略示例
    
    继承 BaseStrategy 并实现 on_trade 方法
    """
    
    def __init__(self):
        super().__init__(strategy_id="my_strategy")
        
        # 策略参数
        self.trade_count = 0
        self.last_price = 0.0
        self.last_order_time = 0
        self.order_interval = 60  # 下单间隔（秒）
        
        # 持仓跟踪
        self.position = {"BTC-USDT": 0.0}
    
    def on_init(self):
        """策略初始化"""
        self.log("策略初始化完成")
    
    def on_start(self):
        """策略启动"""
        self.log(f"策略启动 | 下单间隔: {self.order_interval}秒")
    
    def on_stop(self):
        """策略停止"""
        self.log(f"策略停止 | 总交易: {self.trade_count}条")
    
    def on_trade(self, trade: TradeData):
        """
        处理行情数据
        
        这是策略的核心逻辑所在！
        """
        self.trade_count += 1
        self.last_price = trade.price
        
        # 打印行情（每 100 条）
        if self.trade_count % 100 == 0:
            self.log(f"[行情] {trade.symbol} | 价格: {trade.price:.2f}")
        
        # ========================================
        # 策略逻辑示例：定时下单
        # ========================================
        current_time = time.time()
        if current_time - self.last_order_time >= self.order_interval:
            self.last_order_time = current_time
            self._place_test_order()
    
    def on_report(self, report: OrderReport):
        """处理订单回报"""
        self.log(f"[回报] {report.status} | ID: {report.exchange_order_id}")
        
        # 更新持仓
        if report.is_filled():
            symbol = report.symbol
            qty = report.filled_quantity
            
            # 简化处理：买入增加持仓，卖出减少持仓
            if report.status == "filled":
                self.log(f"[成交] 数量: {qty} | 价格: {report.filled_price}")
    
    def _place_test_order(self):
        """下测试订单"""
        self.log(f"[下单] {datetime.now().strftime('%H:%M:%S')}")
        
        # 市价买入 1 USDT
        order_id = self.buy_market("BTC-USDT", 1)
        
        if order_id:
            self.log(f"       订单ID: {order_id}")
        else:
            self.log("       ✗ 发送失败")


# ============================================================
# 策略模板 3: 完整功能演示
# ============================================================

class FullFeaturedStrategy(BaseStrategy):
    """
    完整功能策略演示
    
    展示所有可用接口：
    - 市价单/限价单
    - 撤单
    - 批量下单
    - 查询账户/持仓
    """
    
    def __init__(self):
        super().__init__(strategy_id="full_demo")
        self.demo_step = 0
        self.last_demo_time = 0
    
    def on_start(self):
        self.log("完整功能演示策略启动")
        self.log("每 30 秒演示一个功能")
    
    def on_trade(self, trade: TradeData):
        """定时演示各种功能"""
        current_time = time.time()
        
        if current_time - self.last_demo_time >= 30:
            self.last_demo_time = current_time
            self._run_demo_step()
    
    def on_report(self, report: OrderReport):
        """处理订单回报"""
        status_emoji = "✓" if report.is_success() else "✗"
        self.log(f"[回报] {status_emoji} {report.status} | "
                 f"ID: {report.exchange_order_id or report.client_order_id}")
        
        if report.error_msg:
            self.log(f"       错误: {report.error_msg}")
    
    def _run_demo_step(self):
        """执行演示步骤"""
        self.demo_step += 1
        
        print()
        print("=" * 50)
        print(f"  演示步骤 {self.demo_step}")
        print("=" * 50)
        
        if self.demo_step == 1:
            # 演示 1: 市价买入
            self.log("[演示] 市价买入 1 USDT 的 BTC")
            order_id = self.buy_market("BTC-USDT", 1)
            self.log(f"       订单ID: {order_id}")
        
        elif self.demo_step == 2:
            # 演示 2: 限价买入
            self.log("[演示] 限价买入 0.0001 BTC @ 50000")
            order_id = self.buy_limit("BTC-USDT", 0.0001, 50000)
            self.log(f"       订单ID: {order_id}")
            # 保存订单ID用于后续撤单
            self._pending_limit_order = order_id
        
        elif self.demo_step == 3:
            # 演示 3: 撤单
            if hasattr(self, '_pending_limit_order'):
                self.log(f"[演示] 撤销订单: {self._pending_limit_order}")
                req_id = self.cancel_order("BTC-USDT", 
                                          client_order_id=self._pending_limit_order)
                self.log(f"       请求ID: {req_id}")
        
        elif self.demo_step == 4:
            # 演示 4: 查询账户（如果服务端支持）
            self.log("[演示] 查询账户余额")
            result = self.client.query_account("USDT")
            if result:
                self.log(f"       结果: {result}")
            else:
                self.log("       查询功能暂不可用")
        
        elif self.demo_step == 5:
            # 演示 5: 批量下单
            self.log("[演示] 批量下单（2个订单）")
            orders = [
                OrderRequest(
                    symbol="BTC-USDT",
                    side="buy",
                    order_type="limit",
                    quantity=0.0001,
                    price=50000,
                    td_mode="cash"
                ),
                OrderRequest(
                    symbol="BTC-USDT",
                    side="sell",
                    order_type="limit",
                    quantity=0.00001,
                    price=200000,
                    td_mode="cash"
                )
            ]
            batch_id = self.client.batch_orders(orders)
            self.log(f"       批量ID: {batch_id}")
        
        else:
            # 重置演示
            self.demo_step = 0
            self.log("[演示] 演示完成，将重新开始")
        
        print()


# ============================================================
# 主程序
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Sequence 策略模板')
    parser.add_argument('--mode', type=str, default='client',
                        choices=['client', 'strategy', 'full'],
                        help='运行模式: client=客户端方式, strategy=策略方式, full=完整演示')
    parser.add_argument('--interval', type=int, default=30,
                        help='下单间隔秒数 (默认: 30)')
    args = parser.parse_args()
    
    print()
    print("=" * 60)
    print("    Sequence 策略模板")
    print("=" * 60)
    print(f"  模式: {args.mode}")
    print(f"  下单间隔: {args.interval} 秒")
    print("=" * 60)
    print()
    
    if args.mode == 'client':
        # 使用客户端方式
        example_using_client()
    
    elif args.mode == 'strategy':
        # 使用策略基类方式
        strategy = MyStrategy()
        strategy.order_interval = args.interval
        run_strategy(strategy)
    
    elif args.mode == 'full':
        # 完整功能演示
        strategy = FullFeaturedStrategy()
        run_strategy(strategy)


if __name__ == "__main__":
    main()

