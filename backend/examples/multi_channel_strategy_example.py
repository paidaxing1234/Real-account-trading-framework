"""
多频道综合策略示例

展示如何同时使用：
1. Tickers频道 - 实时价格监控
2. Candles频道 - K线技术分析
3. Trades频道 - 订单流分析

实现一个简单的多数据源交易策略
"""

import asyncio
import sys
import os
from datetime import datetime
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import EventEngine, TickerData, KlineData, TradeData
from adapters.okx import OKXMarketDataAdapter


class MultiChannelStrategy:
    """
    多频道综合策略
    
    策略逻辑：
    1. 使用K线判断趋势
    2. 使用Ticker监控实时价格
    3. 使用Trades分析订单流
    4. 综合决策是否交易
    """
    
    def __init__(self, name: str = "MultiChannelStrategy"):
        self.name = name
        
        # 数据存储
        self.latest_ticker = None
        self.kline_buffer = deque(maxlen=20)  # 保存最近20根K线
        self.recent_trades = deque(maxlen=100)  # 保存最近100笔交易
        
        # 统计数据
        self.buy_volume = 0
        self.sell_volume = 0
        
        print(f"✅ 策略初始化: {self.name}")
    
    def on_ticker(self, event: TickerData):
        """处理行情数据"""
        if event.symbol != "BTC-USDT":
            return
        
        self.latest_ticker = event
        
        # 计算价差
        if event.bid_price and event.ask_price:
            spread = event.ask_price - event.bid_price
            spread_pct = (spread / event.last_price) * 100
            
            if spread_pct > 0.05:  # 价差超过0.05%
                print(f"\n⚠️  [{self.name}] 价差较大:")
                print(f"   买一: {event.bid_price}, 卖一: {event.ask_price}")
                print(f"   价差: {spread:.2f} ({spread_pct:.3f}%)")
    
    def on_kline(self, event: KlineData):
        """处理K线数据"""
        if event.symbol != "BTC-USDT" or event.interval != "1m":
            return
        
        # 添加到缓冲区
        self.kline_buffer.append(event)
        
        print(f"\n📊 [{self.name}] K线更新:")
        print(f"   时间: {datetime.fromtimestamp(event.timestamp/1000)}")
        print(f"   O:{event.open:.2f}, H:{event.high:.2f}, "
              f"L:{event.low:.2f}, C:{event.close:.2f}")
        print(f"   成交量: {event.volume:.4f}")
        
        # 简单趋势判断
        if len(self.kline_buffer) >= 3:
            recent_closes = [k.close for k in list(self.kline_buffer)[-3:]]
            
            if all(recent_closes[i] > recent_closes[i-1] for i in range(1, 3)):
                print(f"   📈 趋势: 连续上涨")
                self._check_entry_signal("上涨")
            elif all(recent_closes[i] < recent_closes[i-1] for i in range(1, 3)):
                print(f"   📉 趋势: 连续下跌")
                self._check_entry_signal("下跌")
    
    def on_trade(self, event: TradeData):
        """处理交易数据"""
        if event.symbol != "BTC-USDT":
            return
        
        # 添加到缓冲区
        self.recent_trades.append(event)
        
        # 统计订单流
        if event.side == "buy":
            self.buy_volume += event.quantity
        else:
            self.sell_volume += event.quantity
        
        # 每100笔统计一次
        if len(self.recent_trades) >= 100:
            self._analyze_order_flow()
    
    def _check_entry_signal(self, trend: str):
        """检查入场信号"""
        if not self.latest_ticker:
            return
        
        # 结合订单流
        total_volume = self.buy_volume + self.sell_volume
        if total_volume > 0:
            buy_ratio = self.buy_volume / total_volume
            
            print(f"\n🎯 [{self.name}] 信号检查:")
            print(f"   趋势: {trend}")
            print(f"   当前价: {self.latest_ticker.last_price:.2f}")
            print(f"   买盘占比: {buy_ratio*100:.1f}%")
            
            # 简单的交易信号
            if trend == "上涨" and buy_ratio > 0.6:
                print(f"   ✅ 做多信号！（趋势上涨 + 买盘占优）")
            elif trend == "下跌" and buy_ratio < 0.4:
                print(f"   ✅ 做空信号！（趋势下跌 + 卖盘占优）")
    
    def _analyze_order_flow(self):
        """分析订单流"""
        total_volume = self.buy_volume + self.sell_volume
        
        if total_volume > 0:
            buy_ratio = self.buy_volume / total_volume
            sell_ratio = self.sell_volume / total_volume
            
            print(f"\n💹 [{self.name}] 订单流分析（最近100笔）:")
            print(f"   买入量: {self.buy_volume:.4f} ({buy_ratio*100:.1f}%)")
            print(f"   卖出量: {self.sell_volume:.4f} ({sell_ratio*100:.1f}%)")
            
            if buy_ratio > 0.65:
                print(f"   → 买盘占优，可能继续上涨")
            elif sell_ratio > 0.65:
                print(f"   → 卖盘占优，可能继续下跌")
            else:
                print(f"   → 买卖均衡，横盘整理")
        
        # 重置统计
        self.buy_volume = 0
        self.sell_volume = 0
        self.recent_trades.clear()


