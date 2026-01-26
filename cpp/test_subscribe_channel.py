#!/usr/bin/env python3
"""
测试订阅通道是否工作
直接向 ipc:///tmp/seq_subscribe.ipc 发送订阅请求
"""

import zmq
import json
import time

def main():
    print("=" * 60)
    print("  测试订阅通道")
    print("=" * 60)
    print()

    # 连接到订阅通道
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect("ipc:///tmp/seq_subscribe.ipc")

    print("已连接到 ipc:///tmp/seq_subscribe.ipc")
    print()

    # 发送订阅请求
    request = {
        "action": "subscribe",
        "channel": "kline",
        "symbol": "BTC-USDT-SWAP",
        "interval": "1s",
        "strategy_id": "test_script",
        "timestamp": int(time.time() * 1000)
    }

    print("发送订阅请求:")
    print(json.dumps(request, indent=2))
    print()

    socket.send_json(request)
    print("✓ 订阅请求已发送")
    print()

    # 等待一下
    time.sleep(2)

    socket.close()
    context.term()

    print("测试完成")
    print("请检查服务器日志，看是否收到订阅请求")

if __name__ == "__main__":
    main()
