#!/usr/bin/env python3
"""
多策略并发延迟基准测试
======================

专门用于测试 ZeroMQ 框架在多策略并发场景下的延迟表现。

测试场景：
- 5 个策略同时运行
- 服务端每 100ms 推送一次行情
- 每条行情约 8KB
- 共推送 1000 次

测量方式（两种）：
1. 时间戳对比法：使用消息中的 send_time_ns 与接收时间对比
2. 本地计时法：使用 Python time.time_ns() 测量

统计指标：
- 平均延迟、中位数、P90、P99、最大值
- 异常值统计（>1ms 的比例）
- 丢包检测（通过序列号）

使用方法：
    python benchmark_latency.py --id 1

作者: Sequence Framework
"""

import sys
import os
import time
import argparse
import json
import gc
import statistics
import platform
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

# 添加父目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_client import TradingClient, Strategy, TickerData, OrderReport

# ============================================================
# 配置
# ============================================================

# 预热消息数
WARMUP_TICKS = 20

# 禁用 GC
DISABLE_GC = True

# 异常阈值（微秒）
OUTLIER_THRESHOLD_US = 1000  # 1ms

# 是否启用绑核（仅 Linux 支持）
ENABLE_CPU_AFFINITY = True


# ============================================================
# CPU 绑核工具
# ============================================================

def pin_to_cpu(cpu_id: int) -> bool:
    """
    将当前进程绑定到指定 CPU 核心
    
    仅在 Linux 上有效，macOS 不支持
    
    Args:
        cpu_id: CPU 核心 ID (0, 1, 2, ...)
        
    Returns:
        True 成功, False 失败或不支持
    """
    if platform.system() != 'Linux':
        print(f"[绑核] 当前系统 ({platform.system()}) 不支持 CPU 亲和性")
        print(f"[绑核] 在 Linux 服务器上运行时将自动启用")
        return False
    
    try:
        os.sched_setaffinity(0, {cpu_id})
        print(f"[绑核] 进程已绑定到 CPU {cpu_id}")
        return True
    except Exception as e:
        print(f"[绑核] 绑定失败: {e}")
        return False


def set_high_priority() -> bool:
    """
    设置进程为高优先级
    
    使用 nice 值（需要 root 才能设置负值）
    """
    try:
        # 尝试设置最高优先级（需要 root）
        os.nice(-20)
        print(f"[优先级] 已设置为最高优先级 (nice -20)")
        return True
    except PermissionError:
        # 没有 root 权限，设置为普通用户最高
        try:
            current = os.nice(0)
            print(f"[优先级] 当前 nice 值: {current} (使用 sudo 可获得更高优先级)")
            return False
        except:
            return False
    except Exception as e:
        print(f"[优先级] 设置失败: {e}")
        return False


# ============================================================
# 延迟统计类
# ============================================================

@dataclass
class LatencyStats:
    """延迟统计数据"""
    name: str
    samples: List[float] = field(default_factory=list)
    
    def add(self, latency_us: float):
        self.samples.append(latency_us)
    
    def count(self) -> int:
        return len(self.samples)
    
    def mean(self) -> float:
        return statistics.mean(self.samples) if self.samples else 0
    
    def median(self) -> float:
        return statistics.median(self.samples) if self.samples else 0
    
    def stdev(self) -> float:
        return statistics.stdev(self.samples) if len(self.samples) > 1 else 0
    
    def min_val(self) -> float:
        return min(self.samples) if self.samples else 0
    
    def max_val(self) -> float:
        return max(self.samples) if self.samples else 0
    
    def percentile(self, p: float) -> float:
        if not self.samples:
            return 0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * p / 100)
        idx = min(idx, len(sorted_samples) - 1)
        return sorted_samples[idx]
    
    def outlier_count(self, threshold_us: float = OUTLIER_THRESHOLD_US) -> int:
        """统计异常值数量"""
        return sum(1 for s in self.samples if s >= threshold_us)
    
    def outlier_pct(self, threshold_us: float = OUTLIER_THRESHOLD_US) -> float:
        """统计异常值百分比"""
        if not self.samples:
            return 0
        return self.outlier_count(threshold_us) / len(self.samples) * 100
    
    def report(self) -> str:
        if not self.samples:
            return f"{self.name}: 无数据"
        
        return (
            f"{self.name}:\n"
            f"  样本数: {self.count()}\n"
            f"  平均值: {self.mean():.2f} μs ({self.mean()/1000:.3f} ms)\n"
            f"  中位数: {self.median():.2f} μs\n"
            f"  标准差: {self.stdev():.2f} μs\n"
            f"  最小值: {self.min_val():.2f} μs\n"
            f"  最大值: {self.max_val():.2f} μs ({self.max_val()/1000:.3f} ms)\n"
            f"  P50: {self.percentile(50):.2f} μs\n"
            f"  P90: {self.percentile(90):.2f} μs\n"
            f"  P99: {self.percentile(99):.2f} μs ({self.percentile(99)/1000:.3f} ms)\n"
            f"  异常(≥1ms): {self.outlier_count()} ({self.outlier_pct():.2f}%)"
        )


