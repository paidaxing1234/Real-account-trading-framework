#!/usr/bin/env python3
"""
多策略并发延迟测试
====================

测试实盘框架在多策略场景下的通信延迟：
1. 行情推送延迟：模拟高频行情（1ms间隔）推送到5个策略
2. 下单延迟：策略发出下单请求的处理延迟
3. 事件引擎分发延迟

测试配置：
- 5个策略并发运行
- 行情推送频率：1ms（1000次/秒）
- 测试时长：10秒（共约10000条行情）

运行: python test_multi_strategy_latency.py

作者: Sequence Framework
日期: 2024-12
"""

import asyncio
import time
import statistics
import gc
import threading
import os
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import EventEngine, Event, TickerData, KlineData
from adapters.okx import OKXRestAPI

# ============================================================
# 配置参数
# ============================================================

# 策略数量
NUM_STRATEGIES = 5

# 行情推送间隔（毫秒）
TICK_INTERVAL_MS = 1

# 测试时长（秒）
TEST_DURATION_SECONDS = 10

# 预热时间（秒）
WARMUP_SECONDS = 1

# 是否禁用GC
DISABLE_GC = True

# 异常阈值（微秒）
OUTLIER_THRESHOLD_US = 1000  # 1ms

# 模拟下单间隔（每N条行情下单一次）
ORDER_EVERY_N_TICKS = 100


# ============================================================
# 延迟统计类
# ============================================================

@dataclass
class LatencyStats:
    """延迟统计"""
    name: str
    samples: List[float] = field(default_factory=list)
    
    def add(self, latency_us: float):
        """添加样本（微秒）"""
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
        return sum(1 for s in self.samples if s >= threshold_us)
    
    def outlier_pct(self, threshold_us: float = OUTLIER_THRESHOLD_US) -> float:
        if not self.samples:
            return 0
        return self.outlier_count(threshold_us) / len(self.samples) * 100
    
    def report(self) -> str:
        if not self.samples:
            return f"{self.name}: 无数据"
        
        return (
            f"  样本数: {self.count()}\n"
            f"  平均值: {self.mean():.2f} μs ({self.mean()/1000:.3f} ms)\n"
            f"  中位数: {self.median():.2f} μs\n"
            f"  标准差: {self.stdev():.2f} μs\n"
            f"  最小值: {self.min_val():.2f} μs\n"
            f"  最大值: {self.max_val():.2f} μs ({self.max_val()/1000:.3f} ms)\n"
            f"  P50: {self.percentile(50):.2f} μs\n"
            f"  P90: {self.percentile(90):.2f} μs\n"
            f"  P95: {self.percentile(95):.2f} μs\n"
            f"  P99: {self.percentile(99):.2f} μs ({self.percentile(99)/1000:.3f} ms)\n"
            f"  P99.9: {self.percentile(99.9):.2f} μs\n"
            f"  异常(≥1ms): {self.outlier_count()} ({self.outlier_pct():.2f}%)"
        )


# ============================================================
# 高精度行情事件（带纳秒时间戳）
# ============================================================

class HighPrecisionTickerData(TickerData):
    """带高精度时间戳的行情数据"""
    
    __slots__ = ("send_time_ns", "seq_num")
    
    def __init__(
        self,
        symbol: str,
        last_price: float,
        send_time_ns: int = 0,
        seq_num: int = 0,
        **kwargs
    ):
        super().__init__(symbol=symbol, last_price=last_price, **kwargs)
        self.send_time_ns = send_time_ns  # 发送时的纳秒时间戳
        self.seq_num = seq_num  # 序列号


# ============================================================
# 测试策略
# ============================================================

