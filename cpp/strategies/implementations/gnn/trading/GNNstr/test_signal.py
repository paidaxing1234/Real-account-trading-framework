#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试信号处理
"""

import sys
import os
import signal
import time

sys.path.insert(0, '../../../build')
from strategy_base import StrategyBase

class SignalTestStrategy(StrategyBase):
    def __init__(self):
        super().__init__('test_signal', max_kline_bars=100)
        self._set_python_self(self)
        self.tick_count = 0

    def on_init(self):
        print('=' * 60)
        print('信号处理测试')
        print('按 Ctrl+C 退出')
        print('=' * 60)

    def on_tick(self):
        self.tick_count += 1
        if self.tick_count % 1000 == 0:
            print(f'[Tick] {self.tick_count}')

    def on_stop(self):
        print()
        print('=' * 60)
        print(f'[停止] 策略已停止，总tick数: {self.tick_count}')
        print('=' * 60)

if __name__ == '__main__':
    strategy = SignalTestStrategy()

    def signal_handler(signum, frame):
        print("\n[信号] 收到退出信号，正在停止...")
        strategy.stop()
        time.sleep(0.5)
        print("[信号] 退出完成")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print('开始运行，按 Ctrl+C 退出...')
    try:
        strategy.run()
    except KeyboardInterrupt:
        print("\n[中断] 收到键盘中断")
        strategy.stop()
        sys.exit(0)
