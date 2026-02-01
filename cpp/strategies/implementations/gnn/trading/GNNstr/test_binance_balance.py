#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Binance账户余额获取
"""

import sys
import os
import time

# 添加路径
sys.path.insert(0, '../../../build')  # 使用新编译的 strategy_base
from strategy_base import StrategyBase

class TestBalanceStrategy(StrategyBase):
    def __init__(self):
        super().__init__('test_balance', max_kline_bars=100)
        self._set_python_self(self)
        self.balance_received = False

    def on_init(self):
        print('=' * 60)
        print('测试Binance账户余额获取')
        print('=' * 60)
        print()
        print('[1] 注册Binance账户...')

        self.register_binance_account(
            api_key='A0Hw5OAbsWmnS9WZmvux9DO8w1ixraP3zctKD48J0IqbbhDIlddtIK1AplfA6TjZ',
            secret_key='vYvEvgPd56bHh5tG46DBbSbTWVlt43fRPDhnYjva71AOzdwiCAaCttOspXwVBm1u',
            is_testnet=True
        )

    def on_register_report(self, success: bool, error_msg: str):
        if success:
            print('[2] ✓ 账户注册成功')
            print()

            # 立即查询
            usdt = self.get_usdt_available()
            equity = self.get_total_equity()
            print(f'[3] 立即查询余额:')
            print(f'    USDT可用: {usdt:.2f}')
            print(f'    总权益: {equity:.2f}')
            print()

            # 调用refresh_account
            print('[4] 调用 refresh_account()...')
            self.refresh_account()
            print()

            # 等待不同时间后查询
            print('[5] 等待余额数据返回...')
            import threading
            def check_after_delay(delay):
                time.sleep(delay)
                usdt = self.get_usdt_available()
                equity = self.get_total_equity()
                print(f'    [{delay}秒后] USDT={usdt:.2f}, 权益={equity:.2f}')

                if usdt > 0 and not self.balance_received:
                    self.balance_received = True
                    print()
                    print('=' * 60)
                    print(f'✓ 成功获取余额！等待{delay}秒后余额可用')
                    print('=' * 60)

                    # 再等5秒后停止
                    time.sleep(5)
                    self.stop()

            for delay in [1, 2, 3, 5, 10]:
                threading.Thread(target=check_after_delay, args=(delay,), daemon=True).start()
        else:
            print(f'[2] ✗ 账户注册失败: {error_msg}')
            self.stop()

    def on_account_update(self, total_equity: float, margin_ratio: float):
        usdt = self.get_usdt_available()
        print(f'[回调] on_account_update: USDT={usdt:.2f}, 权益={total_equity:.2f}')

    def on_balance_update(self, balances: dict):
        print(f'[回调] on_balance_update: {balances}')
        usdt = self.get_usdt_available()
        print(f'       USDT可用: {usdt:.2f}')

if __name__ == '__main__':
    import signal
    strategy = TestBalanceStrategy()
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())
    strategy.run()
