#!/usr/bin/env python3
"""
================================================================================
                        策略基类 API 完整参考
================================================================================

【编译方法】
    cd cpp/build && cmake .. && make strategy_base

================================================================================
一、数据结构
================================================================================

KlineBar (K线):
    .timestamp  : int64  - 时间戳（毫秒）
    .open       : float  - 开盘价
    .high       : float  - 最高价
    .low        : float  - 最低价
    .close      : float  - 收盘价
    .volume     : float  - 成交量

TradeData (逐笔成交):
    .timestamp  : int64  - 时间戳（毫秒）
    .trade_id   : str    - 成交ID
    .price      : float  - 成交价格
    .quantity   : float  - 成交数量
    .side       : str    - "buy" / "sell"

PositionInfo (持仓):
    .symbol            : str    - 交易对
    .pos_side          : str    - "net" / "long" / "short"
    .quantity          : float  - 持仓数量（张）
    .avg_price         : float  - 持仓均价
    .mark_price        : float  - 标记价格
    .unrealized_pnl    : float  - 未实现盈亏
    .realized_pnl      : float  - 已实现盈亏
    .margin            : float  - 保证金
    .leverage          : float  - 杠杆倍数
    .liquidation_price : float  - 强平价格

BalanceInfo (余额):
    .currency   : str    - 币种 ("USDT", "BTC"...)
    .available  : float  - 可用余额
    .frozen     : float  - 冻结余额
    .total      : float  - 总余额
    .usd_value  : float  - USD估值

OrderInfo (订单):
    .client_order_id   : str   - 客户端订单ID
    .exchange_order_id : str   - 交易所订单ID
    .symbol            : str   - 交易对
    .side              : str   - "buy" / "sell"
    .order_type        : str   - "market" / "limit"
    .pos_side          : str   - "net" / "long" / "short"
    .price             : float - 价格
    .quantity          : int   - 数量（张）
    .filled_quantity   : int   - 已成交数量
    .filled_price      : float - 成交均价
    .error_msg         : str   - 错误信息

ScheduledTask (定时任务):
    .task_name         : str   - 任务名称
    .interval_ms       : int64 - 执行间隔（毫秒）
    .next_run_time_ms  : int64 - 下次执行时间（毫秒时间戳）
    .last_run_time_ms  : int64 - 上次执行时间（毫秒时间戳）
    .enabled           : bool  - 是否启用
    .run_count         : int   - 执行次数

================================================================================
二、构造函数
================================================================================

StrategyBase(strategy_id, max_kline_bars=7200, max_trades=10000, 
             max_orderbook_snapshots=1000, max_funding_rate_records=100)
    strategy_id              : str - 策略ID
    max_kline_bars           : int - K线存储数量（默认7200=2小时1sK线）
    max_trades               : int - Trades存储数量（默认10000条）
    max_orderbook_snapshots  : int - OrderBook存储数量（默认1000个快照）
    max_funding_rate_records : int - FundingRate存储数量（默认100条）

================================================================================
三、账户模块
================================================================================

register_account(api_key, secret_key, passphrase, is_testnet=True)
    api_key    : str  - OKX API Key
    secret_key : str  - OKX Secret Key  
    passphrase : str  - OKX Passphrase
    is_testnet : bool - True=模拟盘, False=实盘
    返回: bool

unregister_account()  -> bool
is_account_registered() -> bool

get_usdt_available()  -> float   # USDT可用余额
get_total_equity()    -> float   # 总权益（USD）
get_all_balances()    -> List[BalanceInfo]

get_all_positions()    -> List[PositionInfo]  # 所有持仓
get_active_positions() -> List[PositionInfo]  # 有效持仓(qty!=0)
get_position(symbol, pos_side="net") -> PositionInfo | None

refresh_account()   -> bool  # 刷新账户信息
refresh_positions() -> bool  # 刷新持仓信息

================================================================================
四、行情模块
================================================================================

【订阅】
subscribe_kline(symbol, interval) -> bool
    symbol   : str - "BTC-USDT-SWAP", "ETH-USDT-SWAP"...
    interval : str - "1s", "1m", "3m", "5m", "15m", "30m", "1H", "4H", "1D"

unsubscribe_kline(symbol, interval) -> bool
subscribe_trades(symbol) -> bool
unsubscribe_trades(symbol) -> bool

subscribe_orderbook(symbol, channel="books5") -> bool
    channel: "books5"(默认), "books", "bbo-tbt", "books-l2-tbt", "books50-l2-tbt", "books-elp"
unsubscribe_orderbook(symbol, channel="books5") -> bool

subscribe_funding_rate(symbol) -> bool  # 仅永续合约
unsubscribe_funding_rate(symbol) -> bool

【查询】
get_klines(symbol, interval)           -> List[KlineBar]
get_closes(symbol, interval)           -> List[float]
get_opens(symbol, interval)            -> List[float]
get_highs(symbol, interval)            -> List[float]
get_lows(symbol, interval)             -> List[float]
get_volumes(symbol, interval)          -> List[float]
get_recent_klines(symbol, interval, n) -> List[KlineBar]
get_last_kline(symbol, interval)       -> KlineBar | None
get_kline_count(symbol, interval)      -> int

get_trades(symbol)                     -> List[TradeData]
get_recent_trades(symbol, n)            -> List[TradeData]
get_trades_by_time(symbol, time_ms)    -> List[TradeData]  # 最近N毫秒内
get_last_trade(symbol)                  -> TradeData | None
get_trade_count(symbol)                 -> int

get_orderbooks(symbol, channel="books5")              -> List[OrderBookSnapshot]
get_recent_orderbooks(symbol, n, channel="books5")   -> List[OrderBookSnapshot]
get_orderbooks_by_time(symbol, time_ms, channel="books5") -> List[OrderBookSnapshot]
get_last_orderbook(symbol, channel="books5")          -> OrderBookSnapshot | None
get_orderbook_count(symbol, channel="books5")         -> int

get_funding_rates(symbol)               -> List[FundingRateData]
get_recent_funding_rates(symbol, n)    -> List[FundingRateData]
get_funding_rates_by_time(symbol, time_ms) -> List[FundingRateData]
get_last_funding_rate(symbol)          -> FundingRateData | None
get_funding_rate_count(symbol)         -> int

================================================================================
五、交易模块
================================================================================

【下单】
send_swap_market_order(symbol, side, quantity, pos_side="net") -> str
    symbol   : str - 交易对 "BTC-USDT-SWAP"
    side     : str - "buy" / "sell"
    quantity : int - 张数
    pos_side : str - "net"(默认), "long", "short"
    返回: 客户端订单ID

send_swap_limit_order(symbol, side, quantity, price, pos_side="net") -> str
    price : float - 限价

【撤单】
cancel_order(symbol, client_order_id) -> bool
cancel_all_orders(symbol="") -> bool  # 空=撤销全部

【查询】
get_active_orders()   -> List[OrderInfo]
pending_order_count() -> int

================================================================================
六、定时任务模块
================================================================================

schedule_task(task_name, interval, start_time="") -> bool
    task_name  : str - 任务名称（在 on_scheduled_task 回调中返回）
    interval   : str - 执行间隔:
        "30s", "60s"        - 秒
        "1m", "5m", "30m"   - 分钟
        "1h", "4h"          - 小时
        "1d"                - 天
        "1w"                - 周
    start_time : str - 首次执行时间，格式 "HH:MM"（如 "14:00"）
        空字符串或"now"表示立即开始
        如果指定时间已过，会自动计算下一个执行时间

unschedule_task(task_name) -> bool    # 取消任务
pause_task(task_name)      -> bool    # 暂停任务
resume_task(task_name)     -> bool    # 恢复任务

get_scheduled_tasks()          -> List[ScheduledTask]  # 所有任务
get_task_info(task_name)       -> ScheduledTask | None

================================================================================
七、回调函数（需重写）
================================================================================

on_init()                                    # 初始化
on_stop()                                    # 停止
on_tick()                                    # 每次循环（约100us）

on_kline(symbol, interval, bar: KlineBar)    # K线回调
on_trade(symbol, trade: TradeData)           # 逐笔成交回调
on_orderbook(symbol, snapshot: OrderBookSnapshot)  # 深度数据回调
on_funding_rate(symbol, fr: FundingRateData)       # 资金费率回调

on_order_report(report: dict)                # 订单回报
    report["status"]: "accepted", "rejected", "filled", 
                      "partially_filled", "cancelled", "live", "failed"
    report["symbol"], report["side"], report["client_order_id"]
    report["filled_quantity"], report["filled_price"], report["error_msg"]

on_register_report(success: bool, error_msg: str)  # 账户注册回报
on_position_update(position: PositionInfo)         # 持仓更新
on_balance_update(balance: BalanceInfo)            # 余额更新
on_scheduled_task(task_name: str)                  # 定时任务回调

================================================================================
八、日志与属性
================================================================================

log_info(msg)   # 输出信息
log_error(msg)  # 输出错误

【只读属性】
.strategy_id  : str
.is_running   : bool
.kline_count  : int
.order_count  : int
.report_count : int

================================================================================
"""

