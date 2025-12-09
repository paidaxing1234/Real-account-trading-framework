"""
简单趋势跟踪策略

策略逻辑：
1. 使用1分钟K线判断短期趋势（连续3根K线上涨/下跌）
2. 使用实时行情确认价格
3. 分析订单流确认买卖力量（买入占比>60%为强势）
4. 综合判断后下单

风险控制：
- 最大持仓：0.01 BTC
- 止损：-1%
- 止盈：+2%
- 最大单次交易：0.01 BTC
"""

import asyncio
import sys
import os
from datetime import datetime
from collections import deque
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import EventEngine, TickerData, KlineData, TradeData
from adapters.okx import OKXMarketDataAdapter, OKXRestAPI


class SimpleTrendStrategy:
    """简单趋势跟踪策略"""
    
    def __init__(
        self,
        event_engine: EventEngine,
        rest_client: OKXRestAPI,
        symbol: str = "BTC-USDT",
        max_position: float = 0.01,
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.02
    ):
        """
        初始化策略
        
        Args:
            event_engine: 事件引擎
            rest_client: REST API客户端（用于下单）
            symbol: 交易对
            max_position: 最大持仓
            stop_loss_pct: 止损百分比
            take_profit_pct: 止盈百分比
        """
        self.engine = event_engine
        self.rest = rest_client
        self.symbol = symbol
        self.max_position = max_position
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        
        # 数据缓存
        self.klines = deque(maxlen=10)  # 保存最近10根K线
        self.latest_ticker = None
        self.recent_trades = deque(maxlen=100)  # 最近100笔交易
        
        # 持仓信息
        self.position = 0.0  # 当前持仓
        self.entry_price = None  # 开仓价格
        self.current_order_id = None  # 当前订单ID
        
        # 订单流统计
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        
        # 日志
        self.log_file = None
        
        # 注册事件监听
        self.engine.register(TickerData, self.on_ticker)
        self.engine.register(KlineData, self.on_kline)
        self.engine.register(TradeData, self.on_trade)
        
        self.log("✅ 策略初始化完成")
        self.log(f"   交易对: {symbol}")
        self.log(f"   最大持仓: {max_position} BTC")
        self.log(f"   止损: {stop_loss_pct*100}%")
        self.log(f"   止盈: {take_profit_pct*100}%")
    
    def log(self, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        
        # 同时写入文件
        if self.log_file:
            self.log_file.write(log_msg + "\n")
            self.log_file.flush()
    
    def on_ticker(self, event: TickerData):
        """处理行情数据"""
        if event.symbol != self.symbol:
            return
        
        self.latest_ticker = event
        
        # 检查止盈止损
        if self.position != 0 and self.entry_price:
            self._check_stop_loss_take_profit()
    
    def on_kline(self, event: KlineData):
        """处理K线数据"""
        if event.symbol != self.symbol or event.interval != "1m":
            return
        
        self.klines.append(event)
        
        self.log(f"\n📊 K线更新: O={event.open:.1f}, H={event.high:.1f}, "
                f"L={event.low:.1f}, C={event.close:.1f}, V={event.volume:.4f}")
        
        # 至少需要3根K线才能判断趋势
        if len(self.klines) >= 3:
            self._check_entry_signal()
    
    def on_trade(self, event: TradeData):
        """处理交易数据"""
        if event.symbol != self.symbol:
            return
        
        self.recent_trades.append(event)
        
        # 统计订单流
        if event.side == "buy":
            self.buy_volume += event.quantity
        else:
            self.sell_volume += event.quantity
    
    def _check_entry_signal(self):
        """检查开仓信号"""
        # 如果已有持仓，不开新仓
        if self.position != 0:
            return
        
        # 分析趋势
        recent_klines = list(self.klines)[-3:]
        closes = [k.close for k in recent_klines]
        
        # 连续3根上涨
        is_uptrend = all(closes[i] > closes[i-1] for i in range(1, 3))
        # 连续3根下跌
        is_downtrend = all(closes[i] < closes[i-1] for i in range(1, 3))
        
        if not (is_uptrend or is_downtrend):
            return
        
        # 分析订单流
        total_volume = self.buy_volume + self.sell_volume
        if total_volume == 0:
            return
        
        buy_ratio = self.buy_volume / total_volume
        
        self.log(f"\n🎯 信号检查:")
        self.log(f"   趋势: {'上涨' if is_uptrend else '下跌' if is_downtrend else '震荡'}")
        self.log(f"   买盘占比: {buy_ratio*100:.1f}%")
        
        # 开仓条件：趋势 + 订单流确认
        if is_uptrend and buy_ratio > 0.6:
            self.log(f"   ✅ 做多信号！（上涨趋势 + 买盘占优）")
            self._open_long()
        elif is_downtrend and buy_ratio < 0.4:
            self.log(f"   ✅ 做空信号！（下跌趋势 + 卖盘占优）")
            # 现货不能做空，这里只是演示逻辑
            self.log(f"   ⚠️  现货无法做空，跳过")
        
        # 重置订单流统计
        self.buy_volume = 0.0
        self.sell_volume = 0.0
    
    def _open_long(self):
        """开多仓"""
        if not self.latest_ticker:
            self.log("   ❌ 无最新行情，无法下单")
            return
        
        # 使用买一价下单（更容易成交）
        price = self.latest_ticker.ask_price or self.latest_ticker.last_price
        quantity = self.max_position
        
        self.log(f"\n📤 准备下单:")
        self.log(f"   方向: 买入（做多）")
        self.log(f"   价格: {price:.2f} USDT")
        self.log(f"   数量: {quantity} BTC")
        
        try:
            # 生成唯一的客户订单ID（使用UUID确保唯一性）
            import uuid
            cl_ord_id = f"trend_{uuid.uuid4().hex[:16]}"
            
            # 下单
            result = self.rest.place_order(
                inst_id=self.symbol,
                td_mode="cash",
                side="buy",
                ord_type="limit",
                px=str(price),
                sz=str(quantity),
                cl_ord_id=cl_ord_id
            )
            
            if result and result.get('code') == '0' and result.get('data'):
                order_data = result['data'][0]
                self.current_order_id = order_data.get('ordId')
                
                self.log(f"   ✅ 下单成功!")
                self.log(f"   订单ID: {self.current_order_id}")
                self.log(f"   客户订单ID: {cl_ord_id}")
                
                # 更新持仓（简化处理，实际应该等订单成交确认）
                self.position = quantity
                self.entry_price = price
                
                self.log(f"   持仓更新: {self.position} BTC @ {self.entry_price:.2f}")
            else:
                self.log(f"   ❌ 下单失败: {result}")
                
        except Exception as e:
            self.log(f"   ❌ 下单异常: {e}")
            import traceback
            traceback.print_exc()
    
    def _check_stop_loss_take_profit(self):
        """检查止盈止损"""
        if not self.latest_ticker or not self.entry_price:
            return
        
        current_price = self.latest_ticker.last_price
        pnl_pct = (current_price - self.entry_price) / self.entry_price
        
        # 止损
        if pnl_pct < -self.stop_loss_pct:
            self.log(f"\n🛑 触发止损！")
            self.log(f"   开仓价: {self.entry_price:.2f}")
            self.log(f"   当前价: {current_price:.2f}")
            self.log(f"   亏损: {pnl_pct*100:.2f}%")
            self._close_position("止损")
        
        # 止盈
        elif pnl_pct > self.take_profit_pct:
            self.log(f"\n🎉 触发止盈！")
            self.log(f"   开仓价: {self.entry_price:.2f}")
            self.log(f"   当前价: {current_price:.2f}")
            self.log(f"   盈利: {pnl_pct*100:.2f}%")
            self._close_position("止盈")
    
    def _close_position(self, reason: str):
        """平仓"""
        if self.position == 0:
            return
        
        if not self.latest_ticker:
            self.log("   ❌ 无最新行情，无法平仓")
            return
        
        # 使用卖一价下单
        price = self.latest_ticker.bid_price or self.latest_ticker.last_price
        quantity = abs(self.position)
        
        self.log(f"\n📤 准备平仓（{reason}）:")
        self.log(f"   方向: 卖出（平多）")
        self.log(f"   价格: {price:.2f} USDT")
        self.log(f"   数量: {quantity} BTC")
        
        try:
            import uuid
            cl_ord_id = f"close_{uuid.uuid4().hex[:16]}"
            
            # 平仓下单
            result = self.rest.place_order(
                inst_id=self.symbol,
                td_mode="cash",
                side="sell",
                ord_type="limit",
                px=str(price),
                sz=str(quantity),
                cl_ord_id=cl_ord_id
            )
            
            if result and result.get('code') == '0' and result.get('data'):
                order_data = result['data'][0]
                self.log(f"   ✅ 平仓下单成功!")
                self.log(f"   订单ID: {order_data.get('ordId')}")
                
                # 计算盈亏
                pnl = (price - self.entry_price) * quantity
                pnl_pct = (price - self.entry_price) / self.entry_price * 100
                
                self.log(f"   💰 盈亏: {pnl:.2f} USDT ({pnl_pct:+.2f}%)")
                
                # 重置持仓
                self.position = 0
                self.entry_price = None
                self.current_order_id = None
            else:
                self.log(f"   ❌ 平仓失败: {result}")
                
        except Exception as e:
            self.log(f"   ❌ 平仓异常: {e}")
    
    def get_status(self):
        """获取策略状态"""
        status = {
            'position': self.position,
            'entry_price': self.entry_price,
            'current_price': self.latest_ticker.last_price if self.latest_ticker else None,
            'kline_count': len(self.klines),
            'trade_count': len(self.recent_trades)
        }
        
        if self.position != 0 and self.entry_price and self.latest_ticker:
            pnl_pct = (self.latest_ticker.last_price - self.entry_price) / self.entry_price * 100
            status['pnl_pct'] = pnl_pct
        
        return status


async def run_strategy(duration: int = 300):
    """
    运行策略
    
    Args:
        duration: 运行时长（秒），默认5分钟
    """
    print("\n" + "🚀" * 40)
    print("简单趋势跟踪策略 - 模拟盘测试")
    print("🚀" * 40)
    
    # 创建日志文件
    log_filename = f"strategies/strategy_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    try:
        # API配置（请使用您的实际密钥）
        API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
        SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
        PASSPHRASE = "Sequence2025."
        
        print(f"\n📝 初始化组件...")
        
        # 创建事件引擎
        engine = EventEngine()
        print("   ✅ EventEngine创建成功")
        
        # 创建REST API客户端
        rest_client = OKXRestAPI(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            passphrase=PASSPHRASE,
            is_demo=True
        )
        print("   ✅ REST API客户端创建成功")
        
        # 创建WebSocket适配器
        ws_adapter = OKXMarketDataAdapter(
            event_engine=engine,
            is_demo=True
        )
        print("   ✅ WebSocket适配器创建成功")
        
        # 创建策略
        strategy = SimpleTrendStrategy(
            event_engine=engine,
            rest_client=rest_client,
            symbol="BTC-USDT",
            max_position=0.01,
            stop_loss_pct=0.01,
            take_profit_pct=0.02
        )
        strategy.log_file = log_file
        print("   ✅ 策略创建成功")
        
        # 查询初始余额
        print(f"\n📊 查询账户信息...")
        balance = rest_client.get_balance(ccy="USDT")
        if balance and balance.get('code') == '0':
            balance_data = balance['data'][0]['details']
            for detail in balance_data:
                if detail['ccy'] == 'USDT':
                    strategy.log(f"   USDT余额: {detail['availBal']}")
                    break
        
        # 启动WebSocket适配器
        print(f"\n🚀 启动WebSocket适配器...")
        await ws_adapter.start()
        await asyncio.sleep(2)
        
        # 订阅数据
        print(f"\n📡 订阅数据源...")
        await ws_adapter.subscribe_ticker("BTC-USDT")
        print("   ✅ 订阅Tickers（行情）")
        
        await ws_adapter.subscribe_candles("BTC-USDT", interval="1m")
        print("   ✅ 订阅Candles（1分钟K线）")
        
        await ws_adapter.subscribe_trades_all("BTC-USDT")
        print("   ✅ 订阅Trades-All（逐笔成交）")
        
        # 等待数据稳定
        await asyncio.sleep(3)
        
        strategy.log(f"\n{'='*60}")
        strategy.log(f"策略开始运行 - 运行时长: {duration}秒")
        strategy.log(f"{'='*60}")
        
        # 运行策略
        start_time = asyncio.get_event_loop().time()
        
        # 定期打印状态
        async def print_status():
            while True:
                await asyncio.sleep(60)  # 每60秒打印一次状态
                status = strategy.get_status()
                strategy.log(f"\n📊 策略状态:")
                strategy.log(f"   持仓: {status['position']} BTC")
                strategy.log(f"   当前价: {status.get('current_price', 'N/A')}")
                if status.get('pnl_pct'):
                    strategy.log(f"   浮动盈亏: {status['pnl_pct']:+.2f}%")
                strategy.log(f"   K线数据: {status['kline_count']}根")
                strategy.log(f"   交易数据: {status['trade_count']}笔")
        
        # 启动状态打印任务
        status_task = asyncio.create_task(print_status())
        
        try:
            # 运行指定时长
            await asyncio.sleep(duration)
        except KeyboardInterrupt:
            strategy.log("\n⚠️  用户中断策略")
        
        # 取消状态打印
        status_task.cancel()
        
        strategy.log(f"\n{'='*60}")
        strategy.log(f"策略运行结束")
        strategy.log(f"{'='*60}")
        
        # 如果有持仓，平仓
        if strategy.position != 0:
            strategy.log(f"\n⚠️  策略结束时仍有持仓，强制平仓")
            strategy._close_position("策略结束")
            await asyncio.sleep(2)
        
        # 最终状态
        final_status = strategy.get_status()
        strategy.log(f"\n📊 最终状态:")
        strategy.log(f"   持仓: {final_status['position']} BTC")
        strategy.log(f"   K线数据: {final_status['kline_count']}根")
        strategy.log(f"   交易数据: {final_status['trade_count']}笔")
        
        # 停止适配器
        print(f"\n🛑 停止WebSocket适配器...")
        await ws_adapter.stop()
        
        print(f"\n✅ 策略运行完成")
        print(f"📝 日志已保存到: {log_filename}")
        
    except Exception as e:
        print(f"\n❌ 策略运行错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if log_file:
            log_file.close()


if __name__ == "__main__":
    # 运行2分钟（演示用）
    asyncio.run(run_strategy(duration=120))

