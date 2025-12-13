#!/usr/bin/env python3
"""
多策略并发延迟测试
==================

同时启动多个策略进程，测试 ZeroMQ 框架在并发场景下的延迟表现。

测试场景：
1. 多策略同时接收行情 - 测试广播延迟
2. 多策略同时发送订单 - 测试并发处理能力
3. 延迟统计和对比分析

使用方法：
    # 启动 3 个策略，每个发送 50 个订单
    python run_multi_strategy_test.py --num-strategies 3 --orders 50
    
    # 启动 5 个策略，高频测试
    python run_multi_strategy_test.py --num-strategies 5 --orders 100 --interval 5

前置条件：
    1. 先启动 C++ 服务端: ./trading_server
    2. 确保 ZeroMQ IPC 端点可用

作者: Sequence Framework
"""

import subprocess
import sys
import os
import time
import argparse
import json
import signal
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置
# ============================================================

# 策略脚本路径
STRATEGY_SCRIPT = os.path.join(os.path.dirname(__file__), "latency_test_strategy.py")

# 报告目录
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


# ============================================================
# 进程管理
# ============================================================

class StrategyProcess:
    """策略进程管理器"""
    
    def __init__(self, strategy_id: int, orders: int, interval: int):
        self.strategy_id = strategy_id
        self.orders = orders
        self.interval = interval
        self.process: Optional[subprocess.Popen] = None
        self.start_time: float = 0
        self.end_time: float = 0
    
    def start(self):
        """启动策略进程"""
        cmd = [
            sys.executable,
            STRATEGY_SCRIPT,
            "--id", str(self.strategy_id),
            "--orders", str(self.orders),
            "--interval", str(self.interval)
        ]
        
        # 不捕获输出，让每个策略直接输出到终端（方便调试）
        self.process = subprocess.Popen(
            cmd,
            # 不使用 PIPE，让输出直接显示
            stdout=None,
            stderr=None
        )
        self.start_time = time.time()
        
        print(f"[Runner] 启动策略 {self.strategy_id}, PID: {self.process.pid}")
    
    def is_running(self) -> bool:
        """检查进程是否运行中"""
        if self.process is None:
            return False
        return self.process.poll() is None
    
    def wait(self, timeout: float = None) -> int:
        """等待进程结束"""
        if self.process is None:
            return -1
        
        try:
            retcode = self.process.wait(timeout=timeout)
            self.end_time = time.time()
            return retcode
        except subprocess.TimeoutExpired:
            return None
    
    def terminate(self):
        """终止进程"""
        if self.process and self.is_running():
            self.process.terminate()
            self.process.wait(timeout=5)
            self.end_time = time.time()
    
    def get_output(self) -> str:
        """获取进程输出"""
        if self.process and self.process.stdout:
            return self.process.stdout.read()
        return ""


# ============================================================
# 测试运行器
# ============================================================