import sys
import signal
import time

try:
    from strategy_base import (
        StrategyBase, KlineBar, TradeData, OrderBookSnapshot, FundingRateData,
        PositionInfo, BalanceInfo, OrderInfo, ScheduledTask
    )
except ImportError:
    print("错误: 未找到 strategy_base 模块，请先编译:")
    print("  cd cpp/build && cmake .. && make strategy_base")
    sys.exit(1)


class ExampleStrategy(StrategyBase):
    """示例策略 - 展示所有接口的实际调用方式"""
    
    def __init__(self, strategy_id: str, symbol: str, 
                 max_kline_bars: int = 7200,
                 max_trades: int = 10000,
                 max_orderbook_snapshots: int = 1000,
                 max_funding_rate_records: int = 100):
        super().__init__(strategy_id, 
                        max_kline_bars=max_kline_bars,
                        max_trades=max_trades,
                        max_orderbook_snapshots=max_orderbook_snapshots,
                        max_funding_rate_records=max_funding_rate_records)
        self.symbol = symbol
        self.kline_count_local = 0
    
    # ======================== 生命周期 ========================
    
    def on_init(self):
        """策略初始化"""
        # 1. 注册账户
        self.register_account(
            api_key="your-api-key",
            secret_key="your-secret-key",
            passphrase="your-passphrase",
            is_testnet=True  # True=模拟盘, False=实盘
        )
        time.sleep(1)
        
        # 2. 订阅K线（可订阅多个）
        self.subscribe_kline(self.symbol, "1s")   # 1秒K线
        # self.subscribe_kline(self.symbol, "1m")   # 1分钟K线
        # self.subscribe_kline("ETH-USDT-SWAP", "1s")
        
        # 3. 订阅逐笔成交（可选）
        # self.subscribe_trades(self.symbol)
        
        # 4. 订阅深度数据（可选）
        # self.subscribe_orderbook(self.symbol, "books5")  # 5档深度
        # self.subscribe_orderbook(self.symbol, "books")   # 400档深度
        # self.subscribe_orderbook(self.symbol, "bbo-tbt") # 1档，10ms推送
        
        # 5. 订阅资金费率（可选，仅永续合约）
        # self.subscribe_funding_rate(self.symbol)
        
        # 6. 注册定时任务
        # 每10秒执行一次（立即开始）
        self.schedule_task("check_position", "10s")
        
        # 每天14:00执行（用于日度调仓等）
        # self.schedule_task("daily_rebalance", "1d", "14:00")
        
        # 每周执行（用于周度报告等）
        # self.schedule_task("weekly_report", "1w", "09:00")
        
        self.log_info(f"策略初始化完成，订阅 {self.symbol}")
    
    def on_stop(self):
        """策略停止"""
        # 取消订阅
        self.unsubscribe_kline(self.symbol, "1s")
        # self.unsubscribe_trades(self.symbol)
        # self.unsubscribe_orderbook(self.symbol, "books5")
        # self.unsubscribe_funding_rate(self.symbol)
        
        # 取消定时任务
        self.unschedule_task("check_position")
        # self.unschedule_task("daily_rebalance")
        # self.unschedule_task("weekly_report")
        
        # 打印定时任务统计
        for task in self.get_scheduled_tasks():
            self.log_info(f"任务 {task.task_name} 共执行 {task.run_count} 次")
        
        # 打印统计
        self.log_info(f"K线数量: {self.get_kline_count(self.symbol, '1s')}")
        self.log_info(f"成交数量: {self.get_trade_count(self.symbol)}")
        self.log_info(f"深度快照数: {self.get_orderbook_count(self.symbol, 'books5')}")
        self.log_info(f"资金费率记录数: {self.get_funding_rate_count(self.symbol)}")
        self.log_info(f"USDT余额: {self.get_usdt_available():.2f}")
        
        # 打印持仓
        for pos in self.get_active_positions():
            self.log_info(f"持仓: {pos.symbol} {pos.quantity}张 盈亏:{pos.unrealized_pnl:.2f}")
    
    # ======================== 行情回调 ========================
    
    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K线回调"""
        if symbol != self.symbol:
            return
        
        self.kline_count_local += 1
        
        # 每30根K线打印一次
        if self.kline_count_local % 30 == 0:
            closes = self.get_closes(symbol, interval)
            self.log_info(f"[K线] {symbol} 收盘:{bar.close:.2f} 存储:{len(closes)}根")
    
    def on_trade(self, symbol: str, trade: TradeData):
        """逐笔成交回调"""
        self.log_info(f"[Trade] {symbol} {trade.side} {trade.quantity} @ {trade.price}")
    
    def on_orderbook(self, symbol: str, snapshot: OrderBookSnapshot):
        """深度数据回调"""
        self.log_info(f"[OrderBook] {symbol} 买价:{snapshot.best_bid_price:.2f} "
                     f"卖价:{snapshot.best_ask_price:.2f} 中间价:{snapshot.mid_price:.2f}")
    
    def on_funding_rate(self, symbol: str, fr: FundingRateData):
        """资金费率回调"""
        self.log_info(f"[FundingRate] {symbol} 费率:{fr.funding_rate:.6f} "
                     f"下一期:{fr.next_funding_rate:.6f}")
    
    # ======================== 订单回调 ========================
    
    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        symbol = report.get("symbol", "")
        side = report.get("side", "")
        
        if status == "filled":
            self.log_info(f"[成交] {symbol} {side} {report.get('filled_quantity')}张")
        elif status == "rejected":
            self.log_error(f"[拒绝] {symbol} {side} 原因:{report.get('error_msg')}")
    
    # ======================== 账户回调 ========================
    
    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.log_info(f"账户注册成功，USDT:{self.get_usdt_available():.2f}")
        else:
            self.log_error(f"账户注册失败: {error_msg}")
    
    def on_position_update(self, position: PositionInfo):
        """持仓更新"""
        if position.quantity != 0:
            self.log_info(f"[持仓] {position.symbol} {position.quantity}张 盈亏:{position.unrealized_pnl:.2f}")
    
    def on_balance_update(self, balance: BalanceInfo):
        """余额更新"""
        if balance.currency == "USDT":
            self.log_info(f"[余额] USDT 可用:{balance.available:.2f}")
    
    # ======================== 定时任务回调 ========================
    
    def on_scheduled_task(self, task_name: str):
        """
        定时任务回调
        
        根据 task_name 判断执行哪个任务逻辑
        """
        if task_name == "check_position":
            self.do_check_position()
        elif task_name == "daily_rebalance":
            self.do_daily_rebalance()
        elif task_name == "weekly_report":
            self.do_weekly_report()
    
    def do_check_position(self):
        """检查持仓（每10秒执行）"""
        positions = self.get_active_positions()
        if positions:
            for pos in positions:
                self.log_info(f"[定时检查] {pos.symbol} 持仓:{pos.quantity}张 盈亏:{pos.unrealized_pnl:.2f}")
        else:
            self.log_info("[定时检查] 无持仓")
    
    def do_daily_rebalance(self):
        """每日调仓（每天14:00执行）"""
        self.log_info("[每日调仓] 开始执行调仓逻辑...")
        # 在这里实现调仓逻辑
        # 例如：检查持仓、计算目标仓位、下单调整等
    
    def do_weekly_report(self):
        """周报（每周执行）"""
        self.log_info("[周报] 生成周度报告...")
        # 在这里实现周报生成逻辑
    
    # ======================== 交易示例 ========================
    
    def place_order_example(self):
        """下单示例（在需要时调用）"""
        # 市价买入
        order_id = self.send_swap_market_order(self.symbol, "buy", 1, "net")
        self.log_info(f"买入订单: {order_id}")
        
        # 市价卖出
        order_id = self.send_swap_market_order(self.symbol, "sell", 1)
        self.log_info(f"卖出订单: {order_id}")
        
        # 限价单
        order_id = self.send_swap_limit_order(self.symbol, "buy", 1, 80000.0)
        self.log_info(f"限价订单: {order_id}")
        
        # 撤单
        self.cancel_order(self.symbol, order_id)
        
        # 撤销所有订单
        self.cancel_all_orders()
    
    def query_example(self):
        """查询示例（在需要时调用）"""
        # K线数据
        klines = self.get_klines(self.symbol, "1s")
        closes = self.get_closes(self.symbol, "1s")
        opens = self.get_opens(self.symbol, "1s")
        highs = self.get_highs(self.symbol, "1s")
        lows = self.get_lows(self.symbol, "1s")
        volumes = self.get_volumes(self.symbol, "1s")
        recent = self.get_recent_klines(self.symbol, "1s", 20)
        last = self.get_last_kline(self.symbol, "1s")
        
        # Trades数据
        trades = self.get_trades(self.symbol)
        recent_trades = self.get_recent_trades(self.symbol, 100)
        trades_1min = self.get_trades_by_time(self.symbol, 60000)  # 最近1分钟
        last_trade = self.get_last_trade(self.symbol)
        trade_count = self.get_trade_count(self.symbol)
        
        # OrderBook数据
        orderbooks = self.get_orderbooks(self.symbol, "books5")
        recent_ob = self.get_recent_orderbooks(self.symbol, 10, "books5")
        ob_1min = self.get_orderbooks_by_time(self.symbol, 60000, "books5")
        last_ob = self.get_last_orderbook(self.symbol, "books5")
        ob_count = self.get_orderbook_count(self.symbol, "books5")
        
        # FundingRate数据
        funding_rates = self.get_funding_rates(self.symbol)
        recent_fr = self.get_recent_funding_rates(self.symbol, 10)
        fr_1hour = self.get_funding_rates_by_time(self.symbol, 3600000)  # 最近1小时
        last_fr = self.get_last_funding_rate(self.symbol)
        fr_count = self.get_funding_rate_count(self.symbol)
        
        # 账户
        usdt = self.get_usdt_available()
        equity = self.get_total_equity()
        balances = self.get_all_balances()
        
        # 持仓
        positions = self.get_all_positions()
        active = self.get_active_positions()
        pos = self.get_position(self.symbol, "net")
        
        # 订单
        orders = self.get_active_orders()
        pending = self.pending_order_count()
        
        # 定时任务
        tasks = self.get_scheduled_tasks()
        task_info = self.get_task_info("check_position")


def main():
    print("=" * 60)
    print("  示例策略 - 策略基类 API 完整参考")
    print("=" * 60)
    
    strategy = ExampleStrategy("example", "BTC-USDT-SWAP")
    
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())
    
    strategy.run()


if __name__ == "__main__":
    main()