class LatencyTestStrategy:
    """延迟测试策略"""
    
    def __init__(self, strategy_id: int, engine: EventEngine, order_callback: Callable = None):
        self.strategy_id = strategy_id
        self.engine = engine
        self.order_callback = order_callback
        
        # 延迟统计
        self.tick_latency = LatencyStats(f"策略{strategy_id}行情延迟")
        
        # 计数器
        self.tick_count = 0
        self.order_count = 0
        
        # 序列号追踪
        self.last_seq_num = -1  # -1 表示尚未初始化
        self.missing_count = 0
        
        # 是否在预热中
        self.warmup = True
        self.warmup_end_time = 0
        self.first_valid_seq = -1  # 预热结束后的第一个序列号
        
        # 注册监听器
        engine.register(HighPrecisionTickerData, self.on_ticker)
    
    def on_ticker(self, event: HighPrecisionTickerData):
        """处理行情事件"""
        recv_time_ns = time.time_ns()
        self.tick_count += 1
        
        # 预热阶段跳过统计
        if self.warmup:
            if time.time() > self.warmup_end_time:
                self.warmup = False
                print(f"  [策略{self.strategy_id}] 预热完成，开始正式测量")
            return
        
        # 计算延迟
        if event.send_time_ns > 0:
            latency_ns = recv_time_ns - event.send_time_ns
            latency_us = latency_ns / 1000.0
            
            if latency_us > 0:  # 排除异常值
                self.tick_latency.add(latency_us)
        
        # 检测丢包（只在预热结束后开始统计）
        if event.seq_num > 0:
            if self.last_seq_num == -1:
                # 预热结束后的第一条消息，初始化序列号
                self.last_seq_num = event.seq_num
                self.first_valid_seq = event.seq_num
            else:
                expected = self.last_seq_num + 1
                if event.seq_num > expected:
                    self.missing_count += (event.seq_num - expected)
                self.last_seq_num = event.seq_num
        
        # 模拟下单
        if self.tick_count % ORDER_EVERY_N_TICKS == 0 and self.order_callback:
            self.order_count += 1
            self.order_callback(self.strategy_id, event.symbol, event.last_price)


# ============================================================
# 行情生成器（模拟高频行情）
# ============================================================

