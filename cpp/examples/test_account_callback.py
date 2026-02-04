#!/usr/bin/env python3
"""
测试账户注册和余额回调
"""

import sys
import os
import time

# 添加 strategies 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'strategies'))

from strategy_base import StrategyBase, KlineBar

class TestAccountStrategy(StrategyBase):
    """测试账户回调的简单策略"""

    def __init__(self):
        super().__init__("test_account_callback")
        self.balance_received = False
        self.account_received = False

    def on_init(self):
        print("=" * 60)
        print("  测试账户注册和余额回调")
        print("=" * 60)

        # 从环境变量读取 API 密钥
        api_key = os.environ.get("BINANCE_API_KEY", "")
        secret_key = os.environ.get("BINANCE_SECRET_KEY", "")

        if not api_key or not secret_key:
            print("[错误] 请设置环境变量 BINANCE_API_KEY 和 BINANCE_SECRET_KEY")
            return

        print(f"[初始化] API Key: {api_key[:8]}...")

        # 注册 Binance 测试网账户
        print("[初始化] 注册 Binance 测试网账户...")
        self.register_binance_account(
            api_key=api_key,
            secret_key=secret_key,
            is_testnet=True
        )
        print("[初始化] 注册请求已发送，等待回调...")

    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            print("[回调] 账户注册成功!")
            print("[回调] 调用 refresh_account() 刷新余额...")
            self.refresh_account()
        else:
            print(f"[回调] 账户注册失败: {error_msg}")

    def on_account_update(self, account):
        """账户更新回调"""
        self.account_received = True
        print(f"[回调] 账户更新: 总权益={account.total_equity:.4f}, 保证金率={account.margin_ratio:.4f}")

    def on_balance_update(self, balance):
        """余额更新回调"""
        self.balance_received = True
        print(f"[回调] 余额更新: 币种={balance.currency}, 可用={balance.available:.4f}, 冻结={balance.frozen:.4f}")

        if balance.currency == "USDT":
            print(f"[成功] 收到 USDT 余额: {balance.available:.2f}")

    def on_position_update(self, position):
        """持仓更新回调"""
        print(f"[回调] 持仓更新: {position.symbol} 数量={position.quantity}")

    def on_tick(self):
        """主循环"""
        pass

    def on_stop(self):
        """策略停止"""
        print()
        print("=" * 60)
        print("  测试结果")
        print("=" * 60)
        print(f"  余额回调: {'收到' if self.balance_received else '未收到'}")
        print(f"  账户回调: {'收到' if self.account_received else '未收到'}")
        print("=" * 60)


def main():
    # 检查环境变量
    if not os.environ.get("BINANCE_API_KEY"):
        # 尝试从配置文件读取
        config_path = os.path.join(
            os.path.dirname(__file__),
            '..', 'strategies', 'configs',
            'alpha_077_094_080_binance_testnet.json'
        )
        if os.path.exists(config_path):
            import json
            with open(config_path) as f:
                config = json.load(f)
            os.environ["BINANCE_API_KEY"] = config.get("account", {}).get("api_key", "")
            os.environ["BINANCE_SECRET_KEY"] = config.get("account", {}).get("secret_key", "")
            print(f"[配置] 从 {config_path} 加载 API 密钥")

    strategy = TestAccountStrategy()

    import signal
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())

    print("[启动] 运行策略，等待回调...")
    print("[提示] 按 Ctrl+C 停止")
    print()

    strategy.run()


if __name__ == "__main__":
    main()