class MultiStrategyTestRunner:
    """多策略测试运行器"""
    
    def __init__(self, num_strategies: int, orders_per_strategy: int, order_interval: int):
        self.num_strategies = num_strategies
        self.orders_per_strategy = orders_per_strategy
        self.order_interval = order_interval
        
        self.processes: List[StrategyProcess] = []
        self.start_time: float = 0
        self.end_time: float = 0
        
        # 确保报告目录存在
        os.makedirs(REPORT_DIR, exist_ok=True)
    
    def run(self):
        """运行测试"""
        print("\n" + "=" * 70)
        print("  ZeroMQ 多策略并发延迟测试")
        print("=" * 70)
        print(f"\n测试配置:")
        print(f"  策略数量: {self.num_strategies}")
        print(f"  每策略订单数: {self.orders_per_strategy}")
        print(f"  订单间隔: 每 {self.order_interval} 条行情")
        print(f"  总订单数: {self.num_strategies * self.orders_per_strategy}")
        print()
        
        self.start_time = time.time()
        
        # 启动所有策略
        print("[Runner] 启动策略进程...")
        for i in range(1, self.num_strategies + 1):
            sp = StrategyProcess(i, self.orders_per_strategy, self.order_interval)
            sp.start()
            self.processes.append(sp)
            # 错开启动时间，避免同时连接
            time.sleep(0.2)
        
        print(f"\n[Runner] 已启动 {self.num_strategies} 个策略进程")
        print("[Runner] 等待测试完成...\n")
        
        # 监控进程
        try:
            self._monitor_processes()
        except KeyboardInterrupt:
            print("\n[Runner] 收到中断信号，停止所有策略...")
            self._stop_all()
        
        self.end_time = time.time()
        
        # 等待一下让文件写入完成
        time.sleep(1)
        
        # 生成汇总报告
        self._generate_summary_report()
    
    def _monitor_processes(self):
        """监控所有进程"""
        while True:
            running = [p for p in self.processes if p.is_running()]
            
            if not running:
                print("\n[Runner] 所有策略已完成")
                break
            
            # 打印状态
            elapsed = time.time() - self.start_time
            print(f"\r[Runner] 运行中: {len(running)}/{self.num_strategies} | "
                  f"耗时: {elapsed:.1f}s", end="", flush=True)
            
            time.sleep(1)
    
    def _stop_all(self):
        """停止所有进程"""
        for p in self.processes:
            if p.is_running():
                print(f"[Runner] 终止策略 {p.strategy_id}")
                p.terminate()
    
    def _generate_summary_report(self):
        """生成汇总报告"""
        print("\n" + "=" * 70)
        print("  汇总报告")
        print("=" * 70)
        
        # 收集所有报告文件
        reports = []
        report_files = list(Path(REPORT_DIR).glob("latency_report_*.json"))
        
        # 只取最近的报告
        recent_time = time.time() - (self.end_time - self.start_time) - 60
        
        for f in report_files:
            if f.stat().st_mtime > recent_time:
                try:
                    with open(f, 'r') as fp:
                        report = json.load(fp)
                        reports.append(report)
                except Exception as e:
                    print(f"[警告] 无法读取报告 {f}: {e}")
        
        if not reports:
            print("\n[警告] 未找到报告文件，请检查策略是否正常运行")
            return
        
        # 汇总统计
        print(f"\n收集到 {len(reports)} 份报告\n")
        
        # 行情延迟汇总
        print("--- 行情推送延迟 (服务端 -> 策略) ---")
        print(f"{'策略ID':<20} {'样本数':<10} {'平均(μs)':<12} {'P50(μs)':<12} {'P90(μs)':<12} {'P99(μs)':<12}")
        print("-" * 78)
        
        all_md_means = []
        all_md_p99 = []
        
        for r in reports:
            md = r.get("market_data_latency", {})
            strategy_id = r.get("strategy_id", "unknown")
            print(f"{strategy_id:<20} {md.get('count', 0):<10} "
                  f"{md.get('mean_us', 0):<12.2f} {md.get('p50_us', 0):<12.2f} "
                  f"{md.get('p90_us', 0):<12.2f} {md.get('p99_us', 0):<12.2f}")
            
            if md.get('mean_us', 0) > 0:
                all_md_means.append(md.get('mean_us', 0))
                all_md_p99.append(md.get('p99_us', 0))
        
        if all_md_means:
            print("-" * 78)
            print(f"{'汇总':<20} {'-':<10} "
                  f"{sum(all_md_means)/len(all_md_means):<12.2f} {'-':<12} "
                  f"{'-':<12} {max(all_md_p99):<12.2f}")
        
        # 订单延迟汇总
        print("\n--- 订单往返延迟 (策略 -> 服务端 -> 策略) ---")
        print(f"{'策略ID':<20} {'样本数':<10} {'平均(μs)':<12} {'P50(μs)':<12} {'P90(μs)':<12} {'P99(μs)':<12}")
        print("-" * 78)
        
        all_rtt_means = []
        all_rtt_p99 = []
        
        for r in reports:
            rtt = r.get("order_rtt_latency", {})
            strategy_id = r.get("strategy_id", "unknown")
            print(f"{strategy_id:<20} {rtt.get('count', 0):<10} "
                  f"{rtt.get('mean_us', 0):<12.2f} {rtt.get('p50_us', 0):<12.2f} "
                  f"{rtt.get('p90_us', 0):<12.2f} {rtt.get('p99_us', 0):<12.2f}")
            
            if rtt.get('mean_us', 0) > 0:
                all_rtt_means.append(rtt.get('mean_us', 0))
                all_rtt_p99.append(rtt.get('p99_us', 0))
        
        if all_rtt_means:
            print("-" * 78)
            print(f"{'汇总':<20} {'-':<10} "
                  f"{sum(all_rtt_means)/len(all_rtt_means):<12.2f} {'-':<12} "
                  f"{'-':<12} {max(all_rtt_p99):<12.2f}")
        
        # 总结
        total_elapsed = self.end_time - self.start_time
        total_orders = sum(r.get("orders_sent", 0) for r in reports)
        total_tickers = sum(r.get("ticker_count", 0) for r in reports)
        
        print(f"\n--- 测试总结 ---")
        print(f"  总运行时间: {total_elapsed:.2f} 秒")
        print(f"  策略数量: {len(reports)}")
        print(f"  总行情处理: {total_tickers}")
        print(f"  总订单处理: {total_orders}")
        
        if all_md_means:
            print(f"\n  行情延迟评估:")
            avg_md = sum(all_md_means) / len(all_md_means)
            print(f"    平均: {avg_md:.2f} μs")
            if avg_md < 100:
                print(f"    评级: ⭐⭐⭐⭐⭐ 极佳 (< 100μs)")
            elif avg_md < 500:
                print(f"    评级: ⭐⭐⭐⭐ 优秀 (< 500μs)")
            elif avg_md < 1000:
                print(f"    评级: ⭐⭐⭐ 良好 (< 1ms)")
            else:
                print(f"    评级: ⭐⭐ 一般 (> 1ms)")
        
        if all_rtt_means:
            print(f"\n  订单往返延迟评估:")
            avg_rtt = sum(all_rtt_means) / len(all_rtt_means)
            print(f"    平均: {avg_rtt:.2f} μs")
            # 注意：这个包含了API调用时间，所以会比较长
            if avg_rtt < 1000:
                print(f"    评级: ⭐⭐⭐⭐⭐ 极佳 (< 1ms)")
            elif avg_rtt < 10000:
                print(f"    评级: ⭐⭐⭐⭐ 优秀 (< 10ms)")
            elif avg_rtt < 100000:
                print(f"    评级: ⭐⭐⭐ 良好 (< 100ms)")
            else:
                print(f"    评级: ⭐⭐ 一般 (> 100ms)  [含API调用延迟]")
        
        print("\n" + "=" * 70)
        
        # 保存汇总报告
        summary = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "num_strategies": self.num_strategies,
                "orders_per_strategy": self.orders_per_strategy,
                "order_interval": self.order_interval
            },
            "results": {
                "total_elapsed_seconds": total_elapsed,
                "total_tickers": total_tickers,
                "total_orders": total_orders,
                "avg_md_latency_us": sum(all_md_means) / len(all_md_means) if all_md_means else 0,
                "max_md_p99_us": max(all_md_p99) if all_md_p99 else 0,
                "avg_rtt_latency_us": sum(all_rtt_means) / len(all_rtt_means) if all_rtt_means else 0,
                "max_rtt_p99_us": max(all_rtt_p99) if all_rtt_p99 else 0
            },
            "individual_reports": reports
        }
        
        summary_file = os.path.join(REPORT_DIR, f"summary_report_{int(time.time())}.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n汇总报告已保存: {summary_file}")


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="多策略并发延迟测试")
    parser.add_argument("--num-strategies", "-n", type=int, default=3, 
                        help="策略数量 (默认: 3)")
    parser.add_argument("--orders", "-o", type=int, default=50, 
                        help="每个策略的测试订单数 (默认: 50)")
    parser.add_argument("--interval", "-i", type=int, default=20, 
                        help="订单间隔，每N条行情发一个订单 (默认: 20)")
    
    args = parser.parse_args()
    
    # 检查策略脚本是否存在
    if not os.path.exists(STRATEGY_SCRIPT):
        print(f"错误: 找不到策略脚本 {STRATEGY_SCRIPT}")
        sys.exit(1)
    
    # 检查服务端是否运行（检查 IPC 文件）
    ipc_file = "/tmp/trading_md.ipc"
    if not os.path.exists(ipc_file):
        print(f"警告: IPC 文件 {ipc_file} 不存在")
        print("请确保 C++ 服务端已启动: ./trading_server")
        print()
    
    # 运行测试
    runner = MultiStrategyTestRunner(
        num_strategies=args.num_strategies,
        orders_per_strategy=args.orders,
        order_interval=args.interval
    )
    
    runner.run()


if __name__ == "__main__":
    main()

