#!/usr/bin/env python3
"""
OKX WebSocket K线订阅测试

支持订阅多个币种的K线数据

运行: python test_kline_websocket.py
"""

import asyncio
from adapters.okx.websocket import OKXWebSocketPublic


# 主流币种列表
SPOT_PAIRS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOGE-USDT",
    "ADA-USDT", "AVAX-USDT", "DOT-USDT", "MATIC-USDT", "LINK-USDT",
    "UNI-USDT", "ATOM-USDT", "LTC-USDT", "BCH-USDT", "ETC-USDT",
    "FIL-USDT", "APT-USDT", "ARB-USDT", "OP-USDT", "NEAR-USDT"
]


async def main():
    print("=" * 60)
    print("  OKX WebSocket K线订阅测试")
    print("=" * 60)
    
    # 创建 business 端点的 WebSocket（K线必须使用此端点）
    ws = OKXWebSocketPublic(is_demo=True, url_type="business")
    
    # 统计
    kline_count = 0
    
    def on_kline(data):
        nonlocal kline_count
        kline_count += 1
        
        arg = data.get('arg', {})
        kline_data = data.get('data', [[]])[0]
        
        if len(kline_data) >= 6:
            inst_id = arg.get('instId', 'N/A')
            channel = arg.get('channel', 'N/A')
            ts, o, h, l, c, vol = kline_data[:6]
            
            # 第9个字段是 confirm：0=未完结, 1=已完结
            confirm = kline_data[8] if len(kline_data) > 8 else "?"
            status = "✅完结" if confirm == "1" else "⏳更新"
            
            print(f"📊 {inst_id:15} | {channel:10} | "
                  f"O:{float(o):>10.2f} H:{float(h):>10.2f} "
                  f"L:{float(l):>10.2f} C:{float(c):>10.2f} "
                  f"V:{float(vol):>12.4f} | {status}")
    
    try:
        # 连接
        print("\n1️⃣  连接 WebSocket...")
        await ws.connect()
        print(f"   URL: {ws.url}")
        
        # 订阅K线
        print(f"\n2️⃣  订阅 {len(SPOT_PAIRS)} 个币种的 1分钟 K线...")
        
        for pair in SPOT_PAIRS:
            await ws.subscribe_candles(pair, "1m", callback=on_kline)
            await asyncio.sleep(0.1)  # 避免发送太快
        
        print("\n3️⃣  等待K线数据 (按 Ctrl+C 停止)...")
        print("-" * 80)
        
        # 每 30 秒打印统计
        while True:
            await asyncio.sleep(30)
            print(f"\n--- 已收到 {kline_count} 条K线 ---\n")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  停止中...")
    
    finally:
        # 清理
        print("\n4️⃣  断开连接...")
        await ws.disconnect()
        print(f"\n✅ 测试完成！共收到 {kline_count} 条K线")


if __name__ == "__main__":
    asyncio.run(main())

