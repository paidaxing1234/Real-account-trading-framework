#!/usr/bin/env python3
"""
stress_test_client.py
多账户多策略持续压力测试

功能：
1. 多账户注册（OKX + Binance）
2. 多策略并发
3. 持续运行，定期发送订单
4. 行情数据统计（Ticker + K线）
5. 实时状态监控
"""
import zmq
import json
import time
import uuid
import random
import threading
import signal
import sys
import argparse
from collections import defaultdict
from datetime import datetime

# IPC 配置（与 C++ zmq_server.h 一致）
IPC_ORDER = "ipc:///tmp/seq_order.ipc"
IPC_REPORT = "ipc:///tmp/seq_report.ipc"
IPC_MARKET_DATA = "ipc:///tmp/seq_md.ipc"
# 按交易所分离的行情通道
IPC_MARKET_DATA_OKX = "ipc:///tmp/seq_md_okx.ipc"
IPC_MARKET_DATA_BINANCE = "ipc:///tmp/seq_md_binance.ipc"

# 全局状态
running = True
stats = {
    'sent': 0,
    'received': 0,
    'success': 0,
    'failed': 0,
    'latencies': [],
    'by_account': defaultdict(lambda: {'sent': 0, 'received': 0, 'success': 0}),
    'by_exchange': defaultdict(lambda: {'sent': 0, 'received': 0, 'success': 0}),
    # 行情数据详细统计
    'md_total': 0,
    'md_by_type': defaultdict(int),      # ticker, trade, depth, kline, mark_price...
    'md_by_exchange': defaultdict(int),  # okx, binance
    'md_symbols': set(),
    'kline_symbols': set(),
}
sent_orders = {}
stats_lock = threading.Lock()
start_time = time.time()

# 行情健康监控
# 格式: { 'okx': { 'BTC-USDT.ticker': {'last_time': time, 'count': n}, 'BTC-USDT.kline': {...} }, 'binance': {...} }
# key = symbol.type (例如: BTC-USDT.ticker, BTCUSDT.kline)
md_health = {
    'okx': defaultdict(lambda: {'last_time': 0, 'count': 0}),
    'binance': defaultdict(lambda: {'last_time': 0, 'count': 0}),
}
md_health_lock = threading.Lock()
MD_TIMEOUT_SECONDS = 30  # 超过30秒没有行情视为异常

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def signal_handler(sig, frame):
    global running
    print(f"\n{Colors.YELLOW}[中断] 收到停止信号，正在退出...{Colors.RESET}")
    running = False

def report_monitor():
    """后台接收回报"""
    global running, stats, sent_orders

    context = zmq.Context()
    sub = context.socket(zmq.SUB)
    sub.setsockopt(zmq.LINGER, 0)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有回报（可改为 "report.strategy_id" 只订阅特定策略）
    sub.setsockopt(zmq.RCVTIMEO, 100)
    sub.connect(IPC_REPORT)

    while running:
        try:
            msg = sub.recv_string()
            # 新格式: report.{strategy_id}|{json_data}
            # 兼容旧格式: {json_data}
            if '|' in msg:
                topic, json_str = msg.split('|', 1)
                data = json.loads(json_str)
            else:
                data = json.loads(msg)

            if data.get("type") in ["order_report", "cancel_report"]:
                with stats_lock:
                    stats['received'] += 1

                    client_order_id = data.get("client_order_id", "")
                    status = data.get("status", "")
                    exchange = data.get("exchange", "unknown")
                    strategy_id = data.get("strategy_id", "")

                    if status in ["accepted", "new", "filled", "partial_fill", "cancelled"]:
                        stats['success'] += 1
                        stats['by_exchange'][exchange]['success'] += 1
                        stats['by_account'][strategy_id]['success'] += 1
                    else:
                        stats['failed'] += 1

                    stats['by_exchange'][exchange]['received'] += 1
                    stats['by_account'][strategy_id]['received'] += 1

                    # 计算延迟
                    if client_order_id in sent_orders:
                        send_time = sent_orders.pop(client_order_id)
                        latency_ms = (time.time() - send_time) * 1000
                        stats['latencies'].append(latency_ms)
                        # 保持延迟列表不要太大
                        if len(stats['latencies']) > 10000:
                            stats['latencies'] = stats['latencies'][-5000:]

        except zmq.Again:
            continue
        except:
            continue

    sub.close()
    context.term()

