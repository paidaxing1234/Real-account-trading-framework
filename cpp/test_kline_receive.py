#!/usr/bin/env python3
"""
测试K线数据接收
直接连接到服务器的行情通道，查看是否能收到K线数据
"""

import zmq
import json
import time
import signal
import sys

running = True

def signal_handler(sig, frame):
    global running
    print('\n停止测试...')
    running = False

signal.signal(signal.SIGINT, signal_handler)

def main():
    print("=" * 60)
    print("  K线数据接收测试")
    print("=" * 60)
    print()

    # 连接到服务器
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("ipc:///tmp/seq_md.ipc")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有消息
    socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒超时

    print("已连接到 ipc:///tmp/seq_md.ipc")
    print("等待K线数据...")
    print()

    kline_count = 0
    okx_kline_count = 0
    binance_kline_count = 0
    other_count = 0

    start_time = time.time()

    while running:
        try:
            msg = socket.recv()

            # 解析消息
            try:
                msg_str = msg.decode('utf-8')

                # 消息格式: topic|json_data
                if '|' in msg_str:
                    topic, json_str = msg_str.split('|', 1)
                    data = json.loads(json_str)
                else:
                    data = json.loads(msg_str)
                    topic = "unknown"

                msg_type = data.get('type', 'unknown')
                exchange = data.get('exchange', 'unknown')
                symbol = data.get('symbol', 'unknown')
                interval = data.get('interval', 'unknown')

                if msg_type == 'kline':
                    kline_count += 1
                    if exchange == 'okx':
                        okx_kline_count += 1
                    elif exchange == 'binance':
                        binance_kline_count += 1

                    # 显示前5条K线数据
                    if kline_count <= 5:
                        print(f"[K线 #{kline_count}]")
                        print(f"  Topic: {topic}")
                        print(f"  交易所: {exchange}")
                        print(f"  交易对: {symbol}")
                        print(f"  周期: {interval}")
                        print(f"  开盘: {data.get('open', 0)}")
                        print(f"  最高: {data.get('high', 0)}")
                        print(f"  最低: {data.get('low', 0)}")
                        print(f"  收盘: {data.get('close', 0)}")
                        print(f"  成交量: {data.get('volume', 0)}")
                        print()
                    elif kline_count % 10 == 0:
                        elapsed = time.time() - start_time
                        print(f"[统计] 已接收 {kline_count} 条K线 (OKX:{okx_kline_count} Binance:{binance_kline_count}) | 运行时间: {elapsed:.1f}秒")
                else:
                    other_count += 1
                    if other_count <= 3:
                        print(f"[其他消息] type={msg_type} exchange={exchange} symbol={symbol}")

            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
            except Exception as e:
                print(f"消息处理错误: {e}")

        except zmq.error.Again:
            # 超时，继续等待
            elapsed = time.time() - start_time
            if elapsed > 5 and kline_count == 0:
                print(f"[警告] 已等待 {elapsed:.1f} 秒，仍未收到任何K线数据")
                print("可能原因:")
                print("  1. 服务器未启动")
                print("  2. 服务器未订阅K线")
                print("  3. 交易所未推送K线数据")
            continue
        except Exception as e:
            print(f"接收错误: {e}")
            break

    # 显示统计
    print()
    print("=" * 60)
    print("  测试结果")
    print("=" * 60)
    print(f"  总K线数: {kline_count}")
    print(f"  OKX K线: {okx_kline_count}")
    print(f"  Binance K线: {binance_kline_count}")
    print(f"  其他消息: {other_count}")
    print(f"  运行时间: {time.time() - start_time:.1f} 秒")
    print("=" * 60)

    socket.close()
    context.term()

if __name__ == "__main__":
    main()
