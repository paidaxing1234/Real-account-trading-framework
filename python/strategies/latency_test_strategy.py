#!/usr/bin/env python3
"""
延迟测试策略
============

专门用于测量 ZeroMQ 框架各项延迟指标的测试策略。

测量指标：
1. 行情推送延迟：服务端发送 -> 策略接收
2. 订单发送延迟：策略发送 -> 服务端接收
3. 订单回报延迟：服务端发送 -> 策略接收
4. 订单往返延迟：策略发送 -> 收到回报

使用方法：
    python latency_test_strategy.py --id 1 --orders 100

作者: Sequence Framework
"""

import sys
import os
import time
import argparse
import json
import statistics
import gc
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

# 添加父目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_client import TradingClient, Strategy, TickerData, OrderReport, OrderRequest

# ============================================================
# 性能优化配置
# ============================================================

# 预热消息数（前 N 条消息不计入统计，用于消除冷启动影响）
WARMUP_TICKS = 50  # 高频模式下需要更多预热

# 是否在测量期间禁用 GC
DISABLE_GC = True

# ============================================================
# 延迟统计类
# ============================================================

@dataclass
class LatencyStats:
    """延迟统计数据"""
    name: str                           # 统计名称
    samples: List[float] = field(default_factory=list)  # 延迟样本（微秒）
    
    def add(self, latency_us: float):
        """添加一个延迟样本（微秒）"""
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
        """计算百分位数"""
        if not self.samples:
            return 0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * p / 100)
        idx = min(idx, len(sorted_samples) - 1)
        return sorted_samples[idx]
    
    def report(self) -> str:
        """生成统计报告"""
        if not self.samples:
            return f"{self.name}: 无数据"
        
        return (
            f"{self.name}:\n"
            f"  样本数: {self.count()}\n"
            f"  平均值: {self.mean():.2f} μs\n"
            f"  中位数: {self.median():.2f} μs\n"
            f"  标准差: {self.stdev():.2f} μs\n"
            f"  最小值: {self.min_val():.2f} μs\n"
            f"  最大值: {self.max_val():.2f} μs\n"
            f"  P50: {self.percentile(50):.2f} μs\n"
            f"  P90: {self.percentile(90):.2f} μs\n"
            f"  P99: {self.percentile(99):.2f} μs"
        )


# ============================================================
# 延迟测试策略
# ============================================================

