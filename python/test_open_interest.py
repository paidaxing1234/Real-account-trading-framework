#!/usr/bin/env python3
"""
OKX WebSocket 持仓总量频道测试

持仓总量频道用于获取永续/交割合约的总持仓量
推送频率：每3秒有数据更新时推送

运行: python test_open_interest.py
"""

import asyncio
from adapters.okx.websocket import OKXWebSocketPublic


# 永续合约列表
SWAP_PAIRS = [
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP", 
    "SOL-USDT-SWAP",
    "XRP-USDT-SWAP",
    "DOGE-USDT-SWAP",
    "LTC-USD-SWAP",
    "BTC-USD-SWAP",
    "ETH-USD-SWAP"
]


async def main():
    print("=" * 70)
    print("  OKX WebSocket 持仓总量频道测试")
    print("=" * 70)
    
    # 创建公共频道 WebSocket
    ws = OKXWebSocketPublic(is_demo=True, url_type="public")
    
    # 统计
    oi_count = 0
    
    def on_open_interest(data):
        nonlocal oi_count
        oi_count += 1
        
        arg = data.get('arg', {})
        oi_list = data.get('data', [])
        
        for oi_data in oi_list:
            inst_id = oi_data.get('instId', 'N/A')
            inst_type = oi_data.get('instType', 'N/A')
            oi = float(oi_data.get('oi', 0))
            oi_ccy = float(oi_data.get('oiCcy', 0))
            oi_usd = float(oi_data.get('oiUsd', 0))
            
            print(f"📊 [OI] {inst_id:16} | 类型: {inst_type:6} | "
                  f"持仓(张): {oi:>15,.2f} | "
                  f"持仓(币): {oi_ccy:>12,.4f} | "
                  f"持仓(USD): ${oi_usd:>15,.2f}")
    
    try:
        # 连接
        print(f"\n1️⃣  连接 WebSocket...")
        await ws.connect()
        print(f"   URL: {ws.url}")
        
        # 订阅持仓总量
        print(f"\n2️⃣  订阅 {len(SWAP_PAIRS)} 个永续合约的持仓总量...")
        
        for pair in SWAP_PAIRS:
            args = [{"channel": "open-interest", "instId": pair}]
            await ws.subscribe(args, callback=on_open_interest)
            print(f"   订阅: {pair}")
            await asyncio.sleep(0.2)
        
        print("\n3️⃣  等待持仓总量数据 (每3秒更新，按 Ctrl+C 停止)...")
        print("-" * 100)
        
        # 每 30 秒打印统计
        while True:
            await asyncio.sleep(30)
            print(f"\n--- 已收到 {oi_count} 条持仓总量更新 ---\n")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  停止中...")
    
    finally:
        # 清理
        print("\n4️⃣  断开连接...")
        await ws.disconnect()
        print(f"\n✅ 测试完成！共收到 {oi_count} 条持仓总量数据")


if __name__ == "__main__":
    asyncio.run(main())

