#!/usr/bin/env python3
"""
延迟测试客户端 - Python端

配合 test_latency_precise 使用，测量端到端延迟
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from journal_reader import JournalReader, TickerEvent

FEEDBACK_FILE = "/tmp/journal_feedback.txt"

def main():
    journal_file = "/tmp/trading_journal.dat"
    
    # 创建反馈文件（通知C++我们已就绪）
    with open(FEEDBACK_FILE, 'w') as f:
        f.write("ready\n")
    
    print("=" * 60)
    print("  Latency Test Client (Python Reader)")
    print("=" * 60)
    print(f"Journal: {journal_file}")
    print("Waiting for C++ Writer to send events...")
    print("=" * 60)
    print()
    
    # 创建Reader（不启用休眠，纯busy loop）
    reader = JournalReader(journal_file, busy_spin_count=999999)
    
    # 手动实现run循环（写入反馈）
    event_count = 0
    
    try:
        while True:
            remote_cursor = reader.get_remote_cursor()
            
            if reader.local_cursor < remote_cursor:
                # 有数据
                reader.mmap.seek(reader.local_cursor)
                header_data = reader.mmap.read(reader.FRAME_HEADER_SIZE)
                header = reader.parse_frame_header(header_data)
                
                msg_type = header['msg_type']
                
                if msg_type == 1:  # TICKER
                    frame_size = 128  # 新的TickerFrame大小
                    reader.mmap.seek(reader.local_cursor)
                    frame_data = reader.mmap.read(frame_size)
                    
                    ticker = reader.parse_ticker(frame_data)
                    
                    # 记录接收时间（纳秒）
                    recv_time_ns = time.time_ns()
                    
                    # 写入反馈文件
                    with open(FEEDBACK_FILE, 'w') as f:
                        f.write(f"{recv_time_ns}\n")
                    
                    reader.local_cursor += frame_size
                    event_count += 1
                    
                    if event_count % 100 == 0:
                        print(f"Received {event_count} events...")
                
                else:
                    break
            
            # 纯busy loop，不休眠
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        print(f"\nTotal events received: {event_count}")
        reader.close()

if __name__ == "__main__":
    main()