class RiskMonitor:
    """
    风险监控组件
    监控价格波动和异常交易
    """
    
    def __init__(self):
        self.last_price = None
        self.price_alerts = 0
    
    def on_ticker(self, event: TickerData):
        """监控价格跳动"""
        if event.symbol != "BTC-USDT":
            return
        
        if self.last_price:
            change = event.last_price - self.last_price
            change_pct = (change / self.last_price) * 100
            
            # 价格跳动超过0.5%
            if abs(change_pct) > 0.5:
                self.price_alerts += 1
                print(f"\n⚠️  [风险监控] 价格剧烈波动 #{self.price_alerts}:")
                print(f"   从 {self.last_price:.2f} → {event.last_price:.2f}")
                print(f"   变化: {change:+.2f} ({change_pct:+.2f}%)")
        
        self.last_price = event.last_price
    
    def on_trade(self, event: TradeData):
        """监控大单"""
        if event.symbol != "BTC-USDT":
            return
        
        # 检测大单（超过10 BTC）
        if event.quantity > 10:
            direction = "买入" if event.side == "buy" else "卖出"
            value = event.quantity * event.price
            
            print(f"\n🔔 [风险监控] 大单成交:")
            print(f"   方向: {direction}")
            print(f"   数量: {event.quantity:.4f} BTC")
            print(f"   价格: {event.price:.2f} USDT")
            print(f"   金额: {value:,.2f} USDT")


async def main():
    """主函数"""
    print("\n" + "🚀" * 40)
    print("多频道综合策略示例")
    print("🚀" * 40)
    
    # 创建事件引擎
    print("\n📝 创建EventEngine...")
    engine = EventEngine()
    
    # 创建适配器
    print("📝 创建OKXMarketDataAdapter...")
    adapter = OKXMarketDataAdapter(
        event_engine=engine,
        is_demo=True
    )
    
    # 创建策略和监控组件
    print("📝 创建策略和监控组件...")
    strategy = MultiChannelStrategy(name="综合策略")
    monitor = RiskMonitor()
    
    # 注册事件监听
    print("📝 注册事件监听...")
    engine.register(TickerData, strategy.on_ticker)
    engine.register(KlineData, strategy.on_kline)
    engine.register(TradeData, strategy.on_trade)
    
    engine.register(TickerData, monitor.on_ticker)
    engine.register(TradeData, monitor.on_trade)
    
    # 启动适配器
    print("\n🚀 启动适配器...")
    await adapter.start()
    
    # 订阅所有数据源
    print("\n📡 订阅数据源...")
    print("   - BTC-USDT Tickers（行情）")
    await adapter.subscribe_ticker("BTC-USDT")
    
    print("   - BTC-USDT Candles 1m（K线）")
    await adapter.subscribe_candles("BTC-USDT", interval="1m")
    
    print("   - BTC-USDT Trades（交易）")
    await adapter.subscribe_trades("BTC-USDT")
    
    # 运行策略
    print("\n⏳ 策略运行中（5分钟）...")
    print("="*80)
    
    try:
        await asyncio.sleep(300)  # 运行5分钟
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
    
    # 停止
    print("\n" + "="*80)
    print("🛑 停止适配器...")
    await adapter.stop()
    
    print("\n✅ 策略运行结束")
    print("="*80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断程序")
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