# ============================================================
# 基准测试策略
# ============================================================

class BenchmarkStrategy(Strategy):
    """
    基准测试策略
    
    专注于测量行情推送延迟，不发送订单
    """
    
    def __init__(self, strategy_id: str, expected_count: int = 1000):
        super().__init__()
        self.strategy_id = strategy_id
        self.expected_count = expected_count
        
        # 延迟统计（两种方式）
        self.latency_by_timestamp = LatencyStats("延迟(时间戳对比)")  # 使用消息中的时间戳
        self.latency_by_local = LatencyStats("延迟(本地计时)")        # 使用本地时间
        
        # 计数器
        self.ticker_count = 0
        self.warmup_complete = False
        
        # 序列号追踪（检测丢包）
        self.last_seq_num = 0
        self.missing_count = 0
        
        # 时间追踪
        self.start_time = time.time()
        self.last_recv_ns = 0
        
        # GC 控制
        self.gc_was_enabled = gc.isenabled()
        
        # 异常值详情
        self.outliers: List[Dict] = []
        
        print(f"[{self.strategy_id}] 基准测试策略初始化")
        print(f"  - 预期消息数: {expected_count}")
        print(f"  - 预热消息数: {WARMUP_TICKS}")
    
    def on_ticker(self, ticker: TickerData):
        """处理行情数据"""
        recv_time_ns = time.time_ns()
        self.ticker_count += 1
        
        # 预热阶段
        if self.ticker_count == WARMUP_TICKS:
            self.warmup_complete = True
            self.start_time = time.time()
            print(f"[{self.strategy_id}] ✓ 预热完成，开始正式测量")
            
            if DISABLE_GC and gc.isenabled():
                gc.disable()
        
        # 正式测量
        if self.warmup_complete:
            # 获取原始数据
            raw_data = ticker.__dict__ if hasattr(ticker, '__dict__') else {}
            
            # 方法1：时间戳对比法
            # 使用消息中的 send_time_ns 字段
            send_time_ns = getattr(ticker, 'timestamp_ns', 0)
            if send_time_ns > 0:
                latency_ns = recv_time_ns - send_time_ns
                latency_us = latency_ns / 1000.0
                
                if latency_us > 0:  # 排除负值（时钟不同步）
                    self.latency_by_timestamp.add(latency_us)
                    
                    # 记录异常值
                    if latency_us >= OUTLIER_THRESHOLD_US:
                        self.outliers.append({
                            "tick": self.ticker_count,
                            "latency_us": latency_us,
                            "method": "timestamp"
                        })
            
            # 方法2：本地计时法
            if self.last_recv_ns > 0:
                # 计算与上一条消息的时间差
                # 理论上应该约等于服务端的发送间隔
                interval_ns = recv_time_ns - self.last_recv_ns
                # 如果间隔显著大于预期（100ms），说明有延迟
                # 这里我们只记录接收间隔的抖动
                pass
            
            self.last_recv_ns = recv_time_ns
            
            # 检测丢包（通过序列号）
            # 需要从原始 JSON 中获取 seq_num
            # TickerData 可能没有这个字段，需要修改
        
        # 进度报告
        if self.ticker_count % 100 == 0:
            elapsed = time.time() - self.start_time
            rate = (self.ticker_count - WARMUP_TICKS) / elapsed if elapsed > 0 else 0
            print(f"[{self.strategy_id}] 收到: {self.ticker_count} | "
                  f"有效样本: {self.latency_by_timestamp.count()} | "
                  f"速率: {rate:.1f}/s | "
                  f"异常: {self.latency_by_timestamp.outlier_count()}")
        
        # 检查是否完成
        if self.ticker_count >= self.expected_count + WARMUP_TICKS:
            print(f"\n[{self.strategy_id}] ✓ 测试完成！")
            self._print_report()
            # 退出策略
            import sys
            sys.exit(0)
    
    def on_order(self, report: OrderReport):
        """不处理订单回报"""
        pass
    
    def on_stop(self):
        """策略停止时生成报告（包括被中断的情况）"""
        if self.latency_by_timestamp.count() > 0:
            print(f"\n[{self.strategy_id}] 策略停止，生成报告...")
            self._print_report()
    
    def _print_report(self):
        """打印测试报告"""
        elapsed = time.time() - self.start_time
        
        # 恢复 GC
        if DISABLE_GC and self.gc_was_enabled:
            gc.enable()
        
        print("\n" + "=" * 70)
        print(f"  延迟基准测试报告 - 策略 {self.strategy_id}")
        print("=" * 70)
        
        print(f"\n【测试配置】")
        print(f"  运行时间: {elapsed:.2f} 秒")
        print(f"  总消息数: {self.ticker_count}")
        print(f"  预热消息: {WARMUP_TICKS}")
        print(f"  有效样本: {self.latency_by_timestamp.count()}")
        
        print(f"\n【延迟统计】")
        print(self.latency_by_timestamp.report())
        
        # 判断是否满足要求
        p99 = self.latency_by_timestamp.percentile(99)
        max_lat = self.latency_by_timestamp.max_val()
        outlier_pct = self.latency_by_timestamp.outlier_pct()
        
        print(f"\n【评估结果】")
        if p99 < 1000:
            print(f"  ✅ P99 延迟 {p99:.0f}μs < 1ms，满足要求")
        else:
            print(f"  ❌ P99 延迟 {p99:.0f}μs ≥ 1ms，不满足要求")
        
        if max_lat < 1000:
            print(f"  ✅ 最大延迟 {max_lat:.0f}μs < 1ms，满足要求")
        else:
            print(f"  ⚠️ 最大延迟 {max_lat:.0f}μs ≥ 1ms，有异常值")
        
        if outlier_pct < 1:
            print(f"  ✅ 异常比例 {outlier_pct:.2f}% < 1%，稳定")
        else:
            print(f"  ⚠️ 异常比例 {outlier_pct:.2f}% ≥ 1%，需优化")
        
        print("\n" + "=" * 70)
        
        # 保存报告
        self._save_report()
    
    def _save_report(self):
        """保存报告到文件"""
        report = {
            "strategy_id": self.strategy_id,
            "timestamp": datetime.now().isoformat(),
            "config": {
                "expected_count": self.expected_count,
                "warmup_ticks": WARMUP_TICKS,
                "outlier_threshold_us": OUTLIER_THRESHOLD_US
            },
            "results": {
                "total_ticks": self.ticker_count,
                "valid_samples": self.latency_by_timestamp.count(),
                "duration_seconds": time.time() - self.start_time
            },
            "latency_timestamp": {
                "count": self.latency_by_timestamp.count(),
                "mean_us": self.latency_by_timestamp.mean(),
                "median_us": self.latency_by_timestamp.median(),
                "min_us": self.latency_by_timestamp.min_val(),
                "max_us": self.latency_by_timestamp.max_val(),
                "p50_us": self.latency_by_timestamp.percentile(50),
                "p90_us": self.latency_by_timestamp.percentile(90),
                "p99_us": self.latency_by_timestamp.percentile(99),
                "outlier_count": self.latency_by_timestamp.outlier_count(),
                "outlier_pct": self.latency_by_timestamp.outlier_pct()
            },
            "outliers": self.outliers[:20]  # 只保存前 20 个异常值
        }
        
        report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(report_dir, exist_ok=True)
        
        filename = f"benchmark_{self.strategy_id}_{int(time.time())}.json"
        filepath = os.path.join(report_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"[{self.strategy_id}] 报告已保存: {filepath}")
        
        return report


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="延迟基准测试")
    parser.add_argument("--id", type=int, default=1, help="策略ID编号")
    parser.add_argument("--count", type=int, default=1000, help="预期消息数量")
    parser.add_argument("--cpu", type=int, default=-1, help="绑定到指定 CPU 核心 (-1=不绑定)")
    parser.add_argument("--md-addr", type=str, default="ipc:///tmp/trading_md.ipc", help="行情地址")
    parser.add_argument("--order-addr", type=str, default="ipc:///tmp/trading_order.ipc", help="订单地址")
    parser.add_argument("--report-addr", type=str, default="ipc:///tmp/trading_report.ipc", help="回报地址")
    
    args = parser.parse_args()
    
    strategy_id = f"benchmark_{args.id}"
    
    print(f"\n{'='*70}")
    print(f"  ZeroMQ 延迟基准测试")
    print(f"  策略ID: {strategy_id}")
    print(f"  预期消息: {args.count}")
    print(f"{'='*70}\n")
    
    # 性能优化：尝试绑核和设置优先级
    if ENABLE_CPU_AFFINITY:
        cpu_id = args.cpu if args.cpu >= 0 else (args.id + 2)  # 默认从 CPU 3 开始
        pin_to_cpu(cpu_id)
    
    set_high_priority()
    
    # 创建客户端
    client = TradingClient(
        strategy_id=strategy_id,
        market_addr=args.md_addr,
        order_addr=args.order_addr,
        report_addr=args.report_addr
    )
    
    # 创建策略
    strategy = BenchmarkStrategy(
        strategy_id=strategy_id,
        expected_count=args.count
    )
    
    print(f"[{strategy_id}] 连接服务器...")
    
    # 运行
    client.run(strategy, log_interval=10)


if __name__ == "__main__":
    main()

