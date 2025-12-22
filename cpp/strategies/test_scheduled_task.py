#!/usr/bin/env python3
"""
定时任务功能测试程序

测试内容：
- 1秒执行一次的任务 (task_1s)
- 1分钟执行一次的任务 (task_1m)

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


class ScheduledTaskTestStrategy(StrategyBase):
    """定时任务测试策略"""
    
    def __init__(self):
        super().__init__("scheduled_task_test", max_kline_bars=100)
        
        # 计数器
        self.task_1s_count = 0
        self.task_1m_count = 0
        
        # 开始时间
        self.start_time = None
    
    def on_init(self):
        """初始化 - 注册定时任务"""
        self.start_time = time.time()
        
        print("=" * 60)
        print("       定时任务测试程序")
        print("=" * 60)
        print()
        print("注册任务:")
        print("  - task_1s: 每 1 秒执行一次")
        print("  - task_1m: 每 1 分钟执行一次")
        print()
        print("按 Ctrl+C 停止测试")
        print()
        print("-" * 60)
        
        # 注册 1秒 执行一次的任务
        self.schedule_task("task_1s", "1s")
        
        # 注册 1分钟 执行一次的任务
        self.schedule_task("task_1m", "1m")
    
    def on_scheduled_task(self, task_name: str):
        """定时任务回调"""
        elapsed = time.time() - self.start_time
        
        if task_name == "task_1s":
            self.task_1s_count += 1
            print(f"[{elapsed:6.1f}s] task_1s 执行 | 总次数: {self.task_1s_count}")
            
        elif task_name == "task_1m":
            self.task_1m_count += 1
            print(f"[{elapsed:6.1f}s] task_1m 执行 | 总次数: {self.task_1m_count}")
            print("-" * 60)
    
    def on_stop(self):
        """停止 - 打印统计"""
        elapsed = time.time() - self.start_time
        
        print()
        print("=" * 60)
        print("                测试结果")
        print("=" * 60)
        print(f"  运行时间: {elapsed:.1f} 秒")
        print()
        print(f"  task_1s (1秒/次):")
        print(f"    - 执行次数: {self.task_1s_count}")
        print(f"    - 预期次数: ~{int(elapsed)}")
        print()
        print(f"  task_1m (1分钟/次):")
        print(f"    - 执行次数: {self.task_1m_count}")
        print(f"    - 预期次数: ~{int(elapsed / 60)}")
        print()
        
        # 获取任务详情
        print("  任务详情:")
        for task in self.get_scheduled_tasks():
            print(f"    - {task.task_name}: 执行 {task.run_count} 次, enabled={task.enabled}")
        
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