class HighFrequencyTickGenerator:
    """高频行情生成器"""
    
    def __init__(self, engine: EventEngine, interval_ms: float = 1.0):
        self.engine = engine
        self.interval_ms = interval_ms
        self.interval_ns = int(interval_ms * 1_000_000)  # 转换为纳秒
        
        self.running = False
        self.seq_num = 0
        self.tick_count = 0
        
        # 统计
        self.send_latency = LatencyStats("发送间隔抖动")
        self.last_send_time_ns = 0
    
    def start(self):
        """启动生成器"""
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """停止生成器"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2.0)
    
    def _run_loop(self):
        """高频发送循环"""
        # 模拟价格
        base_price = 45000.0
        
        while self.running:
            loop_start = time.time_ns()
            
            # 生成行情
            self.seq_num += 1
            self.tick_count += 1
            
            # 模拟价格波动
            price = base_price + (self.seq_num % 100) * 0.1
            
            # 创建行情事件
            ticker = HighPrecisionTickerData(
                symbol="BTC-USDT-TEST",
                last_price=price,
                send_time_ns=loop_start,
                seq_num=self.seq_num,
                bid_price=price - 0.5,
                ask_price=price + 0.5,
            )
            
            # 推送到事件引擎
            self.engine.put(ticker)
            
            # 统计发送间隔
            if self.last_send_time_ns > 0:
                interval_us = (loop_start - self.last_send_time_ns) / 1000.0
                jitter = abs(interval_us - (self.interval_ms * 1000))
                self.send_latency.add(jitter)
            self.last_send_time_ns = loop_start
            
            # 精确等待
            elapsed_ns = time.time_ns() - loop_start
            sleep_ns = self.interval_ns - elapsed_ns
            if sleep_ns > 0:
                time.sleep(sleep_ns / 1_000_000_000)


# ============================================================
# 下单延迟测试
# ============================================================

class OrderLatencyTester:
    """下单延迟测试器"""
    
    def __init__(self, rest_api: OKXRestAPI = None):
        self.rest_api = rest_api
        self.order_latency = LatencyStats("下单延迟")
        self.order_count = 0
        self.lock = threading.Lock()
    
    def place_order(self, strategy_id: int, symbol: str, price: float):
        """
        模拟下单并测量延迟
        
        这里测量的是：
        1. 如果有真实API：REST API调用延迟
        2. 如果没有API：模拟下单处理延迟
        """
        start_ns = time.time_ns()
        
        if self.rest_api:
            # 真实下单（使用模拟盘）
            try:
                result = self.rest_api.place_order(
                    inst_id=symbol.replace("-TEST", ""),
                    td_mode="cash",
                    side="buy",
                    ord_type="limit",
                    px=str(price * 0.95),  # 挂一个不会成交的价格
                    sz="0.0001"  # 最小数量
                )
                # 立即撤单
                if result.get('code') == '0' and result.get('data'):
                    ord_id = result['data'][0].get('ordId')
                    if ord_id:
                        self.rest_api.cancel_order(
                            inst_id=symbol.replace("-TEST", ""),
                            ord_id=ord_id
                        )
            except Exception as e:
                pass  # 忽略错误
        else:
            # 模拟下单处理（模拟一些计算开销）
            _ = hash(f"{strategy_id}:{symbol}:{price}") * 1000
        
        end_ns = time.time_ns()
        latency_us = (end_ns - start_ns) / 1000.0
        
        with self.lock:
            self.order_latency.add(latency_us)
            self.order_count += 1


# ============================================================
# 主测试程序
# ============================================================

def run_latency_test(
    num_strategies: int = NUM_STRATEGIES,
    tick_interval_ms: float = TICK_INTERVAL_MS,
    duration_seconds: float = TEST_DURATION_SECONDS,
    warmup_seconds: float = WARMUP_SECONDS,
    use_real_api: bool = False,
    api_config: dict = None
):
    """
    运行延迟测试
    
    Args:
        num_strategies: 策略数量
        tick_interval_ms: 行情推送间隔（毫秒）
        duration_seconds: 测试时长（秒）
        warmup_seconds: 预热时间（秒）
        use_real_api: 是否使用真实API测试下单
        api_config: API配置（api_key, secret_key, passphrase）
    """
    print("\n" + "=" * 70)
    print("  多策略并发延迟测试")
    print("=" * 70)
    print(f"\n测试配置:")
    print(f"  - 策略数量: {num_strategies}")
    print(f"  - 行情推送间隔: {tick_interval_ms} ms")
    print(f"  - 测试时长: {duration_seconds} 秒")
    print(f"  - 预热时间: {warmup_seconds} 秒")
    print(f"  - 使用真实API: {use_real_api}")
    print(f"  - 预期行情数: {int((duration_seconds - warmup_seconds) * 1000 / tick_interval_ms)}")
    
    # 禁用GC以获得更准确的延迟测量
    gc_was_enabled = gc.isenabled()
    if DISABLE_GC:
        gc.disable()
        print(f"  - GC已禁用（测试期间）")
    
    # 创建事件引擎
    print("\n1️⃣  创建事件引擎...")
    engine = EventEngine()
    
    # 创建下单测试器
    rest_api = None
    if use_real_api and api_config:
        print("2️⃣  创建REST API客户端（模拟盘）...")
        rest_api = OKXRestAPI(
            api_key=api_config['api_key'],
            secret_key=api_config['secret_key'],
            passphrase=api_config['passphrase'],
            is_demo=True
        )
    
    order_tester = OrderLatencyTester(rest_api)
    
    # 创建策略
    print(f"3️⃣  创建 {num_strategies} 个策略...")
    strategies: List[LatencyTestStrategy] = []
    warmup_end_time = time.time() + warmup_seconds
    
    for i in range(num_strategies):
        strategy = LatencyTestStrategy(
            strategy_id=i + 1,
            engine=engine,
            order_callback=order_tester.place_order
        )
        strategy.warmup_end_time = warmup_end_time
        strategies.append(strategy)
        print(f"  - 策略 {i+1} 已创建")
    
    # 创建行情生成器
    print(f"4️⃣  创建高频行情生成器 ({tick_interval_ms}ms 间隔)...")
    tick_generator = HighFrequencyTickGenerator(engine, tick_interval_ms)
    
    # 启动测试
    print(f"\n5️⃣  开始测试...")
    print(f"  - 预热中... ({warmup_seconds}秒)")
    
    test_start = time.time()
    tick_generator.start()
    
    # 等待预热完成
    time.sleep(warmup_seconds)
    print(f"  - 预热完成，开始正式测量...")
    
    # 正式测试
    actual_test_duration = duration_seconds - warmup_seconds
    
    # 每秒打印进度
    for i in range(int(actual_test_duration)):
        time.sleep(1)
        total_ticks = sum(s.tick_count for s in strategies)
        total_samples = sum(s.tick_latency.count() for s in strategies)
        print(f"  - 进度: {i+1}/{int(actual_test_duration)}s | "
              f"行情: {tick_generator.tick_count} | "
              f"策略接收: {total_ticks} | "
              f"有效样本: {total_samples} | "
              f"下单: {order_tester.order_count}")
    
    # 停止测试
    print(f"\n6️⃣  停止测试...")
    tick_generator.stop()
    test_duration = time.time() - test_start
    
    # 恢复GC
    if DISABLE_GC and gc_was_enabled:
        gc.enable()
    
    # 生成报告
    print("\n" + "=" * 70)
    print("  测试报告")
    print("=" * 70)
    
    print(f"\n【总体统计】")
    print(f"  实际测试时长: {test_duration:.2f} 秒")
    print(f"  行情生成数量: {tick_generator.tick_count}")
    print(f"  行情推送速率: {tick_generator.tick_count / test_duration:.1f} 条/秒")
    print(f"  下单次数: {order_tester.order_count}")
    
    # 汇总所有策略的延迟
    all_tick_latencies = LatencyStats("全部策略行情延迟")
    
    print(f"\n【各策略行情延迟】")
    for strategy in strategies:
        print(f"\n  策略 {strategy.strategy_id}:")
        print(f"    接收行情数: {strategy.tick_count}")
        print(f"    有效样本数: {strategy.tick_latency.count()}")
        print(f"    丢包数: {strategy.missing_count}")
        
        if strategy.tick_latency.count() > 0:
            print(f"    平均延迟: {strategy.tick_latency.mean():.2f} μs")
            print(f"    P99延迟: {strategy.tick_latency.percentile(99):.2f} μs")
            print(f"    最大延迟: {strategy.tick_latency.max_val():.2f} μs")
            print(f"    异常(≥1ms): {strategy.tick_latency.outlier_count()} ({strategy.tick_latency.outlier_pct():.2f}%)")
        
        # 汇总
        all_tick_latencies.samples.extend(strategy.tick_latency.samples)
    
    print(f"\n【汇总行情延迟（{num_strategies}个策略）】")
    print(all_tick_latencies.report())
    
    print(f"\n【发送间隔抖动】")
    print(tick_generator.send_latency.report())
    
    if order_tester.order_count > 0:
        print(f"\n【下单延迟】")
        print(order_tester.order_latency.report())
    
    # 评估结果
    print(f"\n【评估结果】")
    
    p99 = all_tick_latencies.percentile(99)
    max_lat = all_tick_latencies.max_val()
    outlier_pct = all_tick_latencies.outlier_pct()
    
    if p99 < 100:
        print(f"  ✅ P99 行情延迟 {p99:.0f}μs < 100μs，非常优秀")
    elif p99 < 1000:
        print(f"  ✅ P99 行情延迟 {p99:.0f}μs < 1ms，满足要求")
    else:
        print(f"  ❌ P99 行情延迟 {p99:.0f}μs ≥ 1ms，需要优化")
    
    if max_lat < 1000:
        print(f"  ✅ 最大行情延迟 {max_lat:.0f}μs < 1ms，满足要求")
    elif max_lat < 10000:
        print(f"  ⚠️ 最大行情延迟 {max_lat:.0f}μs < 10ms，有少量异常")
    else:
        print(f"  ❌ 最大行情延迟 {max_lat:.0f}μs ≥ 10ms，需要优化")
    
    if outlier_pct < 0.1:
        print(f"  ✅ 异常比例 {outlier_pct:.3f}% < 0.1%，非常稳定")
    elif outlier_pct < 1:
        print(f"  ✅ 异常比例 {outlier_pct:.2f}% < 1%，稳定")
    else:
        print(f"  ⚠️ 异常比例 {outlier_pct:.2f}% ≥ 1%，需要优化")
    
    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "num_strategies": num_strategies,
            "tick_interval_ms": tick_interval_ms,
            "duration_seconds": duration_seconds,
            "warmup_seconds": warmup_seconds,
            "use_real_api": use_real_api
        },
        "results": {
            "actual_duration": test_duration,
            "total_ticks": tick_generator.tick_count,
            "tick_rate": tick_generator.tick_count / test_duration,
            "total_orders": order_tester.order_count
        },
        "tick_latency": {
            "total_samples": all_tick_latencies.count(),
            "mean_us": all_tick_latencies.mean(),
            "median_us": all_tick_latencies.median(),
            "min_us": all_tick_latencies.min_val(),
            "max_us": all_tick_latencies.max_val(),
            "p50_us": all_tick_latencies.percentile(50),
            "p90_us": all_tick_latencies.percentile(90),
            "p95_us": all_tick_latencies.percentile(95),
            "p99_us": all_tick_latencies.percentile(99),
            "p999_us": all_tick_latencies.percentile(99.9),
            "outlier_count": all_tick_latencies.outlier_count(),
            "outlier_pct": all_tick_latencies.outlier_pct()
        },
        "order_latency": {
            "total_orders": order_tester.order_count,
            "mean_us": order_tester.order_latency.mean(),
            "p99_us": order_tester.order_latency.percentile(99),
            "max_us": order_tester.order_latency.max_val()
        } if order_tester.order_count > 0 else None,
        "strategies": [
            {
                "id": s.strategy_id,
                "tick_count": s.tick_count,
                "samples": s.tick_latency.count(),
                "mean_us": s.tick_latency.mean(),
                "p99_us": s.tick_latency.percentile(99),
                "max_us": s.tick_latency.max_val(),
                "missing_count": s.missing_count
            }
            for s in strategies
        ]
    }
    
    report_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(report_dir, exist_ok=True)
    
    filename = f"latency_report_{int(time.time())}.json"
    filepath = os.path.join(report_dir, filename)
    
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📊 报告已保存: {filepath}")
    print("\n" + "=" * 70)
    
    return report


# ============================================================
# 真实OKX WebSocket延迟测试
# ============================================================

async def run_real_websocket_latency_test(duration_seconds: int = 60):
    """
    使用真实OKX WebSocket测试延迟
    
    注意：OKX的行情推送频率通常是100-200ms左右，不是1ms
    """
    from adapters.okx import OKXMarketDataAdapter
    
    print("\n" + "=" * 70)
    print("  真实OKX WebSocket延迟测试")
    print("=" * 70)
    
    # 创建事件引擎
    engine = EventEngine()
    
    # 延迟统计
    latency_stats = LatencyStats("WebSocket行情延迟")
    tick_count = 0
    
    def on_ticker(event: TickerData):
        nonlocal tick_count
        tick_count += 1
        
        recv_time_ms = int(time.time() * 1000)
        if event.timestamp:
            latency_ms = recv_time_ms - event.timestamp
            latency_us = latency_ms * 1000
            if latency_us > 0 and latency_us < 1000000:  # 过滤异常值
                latency_stats.add(latency_us)
        
        if tick_count % 10 == 0:
            print(f"  收到 {tick_count} 条行情 | "
                  f"样本: {latency_stats.count()} | "
                  f"平均延迟: {latency_stats.mean():.0f}μs")
    
    engine.register(TickerData, on_ticker)
    
    # 创建适配器
    print("\n1️⃣  创建OKX行情适配器...")
    adapter = OKXMarketDataAdapter(engine, is_demo=True)
    
    try:
        # 启动
        print("2️⃣  连接OKX WebSocket...")
        await adapter.start()
        
        # 订阅多个交易对
        symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
        print(f"3️⃣  订阅 {len(symbols)} 个交易对...")
        for symbol in symbols:
            await adapter.subscribe_ticker(symbol)
            await asyncio.sleep(0.1)
        
        # 等待测试完成
        print(f"4️⃣  测试运行 {duration_seconds} 秒...")
        await asyncio.sleep(duration_seconds)
        
    finally:
        await adapter.stop()
    
    # 打印结果
    print("\n" + "=" * 70)
    print("  测试结果")
    print("=" * 70)
    print(f"\n总行情数: {tick_count}")
    print(f"\n【延迟统计】")
    print(latency_stats.report())
    print("\n" + "=" * 70)


# ============================================================
# 主函数
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="多策略并发延迟测试")
    parser.add_argument("--strategies", "-s", type=int, default=NUM_STRATEGIES,
                        help=f"策略数量 (默认: {NUM_STRATEGIES})")
    parser.add_argument("--interval", "-i", type=float, default=TICK_INTERVAL_MS,
                        help=f"行情推送间隔(ms) (默认: {TICK_INTERVAL_MS})")
    parser.add_argument("--duration", "-d", type=float, default=TEST_DURATION_SECONDS,
                        help=f"测试时长(秒) (默认: {TEST_DURATION_SECONDS})")
    parser.add_argument("--warmup", "-w", type=float, default=WARMUP_SECONDS,
                        help=f"预热时间(秒) (默认: {WARMUP_SECONDS})")
    parser.add_argument("--real-ws", action="store_true",
                        help="使用真实OKX WebSocket测试")
    parser.add_argument("--real-api", action="store_true",
                        help="使用真实API测试下单延迟（需要配置API密钥）")
    
    args = parser.parse_args()
    
    if args.real_ws:
        # 真实WebSocket测试
        asyncio.run(run_real_websocket_latency_test(int(args.duration)))
    else:
        # 模拟高频测试
        api_config = None
        if args.real_api:
            # 这里可以从环境变量或配置文件读取
            api_config = {
                "api_key": os.environ.get("OKX_API_KEY", ""),
                "secret_key": os.environ.get("OKX_SECRET_KEY", ""),
                "passphrase": os.environ.get("OKX_PASSPHRASE", "")
            }
            if not all(api_config.values()):
                print("⚠️  警告：未配置API密钥，下单测试将使用模拟模式")
                api_config = None
        
        run_latency_test(
            num_strategies=args.strategies,
            tick_interval_ms=args.interval,
            duration_seconds=args.duration,
            warmup_seconds=args.warmup,
            use_real_api=bool(api_config),
            api_config=api_config
        )


if __name__ == "__main__":
    main()