class LatencyTestStrategy(Strategy):
    """
    延迟测试策略
    
    功能：
    1. 记录每条行情的接收延迟
    2. 按固定间隔发送测试订单
    3. 记录订单往返延迟
    4. 生成延迟统计报告
    """
    
    def __init__(self, strategy_id: str, num_orders: int = 100, order_interval: int = 10):
        """
        初始化延迟测试策略
        
        Args:
            strategy_id: 策略ID
            num_orders: 要发送的测试订单数量
            order_interval: 每隔多少条行情发送一个订单
        """
        super().__init__()  # 基类不需要参数
        self.strategy_id = strategy_id  # 手动设置（会被 TradingClient 覆盖）
        
        self.num_orders = num_orders
        self.order_interval = order_interval
        
        # 延迟统计（记录两份：原始 + 过滤后）
        self.md_latency_raw = LatencyStats("行情推送延迟(原始)")       # 包含所有数据
        self.md_latency_filtered = LatencyStats("行情推送延迟(过滤)")  # 过滤 >1ms 异常值
        self.order_rtt = LatencyStats("订单往返延迟")                  # 策略发送 -> 收到回报
        
        # 计数器
        self.ticker_count = 0
        self.orders_sent = 0
        self.orders_received = 0
        
        # 记录发送时间，用于计算往返延迟
        # key: client_order_id, value: send_time_ns
        self.pending_orders: Dict[str, int] = {}
        
        # 最新价格（用于生成订单）
        self.last_price = 0.0
        
        # 开始时间
        self.start_time = time.time()
        
        # 预热标志
        self.warmup_complete = False
        
        # GC 控制
        self.gc_was_enabled = gc.isenabled()
        
        print(f"[{self.strategy_id}] 延迟测试策略初始化")
        print(f"  - 计划发送订单数: {num_orders}")
        print(f"  - 订单间隔: 每 {order_interval} 条行情")
        print(f"  - 预热消息数: {WARMUP_TICKS}")
        print(f"  - 禁用GC: {DISABLE_GC}")
    
    def on_ticker(self, ticker: TickerData):
        """
        处理行情数据
        
        测量行情推送延迟 = 当前时间 - 服务端发送时间
        """
        self.ticker_count += 1
        
        # 预热阶段：前 N 条消息不计入统计（消除冷启动影响）
        if self.ticker_count == WARMUP_TICKS:
            self.warmup_complete = True
            print(f"[{self.strategy_id}] ✓ 预热完成，开始正式测量")
            
            # 预热完成后禁用 GC，避免 GC 暂停影响延迟测量
            if DISABLE_GC and gc.isenabled():
                gc.disable()
                print(f"[{self.strategy_id}] ✓ GC 已禁用")
        
        # 计算行情延迟（纳秒 -> 微秒）
        now_ns = time.time_ns()
        if ticker.timestamp_ns > 0 and self.warmup_complete:
            latency_ns = now_ns - ticker.timestamp_ns
            latency_us = latency_ns / 1000.0
            
            # 原始数据：全部记录
            self.md_latency_raw.add(latency_us)
            
            # 过滤数据：只记录 < 1ms 的（用于评估正常情况）
            if latency_us < 1000:
                self.md_latency_filtered.add(latency_us)
            else:
                # 记录异常值详情，帮助分析原因
                last_ns = getattr(self, '_last_tick_ns', now_ns)
                print(f"[⚠️ 异常延迟] 第 {self.ticker_count} 条 | "
                      f"延迟: {latency_us/1000:.2f} ms | "
                      f"距上次接收: {(now_ns - last_ns) / 1e6:.1f} ms")
            
            # 记录本次接收时间
            self._last_tick_ns = now_ns
        
        # 更新最新价格
        self.last_price = ticker.last_price
        
        # 每隔 order_interval 条行情发送一个测试订单
        if (self.ticker_count % self.order_interval == 0 and 
            self.orders_sent < self.num_orders and 
            self.last_price > 0):
            self._send_test_order()
        
        # 每 100 条行情打印进度
        if self.ticker_count % 100 == 0:
            elapsed = time.time() - self.start_time
            print(f"[{self.strategy_id}] 行情: {self.ticker_count} | "
                  f"订单: {self.orders_sent}/{self.num_orders} | "
                  f"回报: {self.orders_received} | "
                  f"耗时: {elapsed:.1f}s")
    
    def on_order(self, report: OrderReport):
        """
        处理订单回报（重写基类方法）
        
        测量订单往返延迟 = 当前时间 - 订单发送时间
        """
        self.orders_received += 1
        
        # 查找发送时间
        client_order_id = report.client_order_id
        if client_order_id in self.pending_orders:
            send_time_ns = self.pending_orders.pop(client_order_id)
            now_ns = time.time_ns()
            rtt_ns = now_ns - send_time_ns
            rtt_us = rtt_ns / 1000.0
            self.order_rtt.add(rtt_us)
            
            # 打印单条延迟（仅前几条）
            if self.orders_received <= 5:
                print(f"[{self.strategy_id}] 订单回报 #{self.orders_received} | "
                      f"RTT: {rtt_us:.2f} μs | "
                      f"状态: {report.status}")
        
        # 检查是否完成测试
        if self.orders_received >= self.num_orders:
            print(f"\n[{self.strategy_id}] ✓ 测试完成！")
            self._print_report()
    
    def _send_test_order(self):
        """发送测试订单"""
        self.orders_sent += 1
        
        # 生成订单ID（OKX 只允许字母和数字，不能有下划线！）
        # 格式: latencytest1order3 (去掉所有下划线)
        safe_strategy_id = self.strategy_id.replace("_", "")
        client_order_id = f"{safe_strategy_id}order{self.orders_sent}"
        
        # 记录发送时间
        send_time_ns = time.time_ns()
        self.pending_orders[client_order_id] = send_time_ns
        
        # 发送限价买单（价格设置得很低，不会真正成交）
        # 这样可以测试延迟而不产生实际交易
        test_price = self.last_price * 0.95  # 比当前价低 5%
        
        # 创建 OrderRequest 对象（使用自定义 client_order_id）
        order = OrderRequest(
            strategy_id=self.strategy_id,
            symbol="BTC-USDT",
            side="buy",
            order_type="limit",
            quantity=0.001,
            price=test_price,
            client_order_id=client_order_id  # 使用自定义订单ID
        )
        
        # 调用基类的 send_order 发送订单
        self.send_order(order)
    
    def _print_report(self):
        """打印延迟报告"""
        elapsed = time.time() - self.start_time
        
        # 恢复 GC
        if DISABLE_GC and self.gc_was_enabled:
            gc.enable()
            print(f"[{self.strategy_id}] ✓ GC 已恢复")
        
        print("\n" + "=" * 60)
        print(f"  延迟测试报告 - 策略 {self.strategy_id}")
        print("=" * 60)
        print(f"\n运行时间: {elapsed:.2f} 秒")
        print(f"行情总数: {self.ticker_count} (预热: {WARMUP_TICKS})")
        print(f"订单发送: {self.orders_sent}")
        print(f"订单回报: {self.orders_received}")
        
        # 计算异常值数量
        raw_count = self.md_latency_raw.count()
        filtered_count = self.md_latency_filtered.count()
        outlier_count = raw_count - filtered_count
        outlier_pct = (outlier_count / raw_count * 100) if raw_count > 0 else 0
        
        print(f"\n--- 行情延迟统计 ---")
        print(f"总样本: {raw_count} | 正常(<1ms): {filtered_count} | 异常(≥1ms): {outlier_count} ({outlier_pct:.1f}%)")
        
        print(f"\n【原始数据 - 包含所有值】")
        print(self.md_latency_raw.report())
        
        print(f"\n【过滤数据 - 仅 <1ms 的正常值】")
        print(self.md_latency_filtered.report())
        
        print(f"\n--- 订单延迟统计 ---\n")
        print(self.order_rtt.report())
        print("\n" + "=" * 60)
        
        # 保存报告到文件
        self._save_report()
    
    def _save_report(self):
        """保存报告到 JSON 文件"""
        report = {
            "strategy_id": self.strategy_id,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": time.time() - self.start_time,
            "ticker_count": self.ticker_count,
            "orders_sent": self.orders_sent,
            "orders_received": self.orders_received,
            "market_data_latency_raw": {
                "count": self.md_latency_raw.count(),
                "mean_us": self.md_latency_raw.mean(),
                "median_us": self.md_latency_raw.median(),
                "min_us": self.md_latency_raw.min_val(),
                "max_us": self.md_latency_raw.max_val(),
                "p50_us": self.md_latency_raw.percentile(50),
                "p90_us": self.md_latency_raw.percentile(90),
                "p99_us": self.md_latency_raw.percentile(99),
            },
            "market_data_latency_filtered": {
                "count": self.md_latency_filtered.count(),
                "mean_us": self.md_latency_filtered.mean(),
                "median_us": self.md_latency_filtered.median(),
                "min_us": self.md_latency_filtered.min_val(),
                "max_us": self.md_latency_filtered.max_val(),
                "p50_us": self.md_latency_filtered.percentile(50),
                "p90_us": self.md_latency_filtered.percentile(90),
                "p99_us": self.md_latency_filtered.percentile(99),
            },
            "order_rtt_latency": {
                "count": self.order_rtt.count(),
                "mean_us": self.order_rtt.mean(),
                "median_us": self.order_rtt.median(),
                "min_us": self.order_rtt.min_val(),
                "max_us": self.order_rtt.max_val(),
                "p50_us": self.order_rtt.percentile(50),
                "p90_us": self.order_rtt.percentile(90),
                "p99_us": self.order_rtt.percentile(99),
            }
        }
        
        # 保存到文件
        report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(report_dir, exist_ok=True)
        
        filename = f"latency_report_{self.strategy_id}_{int(time.time())}.json"
        filepath = os.path.join(report_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"[{self.strategy_id}] 报告已保存: {filepath}")
        
        return report


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="延迟测试策略")
    parser.add_argument("--id", type=int, default=1, help="策略ID编号")
    parser.add_argument("--orders", type=int, default=50, help="测试订单数量")
    parser.add_argument("--interval", type=int, default=20, help="订单间隔（每N条行情发一个订单）")
    parser.add_argument("--md-addr", type=str, default="ipc:///tmp/trading_md.ipc", help="行情地址")
    parser.add_argument("--order-addr", type=str, default="ipc:///tmp/trading_order.ipc", help="订单地址")
    parser.add_argument("--report-addr", type=str, default="ipc:///tmp/trading_report.ipc", help="回报地址")
    
    args = parser.parse_args()
    
    strategy_id = f"latency_test_{args.id}"
    
    print(f"\n{'='*60}")
    print(f"  ZeroMQ 延迟测试策略")
    print(f"  策略ID: {strategy_id}")
    print(f"{'='*60}\n")
    
    # 创建客户端（使用正确的参数名）
    client = TradingClient(
        strategy_id=strategy_id,
        market_addr=args.md_addr,
        order_addr=args.order_addr,
        report_addr=args.report_addr
    )
    
    # 创建策略
    strategy = LatencyTestStrategy(
        strategy_id=strategy_id,
        num_orders=args.orders,
        order_interval=args.interval
    )
    
    print(f"[{strategy_id}] 连接服务器...")
    print(f"  行情: {args.md_addr}")
    print(f"  订单: {args.order_addr}")
    print(f"  回报: {args.report_addr}")
    print()
    
    # 使用 run() 方法运行策略（正确的 API）
    # run() 内部会处理连接、主循环、断开
    client.run(strategy, log_interval=5)


if __name__ == "__main__":
    main()

