#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细测试账户余额获取流程
"""

import sys
import os
import time

sys.path.insert(0, '../../../build')  # 使用新编译的 strategy_base
from strategy_base import StrategyBase

class DetailedAccountTest(StrategyBase):
    def __init__(self):
        super().__init__('test_account_detail', max_kline_bars=100)
        self._set_python_self(self)
        self.callback_count = 0

    def on_init(self):
        print('=' * 70)
        print('详细测试：Binance账户余额获取流程')
        print('=' * 70)
        print()

        # 测试1：注册前查询
        print('[测试1] 注册前查询余额:')
        print(f'  is_registered: {self.is_account_registered()}')
        print(f'  get_usdt_available(): {self.get_usdt_available()}')
        print(f'  get_total_equity(): {self.get_total_equity()}')
        print(f'  get_all_balances(): {self.get_all_balances()}')
        print()

        # 测试2：注册账户
        print('[测试2] 注册Binance账户...')
        result = self.register_binance_account(
            api_key='A0Hw5OAbsWmnS9WZmvux9DO8w1ixraP3zctKD48J0IqbbhDIlddtIK1AplfA6TjZ',
            secret_key='vYvEvgPd56bHh5tG46DBbSbTWVlt43fRPDhnYjva71AOzdwiCAaCttOspXwVBm1u',
            is_testnet=True
        )
        print(f'  register_binance_account() 返回: {result}')
        print()

    def on_register_report(self, success: bool, error_msg: str):
        print('[测试3] 收到注册回报:')
        print(f'  success: {success}')
        print(f'  error_msg: {error_msg}')
        print(f'  is_registered: {self.is_account_registered()}')
        print()

        if not success:
            print(f'✗ 注册失败: {error_msg}')
            self.stop()
            return

        # 测试4：注册后立即查询
        print('[测试4] 注册成功后立即查询:')
        print(f'  get_usdt_available(): {self.get_usdt_available()}')
        print(f'  get_total_equity(): {self.get_total_equity()}')
        balances = self.get_all_balances()
        print(f'  get_all_balances() 数量: {len(balances)}')
        for bal in balances:
            print(f'    - {bal}')
        print()

        # 测试5：调用refresh_account
        print('[测试5] 调用 refresh_account()...')
        result = self.refresh_account()
        print(f'  refresh_account() 返回: {result}')
        print()

        # 测试6：等待不同时间后查询
        print('[测试6] 等待余额数据返回...')
        import threading
        def check_after_delay(delay):
            time.sleep(delay)
            usdt = self.get_usdt_available()
            equity = self.get_total_equity()
            balances = self.get_all_balances()
            print(f'  [{delay}秒后] USDT={usdt:.2f}, 权益={equity:.2f}, 余额数={len(balances)}')

            if delay == 10:
                print()
                print('=' * 70)
                print('测试完成，10秒后仍无余额数据')
                print('=' * 70)
                self.stop()

        for delay in [1, 2, 3, 5, 10]:
            threading.Thread(target=check_after_delay, args=(delay,), daemon=True).start()

    def on_account_update(self, total_equity: float, margin_ratio: float):
        self.callback_count += 1
        print(f'[回调#{self.callback_count}] on_account_update 被触发:')
        print(f'  total_equity: {total_equity}')
        print(f'  margin_ratio: {margin_ratio}')
        usdt = self.get_usdt_available()
        balances = self.get_all_balances()
        print(f'  get_usdt_available(): {usdt}')
        print(f'  get_all_balances() 数量: {len(balances)}')
        for bal in balances:
            print(f'    - {bal}')
        print()

    def on_balance_update(self, balance: dict):
        self.callback_count += 1
        print(f'[回调#{self.callback_count}] on_balance_update 被触发:')
        print(f'  balance: {balance}')
        print()

if __name__ == '__main__':
    import signal
    strategy = DetailedAccountTest()
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())

    print('开始运行测试...')
    print()
    strategy.run()
