"""
FactorNeutral 实盘策略 - 基于溢价因子的多空中性策略

继承 PyStrategyBase (C++ 基类)，实现实盘交易逻辑

策略逻辑：
1. 做多低溢价（被低估）标的
2. 做空高溢价（被高估）标的
3. 通过容忍度机制控制调仓频率
4. 基于24h成交量过滤流动性不足的标的
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Set, List, Tuple, Optional
import json

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入 C++ 绑定模块
try:
    from build import strategy_module
    PyStrategyBase = strategy_module.PyStrategyBase
except ImportError as e:
    print(f"导入 strategy_module 失败: {e}")
    print("请先编译 C++ 模块: cd cpp && mkdir -p build && cd build && cmake .. && make")
    sys.exit(1)


class FactorNeutralLive(PyStrategyBase):
    """
    基于因子的多空中性实盘策略

    参数说明：
    - factor: 因子名称（如 'premium'）
    - ascending: True 表示因子值小的做多（低溢价做多）
    - long_tolerance: 多头容忍度，排名超过此值则调出
    - short_tolerance: 空头容忍度，排名低于此值则调出
    - long_num: 多头持仓标的数量
    - short_num: 空头持仓标的数量
    - amount: 每个标的初始开仓金额（USDT）
    - vol24h_open: 24h成交量开仓门槛
    - vol24h_hold: 24h成交量持仓门槛
    - rebalance_interval: rebalance 间隔
    """

    def __init__(
        self,
        strategy_id: str = "factor_neutral",
        factor: str = "premium",
        ascending: bool = True,
        long_tolerance: float = 0.8,
        short_tolerance: float = 0.2,
        long_num: int = 20,
        short_num: int = 20,
        amount: float = 10000.0,
        vol24h_open: float = 24 * 25 * 10**4,
        vol24h_hold: float = 24 * 5 * 10**4,
        rebalance_interval: str = "1h",
    ):
        # 调用 C++ 基类构造函数
        super().__init__(strategy_id)

        # 策略参数
        self.factor = factor
        self.ascending = ascending
        self.long_tolerance = long_tolerance
        self.short_tolerance = short_tolerance
        self.long_num = long_num
        self.short_num = short_num
        self.amount = amount
        self.vol24h_open = vol24h_open
        self.vol24h_hold = vol24h_hold
        self.rebalance_interval = rebalance_interval

        # 状态变量
        self.price_dict: Dict[str, float] = {}          # symbol -> 最新价格
        self.factor_dict: Dict[str, float] = {}         # symbol -> 因子值
        self.vol24h_dict: Dict[str, float] = {}         # symbol -> 24h成交量
        self.open_time_dict: Dict[str, datetime] = {}   # symbol -> 开仓时间

        # 持仓状态（本地维护，与交易所同步）
        self.long_positions: Dict[str, float] = {}      # symbol -> quantity (正数)
        self.short_positions: Dict[str, float] = {}     # symbol -> quantity (负数)

        # 交易对列表
        self.symbols: List[str] = []

        # 上次 rebalance 时间
        self.last_rebalance_time: Optional[datetime] = None

    def on_init(self):
        """策略初始化"""
        self.log_info("=" * 50)
        self.log_info("FactorNeutral 实盘策略初始化")
        self.log_info(f"  因子: {self.factor}")
        self.log_info(f"  排序: {'升序(低做多)' if self.ascending else '降序(高做多)'}")
        self.log_info(f"  多头容忍度: {self.long_tolerance}")
        self.log_info(f"  空头容忍度: {self.short_tolerance}")
        self.log_info(f"  多头数量: {self.long_num}")
        self.log_info(f"  空头数量: {self.short_num}")
        self.log_info(f"  单标的金额: {self.amount} USDT")
        self.log_info(f"  Rebalance间隔: {self.rebalance_interval}")
        self.log_info("=" * 50)

        # 注册定时任务：定时 rebalance
        self.schedule_task("do_rebalance", self.rebalance_interval)

        # 注册定时任务：定时更新因子数据
        self.schedule_task("update_factor_data", "5m")

        # 初始化：获取交易对列表和因子数据
        self._init_symbols()
        self.update_factor_data()

        # 同步当前持仓
        self._sync_positions()

    def on_stop(self):
        """策略停止"""
        self.log_info("FactorNeutral 策略停止")
        self._print_position_summary()

    def on_tick(self):
        """每个 tick 调用（高频，保持轻量）"""
        pass

    def on_kline(self, symbol: str, interval: str, bar):
        """K线回调 - 更新价格"""
        self.price_dict[symbol] = bar.close

    def on_order_report(self, report):
        """订单回报回调"""
        try:
            report_dict = json.loads(str(report)) if isinstance(report, str) else report
            status = report_dict.get("status", "")
            symbol = report_dict.get("symbol", "")
            side = report_dict.get("side", "")
            filled_qty = float(report_dict.get("filled_qty", 0))

            if status == "FILLED":
                self.log_info(f"[订单成交] {symbol} {side} {filled_qty}")
                # 更新本地持仓
                self._update_local_position(symbol, side, filled_qty)

        except Exception as e:
            self.log_error(f"处理订单回报失败: {e}")

    def on_position_update(self, position):
        """持仓更新回调"""
        symbol = position.symbol
        qty = position.quantity

        if qty > 0:
            self.long_positions[symbol] = qty
            if symbol in self.short_positions:
                del self.short_positions[symbol]
        elif qty < 0:
            self.short_positions[symbol] = qty
            if symbol in self.long_positions:
                del self.long_positions[symbol]
        else:
            # 仓位为0，清除
            self.long_positions.pop(symbol, None)
            self.short_positions.pop(symbol, None)
            self.open_time_dict.pop(symbol, None)

    # ============================================================
    # 定时任务方法
    # ============================================================

    def update_factor_data(self):
        """更新因子数据（定时任务）"""
        self.log_info("[因子更新] 开始更新因子数据...")

        try:
            # 获取所有交易对的溢价指数
            for symbol in self.symbols:
                klines = self.get_binance_premium_index_klines(symbol, "1h", 0, 0, 24)
                if klines and len(klines) > 0:
                    # 取最新一根K线的收盘价作为当前溢价
                    last_kline = klines[-1]
                    premium = float(last_kline[4])  # 收盘价
                    self.factor_dict[symbol] = premium

            self.log_info(f"[因子更新] 完成，共 {len(self.factor_dict)} 个标的")

        except Exception as e:
            self.log_error(f"[因子更新] 失败: {e}")

    def do_rebalance(self):
        """执行 rebalance（定时任务）"""
        self.log_info("[Rebalance] 开始执行...")

        try:
            # 1. 计算因子排名
            ranked_symbols = self._calculate_factor_rank()
            if not ranked_symbols:
                self.log_info("[Rebalance] 无有效因子数据，跳过")
                return

            # 2. 计算调出标的
            long_out, short_out = self._calculate_out_symbols(ranked_symbols)

            # 3. 计算调入标的
            long_in, short_in = self._calculate_in_symbols(ranked_symbols)

            # 4. 执行平仓
            self._execute_close_positions(long_out | short_out)

            # 5. 执行开仓
            self._execute_open_positions(long_in, is_long=True)
            self._execute_open_positions(short_in, is_long=False)

            # 6. 更新 rebalance 时间
            self.last_rebalance_time = datetime.now()

            self._print_position_summary()

        except Exception as e:
            self.log_error(f"[Rebalance] 失败: {e}")

    # ============================================================
    # 内部方法
    # ============================================================

    def _init_symbols(self):
        """初始化交易对列表"""
        # 从历史数据模块获取可用交易对
        try:
            self.symbols = self.get_available_historical_symbols("binance")
            # 过滤只保留 USDT 永续合约
            self.symbols = [s for s in self.symbols if s.endswith("USDT")]
            self.log_info(f"[初始化] 获取到 {len(self.symbols)} 个交易对")
        except Exception as e:
            self.log_error(f"[初始化] 获取交易对失败: {e}")
            # 使用默认列表
            self.symbols = [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
                "DOGEUSDT", "SOLUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT"
            ]

    def _sync_positions(self):
        """同步当前持仓"""
        try:
            positions = self.get_active_positions()
            for pos in positions:
                symbol = pos.symbol
                qty = pos.quantity
                if qty > 0:
                    self.long_positions[symbol] = qty
                elif qty < 0:
                    self.short_positions[symbol] = qty

            self.log_info(f"[同步持仓] 多头: {len(self.long_positions)}, 空头: {len(self.short_positions)}")

        except Exception as e:
            self.log_error(f"[同步持仓] 失败: {e}")

    def _calculate_factor_rank(self) -> List[Tuple[str, float, float]]:
        """
        计算因子排名
        返回: [(symbol, factor_value, rank_pct), ...] 按因子排序
        """
        # 过滤有效数据
        valid_data = []
        for symbol in self.symbols:
            if symbol in self.factor_dict and symbol in self.price_dict:
                factor_val = self.factor_dict[symbol]
                vol24h = self.vol24h_dict.get(symbol, float('inf'))
                valid_data.append((symbol, factor_val, vol24h))

        if not valid_data:
            return []

        # 按因子排序
        valid_data.sort(key=lambda x: x[1], reverse=not self.ascending)

        # 计算排名百分位
        n = len(valid_data)
        result = []
        for i, (symbol, factor_val, vol24h) in enumerate(valid_data):
            rank_pct = (i + 1) / n
            result.append((symbol, factor_val, rank_pct))

        return result

    def _calculate_out_symbols(
        self,
        ranked_symbols: List[Tuple[str, float, float]]
    ) -> Tuple[Set[str], Set[str]]:
        """
        计算需要调出的标的
        返回: (long_out, short_out)
        """
        # 构建排名字典
        rank_dict = {s[0]: s[2] for s in ranked_symbols}
        symbol_set = set(rank_dict.keys())

        # 多头调出
        long_out = set()
        for symbol in self.long_positions:
            # 因子数据缺失 -> 调出
            if symbol not in symbol_set:
                long_out.add(symbol)
                continue
            # 成交量不足 -> 调出
            if self.vol24h_dict.get(symbol, 0) < self.vol24h_hold:
                long_out.add(symbol)
                continue
            # 排名超过容忍度 -> 调出
            if rank_dict[symbol] > self.long_tolerance:
                long_out.add(symbol)

        # 空头调出
        short_out = set()
        for symbol in self.short_positions:
            # 因子数据缺失 -> 调出
            if symbol not in symbol_set:
                short_out.add(symbol)
                continue
            # 成交量不足 -> 调出
            if self.vol24h_dict.get(symbol, 0) < self.vol24h_hold:
                short_out.add(symbol)
                continue
            # 排名低于容忍度 -> 调出（空头是排名高的）
            if rank_dict[symbol] < self.short_tolerance:
                short_out.add(symbol)

        return long_out, short_out

    def _calculate_in_symbols(
        self,
        ranked_symbols: List[Tuple[str, float, float]]
    ) -> Tuple[Set[str], Set[str]]:
        """
        计算需要调入的标的
        返回: (long_in, short_in)
        """
        current_positions = set(self.long_positions.keys()) | set(self.short_positions.keys())

        # 多头调入数量
        long_in_n = max(0, self.long_num - len(self.long_positions))
        long_in = set()

        if long_in_n > 0:
            # 从排名最前的开始选（因子值最小/最大，取决于 ascending）
            for symbol, factor_val, rank_pct in ranked_symbols:
                if len(long_in) >= long_in_n:
                    break
                if symbol in current_positions:
                    continue
                if self.vol24h_dict.get(symbol, 0) < self.vol24h_open:
                    continue
                long_in.add(symbol)

        # 空头调入数量
        short_in_n = max(0, self.short_num - len(self.short_positions))
        short_in = set()

        if short_in_n > 0:
            # 从排名最后的开始选
            for symbol, factor_val, rank_pct in reversed(ranked_symbols):
                if len(short_in) >= short_in_n:
                    break
                if symbol in current_positions:
                    continue
                if self.vol24h_dict.get(symbol, 0) < self.vol24h_open:
                    continue
                short_in.add(symbol)

        return long_in, short_in

    def _execute_close_positions(self, symbols_to_close: Set[str]):
        """执行平仓"""
        for symbol in symbols_to_close:
            try:
                if symbol in self.long_positions:
                    qty = self.long_positions[symbol]
                    self.log_info(f"[平仓] 多头 {symbol} 数量: {qty}")
                    self.send_binance_futures_market_order(symbol, "sell", qty)

                elif symbol in self.short_positions:
                    qty = abs(self.short_positions[symbol])
                    self.log_info(f"[平仓] 空头 {symbol} 数量: {qty}")
                    self.send_binance_futures_market_order(symbol, "buy", qty)

            except Exception as e:
                self.log_error(f"[平仓] {symbol} 失败: {e}")

    def _execute_open_positions(self, symbols_to_open: Set[str], is_long: bool):
        """执行开仓"""
        total_positions = self.long_num + self.short_num
        weight = 1.0 / total_positions

        for symbol in symbols_to_open:
            try:
                price = self.price_dict.get(symbol)
                if not price or price <= 0:
                    self.log_error(f"[开仓] {symbol} 价格无效")
                    continue

                # 计算开仓数量
                qty = self.amount * total_positions * weight / price

                if is_long:
                    self.log_info(f"[开仓] 多头 {symbol} 数量: {qty:.6f}")
                    self.send_binance_futures_market_order(symbol, "buy", qty)
                else:
                    self.log_info(f"[开仓] 空头 {symbol} 数量: {qty:.6f}")
                    self.send_binance_futures_market_order(symbol, "sell", qty)

                # 记录开仓时间
                self.open_time_dict[symbol] = datetime.now()

            except Exception as e:
                self.log_error(f"[开仓] {symbol} 失败: {e}")

    def _update_local_position(self, symbol: str, side: str, filled_qty: float):
        """更新本地持仓"""
        if side.upper() == "BUY":
            # 买入：增加多头或减少空头
            if symbol in self.short_positions:
                self.short_positions[symbol] += filled_qty
                if self.short_positions[symbol] >= 0:
                    del self.short_positions[symbol]
            else:
                self.long_positions[symbol] = self.long_positions.get(symbol, 0) + filled_qty
        else:
            # 卖出：减少多头或增加空头
            if symbol in self.long_positions:
                self.long_positions[symbol] -= filled_qty
                if self.long_positions[symbol] <= 0:
                    del self.long_positions[symbol]
            else:
                self.short_positions[symbol] = self.short_positions.get(symbol, 0) - filled_qty

    def _print_position_summary(self):
        """打印持仓摘要"""
        self.log_info("=" * 40)
        self.log_info("持仓摘要")
        self.log_info(f"  多头: {len(self.long_positions)} 个")
        for symbol, qty in list(self.long_positions.items())[:5]:
            self.log_info(f"    {symbol}: {qty:.6f}")
        if len(self.long_positions) > 5:
            self.log_info(f"    ... 还有 {len(self.long_positions) - 5} 个")

        self.log_info(f"  空头: {len(self.short_positions)} 个")
        for symbol, qty in list(self.short_positions.items())[:5]:
            self.log_info(f"    {symbol}: {qty:.6f}")
        if len(self.short_positions) > 5:
            self.log_info(f"    ... 还有 {len(self.short_positions) - 5} 个")
        self.log_info("=" * 40)


def main():
    """主函数"""
    # 从环境变量读取配置
    api_key = os.getenv("BINANCE_API_KEY", "")
    secret_key = os.getenv("BINANCE_SECRET_KEY", "")
    is_testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # 创建策略实例
    strategy = FactorNeutralLive(
        strategy_id="factor_neutral_premium",
        factor="premium",
        ascending=True,
        long_tolerance=0.8,
        short_tolerance=0.2,
        long_num=20,
        short_num=20,
        amount=10000.0,
        vol24h_open=24 * 25 * 10**4,
        vol24h_hold=24 * 5 * 10**4,
        rebalance_interval="1h",
    )

    # 注册账户
    if api_key and secret_key:
        strategy.register_binance_account(api_key, secret_key, is_testnet)
    else:
        print("警告: 未设置 BINANCE_API_KEY 和 BINANCE_SECRET_KEY 环境变量")
        print("策略将以只读模式运行（无法下单）")

    # 运行策略
    try:
        strategy.run()
    except KeyboardInterrupt:
        print("\n收到中断信号，正在停止策略...")
        strategy.stop()


if __name__ == "__main__":
    main()