def market_data_monitor():
    """后台监控行情数据（订阅所有通道：统一通道 + OKX + Binance）"""
    global running, stats, md_health

    context = zmq.Context()

    # 创建三个订阅者，分别订阅统一通道和交易所专用通道
    subs = []

    # 统一通道
    sub_unified = context.socket(zmq.SUB)
    sub_unified.setsockopt(zmq.LINGER, 0)
    sub_unified.setsockopt_string(zmq.SUBSCRIBE, "")
    sub_unified.setsockopt(zmq.RCVTIMEO, 100)
    sub_unified.connect(IPC_MARKET_DATA)
    subs.append(("unified", sub_unified))

    # OKX 专用通道
    sub_okx = context.socket(zmq.SUB)
    sub_okx.setsockopt(zmq.LINGER, 0)
    sub_okx.setsockopt_string(zmq.SUBSCRIBE, "")
    sub_okx.setsockopt(zmq.RCVTIMEO, 100)
    sub_okx.connect(IPC_MARKET_DATA_OKX)
    subs.append(("okx", sub_okx))

    # Binance 专用通道
    sub_binance = context.socket(zmq.SUB)
    sub_binance.setsockopt(zmq.LINGER, 0)
    sub_binance.setsockopt_string(zmq.SUBSCRIBE, "")
    sub_binance.setsockopt(zmq.RCVTIMEO, 100)
    sub_binance.connect(IPC_MARKET_DATA_BINANCE)
    subs.append(("binance", sub_binance))

    print(f"  {Colors.CYAN}已订阅行情通道: 统一通道 + OKX专用 + Binance专用{Colors.RESET}")

    while running:
        for channel_name, sub in subs:
            try:
                msg = sub.recv_string(zmq.NOBLOCK)
                # ZMQ 消息格式: topic|{json_data}
                # 例如: binance.ticker.BTCUSDT|{"type":"ticker",...}
                pipe_pos = msg.find('|')
                json_start = msg.find('{')

                if json_start >= 0:
                    # 解析 topic 前缀
                    if pipe_pos > 0 and pipe_pos < json_start:
                        topic = msg[:pipe_pos].strip()
                    else:
                        topic = msg[:json_start].strip() if json_start > 0 else ""

                    data = json.loads(msg[json_start:])

                    # 提取信息
                    symbol = data.get("symbol", "")
                    data_type = data.get("type", "unknown")

                    # 从 topic 解析交易所和数据类型
                    # topic 格式: exchange.type.symbol[.interval]
                    topic_parts = topic.split('.') if topic else []
                    if len(topic_parts) >= 2:
                        exchange = topic_parts[0].lower()  # okx, binance
                        if data_type == "unknown":
                            data_type = topic_parts[1].lower()  # ticker, kline, trade, depth...
                    else:
                        # 尝试从数据中获取交易所
                        exchange = data.get("exchange", "unknown").lower()

                    with stats_lock:
                        stats['md_total'] += 1
                        stats['md_by_type'][data_type] += 1
                        stats['md_by_exchange'][exchange] += 1

                        if symbol:
                            stats['md_symbols'].add(symbol)
                            if data_type == "kline":
                                stats['kline_symbols'].add(symbol)

                    # 更新行情健康状态 (key = symbol.type)
                    if symbol and exchange in ['okx', 'binance'] and data_type:
                        key = f"{symbol}.{data_type}"
                        with md_health_lock:
                            health = md_health[exchange][key]
                            health['last_time'] = time.time()
                            health['count'] += 1

            except zmq.Again:
                continue
            except:
                continue

        # 短暂休眠避免 CPU 占用过高
        time.sleep(0.001)

    for _, sub in subs:
        sub.close()
    context.term()

def register_accounts(push, accounts):
    """批量注册账户"""
    print(f"\n  {Colors.CYAN}注册 {len(accounts)} 个账户...{Colors.RESET}")

    for acc in accounts:
        reg_msg = {
            "type": "register_account",
            "strategy_id": acc['strategy_id'],
            "exchange": acc['exchange'],
            "api_key": f"test_key_{acc['exchange']}_{uuid.uuid4().hex[:8]}",
            "secret_key": f"test_secret_{uuid.uuid4().hex[:16]}",
            "is_testnet": True,
            "timestamp": int(time.time() * 1000)
        }
        if acc['exchange'] == 'okx':
            reg_msg['passphrase'] = "test_passphrase"

        push.send_string(json.dumps(reg_msg))
        time.sleep(0.05)

    time.sleep(0.5)
    print(f"  {Colors.GREEN}✓ 账户注册完成{Colors.RESET}")

