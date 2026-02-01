#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GNN策略 - 配置文件版本（从Redis读取历史数据）

从 configs/ 目录读取JSON配置文件运行

使用方法:
    cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies/GNN_model/trading/GNNstr
    python3 gnn_strategy_config.py --config ../../../../configs/gnn_multi_coin.json

编译依赖：
    cd cpp/build && cmake .. && make strategy_base
"""

import sys
import os
import signal
import time
import argparse
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

# 路径设置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))           # GNNstr/
TRADING_DIR = os.path.dirname(SCRIPT_DIR)                          # trading/
GNN_MODEL_DIR = os.path.dirname(TRADING_DIR)                       # GNN_model/
STRATEGIES_DIR = os.path.dirname(GNN_MODEL_DIR)                    # strategies/
BUILD_DIR = os.path.join(STRATEGIES_DIR, 'build')                 # strategies/build/

# 添加路径用于导入
sys.path.insert(0, BUILD_DIR)         # 用于导入 strategy_base（使用新编译的版本）
sys.path.insert(0, TRADING_DIR)       # 用于导入 GNNStr
sys.path.insert(0, STRATEGIES_DIR)    # 用于导入 strategy_logger

from strategy_base import StrategyBase
from GNNStr import GNN_Strategy, SEQ_LEN, SEEDS, TOP_K_GRAPH
from redis_history_fetcher import RedisHistoryFetcher, fetch_all_history_from_redis
from strategy_logger import setup_strategy_logging


class GNNConfigStrategy(StrategyBase):
    """GNN交易策略 - 从配置文件读取参数，从Redis读取历史数据"""

    def __init__(self, config_file: str, log_file_path: str = ""):
        """
        初始化策略

        Args:
            config_file: 配置文件路径
            log_file_path: 日志文件路径（空字符串表示不记录到文件）
        """
        # 加载配置
        self.config = self._load_config(config_file)

        # 初始化基类
        strategy_id = self.config.get("strategy_id", "gnn_strategy")
        super().__init__(strategy_id, max_kline_bars=1500, log_file_path=log_file_path)
        self._set_python_self(self)

        # 从配置读取参数
        self.exchange = self.config.get("exchange", "okx")
        self.api_key = self.config.get("api_key", "")
        self.secret_key = self.config.get("secret_key", "")
        self.passphrase = self.config.get("passphrase", "")
        self.is_testnet = self.config.get("is_testnet", True)

        # 策略参数
        params = self.config.get("params", {})
        self.n_layers = params.get("n_layers", 20)
        self.position_size_usdt = params.get("position_size_usdt", 500)
        self.history_bars = params.get("history_bars", 1200)
        self.interval = params.get("interval", "1m")
        self.schedule_interval = params.get("schedule_interval", "10m")
        self.schedule_time = params.get("schedule_time", "now")

        # Redis配置
        self.redis_host = params.get("redis_host", "127.0.0.1")
        self.redis_port = params.get("redis_port", 6379)
        self.redis_password = params.get("redis_password", "")

        # 币种池
        self.symbols = params.get("symbols", [])
        if not self.symbols:
            # 如果配置中没有指定币种，从文件加载
            currency_pool_file = params.get("currency_pool_file", "")
            if not currency_pool_file:
                # 根据交易所选择默认币种池文件
                if self.exchange == "okx":
                    currency_pool_file = os.path.join(TRADING_DIR, "currency_pool_okx.txt")
                elif self.exchange == "binance":
                    currency_pool_file = os.path.join(TRADING_DIR, "currency_pool_binance.txt")
            if currency_pool_file:
                self.symbols = self._load_currency_pool(currency_pool_file)

        # 状态
        self.account_ready = False
        self.data_ready = False
        self.first_execution_done = False  # 是否已执行首次策略
        self.execution_count = 0
        self.last_execution_time = None

        # Redis数据获取器
        self.redis_fetcher = None

        # GNN模型
        self.gnn = None

        # 历史数据缓存
        self.history_df = None

        # 当前目标仓位
        self.target_positions = {}

        # 打印配置信息
        self._print_config()

    def _load_config(self, config_file: str) -> dict:
        """加载配置文件"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print(f"[配置] 成功加载配置文件: {config_file}")
            return config
        except FileNotFoundError:
            print(f"[错误] 配置文件不存在: {config_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"[错误] 配置文件格式错误: {e}")
            sys.exit(1)

    def _load_currency_pool(self, file_path: str) -> list:
        """加载币种池"""
        symbols = []
        try:
            with open(file_path, "r") as f:
                for line in f:
                    symbol = line.strip()
                    if symbol and not symbol.startswith("#"):
                        symbols.append(symbol)
            print(f"[币种池] 从文件加载 {len(symbols)} 个币种")
        except FileNotFoundError:
            print(f"[币种池] 文件不存在: {file_path}")
        return symbols

    def _print_config(self):
        """打印配置信息"""
        print("=" * 60)
        print(f"  {self.config.get('strategy_name', 'GNN策略')}")
        print("=" * 60)
        print()
        print(f"策略ID: {self.config.get('strategy_id')}")
        print(f"交易所: {self.exchange} {'(模拟盘)' if self.is_testnet else '(实盘)'}")
        print(f"Redis: {self.redis_host}:{self.redis_port}")
        print(f"币种数量: {len(self.symbols)}")
        print(f"分层数量: {self.n_layers}")
        print(f"仓位金额: {self.position_size_usdt} USDT")
        print(f"定时执行: 每{self.schedule_interval} {self.schedule_time}")
        print()

        # 打印联系人信息
        contacts = self.config.get("contacts", [])
        if contacts:
            print("联系人:")
            for contact in contacts:
                print(f"  - {contact.get('name')} ({contact.get('role')})")
                print(f"    电话: {contact.get('phone')}, 微信: {contact.get('wechat')}")

        # 打印风控信息
        risk_control = self.config.get("risk_control", {})
        if risk_control.get("enabled"):
            print()
            print("风控设置:")
            print(f"  最大持仓: {risk_control.get('max_position_value')} USDT")
            print(f"  最大日亏损: {risk_control.get('max_daily_loss')} USDT")
            print(f"  单笔限额: {risk_control.get('max_order_amount')} USDT")

        print()
        print("-" * 60)

    def _connect_redis(self) -> bool:
        """连接到Redis"""
        self.redis_fetcher = RedisHistoryFetcher(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password
        )
        return self.redis_fetcher.connect()

    def _fetch_history_from_redis(self) -> pd.DataFrame:
        """从Redis获取历史数据"""
        if not self.redis_fetcher:
            self.log_error("[Redis] 未连接")
            return pd.DataFrame()

        self.log_info(f"[Redis] 获取 {len(self.symbols)} 个币种的历史K线...")
        start_time = time.time()

        # 根据交易所选择symbol格式
        if self.exchange == "okx":
            symbol_format = "okx"
        elif self.exchange == "binance":
            symbol_format = "binance"
        else:
            symbol_format = "okx"

        df = fetch_all_history_from_redis(
            fetcher=self.redis_fetcher,
            symbols=self.symbols,
            interval=self.interval,
            limit=self.history_bars,
            symbol_format=symbol_format,
            exchange=self.exchange
        )

        elapsed = time.time() - start_time

        if not df.empty:
            self.log_info(f"[Redis] 完成: {len(df)} 条数据, 耗时 {elapsed:.2f}s")
        else:
            self.log_error("[Redis] 获取失败，无有效数据")

        return df

    def on_init(self):
        """策略初始化"""
        # 1. 连接Redis
        self.log_info("[初始化] 连接Redis...")
        if not self._connect_redis():
            self.log_error("[初始化] Redis连接失败")
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
        self.log_info("[初始化] 从Redis获取历史K线数据...")
        self.history_df = self._fetch_history_from_redis()
        if self.history_df.empty:
            self.log_error("[初始化] 历史数据获取失败，请确保data_recorder正在运行")
            return

        self.data_ready = True
        self.log_info(f"[初始化] 历史数据准备完成: {len(self.history_df)} 条")

        # 4. 注册账户
        self.log_info("[初始化] 注册账户...")
        if self.exchange == "okx":
            self.register_account(
                api_key=self.api_key,
                secret_key=self.secret_key,
                passphrase=self.passphrase,
                is_testnet=self.is_testnet
            )
        elif self.exchange == "binance":
            self.register_binance_account(
                api_key=self.api_key,
                secret_key=self.secret_key,
                is_testnet=self.is_testnet
            )
        else:
            self.log_error(f"[初始化] 不支持的交易所: {self.exchange}")
            return

        # 5. 注册定时任务
        self.schedule_task("execute_strategy", self.schedule_interval, self.schedule_time)
        self.log_info(f"[初始化] 定时任务已注册: 每{self.schedule_interval} {self.schedule_time}执行")

        print("-" * 60)
        print("[初始化] 完成，等待定时执行...")
        print("=" * 60)

    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.account_ready = True
            self.log_info("[账户] ✓ 注册成功，正在查询余额...")

            # 主动刷新账户余额
            self.refresh_account()
        else:
            self.log_error(f"[账户] ✗ 注册失败: {error_msg}")

    def on_account_update(self, total_equity: float, margin_ratio: float):
        """账户更新回调 - 收到余额数据时触发"""
        usdt = self.get_usdt_available()
        self.log_info(f"[账户] 余额更新: USDT={usdt:.2f}, 总权益={total_equity:.2f}")

        # 如果是首次余额更新且数据已就绪，执行首次策略
        if not self.first_execution_done and self.data_ready and usdt >= 10:
            self.log_info("[策略] 余额已更新，执行首次策略计算...")
            self.first_execution_done = True
            self.execute_strategy()

    def on_balance_update(self, balances: dict):
        """余额更新回调"""
        self.log_info(f"[账户] on_balance_update 回调: {balances}")
        usdt = self.get_usdt_available()
        self.log_info(f"[账户] USDT可用余额: {usdt:.2f}")

    def execute_strategy(self):
        """执行策略（定时任务调用）"""
        self.execution_count += 1

        if not self.account_ready:
            self.log_info(f"[策略#{self.execution_count}] 跳过: 账户未就绪")
            return

        if not self.data_ready:
            self.log_info(f"[策略#{self.execution_count}] 跳过: 数据未就绪")
            return

        # 刷新账户余额
        self.refresh_account()

        # 获取当前余额并检查
        usdt_available = self.get_usdt_available()
        if usdt_available < 10:  # 至少需要10 USDT
            self.log_info(f"[策略#{self.execution_count}] 跳过: 余额不足或未更新 (当前: {usdt_available:.2f} USDT)")
            return

        self.log_info("=" * 60)
        self.log_info(f"[策略#{self.execution_count}] 开始执行GNN策略计算...")
        start_time = time.time()

        # 显示当前余额
        self.log_info(f"[策略] 可用余额: {usdt_available:.2f} USDT")

        try:
            # 1. 刷新历史数据
            self.log_info("[策略] 从Redis刷新历史数据...")
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
            self._adjust_positions()

            self.last_execution_time = datetime.now(timezone.utc)
            self.log_info(f"[策略] 执行完成: {self.last_execution_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        except Exception as e:
            self.log_error(f"[策略] 执行失败: {e}")
            import traceback
            traceback.print_exc()

        self.log_info("=" * 60)

    def adjust_binance_quantity(self, symbol: str, quantity: float, price: float, min_notional: float = 100.0):
        """
        调整 Binance 订单数量以符合交易规则

        Args:
            symbol: 交易对
            quantity: 原始数量
            price: 当前价格
            min_notional: 最小订单金额（默认 100 USDT）

        Returns:
            调整后的数量，如果无法满足最小金额则返回 0
        """
        # Binance 合约的数量精度规则（常见币种）
        # 精度值表示小数位数：0=整数，1=一位小数，2=两位小数，3=三位小数
        quantity_precision = {
            'BTCUSDT': 3,    # 0.001
            'ETHUSDT': 3,    # 0.001
            'BNBUSDT': 2,    # 0.01
            'ADAUSDT': 1,    # 0.1
            'DOGEUSDT': 0,   # 1
            'XRPUSDT': 1,    # 0.1
            'DOTUSDT': 1,    # 0.1
            'UNIUSDT': 0,    # 1 (整数)
            'LTCUSDT': 3,    # 0.001
            'LINKUSDT': 2,   # 0.01
            'BCHUSDT': 3,    # 0.001
            'MATICUSDT': 0,  # 1
            'SOLUSDT': 2,    # 0.01
            'AVAXUSDT': 1,   # 0.1
            'ATOMUSDT': 2,   # 0.01
            'FILUSDT': 2,    # 0.01
            'TRXUSDT': 0,    # 1
            'ETCUSDT': 1,    # 0.1
            'XLMUSDT': 0,    # 1
            'VETUSDT': 0,    # 1
            'ICPUSDT': 1,    # 0.1
            'THETAUSDT': 0,  # 1
            'AXSUSDT': 0,    # 1 (整数)
            'SANDUSDT': 0,   # 1
            'MANAUSDT': 0,   # 1
            'AAVEUSDT': 2,   # 0.01
            'ALGOUSDT': 0,   # 1
            'KSMUSDT': 3,    # 0.001
            'NEARUSDT': 1,   # 0.1
            'FTMUSDT': 0,    # 1
            'GRTUSDT': 0,    # 1
            'ENJUSDT': 0,    # 1
            'CHZUSDT': 0,    # 1
            'ZILUSDT': 0,    # 1
            'COMPUSDT': 3,   # 0.001
            'SNXUSDT': 1,    # 0.1
            'MKRUSDT': 4,    # 0.0001
            'DASHUSDT': 3,   # 0.001
            'ZECUSDT': 3,    # 0.001
            'YFIUSDT': 4,    # 0.0001
            'BATUSDT': 0,    # 1
            'ZRXUSDT': 0,    # 1
            'CRVUSDT': 1,    # 0.1
            'SUSHIUSDT': 1,  # 0.1
            '1INCHUSDT': 1,  # 0.1
            'RUNEUSDT': 1,   # 0.1
            'OCEANUSDT': 0,  # 1
            'BELUSDT': 1,    # 0.1
            'LITUSDT': 1,    # 0.1
            'COTIUSDT': 0,   # 1
            'ANKRUSDT': 0,   # 1
            'OGNUSDT': 0,    # 1
            'REEFUSDT': 0,   # 1
            'RLCUSDT': 1,    # 0.1
            'NKNUSDT': 0,    # 1
            'LRCUSDT': 0,    # 1
            'SCUSDT': 0,     # 1
            'CHRUSDT': 0,    # 1
            'HOTUSDT': 0,    # 1
            'STMXUSDT': 0,   # 1
            'DENTUSDT': 0,   # 1
            'HBARUSDT': 0,   # 1
            'CELRUSDT': 0,   # 1
            'IOTXUSDT': 0,   # 1
            'ONEUSDT': 0,    # 1
            'LINAUSDT': 0,   # 1 (LINEAUSDT 可能是 LINAUSDT)
            'LINEAUSDT': 0,  # 1
            'AUCTIONUSDT': 2, # 0.01
            'RESOLVUSDT': 1,  # 0.1
            'ENSOUSDT': 1,    # 0.1
        }

        # 获取精度，默认为 0（整数）
        precision = quantity_precision.get(symbol, 0)

        # 根据精度调整数量
        adjusted_qty = round(quantity, precision)

        # 确保至少有最小数量
        if adjusted_qty == 0:
            adjusted_qty = 10 ** (-precision) if precision > 0 else 1

        # 检查最小订单金额
        notional = adjusted_qty * price
        if notional < min_notional:
            # 计算满足最小金额的数量
            min_qty = min_notional / price
            adjusted_qty = round(min_qty * 1.01, precision)  # 增加 1% 以确保满足要求

            # 再次检查
            notional = adjusted_qty * price
            if notional < min_notional:
                self.log_info(f"[调仓] {symbol} 订单金额 {notional:.2f} USDT 小于最小限制 {min_notional} USDT，跳过")
                return 0

        return adjusted_qty

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

        # 风控检查
        risk_control = self.config.get("risk_control", {})
        if risk_control.get("enabled"):
            max_position = risk_control.get("max_position_value", float('inf'))
            total_equity = self.get_total_equity()
            if total_equity > max_position:
                self.log_info(f"[风控] 超过最大持仓限制 {max_position} USDT，停止调仓")
                return

        # 使用固定小仓位
        allocation = min(self.position_size_usdt, usdt_available * 0.5)

        # 计算目标持仓数量
        order_count = 0
        for symbol, weight in self.target_positions.items():
            target_value = allocation * abs(weight)

            # 获取当前价格
            symbol_df = self.history_df[self.history_df["Ticker"] == symbol]
            if symbol_df.empty:
                continue

            current_price = float(symbol_df["Close"].iloc[-1])
            if current_price <= 0:
                continue

            # 根据交易所计算目标数量
            if self.exchange == "okx":
                # OKX合约：计算张数（1张=0.01个币）
                target_qty = int(target_value / current_price / 0.01)
            elif self.exchange == "binance":
                # Binance：计算币数量
                raw_qty = target_value / current_price
                # 调整数量以符合 Binance 规则
                target_qty = self.adjust_binance_quantity(symbol, raw_qty, current_price)
                if target_qty == 0:
                    continue  # 跳过无法满足最小金额的订单
            else:
                continue

            if target_qty <= 0:
                continue

            # 获取当前仓位
            current_qty = 0
            if symbol in current_pos_map:
                current_qty = current_pos_map[symbol].quantity

            # 计算差额
            if weight > 0:
                diff = target_qty - current_qty
            else:
                diff = -target_qty - current_qty

            if abs(diff) < (1 if self.exchange == "okx" else 0.001):
                continue

            # 下单
            order_side = "buy" if diff > 0 else "sell"
            order_qty = abs(diff)

            self.log_info(f"[调仓] {symbol} {order_side.upper()} {order_qty} "
                         f"(权重: {weight*100:.2f}%, 价格: {current_price:.2f})")

            # 发送订单
            if self.exchange == "okx":
                order_id = self.send_swap_market_order(symbol, order_side, int(order_qty), "net")
            elif self.exchange == "binance":
                order_id = self.send_binance_futures_market_order(
                    symbol=symbol,
                    side=order_side,
                    quantity=order_qty,
                    pos_side="BOTH"
                )
            else:
                order_id = None

            if order_id:
                self.log_info(f"[调仓] 订单ID: {order_id}")
                order_count += 1
            else:
                self.log_error(f"[调仓] 订单发送失败: {symbol}")

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

        # 获取数量（尝试多个字段）
        quantity = report.get("quantity", 0)
        if quantity == 0:
            quantity = report.get("filled_quantity", 0)
        if quantity == 0:
            quantity = report.get("orig_qty", 0)

        if status == "filled":
            filled_qty = report.get("filled_quantity", quantity)
            filled_price = report.get("filled_price", 0)
            self.log_info(f"[成交] {exchange}|{symbol} {side} {filled_qty} @ {filled_price:.2f}")
        elif status == "rejected":
            error_msg = report.get("error_msg", "")
            self.log_error(f"[拒绝] {exchange}|{symbol} {side} {quantity} | {error_msg}")
        elif status == "accepted":
            self.log_info(f"[接受] {exchange}|{symbol} {side} {quantity}")

    def on_stop(self):
        """策略停止"""
        print()
        print("=" * 60)
        print("[策略] GNN策略停止")
        print(f"[策略] 总执行次数: {self.execution_count}")
        if self.last_execution_time:
            print(f"[策略] 最后执行: {self.last_execution_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # 打印当前持仓
        positions = self.get_active_positions()
        if positions:
            print(f"[策略] 当前持仓: {len(positions)} 个")
            for p in positions:
                print(f"  - {p.symbol}: {p.quantity} @ {p.avg_price:.2f}")

        # 断开Redis
        if self.redis_fetcher:
            self.redis_fetcher.disconnect()

        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='GNN策略 - 配置文件版本（Redis）')
    parser.add_argument('--config', type=str, required=True,
                       help='配置文件路径 (如: ../../../../configs/gnn_multi_coin.json)')

    args = parser.parse_args()

    # 检查配置文件是否存在
    if not os.path.exists(args.config):
        # 这个错误在日志初始化之前，所以不会被记录（这是合理的，因为配置文件都不存在）
        print(f"错误: 配置文件不存在: {args.config}")
        sys.exit(1)

    # 预先加载配置以获取 strategy_id 和 exchange
    with open(args.config, 'r', encoding='utf-8') as f:
        config = json.load(f)

    strategy_id = config.get("strategy_id", "gnn_strategy")
    exchange = config.get("exchange", "binance")

    # ★ 设置日志（在创建策略之前，尽早初始化）
    log_dir = os.path.join(STRATEGIES_DIR, 'log')
    logger = setup_strategy_logging(exchange=exchange, strategy_id=strategy_id, log_dir=log_dir)

    # 现在所有的print都会被记录
    print(f"✓ 配置文件: {args.config}")
    print(f"✓ 日志文件: {logger.log_file}")
    print()

    # 创建策略
    strategy = GNNConfigStrategy(args.config, log_file_path=logger.log_file)

    # 注册信号处理 - 使用更强制的方式
    def signal_handler(signum, frame):
        print("\n" + "=" * 60)
        print("[信号] 收到退出信号 (Ctrl+C)，正在停止策略...")
        print("=" * 60)
        try:
            strategy.stop()
            logger.close()  # 关闭日志文件
            # 给策略一点时间清理
            time.sleep(0.5)
        except:
            pass
        print("[信号] 强制退出")
        # 使用 os._exit 强制退出，不等待线程
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 运行策略
    try:
        strategy.run()
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("[中断] 收到键盘中断，正在停止...")
        print("=" * 60)
        try:
            strategy.stop()
            logger.close()  # 关闭日志文件
            time.sleep(0.5)
        except:
            pass
        print("[中断] 强制退出")
        os._exit(0)
    except Exception as e:
        print(f"\n[错误] 策略异常: {e}")
        import traceback
        traceback.print_exc()
        logger.close()  # 关闭日志文件
        os._exit(1)
    finally:
        logger.close()  # 确保日志文件被关闭


if __name__ == "__main__":
    main()
