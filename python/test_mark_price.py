#!/usr/bin/env python3
"""
OKX WebSocket 标记价格频道测试

标记价格有变化时每200ms推送，没变化时每10s推送

运行: python test_mark_price.py
"""

import asyncio
from adapters.okx.websocket import OKXWebSocketPublic


# 产品列表（现货、永续合约）
PAIRS = [
    # 现货/杠杆
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    # 永续合约
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SOL-USDT-SWAP"
]


async def main():
    print("=" * 70)
    print("  OKX WebSocket 标记价格频道测试")
    print("=" * 70)
    
    # 创建公共频道 WebSocket
    ws = OKXWebSocketPublic(is_demo=True, url_type="public")
    
    # 统计
    mp_count = 0
    latest_prices = {}
    
    def on_mark_price(data):
        nonlocal mp_count
        mp_count += 1
        
        arg = data.get('arg', {})
        mp_list = data.get('data', [])
        
        for mp_data in mp_list:
            inst_id = mp_data.get('instId', 'N/A')
            inst_type = mp_data.get('instType', 'N/A')
            mark_px = float(mp_data.get('markPx', 0))
            
            latest_prices[inst_id] = mark_px
            
            print(f"📈 [MarkPrice] {inst_id:16} | 类型: {inst_type:8} | "
                  f"标记价格: ${mark_px:>12,.2f}")
    
    try:
        # 连接
        print(f"\n1️⃣  连接 WebSocket...")
        await ws.connect()
        print(f"   URL: {ws.url}")
        
        # 订阅标记价格
        print(f"\n2️⃣  订阅 {len(PAIRS)} 个产品的标记价格...")
        
        for pair in PAIRS:
            args = [{"channel": "mark-price", "instId": pair}]
            await ws.subscribe(args, callback=on_mark_price)
            print(f"   订阅: {pair}")
            await asyncio.sleep(0.2)
        
        print("\n3️⃣  等待标记价格数据...")
        print("   (有变化时200ms推送，无变化时10s推送)")
        print("   按 Ctrl+C 停止")
        print("-" * 80)
        
        # 每 30 秒打印统计
        while True:
            await asyncio.sleep(30)
            print(f"\n--- 已收到 {mp_count} 条标记价格更新 ---")
            print("最新标记价格:")
            for inst_id, price in sorted(latest_prices.items()):
                print(f"  {inst_id:16}: ${price:,.2f}")
            print("-" * 40 + "\n")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  停止中...")
    
    finally:
        # 清理
        print("\n4️⃣  断开连接...")
        await ws.disconnect()
        print(f"\n✅ 测试完成！共收到 {mp_count} 条标记价格数据")


if __name__ == "__main__":
    asyncio.run(main())

