#!/usr/bin/env python3
"""
测试ZMQ消息接收和解析
"""

import zmq
import json
import time

def main():
    print("=" * 60)
    print("  测试ZMQ消息接收")
    print("=" * 60)
    print()

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("ipc:///tmp/seq_md.ipc")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    socket.setsockopt(zmq.RCVTIMEO, 1000)

    print("已连接到 ipc:///tmp/seq_md.ipc")
    print("等待消息...")
    print()

    count = 0
    kline_count = 0

    for i in range(10):
        try:
            msg = socket.recv()
            msg_str = msg.decode('utf-8')
            count += 1

            print(f"[消息 #{count}]")
            print(f"  原始消息长度: {len(msg_str)} 字节")

            # 检查是否有主题前缀
            if '|' in msg_str:
                topic, json_str = msg_str.split('|', 1)
                print(f"  主题: {topic}")
                print(f"  JSON长度: {len(json_str)} 字节")

                try:
                    data = json.loads(json_str)
                    msg_type = data.get('type', 'unknown')
                    print(f"  类型: {msg_type}")

                    if msg_type == 'kline':
                        kline_count += 1
                        print(f"  交易所: {data.get('exchange')}")
                        print(f"  交易对: {data.get('symbol')}")
                        print(f"  周期: {data.get('interval')}")
                        print(f"  收盘价: {data.get('close')}")
                except json.JSONDecodeError as e:
                    print(f"  JSON解析失败: {e}")
            else:
                print("  没有主题前缀，尝试直接解析JSON...")
                try:
                    data = json.loads(msg_str)
                    print(f"  类型: {data.get('type')}")
                except json.JSONDecodeError as e:
                    print(f"  JSON解析失败: {e}")

            print()

        except zmq.error.Again:
            print(f"[超时] 等待第 {i+1} 次...")
            continue

    print()
    print("=" * 60)
    print(f"  总消息数: {count}")
    print(f"  K线消息数: {kline_count}")
    print("=" * 60)

    socket.close()
    context.term()

if __name__ == "__main__":
    main()
