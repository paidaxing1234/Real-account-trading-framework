#!/usr/bin/env python3
"""
Journal Reader - Python端的无锁队列读取器

使用 mmap + busy loop 实现纳秒级延迟
"""

import mmap
import struct
import time
import os
from dataclasses import dataclass
from typing import Optional, Callable

@dataclass
class TickerEvent:
    """Ticker事件"""
    symbol: str
    last_price: float
    bid_price: float
    ask_price: float
    volume: float
    gen_time_ns: int
    
    def __repr__(self):
        return f"Ticker({self.symbol} @ {self.last_price:.2f})"

@dataclass
class OrderEvent:
    """Order事件"""
    symbol: str
    order_id: int
    side: int
    order_type: int
    price: float
    quantity: float
    gen_time_ns: int

class JournalReader:
    """
    Journal读取器
    
    使用busy loop主动轮询，实现极低延迟
    """
    
    PAGE_HEADER_SIZE = 64
    FRAME_HEADER_SIZE = 32
    
    def __init__(self, file_path: str, busy_spin_count: int = 1000):
        """
        初始化Reader
        
        Args:
            file_path: Journal文件路径
            busy_spin_count: busy loop次数（之后开始休眠）
        """
        self.file_path = file_path
        self.busy_spin_count = busy_spin_count
        
        # 等待文件创建
        print(f"[JournalReader] Waiting for journal file: {file_path}")
        while not os.path.exists(file_path):
            time.sleep(0.01)
        
        # 等待文件有内容
        while os.path.getsize(file_path) == 0:
            time.sleep(0.01)
        
        # 打开文件
        self.fd = os.open(file_path, os.O_RDONLY)
        
        # 获取文件大小
        file_size = os.fstat(self.fd).st_size
        
        # mmap映射（只读）
        self.mmap = mmap.mmap(self.fd, file_size, mmap.MAP_SHARED, mmap.PROT_READ)
        
        # 初始化本地游标（从数据区开始）
        self.local_cursor = self.PAGE_HEADER_SIZE
        
        print(f"[JournalReader] Initialized: {file_path} (size: {file_size / 1024 / 1024:.1f} MB)")
    
    def get_remote_cursor(self) -> int:
        """读取写入端的游标"""
        self.mmap.seek(0)
        return struct.unpack('I', self.mmap.read(4))[0]
    
    def parse_frame_header(self, data: bytes) -> dict:
        """解析FrameHeader"""
        length = struct.unpack('I', data[0:4])[0]
        msg_type = struct.unpack('I', data[4:8])[0]
        gen_time_ns = struct.unpack('Q', data[8:16])[0]
        trigger_time_ns = struct.unpack('Q', data[16:24])[0]
        source = struct.unpack('I', data[24:28])[0]
        dest = struct.unpack('I', data[28:32])[0]
        
        return {
            'length': length,
            'msg_type': msg_type,
            'gen_time_ns': gen_time_ns,
            'trigger_time_ns': trigger_time_ns,
            'source': source,
            'dest': dest,
        }
    
    def parse_ticker(self, data: bytes) -> TickerEvent:
        """解析Ticker帧（128字节）"""
        header = self.parse_frame_header(data[0:self.FRAME_HEADER_SIZE])
        
        # TickerFrame: 从32字节开始
        offset = self.FRAME_HEADER_SIZE
        symbol = data[offset:offset+24].decode('utf-8').rstrip('\x00')
        last_price = struct.unpack('d', data[offset+24:offset+32])[0]
        bid_price = struct.unpack('d', data[offset+32:offset+40])[0]
        ask_price = struct.unpack('d', data[offset+40:offset+48])[0]
        volume = struct.unpack('d', data[offset+48:offset+56])[0]
        
        return TickerEvent(
            symbol=symbol,
            last_price=last_price,
            bid_price=bid_price,
            ask_price=ask_price,
            volume=volume,
            gen_time_ns=header['gen_time_ns']
        )
    
    def parse_order(self, data: bytes) -> OrderEvent:
        """解析Order帧（256字节）"""
        header = self.parse_frame_header(data[0:self.FRAME_HEADER_SIZE])
        
        # OrderFrame: 从32字节开始
        offset = self.FRAME_HEADER_SIZE
        symbol = data[offset:offset+24].decode('utf-8').rstrip('\x00')
        order_id = struct.unpack('Q', data[offset+24:offset+32])[0]
        side = struct.unpack('I', data[offset+32:offset+36])[0]
        order_type = struct.unpack('I', data[offset+36:offset+40])[0]
        price = struct.unpack('d', data[offset+48:offset+56])[0]
        quantity = struct.unpack('d', data[offset+56:offset+64])[0]
        
        return OrderEvent(
            symbol=symbol,
            order_id=order_id,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            gen_time_ns=header['gen_time_ns']
        )
    
    def run(self, 
            on_ticker: Optional[Callable[[TickerEvent], None]] = None,
            on_order: Optional[Callable[[OrderEvent], None]] = None,
            max_events: int = 0):
        """
        主循环：Busy Loop
        
        Args:
            on_ticker: Ticker事件回调
            on_order: Order事件回调
            max_events: 最大处理事件数（0=无限）
        """
        print("[JournalReader] Starting busy loop...")
        
        event_count = 0
        start_time = time.time()
        idle_count = 0
        
        # 延迟统计
        latency_samples = []
        
        while True:
            # 1. 检查远程游标
            remote_cursor = self.get_remote_cursor()
            
            # 2. 有新数据？
            if self.local_cursor < remote_cursor:
                # 有数据！
                idle_count = 0
                
                # 读取帧头
                self.mmap.seek(self.local_cursor)
                header_data = self.mmap.read(self.FRAME_HEADER_SIZE)
                header = self.parse_frame_header(header_data)
                
                msg_type = header['msg_type']
                
                # 读取完整帧
                if msg_type == 1:  # TICKER
                    frame_size = 128  # 新的TickerFrame大小
                    self.mmap.seek(self.local_cursor)
                    frame_data = self.mmap.read(frame_size)
                    
                    ticker = self.parse_ticker(frame_data)
                    
                    # 计算延迟（纳秒）
                    now_ns = time.time_ns()
                    latency_ns = now_ns - ticker.gen_time_ns
                    latency_samples.append(latency_ns)
                    
                    # 回调
                    if on_ticker:
                        on_ticker(ticker)
                    
                    self.local_cursor += frame_size
                    
                elif msg_type == 2:  # ORDER
                    frame_size = 256  # 新的OrderFrame大小
                    self.mmap.seek(self.local_cursor)
                    frame_data = self.mmap.read(frame_size)
                    
                    order = self.parse_order(frame_data)
                    
                    if on_order:
                        on_order(order)
                    
                    self.local_cursor += frame_size
                
                else:
                    print(f"[JournalReader] Unknown msg_type: {msg_type}")
                    break
                
                event_count += 1
                
                # 定期打印统计
                if event_count % 10000 == 0:
                    elapsed = time.time() - start_time
                    throughput = event_count / elapsed
                    
                    if latency_samples:
                        avg_latency = sum(latency_samples) / len(latency_samples)
                        min_latency = min(latency_samples)
                        max_latency = max(latency_samples)
                        
                        print(f"[Stats] Events: {event_count}, "
                              f"Throughput: {throughput:.0f}/s, "
                              f"Latency(ns): avg={avg_latency:.0f}, "
                              f"min={min_latency:.0f}, max={max_latency:.0f}")
                        
                        latency_samples.clear()
                
                # 达到最大事件数？
                if max_events > 0 and event_count >= max_events:
                    break
            
            else:
                # 无数据
                idle_count += 1
                
                # 动态休眠策略
                if idle_count < self.busy_spin_count:
                    # 纯busy loop（极低延迟）
                    pass
                elif idle_count < self.busy_spin_count * 10:
                    # 极短休眠
                    time.sleep(0.000001)  # 1微秒
                else:
                    # 稍长休眠
                    time.sleep(0.00001)   # 10微秒
        
        # 最终统计
        elapsed = time.time() - start_time
        throughput = event_count / elapsed if elapsed > 0 else 0
        
        print(f"\n[JournalReader] Finished!")
        print(f"  Total Events: {event_count}")
        print(f"  Total Time: {elapsed:.3f}s")
        print(f"  Throughput: {throughput:.0f} events/s")
    
    def close(self):
        """关闭Reader"""
        if hasattr(self, 'mmap'):
            self.mmap.close()
        if hasattr(self, 'fd'):
            os.close(self.fd)

# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 journal_reader.py <journal_file>")
        sys.exit(1)
    
    journal_file = sys.argv[1]
    
    def on_ticker(ticker: TickerEvent):
        print(f"Received: {ticker}")
    
    reader = JournalReader(journal_file)
    
    try:
        reader.run(on_ticker=on_ticker, max_events=100)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        reader.close()