def format_duration(seconds):
    """格式化时长"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def check_md_health():
    """检查行情健康状态，返回异常的交易对列表"""
    now = time.time()
    unhealthy = {'okx': [], 'binance': []}
    healthy_count = {'okx': 0, 'binance': 0}

    with md_health_lock:
        for exchange in ['okx', 'binance']:
            for symbol, health in md_health[exchange].items():
                if health['last_time'] > 0:
                    age = now - health['last_time']
                    if age > MD_TIMEOUT_SECONDS:
                        unhealthy[exchange].append((symbol, age, health['count']))
                    else:
                        healthy_count[exchange] += 1

    return unhealthy, healthy_count

def print_md_health_report():
    """打印行情健康报告"""
    unhealthy, healthy_count = check_md_health()

    print(f"\n  {Colors.YELLOW}【行情健康检查】{Colors.RESET}")
    print(f"    OKX:     {Colors.GREEN}{healthy_count['okx']} 正常{Colors.RESET}", end='')
    if unhealthy['okx']:
        print(f" | {Colors.RED}{len(unhealthy['okx'])} 异常{Colors.RESET}")
        for sym, age, cnt in unhealthy['okx'][:5]:  # 最多显示5个
            print(f"      {Colors.RED}✗ {sym}: {age:.0f}秒无数据 (累计{cnt}条){Colors.RESET}")
    else:
        print()

    print(f"    Binance: {Colors.GREEN}{healthy_count['binance']} 正常{Colors.RESET}", end='')
    if unhealthy['binance']:
        print(f" | {Colors.RED}{len(unhealthy['binance'])} 异常{Colors.RESET}")
        for sym, age, cnt in unhealthy['binance'][:5]:
            print(f"      {Colors.RED}✗ {sym}: {age:.0f}秒无数据 (累计{cnt}条){Colors.RESET}")
    else:
        print()

def print_status():
    """打印当前状态"""
    global stats, start_time

    elapsed = time.time() - start_time

    with stats_lock:
        order_rate = stats['sent'] / elapsed if elapsed > 0 else 0
        md_rate = stats['md_total'] / elapsed if elapsed > 0 else 0

        lost = stats['sent'] - stats['received']
        loss_pct = (lost / stats['sent'] * 100) if stats['sent'] > 0 else 0

        # 延迟统计
        if stats['latencies']:
            latencies = sorted(stats['latencies'][-1000:])
            avg_lat = sum(latencies) / len(latencies)
            p99_lat = latencies[int(len(latencies) * 0.99)] if len(latencies) > 100 else latencies[-1]
        else:
            avg_lat = 0
            p99_lat = 0

        # 按类型统计行情
        type_summary = ", ".join([f"{t}:{c}" for t, c in sorted(stats['md_by_type'].items())])
        exchange_summary = ", ".join([f"{e}:{c}" for e, c in sorted(stats['md_by_exchange'].items())])

    # 检查行情健康
    unhealthy, healthy_count = check_md_health()
    total_unhealthy = len(unhealthy['okx']) + len(unhealthy['binance'])

    # 状态指示
    if total_unhealthy > 0:
        health_indicator = f"{Colors.RED}⚠{total_unhealthy}{Colors.RESET}"
    else:
        health_indicator = f"{Colors.GREEN}✓{Colors.RESET}"

    print(f"\r{Colors.CYAN}[{format_duration(elapsed)}]{Colors.RESET} "
          f"订单: {stats['sent']} ({order_rate:.1f}/s) 成功:{stats['success']} 丢单:{lost} | "
          f"行情: {stats['md_total']} ({md_rate:.0f}/s) {health_indicator} | "
          f"延迟: {avg_lat:.1f}ms", end='', flush=True)

    # 如果有异常，打印详细信息
    if total_unhealthy > 0:
        print()  # 换行
        if unhealthy['okx']:
            okx_syms = [f"{s[0]}({s[1]:.0f}s)" for s in sorted(unhealthy['okx'], key=lambda x: -x[1])[:5]]
            print(f"    {Colors.RED}OKX异常({len(unhealthy['okx'])}): {', '.join(okx_syms)}{Colors.RESET}")
        if unhealthy['binance']:
            bn_syms = [f"{s[0]}({s[1]:.0f}s)" for s in sorted(unhealthy['binance'], key=lambda x: -x[1])[:5]]
            print(f"    {Colors.RED}Binance异常({len(unhealthy['binance'])}): {', '.join(bn_syms)}{Colors.RESET}")

def run_continuous_test(orders_per_sec, num_accounts=4, num_strategies=2, report_interval=5):
    """持续运行压力测试"""
    global running, stats, sent_orders, start_time

    # 重置统计
    stats = {
        'sent': 0, 'received': 0, 'success': 0, 'failed': 0,
        'latencies': [],
        'by_account': defaultdict(lambda: {'sent': 0, 'received': 0, 'success': 0}),
        'by_exchange': defaultdict(lambda: {'sent': 0, 'received': 0, 'success': 0}),
        'md_total': 0,
        'md_by_type': defaultdict(int),
        'md_by_exchange': defaultdict(int),
        'md_symbols': set(),
        'kline_symbols': set(),
    }
    sent_orders = {}
    start_time = time.time()

    context = zmq.Context()
    push = context.socket(zmq.PUSH)
    push.setsockopt(zmq.LINGER, 1000)
    push.connect(IPC_ORDER)

    # 启动监控线程
    threads = []

    report_thread = threading.Thread(target=report_monitor, daemon=True)
    report_thread.start()
    threads.append(report_thread)

    md_thread = threading.Thread(target=market_data_monitor, daemon=True)
    md_thread.start()
    threads.append(md_thread)

    time.sleep(0.5)

    # 创建多账户配置
    accounts = []
    exchanges = ['okx', 'binance']
    for i in range(num_accounts):
        exchange = exchanges[i % len(exchanges)]
        for j in range(num_strategies):
            accounts.append({
                'strategy_id': f"paper_account{i}_strategy{j}",
                'exchange': exchange,
            })

    # 注册账户
    register_accounts(push, accounts)

    print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.CYAN}       持续压力测试 (Ctrl+C 停止){Colors.RESET}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"  目标速率: {orders_per_sec} 订单/秒")
    print(f"  账户数量: {num_accounts} | 策略数: {len(accounts)}")
    print(f"  交易所: OKX + Binance")
    print(f"  数据订阅: Ticker + K线")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")

    # 交易对配置
    okx_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT"]
    binance_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

    last_status_time = time.time()
    batch_start = time.time()
    batch_count = 0
    order_interval = 1.0 / orders_per_sec if orders_per_sec > 0 else 0.1

    try:
        while running:
            # 发送订单
            acc = random.choice(accounts)
            exchange = acc['exchange']
            strategy_id = acc['strategy_id']

            if exchange == 'okx':
                symbol = random.choice(okx_symbols)
            else:
                symbol = random.choice(binance_symbols)

            order_id = f"stress_{uuid.uuid4().hex[:12]}"
            order = {
                "type": "order_request",
                "strategy_id": strategy_id,
                "exchange": exchange,
                "client_order_id": order_id,
                "symbol": symbol,
                "side": random.choice(["buy", "sell"]),
                "order_type": "limit",
                "quantity": round(random.uniform(0.001, 0.1), 4),
                "price": round(random.uniform(30000, 100000), 2),
                "td_mode": "cash" if exchange == 'okx' else "CROSSED",
                "timestamp": int(time.time() * 1000)
            }

            sent_orders[order_id] = time.time()
            push.send_string(json.dumps(order))

            with stats_lock:
                stats['sent'] += 1
                stats['by_account'][strategy_id]['sent'] += 1
                stats['by_exchange'][exchange]['sent'] += 1

            batch_count += 1

            # 速率控制
            if orders_per_sec >= 10:
                if batch_count >= orders_per_sec // 10:
                    elapsed = time.time() - batch_start
                    expected = batch_count / orders_per_sec
                    if elapsed < expected:
                        time.sleep(expected - elapsed)
                    batch_start = time.time()
                    batch_count = 0
            else:
                time.sleep(order_interval)

            # 定期打印状态
            if time.time() - last_status_time >= report_interval:
                print_status()
                last_status_time = time.time()

    except KeyboardInterrupt:
        pass

    running = False
    print(f"\n\n{Colors.YELLOW}正在停止...{Colors.RESET}")
    time.sleep(1)

    # 最终统计
    elapsed = time.time() - start_time

    print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.CYAN}       最终统计{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")

    print(f"\n  {Colors.YELLOW}【运行时间】{Colors.RESET} {format_duration(elapsed)}")

    print(f"\n  {Colors.YELLOW}【订��统计】{Colors.RESET}")
    print(f"    发送: {stats['sent']} ({stats['sent']/elapsed:.1f}/s)")
    print(f"    成功: {stats['success']}")
    print(f"    失败: {stats['failed']}")
    lost = stats['sent'] - stats['received']
    print(f"    丢单: {lost} ({lost/max(stats['sent'],1)*100:.2f}%)")

    print(f"\n  {Colors.YELLOW}【按交易所】{Colors.RESET}")
    for exchange, data in stats['by_exchange'].items():
        print(f"    {exchange.upper()}: 发送={data['sent']}, 成功={data['success']}")

    print(f"\n  {Colors.YELLOW}【行情数据】{Colors.RESET}")
    print(f"    总计: {stats['md_total']} ({stats['md_total']/elapsed:.0f}/s), {len(stats['md_symbols'])} 个交易对")

    # 按数据类型统计
    if stats['md_by_type']:
        print(f"\n    {Colors.CYAN}按类型:{Colors.RESET}")
        for data_type, count in sorted(stats['md_by_type'].items(), key=lambda x: -x[1]):
            rate = count / elapsed
            print(f"      {data_type}: {count} ({rate:.0f}/s)")

    # 按交易所统计
    if stats['md_by_exchange']:
        print(f"\n    {Colors.CYAN}按交易所:{Colors.RESET}")
        for exchange, count in sorted(stats['md_by_exchange'].items(), key=lambda x: -x[1]):
            rate = count / elapsed
            print(f"      {exchange.upper()}: {count} ({rate:.0f}/s)")

    # K线交易对
    if stats['kline_symbols']:
        print(f"\n    K线交易对: {len(stats['kline_symbols'])} 个")

    # 行情健康报告
    print_md_health_report()

    if stats['latencies']:
        latencies = sorted(stats['latencies'])
        print(f"\n  {Colors.YELLOW}【延迟统计】{Colors.RESET}")
        print(f"    平均: {sum(latencies)/len(latencies):.2f} ms")
        print(f"    P50:  {latencies[int(len(latencies)*0.50)]:.2f} ms")
        print(f"    P95:  {latencies[int(len(latencies)*0.95)]:.2f} ms")
        print(f"    P99:  {latencies[int(len(latencies)*0.99)]:.2f} ms")

    print(f"\n{Colors.GREEN}测试结束{Colors.RESET}\n")

    push.close()
    context.term()


def run_batch_test(total_orders, orders_per_sec, num_accounts=4, num_strategies=2):
    """运行固定数量的批量测试（原有功能保留）"""
    global running, stats, sent_orders, start_time

    stats = {
        'sent': 0, 'received': 0, 'success': 0, 'failed': 0,
        'latencies': [],
        'by_account': defaultdict(lambda: {'sent': 0, 'received': 0, 'success': 0}),
        'by_exchange': defaultdict(lambda: {'sent': 0, 'received': 0, 'success': 0}),
        'md_total': 0,
        'md_by_type': defaultdict(int),
        'md_by_exchange': defaultdict(int),
        'md_symbols': set(),
        'kline_symbols': set(),
    }
    sent_orders = {}
    start_time = time.time()

    context = zmq.Context()
    push = context.socket(zmq.PUSH)
    push.setsockopt(zmq.LINGER, 1000)
    push.connect(IPC_ORDER)

    # 启动监控线程
    report_thread = threading.Thread(target=report_monitor, daemon=True)
    report_thread.start()
    md_thread = threading.Thread(target=market_data_monitor, daemon=True)
    md_thread.start()

    time.sleep(0.5)

    # 创建账户
    accounts = []
    exchanges = ['okx', 'binance']
    for i in range(num_accounts):
        exchange = exchanges[i % len(exchanges)]
        for j in range(num_strategies):
            accounts.append({
                'strategy_id': f"paper_account{i}_strategy{j}",
                'exchange': exchange,
            })

    register_accounts(push, accounts)

    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.CYAN}       批量压力测试{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"  订单总数: {total_orders}")
    print(f"  目标速率: {orders_per_sec} 订单/秒")
    print(f"  账户: {num_accounts} | 策略: {len(accounts)}")
    print()

    okx_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT"]
    binance_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

    batch_start = time.time()
    batch_count = 0

    for i in range(total_orders):
        if not running:
            break

        acc = random.choice(accounts)
        exchange = acc['exchange']
        strategy_id = acc['strategy_id']
        symbol = random.choice(okx_symbols if exchange == 'okx' else binance_symbols)

        order_id = f"stress_{uuid.uuid4().hex[:12]}"
        order = {
            "type": "order_request",
            "strategy_id": strategy_id,
            "exchange": exchange,
            "client_order_id": order_id,
            "symbol": symbol,
            "side": random.choice(["buy", "sell"]),
            "order_type": "limit",
            "quantity": round(random.uniform(0.001, 0.1), 4),
            "price": round(random.uniform(30000, 100000), 2),
            "td_mode": "cash" if exchange == 'okx' else "CROSSED",
            "timestamp": int(time.time() * 1000)
        }

        sent_orders[order_id] = time.time()
        push.send_string(json.dumps(order))

        with stats_lock:
            stats['sent'] += 1
            stats['by_account'][strategy_id]['sent'] += 1
            stats['by_exchange'][exchange]['sent'] += 1

        batch_count += 1
        if batch_count >= orders_per_sec // 10:
            elapsed = time.time() - batch_start
            expected = batch_count / orders_per_sec
            if elapsed < expected:
                time.sleep(expected - elapsed)
            batch_start = time.time()
            batch_count = 0

        if (i + 1) % 500 == 0:
            print(f"  {Colors.CYAN}[Monitor]{Colors.RESET} 已接收 {stats['received']} 条回报, 成功: {stats['success']}")

    send_time = time.time() - start_time
    print(f"\n  {Colors.GREEN}发送完成{Colors.RESET} ({send_time:.2f}s, {stats['sent']/send_time:.1f}/s)")

    # 等待回报
    print(f"  等待回报...")
    wait_start = time.time()
    while time.time() - wait_start < 10:
        if stats['received'] >= stats['sent']:
            break
        time.sleep(0.1)

    running = False
    time.sleep(0.5)

    # 结果
    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.CYAN}       测试结果{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")

    print(f"  订单: 发送={stats['sent']}, 成功={stats['success']}, 失败={stats['failed']}")
    lost = stats['sent'] - stats['received']
    print(f"  丢单: {lost} ({lost/max(stats['sent'],1)*100:.2f}%)")

    # 行情统计
    print(f"\n  {Colors.YELLOW}【行情数据】{Colors.RESET}")
    print(f"    总计: {stats['md_total']} ({stats['md_total']/send_time:.0f}/s)")
    if stats['md_by_type']:
        type_str = ", ".join([f"{t}:{c}" for t, c in sorted(stats['md_by_type'].items(), key=lambda x: -x[1])])
        print(f"    按类型: {type_str}")
    if stats['md_by_exchange']:
        exchange_str = ", ".join([f"{e}:{c}" for e, c in sorted(stats['md_by_exchange'].items(), key=lambda x: -x[1])])
        print(f"    按交易所: {exchange_str}")

    if stats['latencies']:
        latencies = sorted(stats['latencies'])
        print(f"  延迟: 平均={sum(latencies)/len(latencies):.2f}ms, P99={latencies[int(len(latencies)*0.99)]:.2f}ms")

    result = lost == 0 and stats['failed'] == 0
    print(f"\n{Colors.GREEN}[PASS]{Colors.RESET}" if result else f"{Colors.RED}[FAIL]{Colors.RESET}")

    push.close()
    context.term()
    return result


def main():
    parser = argparse.ArgumentParser(description='多账户多策略压力测试')
    parser.add_argument('--continuous', '-c', action='store_true',
                        help='持续运行模式（Ctrl+C停止）')
    parser.add_argument('--orders', '-n', type=int, default=1000,
                        help='批量模式下的订单数量 (默认: 1000)')
    parser.add_argument('--rate', '-r', type=int, default=100,
                        help='每秒订单数 (默认: 100)')
    parser.add_argument('--accounts', '-a', type=int, default=4,
                        help='账户数量 (默认: 4)')
    parser.add_argument('--strategies', '-s', type=int, default=2,
                        help='每账户策略数 (默认: 2)')
    parser.add_argument('--interval', '-i', type=int, default=5,
                        help='状态报告间隔秒数 (默认: 5)')

    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.continuous:
        run_continuous_test(
            orders_per_sec=args.rate,
            num_accounts=args.accounts,
            num_strategies=args.strategies,
            report_interval=args.interval
        )
    else:
        success = run_batch_test(
            total_orders=args.orders,
            orders_per_sec=args.rate,
            num_accounts=args.accounts,
            num_strategies=args.strategies
        )
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
