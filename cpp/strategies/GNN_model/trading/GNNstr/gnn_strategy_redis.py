#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GNN策略 - Redis版本

定时执行：每10分钟运行一次
功能：
  1. 从 Redis 获取历史K线数据（由 data_recorder 实时录入）
  2. 加载GNN模型进行预测
  3. 根据预测结果调整仓位

运行方式：
    python gnn_strategy_redis.py

环境变量：
    REDIS_HOST       - Redis 主机地址 (默认: 127.0.0.1)
    REDIS_PORT       - Redis 端口 (默认: 6379)
    REDIS_PASSWORD   - Redis 密码 (默认: 空)
    BINANCE_API_KEY  - Binance API Key
    BINANCE_SECRET_KEY - Binance Secret Key
    BINANCE_TESTNET  - 是否使用测试网 (1=是, 0=否, 默认: 1)

编译依赖：
    cd cpp/build && cmake .. && make strategy_base

注意：
  - 需要先启动 data_recorder 录制行情数据到 Redis
  - 使用 Binance 永续合约 (USDT-M Futures)

@author Sequence Team
@date 2026-01
"""

import sys
import os
import signal
import time
import numpy as np
import pandas as pd
from datetime import datetime, timezone

# 路径设置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))           # GNNstr/
TRADING_DIR = os.path.dirname(SCRIPT_DIR)                          # trading/
GNN_MODEL_DIR = os.path.dirname(TRADING_DIR)                       # GNN_model/
STRATEGIES_DIR = os.path.dirname(GNN_MODEL_DIR)                    # strategies/

# 添加路径用于导入
sys.path.insert(0, STRATEGIES_DIR)
sys.path.insert(0, TRADING_DIR)

from strategy_base import StrategyBase
from GNNStr import GNN_Strategy, SEQ_LEN, SEEDS, TOP_K_GRAPH
from redis_history_fetcher import RedisHistoryFetcher, fetch_all_history_from_redis

# ======================
# 配置
# ======================

# 交易所选择
EXCHANGE = "binance"  # 使用 Binance

# 策略配置
HISTORY_BARS = 1200          # 需要的历史K线数量
INTERVAL = "1m"              # K线周期
N_LAYERS = 20                # 分层数量（TOP_PCT = 1/20 = 5%）
POSITION_SIZE_USDT = 100     # 测试用小仓位

# 定时配置
SCHEDULE_INTERVAL = "10m"    # 每10分钟执行一次

# 币种池文件路径 (Binance格式，Redis 中使用 Binance 格式存储)
CURRENCY_POOL_BINANCE_FILE = os.path.join(TRADING_DIR, "currency_pool_binance.txt")
CURRENCY_POOL_OKX_FILE = os.path.join(TRADING_DIR, "currency_pool_okx.txt")


def convert_okx_to_binance_symbol(okx_symbol: str) -> str:
    """
    将 OKX 格式的交易对转换为 Binance 格式
    OKX: BTC-USDT-SWAP -> Binance: BTCUSDT
    """
    if "-SWAP" in okx_symbol:
        parts = okx_symbol.replace("-SWAP", "").split("-")
        return "".join(parts)
    elif "-" in okx_symbol:
        return okx_symbol.replace("-", "")
    return okx_symbol


def convert_binance_to_okx_symbol(binance_symbol: str) -> str:
    """
    将 Binance 格式的交易对转换为 OKX 格式
    Binance: BTCUSDT -> OKX: BTC-USDT-SWAP
    """
    if binance_symbol.endswith("USDT"):
        base = binance_symbol[:-4]
        return f"{base}-USDT-SWAP"
    return binance_symbol


class GNNRedisStrategy(StrategyBase):
    """GNN交易策略 - Redis版本（从Redis获取历史数据）"""

    def __init__(self):
        # 初始化基类
        super().__init__("gnn_redis", max_kline_bars=HISTORY_BARS + 100)
        self._set_python_self(self)

        # 策略配置
        self.exchange = EXCHANGE
        self.n_layers = N_LAYERS
        self.position_size_usdt = POSITION_SIZE_USDT

        # Binance API密钥
        self.api_key = os.getenv("BINANCE_API_KEY", "8gx21GMHaQQQ8vekG7ErB1f6c13HsSpSGql9y45aj2wSMhIrqI2Fb8Sr6j6m6MqE")
        self.secret_key = os.getenv("BINANCE_SECRET_KEY", "smE8BKGDbwrxoTTJb703MiDCJOYUvaB5pknrXBTGGzTLt7kQGwubL83YNkNEsN9T")
        self.is_testnet = os.getenv("BINANCE_TESTNET", "1") == "1"

        # Redis 配置
        self.redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD", "")

        # 状态
        self.account_ready = False
        self.data_ready = False
        self.execution_count = 0
        self.last_execution_time = None

        # Redis 数据获取器
        self.redis_fetcher = None

        # 币种池（Binance 格式，因为 Redis 中使用 Binance 格式）
        self.symbols_binance = self._load_currency_pool()

        # GNN模型
        self.gnn = None

        # 历史数据缓存
        self.history_df = None

        # 当前目标仓位
        self.target_positions = {}

        # 测试模式
        self.dry_run = False

    def _load_currency_pool(self) -> list:
        """加载币种池（Binance 格式）"""
        symbols = []
        try:
            # 优先加载 Binance 格式的币种池
            if os.path.exists(CURRENCY_POOL_BINANCE_FILE):
                with open(CURRENCY_POOL_BINANCE_FILE, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            symbols.append(line)
                self.log_info(f"[币种池] 加载 {len(symbols)} 个 Binance 格式币种")
            elif os.path.exists(CURRENCY_POOL_OKX_FILE):
                # 从 OKX 格式转换
                with open(CURRENCY_POOL_OKX_FILE, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            binance_symbol = convert_okx_to_binance_symbol(line)
                            symbols.append(binance_symbol)
                self.log_info(f"[币种池] 从 OKX 格式转换 {len(symbols)} 个币种")
        except FileNotFoundError as e:
            self.log_error(f"[币种池] 文件不存在: {e}")

        return symbols

    def _connect_redis(self) -> bool:
        """连接到 Redis"""
        self.redis_fetcher = RedisHistoryFetcher(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password
        )
        return self.redis_fetcher.connect()

    def _fetch_history_from_redis(self) -> pd.DataFrame:
        """从 Redis 获取历史数据"""
        if not self.redis_fetcher:
            self.log_error("[Redis] 未连接")
            return pd.DataFrame()

        self.log_info(f"[Redis] 获取 {len(self.symbols_binance)} 个币种的历史K线...")
        start_time = time.time()

        df = fetch_all_history_from_redis(
            fetcher=self.redis_fetcher,
            symbols=self.symbols_binance,
            interval=INTERVAL,
            limit=HISTORY_BARS,
            symbol_format="binance"  # Redis 中使用 Binance 格式存储
        )

        elapsed = time.time() - start_time

        if not df.empty:
            self.log_info(f"[Redis] 完成: {len(df)} 条数据, 耗时 {elapsed:.2f}s")
        else:
            self.log_error("[Redis] 获取失败，无有效数据")

        return df

    def on_init(self):
        """策略初始化"""
        print("=" * 60)
        print("       GNN策略 - Redis版本")
        print("       从 Redis 获取历史数据")
        print("=" * 60)
        print()
        print(f"  交易所: Binance {'(测试网)' if self.is_testnet else '(主网)'}")
        print(f"  Redis: {self.redis_host}:{self.redis_port}")
        print(f"  定时执行: 每 {SCHEDULE_INTERVAL} 执行一次")
        print(f"  仓位金额: {self.position_size_usdt} USDT")
        print(f"  Dry Run: {'是' if self.dry_run else '否'}")
        print()
        print(f"币种数量: {len(self.symbols_binance)}")
        print(f"分层数量: {self.n_layers}")
        print()
        print("-" * 60)

        # 检查 API 密钥
        if not self.api_key or not self.secret_key:
            self.log_error("[初始化] 请设置环境变量 BINANCE_API_KEY 和 BINANCE_SECRET_KEY")
            return

        # 1. 连接 Redis
        self.log_info("[初始化] 连接 Redis...")
        if not self._connect_redis():
            self.log_error("[初始化] Redis 连接失败")
            return

        # 2. 加载GNN模型
        self.log_info("[初始化] 加载GNN模型...")
        try:
            model_dir = os.path.join(TRADING_DIR, "model")
            self.gnn = GNN_Strategy(model_dir=model_dir, seeds=SEEDS, top_k_graph=TOP_K_GRAPH)
            self.log_info("[初始化] GNN模型加载成功")
        except Exception as e:
            self.log_error(f"[初始化] GNN模型加载失败: {e}")
            return

        # 3. 获取历史数据
        self.log_info("[初始化] 从 Redis 获取历史K线数据...")
        self.history_df = self._fetch_history_from_redis()
        if self.history_df.empty:
            self.log_error("[初始化] 历史数据获取失败，请确保 data_recorder 正在运行")
            return

        self.data_ready = True
        self.log_info(f"[初始化] 历史数据准备完成: {len(self.history_df)} 条")

        # 4. 注册账户 (Binance)
        self.log_info("[初始化] 注册 Binance 账户...")
        self.register_binance_account(
            api_key=self.api_key,
            secret_key=self.secret_key,
            is_testnet=self.is_testnet
        )

        # 5. 注册定时任务
        self.schedule_task("execute_strategy", SCHEDULE_INTERVAL)
        self.log_info(f"[初始化] 定时任务已注册: 每 {SCHEDULE_INTERVAL} 执行")

        print("-" * 60)
        print("[初始化] 完成，等待定时执行...")
        print("=" * 60)

    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.account_ready = True
            usdt = self.get_usdt_available()
            self.log_info(f"[账户] Binance 注册成功, USDT余额: {usdt:.2f}")

            # 首次执行策略
            if self.data_ready:
                self.log_info("[策略] 首次执行策略计算...")
                self.execute_strategy()
        else:
            self.log_error(f"[账户] 注册失败: {error_msg}")

    def execute_strategy(self):
        """执行策略（定时任务调用）"""
        self.execution_count += 1

        if not self.account_ready:
            self.log_info(f"[策略#{self.execution_count}] 跳过: 账户未就绪")
            return

        if not self.data_ready:
            self.log_info(f"[策略#{self.execution_count}] 跳过: 数据未就绪")
            return

        self.log_info("=" * 60)
        self.log_info(f"[策略#{self.execution_count}] 开始执行GNN策略计算 (Redis)...")
        start_time = time.time()

        try:
            # 1. 刷新历史数据
            self.log_info("[策略] 从 Redis 刷新历史数据...")
            new_df = self._fetch_history_from_redis()
            if not new_df.empty:
                self.history_df = new_df

            if self.history_df is None or self.history_df.empty:
                self.log_error("[策略] 无历史数据")
                return

            # 2. 计算目标仓位
            self.log_info("[策略] 计算目标仓位...")
            self.target_positions = self.gnn.cal_target_position(self.history_df, self.n_layers)

            elapsed = time.time() - start_time
            self.log_info(f"[策略] 计算完成, 耗时: {elapsed:.2f}s")

            if not self.target_positions:
                self.log_info("[策略] 无有效仓位信号")
                return

            # 3. 打印目标仓位
            long_positions = {k: v for k, v in self.target_positions.items() if v > 0}
            short_positions = {k: v for k, v in self.target_positions.items() if v < 0}

            self.log_info(f"[策略] 多头仓位 ({len(long_positions)}个):")
            for symbol, weight in sorted(long_positions.items(), key=lambda x: -x[1]):
                self.log_info(f"  + {symbol}: {weight*100:.2f}%")

            self.log_info(f"[策略] 空头仓位 ({len(short_positions)}个):")
            for symbol, weight in sorted(short_positions.items(), key=lambda x: x[1]):
                self.log_info(f"  - {symbol}: {weight*100:.2f}%")

            # 4. 执行调仓
            if not self.dry_run:
                self._adjust_positions()
            else:
                self.log_info("[策略] Dry Run模式，不实际下单")

            self.last_execution_time = datetime.now(timezone.utc)
            self.log_info(f"[策略] 执行完成: {self.last_execution_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        except Exception as e:
            self.log_error(f"[策略] 执行失败: {e}")
            import traceback
            traceback.print_exc()

        self.log_info("=" * 60)

    def _adjust_positions(self):
        """调整仓位"""
        if not self.target_positions:
            return

        # 获取当前持仓
        current_positions = self.get_active_positions()
        current_pos_map = {p.symbol: p for p in current_positions}

        # 获取账户余额
        usdt_available = self.get_usdt_available()
        self.log_info(f"[调仓] 可用余额: {usdt_available:.2f} USDT")

        # 使用固定小仓位
        allocation = min(self.position_size_usdt, usdt_available * 0.5)

        # 计算目标持仓数量
        order_count = 0
        for binance_symbol, weight in self.target_positions.items():
            target_value = allocation * abs(weight)

            # 获取当前价格 (DataFrame 中的 Ticker 使用 Binance 格式)
            symbol_df = self.history_df[self.history_df["Ticker"] == binance_symbol]
            if symbol_df.empty:
                continue

            current_price = float(symbol_df["Close"].iloc[-1])
            if current_price <= 0:
                continue

            # 计算目标数量（Binance 使用币数量）
            target_qty = target_value / current_price
            if target_qty < 0.001:
                continue

            # 获取当前仓位
            current_qty = 0
            if binance_symbol in current_pos_map:
                current_qty = current_pos_map[binance_symbol].quantity

            # 计算差额
            if weight > 0:
                diff = target_qty - current_qty
            else:
                diff = -target_qty - current_qty

            if abs(diff) < 0.001:
                continue

            # 下单
            order_side = "buy" if diff > 0 else "sell"
            order_qty = round(abs(diff), 3)

            self.log_info(f"[调仓] {binance_symbol} {order_side.upper()} {order_qty:.4f} "
                         f"(权重: {weight*100:.2f}%, 价格: {current_price:.2f})")

            # 发送 Binance 订单
            order_id = self.send_binance_futures_market_order(
                symbol=binance_symbol,
                side=order_side,
                quantity=order_qty,
                pos_side="BOTH"
            )

            if order_id:
                self.log_info(f"[调仓] 订单ID: {order_id}")
                order_count += 1
            else:
                self.log_error(f"[调仓] 订单发送失败: {binance_symbol}")

            # 限制每次调仓的订单数量
            if order_count >= 5:
                self.log_info("[调仓] 达到测试订单上限(5单)，停止调仓")
                break

    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        symbol = report.get("symbol", "")
        side = report.get("side", "")
        exchange = report.get("exchange", "")

        if status == "filled":
            filled_qty = report.get("filled_quantity", 0)
            filled_price = report.get("filled_price", 0)
            self.log_info(f"[成交] {exchange}|{symbol} {side} {filled_qty} @ {filled_price:.2f}")
        elif status == "rejected":
            error_msg = report.get("error_msg", "")
            self.log_error(f"[拒绝] {exchange}|{symbol} {side} | {error_msg}")
        elif status == "accepted":
            self.log_info(f"[接受] {exchange}|{symbol} {side}")

    def on_stop(self):
        """策略停止"""
        print()
        print("=" * 60)
        print("[策略] Redis GNN策略停止")
        print(f"[策略] 总执行次数: {self.execution_count}")
        if self.last_execution_time:
            print(f"[策略] 最后执行: {self.last_execution_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # 打印当前持仓
        positions = self.get_active_positions()
        if positions:
            print(f"[策略] 当前持仓: {len(positions)} 个")
            for p in positions:
                print(f"  - {p.symbol}: {p.quantity} @ {p.avg_price:.2f}")

        # 断开 Redis
        if self.redis_fetcher:
            self.redis_fetcher.disconnect()

        print("=" * 60)


def main():
    # 检查环境变量
    if not os.getenv("BINANCE_API_KEY"):
        print("请设置环境变量:")
        print("  export BINANCE_API_KEY=your_api_key")
        print("  export BINANCE_SECRET_KEY=your_secret_key")
        print("  export BINANCE_TESTNET=1  # 1=测试网, 0=主网")
        print()
        print("可选 Redis 配置:")
        print("  export REDIS_HOST=127.0.0.1")
        print("  export REDIS_PORT=6379")
        print("  export REDIS_PASSWORD=your_password")
        return

    strategy = GNNRedisStrategy()

    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())

    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()
