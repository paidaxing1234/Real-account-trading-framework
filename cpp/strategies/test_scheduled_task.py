#!/usr/bin/env python3
"""
定时任务功能测试程序（带下单）

测试内容：
- 1秒执行一次的任务 (task_1s): 买入 1 张 BTC 合约
- 1分钟执行一次的任务 (task_1m): 卖出 1 张 BTC 合约

注意：
- OKX 永续合约 BTC-USDT-SWAP 最小单位是 1 张 = 0.01 BTC
- 0.00001 BTC 不足 1 张，使用最小 1 张
- 0.0006 BTC = 0.06 张，使用最小 1 张

运行方式：
    python test_scheduled_task.py

编译依赖：
    cd cpp/build && cmake .. && make strategy_base
"""

import sys
import signal
import time

try:
    from strategy_base import StrategyBase, ScheduledTask
except ImportError:
    print("错误: 未找到 strategy_base 模块，请先编译:")
    print("  cd cpp/build && cmake .. && make strategy_base")
    sys.exit(1)


# ========== 配置 API 密钥 ==========
API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
PASSPHRASE = "Sequence2025"
IS_TESTNET = True  # True=模拟盘, False=实盘


class ScheduledTaskTestStrategy(StrategyBase):
    """定时任务测试策略（带下单）"""
    
    def __init__(self):
        super().__init__("scheduled_task_test", max_kline_bars=100)
        
        # 交易对
        self.symbol = "BTC-USDT-SWAP"
        
        # 计数器
        self.task_1s_count = 0
        self.task_1m_count = 0
        
        # 下单统计
        self.buy_order_count = 0
        self.sell_order_count = 0
        
        # 开始时间
        self.start_time = None
        
        # 账户是否注册成功
        self.account_ready = False
    
    def on_init(self):
        """初始化"""
        self.start_time = time.time()
        
        print("=" * 60)
        print("       定时任务下单测试程序")
        print("=" * 60)
        print()
        print(f"交易对: {self.symbol}")
        print(f"模式: {'模拟盘' if IS_TESTNET else '实盘'}")
        print()
        print("任务说明:")
        print("  - task_1s: 每 1 秒买入 1 张")
        print("  - task_1m: 每 1 分钟卖出 1 张")
        print()
        print("按 Ctrl+C 停止测试")
        print()
        print("-" * 60)
        
        # 1. 注册账户
        print("[初始化] 正在注册账户...")
        self.register_account(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            passphrase=PASSPHRASE,
            is_testnet=IS_TESTNET
        )
        
        # 等待账户注册完成
        time.sleep(2)
        
        # 2. 注册定时任务
        # 每 1 秒执行买入
        self.schedule_task("task_1s", "1s")
        
        # 每 1 分钟执行卖出
        self.schedule_task("task_1m", "1m")
        
        print("[初始化] 定时任务已注册")
        print("-" * 60)
    
    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.account_ready = True
            print(f"[账户] ✓ 注册成功，USDT余额: {self.get_usdt_available():.2f}")
        else:
            print(f"[账户] ✗ 注册失败: {error_msg}")
    
    def on_scheduled_task(self, task_name: str):
        """定时任务回调"""
        elapsed = time.time() - self.start_time
        
        if task_name == "task_1s":
            self.task_1s_count += 1
            self.do_buy_order(elapsed)
            
        elif task_name == "task_1m":
            self.task_1m_count += 1
            self.do_sell_order(elapsed)
    
    def do_buy_order(self, elapsed: float):
        """执行买入（每1秒）"""
        if not self.account_ready:
            print(f"[{elapsed:6.1f}s] task_1s | 跳过: 账户未就绪")
            return
        
        # 买入 1 张（0.01 BTC）
        order_id = self.send_swap_market_order(
            symbol=self.symbol,
            side="buy",
            quantity=1,
            pos_side="net"
        )
        
        self.buy_order_count += 1
        print(f"[{elapsed:6.1f}s] task_1s | 买入 1 张 | 订单: {order_id} | 总买入: {self.buy_order_count}")
    
    def do_sell_order(self, elapsed: float):
        """执行卖出（每1分钟）"""
        if not self.account_ready:
            print(f"[{elapsed:6.1f}s] task_1m | 跳过: 账户未就绪")
            return
        
        # 卖出 1 张（0.01 BTC）
        order_id = self.send_swap_market_order(
            symbol=self.symbol,
            side="sell",
            quantity=1,
            pos_side="net"
        )
        
        self.sell_order_count += 1
        print(f"[{elapsed:6.1f}s] task_1m | 卖出 1 张 | 订单: {order_id} | 总卖出: {self.sell_order_count}")
        print("-" * 60)
    
    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        side = report.get("side", "")
        filled_qty = report.get("filled_quantity", 0)
        filled_price = report.get("filled_price", 0)
        error_msg = report.get("error_msg", "")
        
        if status == "filled":
            print(f"  └─ [成交] {side} {filled_qty}张 @ {filled_price}")
        elif status == "rejected":
            print(f"  └─ [拒绝] {side} 原因: {error_msg}")
    
    def on_stop(self):
        """停止 - 打印统计"""
        elapsed = time.time() - self.start_time
        
        # 取消定时任务
        self.unschedule_task("task_1s")
        self.unschedule_task("task_1m")
        
        print()
        print("=" * 60)
        print("                测试结果")
        print("=" * 60)
        print(f"  运行时间: {elapsed:.1f} 秒")
        print()
        print(f"  task_1s (1秒/次 买入):")
        print(f"    - 执行次数: {self.task_1s_count}")
        print(f"    - 买入订单: {self.buy_order_count}")
        print()
        print(f"  task_1m (1分钟/次 卖出):")
        print(f"    - 执行次数: {self.task_1m_count}")
        print(f"    - 卖出订单: {self.sell_order_count}")
        print()
        
        # 打印持仓
        print("  当前持仓:")
        positions = self.get_active_positions()
        if positions:
            for pos in positions:
                print(f"    - {pos.symbol}: {pos.quantity}张 盈亏:{pos.unrealized_pnl:.2f}")
        else:
            print("    - 无持仓")
        
        print()
        print(f"  账户余额: {self.get_usdt_available():.2f} USDT")
        print("=" * 60)


def main():
    strategy = ScheduledTaskTestStrategy()
    
    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())
    
    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()

