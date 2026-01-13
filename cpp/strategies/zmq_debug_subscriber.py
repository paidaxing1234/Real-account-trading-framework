#!/usr/bin/env python3
"""
ZMQ 频道调试订阅器
订阅所有ZMQ频道并打印收到的消息，用于调试
"""

import zmq
import json
import threading
import time
from datetime import datetime

# IPC 地址配置（与 C++ 服务器一致）
class IpcAddresses:
    MARKET_DATA = "ipc:///tmp/seq_md.ipc"      # 行情数据
    ORDER = "ipc:///tmp/seq_order.ipc"          # 订单通道
    REPORT = "ipc:///tmp/seq_report.ipc"        # 回报通道
    QUERY = "ipc:///tmp/seq_query.ipc"          # 查询通道
    SUBSCRIBE = "ipc:///tmp/seq_subscribe.ipc"  # 订阅管理

# 颜色输出
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def format_timestamp():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def subscribe_market_data(context):
    """订阅行情数据"""
    socket = context.socket(zmq.SUB)
    socket.connect(IpcAddresses.MARKET_DATA)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有消息

    print(f"{Colors.GREEN}[行情] 已连接: {IpcAddresses.MARKET_DATA}{Colors.RESET}")

    while True:
        try:
            msg = socket.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            msg_type = data.get("type", "unknown")
            symbol = data.get("symbol", "")

            if msg_type == "ticker":
                price = data.get("price", 0)
                exchange = data.get("exchange", "")
                print(f"{Colors.GREEN}[{format_timestamp()}] [行情-Ticker] {exchange} {symbol}: {price}{Colors.RESET}")
            elif msg_type == "trade":
                price = data.get("price", 0)
                qty = data.get("quantity", 0)
                side = data.get("side", "")
                print(f"{Colors.GREEN}[{format_timestamp()}] [行情-Trade] {symbol}: {side} {qty} @ {price}{Colors.RESET}")
            elif msg_type == "kline":
                interval = data.get("interval", "")
                close = data.get("close", 0)
                print(f"{Colors.GREEN}[{format_timestamp()}] [行情-K线] {symbol} {interval}: close={close}{Colors.RESET}")
            else:
                print(f"{Colors.GREEN}[{format_timestamp()}] [行情-{msg_type}] {json.dumps(data, ensure_ascii=False)[:200]}{Colors.RESET}")
        except zmq.Again:
            time.sleep(0.001)
        except Exception as e:
            print(f"{Colors.RED}[行情错误] {e}{Colors.RESET}")

def subscribe_report(context):
    """订阅回报数据"""
    socket = context.socket(zmq.SUB)
    socket.connect(IpcAddresses.REPORT)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")

    print(f"{Colors.YELLOW}[回报] 已连接: {IpcAddresses.REPORT}{Colors.RESET}")

    while True:
        try:
            msg = socket.recv_string(zmq.NOBLOCK)
            # 消息格式: topic|json_data
            if "|" in msg:
                _, json_str = msg.split("|", 1)
                data = json.loads(json_str)
            else:
                data = json.loads(msg)
            msg_type = data.get("type", "unknown")

            if msg_type == "order_report":
                strategy_id = data.get("strategy_id", "")
                client_order_id = data.get("client_order_id", "")
                status = data.get("status", "")
                side = data.get("side", "N/A")
                price = data.get("filled_price", 0)
                qty = data.get("filled_quantity", 0)
                print(f"{Colors.YELLOW}[{format_timestamp()}] [回报-订单] {strategy_id} | {client_order_id} | {side} | 状态:{status} | 价格:{price} | 数量:{qty}{Colors.RESET}")
                print(f"{Colors.YELLOW}    完整数据: {json.dumps(data, ensure_ascii=False)}{Colors.RESET}")
            else:
                print(f"{Colors.YELLOW}[{format_timestamp()}] [回报-{msg_type}] {json.dumps(data, ensure_ascii=False)[:300]}{Colors.RESET}")
        except zmq.Again:
            time.sleep(0.001)
        except Exception as e:
            print(f"{Colors.RED}[回报错误] {e}{Colors.RESET}")

def main():
    print("=" * 60)
    print("  ZMQ 频道调试订阅器")
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    print()

    context = zmq.Context()

    # 启动订阅线程
    threads = []

    # 行情订阅
    t1 = threading.Thread(target=subscribe_market_data, args=(context,), daemon=True)
    t1.start()
    threads.append(t1)

    # 回报订阅
    t2 = threading.Thread(target=subscribe_report, args=(context,), daemon=True)
    t2.start()
    threads.append(t2)

    print()
    print(f"{Colors.CYAN}等待消息...{Colors.RESET}")
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{Colors.MAGENTA}停止订阅...{Colors.RESET}")
        context.term()

if __name__ == "__main__":
    main()
