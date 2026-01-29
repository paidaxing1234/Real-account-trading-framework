#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试：使用旧的 strategy_base 模块测试余额获取
"""

import sys
import os
import time

# 使用新编译的 strategy_base（在 build 目录下）
sys.path.insert(0, '../../../build')
from strategy_base import StrategyBase

class SimpleBalanceTest(StrategyBase):
    def __init__(self):
        super().__init__('test_balance_simple', max_kline_bars=100)
        self._set_python_self(self)
        self.got_balance = False

    def on_init(self):
        print('=' * 60)
        print('简单余额测试')
        print('=' * 60)
        print()

        # 注册账户
        print('[1] 注册 Binance 账户...')
        self.register_binance_account(
            api_key='A0Hw5OAbsWmnS9WZmvux9DO8w1ixraP3zctKD48J0IqbbhDIlddtIK1AplfA6TjZ',
            secret_key='vYvEvgPd56bHh5tG46DBbSbTWVlt43fRPDhnYjva71AOzdwiCAaCttOspXwVBm1u',
            is_testnet=True
        )

    def on_register_report(self, success: bool, error_msg: str):
        if success:
            print('[2] ✓ 账户注册成功')
            print()

            # 调用 refresh_account
            print('[3] 调用 refresh_account()...')
            self.refresh_account()
            print()

            # 等待5秒后检查
            import threading
            def check_balance():
                time.sleep(5)
                usdt = self.get_usdt_available()
                equity = self.get_total_equity()
                balances = self.get_all_balances()

                print('[4] 5秒后查询结果:')
                print(f'    USDT可用: {usdt:.2f}')
                print(f'    总权益: {equity:.2f}')
                print(f'    余额数量: {len(balances)}')

                if usdt > 0 or equity > 0:
                    print()
                    print('=' * 60)
                    print('✓ 成功获取余额！')
                    print('=' * 60)
                    self.got_balance = True
                else:
                    print()
                    print('=' * 60)
                    print('✗ 未能获取余额')
                    print('=' * 60)

                time.sleep(2)
                self.stop()

            threading.Thread(target=check_balance, daemon=True).start()
        else:
            print(f'[2] ✗ 注册失败: {error_msg}')
            self.stop()

    def on_account_update(self, total_equity: float, margin_ratio: float):
        print(f'[回调] on_account_update: 权益={total_equity:.2f}, 保证金率={margin_ratio:.4f}')

if __name__ == '__main__':
    import signal
    strategy = SimpleBalanceTest()
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())

    print('开始运行测试...')
    print()
    strategy.run()

    if strategy.got_balance:
        print('\n测试通过！')
        exit(0)
    else:
        print('\n测试失败！')
        exit(1)
