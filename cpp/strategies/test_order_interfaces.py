#!/usr/bin/env python3
"""
订单接口测试程序

测试内容：
1. 基础下单接口（市价、限价）
2. 带止盈止损的市价单
3. 带止盈止损的限价单
4. 高级订单类型（post_only, fok, ioc）
5. 批量下单

运行方式：
    python test_order_interfaces.py

编译依赖：
    cd cpp/build && cmake .. && make strategy_base
"""

import sys
import signal
import time

try:
    from strategy_base import StrategyBase
except ImportError:
    print("错误: 未找到 strategy_base 模块，请先编译:")
    print("  cd cpp/build && cmake .. && make strategy_base")
    sys.exit(1)


class OrderInterfaceTestStrategy(StrategyBase):
    """订单接口测试策略"""
    
    def __init__(self):
        super().__init__("order_test", max_kline_bars=100)
        # 注意: 本测试不使用定时任务，无需调用 _set_python_self(self)
        
        # 交易对
        self.symbol = "BTC-USDT-SWAP"

        # 状态：等待“账户就绪 + 价格就绪(收到至少1根K线)”后再开始测试
        self.account_ready = False
        self.price_ready = False
        self.last_price = None
        self.tests_started = False
        
        # 测试状态
        self.test_step = 0
        self.test_results = {
            "market_order": False,
            "limit_order": False,
            "market_order_with_tp_sl": False,
            "limit_order_with_tp_sl": False,
            "advanced_order": False,
            "batch_orders": False
        }
        
        # API密钥（请替换为您的密钥）
        self.api_key = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
        self.secret_key = "888CC77C745F1B49E75A992F38929992"
        self.passphrase = "Sequence2025."
        self.is_testnet = True  # True=模拟盘, False=实盘
    
    def on_init(self):
        """初始化"""
        print("=" * 60)
        print("       订单接口测试程序")
        print("=" * 60)
        print()
        print(f"交易对: {self.symbol}")
        print(f"模式: {'模拟盘' if self.is_testnet else '实盘'}")
        print()
        print("测试内容:")
        print("  1. 基础下单（市价、限价）")
        print("  2. 带止盈止损的市价单")
        print("  3. 带止盈止损的限价单")
        print("  4. 高级订单类型（post_only, fok, ioc）")
        print("  5. 批量下单")
        print()
        print("按 Ctrl+C 停止测试")
        print()
        print("-" * 60)
        
        # 注册账户
        print("[初始化] 正在注册账户...")
        self.register_account(
            api_key=self.api_key,
            secret_key=self.secret_key,
            passphrase=self.passphrase,
            is_testnet=self.is_testnet
        )
        
        # 订阅K线（用于获取当前价格）
        self.subscribe_kline(self.symbol, "1s")
        
        print("[初始化] 等待账户注册完成...")
        print("-" * 60)
    
    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.account_ready = True
            print(f"[账户] ✓ 注册成功，USDT余额: {self.get_usdt_available():.2f}")
            print()
            print("=" * 60)
            print("开始测试订单接口...")
            print("=" * 60)
            print()
            # 注意：不要在这里立即测试。等收到至少1根K线（price_ready=True）再开始。
            self.maybe_start_tests()
        else:
            print(f"[账户] ✗ 注册失败: {error_msg}")
            print("请检查API密钥是否正确")
    
    def on_kline(self, symbol: str, interval: str, bar):
        """K线回调 - 用于获取当前价格"""
        if symbol != self.symbol:
            return
        if interval != "1s":
            return

        # 记录最新价格（用于后续测试定价）
        self.last_price = float(bar.close)
        if not self.price_ready:
            self.price_ready = True
            self.maybe_start_tests()

    def maybe_start_tests(self):
        """仅在账户就绪 + 价格就绪后启动一次测试"""
        if self.tests_started:
            return
        if not self.account_ready:
            return
        if not self.price_ready:
            return

        self.tests_started = True
        # 稍等一小会，确保 KlineBuffer 已写入（避免竞态）
        time.sleep(0.2)
        self.run_tests()
    
    def run_tests(self):
        """依次执行所有测试"""
        # 测试1: 基础下单
        self.test_basic_orders()
        time.sleep(2)
        
        # 测试2: 带止盈止损的订单
        self.test_orders_with_tp_sl()
        time.sleep(2)
        
        # 测试3: 高级订单类型
        self.test_advanced_orders()
        time.sleep(2)
        
        # 测试4: 批量下单
        self.test_batch_orders()
        time.sleep(2)
        
        # 打印测试总结
        self.print_test_summary()
    
    def test_basic_orders(self):
        """测试1: 基础下单接口"""
        print("\n" + "=" * 60)
        print("测试1: 基础下单接口")
        print("=" * 60)

        # 获取当前价格：优先使用 on_kline 保存的 last_price，避免 get_last_kline 的竞态
        current_price = self.last_price
        if current_price is None:
            # 兜底：最多重试 2 秒，等待缓存落地
            deadline = time.time() + 2.0
            while time.time() < deadline:
                last_kline = self.get_last_kline(self.symbol, "1s")
                if last_kline is not None:
                    current_price = float(last_kline.close)
                    break
                time.sleep(0.1)

        if current_price is None:
            print("⚠️  无法获取当前价格（尚未收到1s K线），跳过测试")
            return

        print(f"当前价格: {current_price:.2f}")
        print()
        
        # 1.1 市价买入
        print("[1.1] 测试市价买入订单...")
        order_id = self.send_swap_market_order(self.symbol, "buy", 1, "net")
        if order_id:
            print(f"  ✓ 订单ID: {order_id}")
            self.test_results["market_order"] = True
        else:
            print("  ✗ 下单失败")
        time.sleep(1)
        
        # 1.2 限价卖出（价格低于当前价）
        print("[1.2] 测试限价卖出订单...")
        limit_price = current_price * 1.05  # 高于当前价5%
        order_id = self.send_swap_limit_order(self.symbol, "sell", 1, limit_price, "net")
        if order_id:
            print(f"  ✓ 订单ID: {order_id} | 价格: {limit_price:.2f}")
            self.test_results["limit_order"] = True
        else:
            print("  ✗ 下单失败")
        print()
    
    def test_orders_with_tp_sl(self):
        """测试2: 带止盈止损的订单"""
        print("\n" + "=" * 60)
        print("测试2: 带止盈止损的订单")
        print("=" * 60)
        
        current_price = self.last_price
        if current_price is None:
            last_kline = self.get_last_kline(self.symbol, "1s")
            if last_kline is None:
                print("⚠️  无法获取当前价格，跳过测试")
                return
            current_price = float(last_kline.close)
        print(f"当前价格: {current_price:.2f}")
        print()
        
        # 2.1 市价买入（带止盈止损）
        print("[2.1] 测试市价买入订单（带止盈止损）...")
        tp_trigger = str(current_price * 1.02)  # 止盈触发价：当前价+2%
        tp_ord = "-1"  # 市价止盈
        sl_trigger = str(current_price * 0.98)  # 止损触发价：当前价-2%
        sl_ord = "-1"  # 市价止损
        
        order_id = self.send_swap_market_order_with_tp_sl(
            self.symbol, "buy", 1,
            tp_trigger_px=tp_trigger,
            tp_ord_px=tp_ord,
            sl_trigger_px=sl_trigger,
            sl_ord_px=sl_ord,
            pos_side="net",
            tag="testTpSl"
        )
        if order_id:
            print(f"  ✓ 订单ID: {order_id}")
            print(f"    止盈触发: {tp_trigger} | 止损触发: {sl_trigger}")
            self.test_results["market_order_with_tp_sl"] = True
        else:
            print("  ✗ 下单失败")
        time.sleep(1)
        
        # 2.2 限价卖出（带止盈止损）
        print("[2.2] 测试限价卖出订单（带止盈止损）...")
        limit_price = current_price * 1.03  # 限价：当前价+3%
        tp_trigger = str(limit_price * 0.98)  # 止盈触发价：限价-2%
        sl_trigger = str(limit_price * 1.02)  # 止损触发价：限价+2%
        
        order_id = self.send_swap_limit_order_with_tp_sl(
            self.symbol, "sell", 1, limit_price,
            tp_trigger_px=tp_trigger,
            tp_ord_px="-1",
            sl_trigger_px=sl_trigger,
            sl_ord_px="-1",
            pos_side="net",
            tag="testTpSlLimit"
        )
        if order_id:
            print(f"  ✓ 订单ID: {order_id} | 限价: {limit_price:.2f}")
            print(f"    止盈触发: {tp_trigger} | 止损触发: {sl_trigger}")
            self.test_results["limit_order_with_tp_sl"] = True
        else:
            print("  ✗ 下单失败")
        print()
    
    def test_advanced_orders(self):
        """测试3: 高级订单类型"""
        print("\n" + "=" * 60)
        print("测试3: 高级订单类型")
        print("=" * 60)
        
        current_price = self.last_price
        if current_price is None:
            last_kline = self.get_last_kline(self.symbol, "1s")
            if last_kline is None:
                print("⚠️  无法获取当前价格，跳过测试")
                return
            current_price = float(last_kline.close)
        print(f"当前价格: {current_price:.2f}")
        print()
        
        # 3.1 post_only 订单（只做maker）
        print("[3.1] 测试 post_only 订单（只做maker）...")
        limit_price = current_price * 1.05  # 高于当前价5%
        order_id = self.send_swap_advanced_order(
            self.symbol, "sell", 1, limit_price,
            ord_type="post_only",
            pos_side="net",
            tag="testPostOnly"
        )
        if order_id:
            print(f"  ✓ 订单ID: {order_id} | 价格: {limit_price:.2f}")
            self.test_results["advanced_order"] = True
        else:
            print("  ✗ 下单失败")
        time.sleep(1)
        
        # 3.2 FOK 订单（全部成交或立即取消）
        print("[3.2] 测试 FOK 订单（全部成交或立即取消）...")
        limit_price = current_price * 0.95  # 低于当前价5%（可能立即成交）
        order_id = self.send_swap_advanced_order(
            self.symbol, "buy", 1, limit_price,
            ord_type="fok",
            pos_side="net",
            tag="testFok"
        )
        if order_id:
            print(f"  ✓ 订单ID: {order_id} | 价格: {limit_price:.2f}")
        else:
            print("  ✗ 下单失败")
        time.sleep(1)
        
        # 3.3 IOC 订单（立即成交并取消剩余）
        print("[3.3] 测试 IOC 订单（立即成交并取消剩余）...")
        limit_price = current_price * 0.96  # 低于当前价4%（可能立即成交）
        order_id = self.send_swap_advanced_order(
            self.symbol, "buy", 1, limit_price,
            ord_type="ioc",
            pos_side="net",
            tag="testIoc"
        )
        if order_id:
            print(f"  ✓ 订单ID: {order_id} | 价格: {limit_price:.2f}")
        else:
            print("  ✗ 下单失败")
        print()
    
    def test_batch_orders(self):
        """测试4: 批量下单"""
        print("\n" + "=" * 60)
        print("测试4: 批量下单")
        print("=" * 60)
        
        current_price = self.last_price
        if current_price is None:
            last_kline = self.get_last_kline(self.symbol, "1s")
            if last_kline is None:
                print("⚠️  无法获取当前价格，跳过测试")
                return
            current_price = float(last_kline.close)
        print(f"当前价格: {current_price:.2f}")
        print()
        
        # 构建批量订单
        orders = [
            {
                "symbol": self.symbol,
                "side": "buy",
                "order_type": "limit",
                "quantity": 1,
                "price": current_price * 0.97,  # 低于当前价3%
                "pos_side": "net",
                "tag": "batch1"
            },
            {
                "symbol": self.symbol,
                "side": "sell",
                "order_type": "limit",
                "quantity": 1,
                "price": current_price * 1.03,  # 高于当前价3%
                "pos_side": "net",
                "tag": "batch2"
            },
            {
                "symbol": self.symbol,
                "side": "buy",
                "order_type": "market",
                "quantity": 1,
                "price": 0,  # 市价单
                "pos_side": "net",
                "tag": "batch3",
                "tp_trigger_px": str(current_price * 1.02),  # 止盈触发价
                "tp_ord_px": "-1",  # 市价止盈
                "sl_trigger_px": str(current_price * 0.98),  # 止损触发价
                "sl_ord_px": "-1"  # 市价止损
            }
        ]
        
        print(f"[4.1] 测试批量下单（{len(orders)} 个订单）...")
        order_ids = self.send_batch_orders(orders)
        if order_ids and len(order_ids) == len(orders):
            print(f"  ✓ 成功提交 {len(order_ids)} 个订单")
            for i, order_id in enumerate(order_ids, 1):
                print(f"    订单{i}: {order_id}")
            self.test_results["batch_orders"] = True
        else:
            print(f"  ✗ 批量下单失败，返回 {len(order_ids) if order_ids else 0} 个订单ID")
        print()
    
    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        symbol = report.get("symbol", "")
        side = report.get("side", "")
        client_order_id = report.get("client_order_id", "")
        tag = report.get("tag", "")
        
        if status == "filled":
            filled_qty = report.get("filled_quantity", 0)
            filled_price = report.get("filled_price", 0)
            print(f"  └─ [成交] {symbol} {side} {filled_qty}张 @ {filled_price:.2f} | 订单ID: {client_order_id}")
            if tag:
                print(f"     标签: {tag}")
        elif status == "rejected":
            error_msg = report.get("error_msg", "")
            print(f"  └─ [拒绝] {symbol} {side} | 原因: {error_msg} | 订单ID: {client_order_id}")
        elif status == "accepted":
            print(f"  └─ [接受] {symbol} {side} | 订单ID: {client_order_id}")
            if tag:
                print(f"     标签: {tag}")
    
    def print_test_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        print()
        
        total = len(self.test_results)
        passed = sum(1 for v in self.test_results.values() if v)
        
        for test_name, result in self.test_results.items():
            status = "✓ 通过" if result else "✗ 失败"
            print(f"  {test_name:30s} : {status}")
        
        print()
        print(f"总计: {passed}/{total} 通过")
        print("=" * 60)
    
    def on_stop(self):
        """停止"""
        print("\n" + "=" * 60)
        print("测试结束")
        print("=" * 60)
        
        # 取消订阅
        self.unsubscribe_kline(self.symbol, "1s")
        
        # 打印活跃订单
        active_orders = self.get_active_orders()
        if active_orders:
            print(f"\n当前活跃订单数: {len(active_orders)}")
            for order in active_orders:
                print(f"  - {order.symbol} {order.side} {order.quantity}张 @ {order.price:.2f} | ID: {order.client_order_id}")


def main():
    strategy = OrderInterfaceTestStrategy()
    
    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())
    
    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()

