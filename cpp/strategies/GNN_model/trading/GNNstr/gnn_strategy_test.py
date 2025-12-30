#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GNN策略 - 测试版本

定时执行：每10分钟运行一次
功能：
  1. 启动时通过OKX REST API获取历史K线数据（1200条1分钟K线）
  2. 加载GNN模型进行预测
  3. 根据预测结果调整仓位（测试用小仓位）

运行方式：
    python gnn_strategy_test.py

编译依赖：
    cd cpp/build && cmake .. && make strategy_base

注意：
  - 这是测试版本，每10分钟执行一次
  - 仓位金额设置为较小值，用于验证策略逻辑
  - 建议在模拟盘环境测试
"""

import sys
import os
import signal
import time
import requests
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# 添加父目录到路径，用于导入GNN模型
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from strategy_base import StrategyBase
except ImportError:
    # 尝试从cpp/strategies目录导入
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                    'Real-account-trading-framework/cpp/strategies'))
    from strategy_base import StrategyBase

# 导入GNN模型
from GNNStr import GNN_Strategy, SEQ_LEN, MODEL_DIR, SEEDS, TOP_K_GRAPH

# ======================
# 测试配置
# ======================
HISTORY_BARS = 1200          # 需要的历史K线数量
INTERVAL = "1m"              # K线周期
N_LAYERS = 20                # 分层数量（TOP_PCT = 1/20 = 5%）
POSITION_SIZE_USDT = 100     # 测试用小仓位

# 定时配置 - 测试版本
SCHEDULE_INTERVAL = "10m"    # 每10分钟执行一次

# OKX API配置（公开API，无需认证）
OKX_BASE_URL = "https://www.okx.com"
OKX_HISTORY_CANDLES = "/api/v5/market/history-candles"

# 币种池文件路径
CURRENCY_POOL_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                   "currency_pool_okx.txt")


class GNNTestStrategy(StrategyBase):
    """GNN交易策略 - 测试版本（每10分钟执行）"""
    
    def __init__(self):
        # 初始化基类（增加K线存储容量）
        super().__init__("gnn_test", max_kline_bars=HISTORY_BARS + 100)
        self._set_python_self(self)
        
        # 策略配置
        self.n_layers = N_LAYERS
        self.position_size_usdt = POSITION_SIZE_USDT
        
        # API密钥（请替换为您的密钥）
        self.api_key = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
        self.secret_key = "888CC77C745F1B49E75A992F38929992"
        self.passphrase = "Sequence2025."
        self.is_testnet = True  # True=模拟盘, False=实盘
        
        # 状态
        self.account_ready = False
        self.data_ready = False
        self.execution_count = 0
        self.last_execution_time = None
        
        # 币种池
        self.symbols = self._load_currency_pool()
        
        # GNN模型
        self.gnn = None
        
        # 历史数据缓存
        self.history_df = None
        
        # 当前目标仓位
        self.target_positions = {}
        
        # 测试模式：只打印不下单
        self.dry_run = False  # 设为True则只打印不实际下单
        
    def _load_currency_pool(self) -> list:
        """加载币种池"""
        symbols = []
        try:
            with open(CURRENCY_POOL_FILE, "r") as f:
                for line in f:
                    symbol = line.strip()
                    if symbol:
                        symbols.append(symbol)
            self.log_info(f"[币种池] 加载 {len(symbols)} 个币种")
        except FileNotFoundError:
            self.log_error(f"[币种池] 文件不存在: {CURRENCY_POOL_FILE}")
        return symbols
    
    def _fetch_history_klines(self, symbol: str, limit: int = 300) -> pd.DataFrame:
        """
        获取单个币种的历史K线数据
        OKX API 每次最多返回300条，需要多次请求
        """
        all_data = []
        after = ""  # 分页参数
        
        # 将SWAP格式转换为API格式
        inst_id = symbol  # OKX合约ID格式
        
        remaining = limit
        while remaining > 0:
            batch_size = min(remaining, 300)
            params = {
                "instId": inst_id,
                "bar": INTERVAL,
                "limit": str(batch_size)
            }
            if after:
                params["after"] = after
            
            try:
                resp = requests.get(
                    OKX_BASE_URL + OKX_HISTORY_CANDLES,
                    params=params,
                    timeout=30
                )
                data = resp.json()
                
                if data.get("code") != "0" or not data.get("data"):
                    break
                
                candles = data["data"]
                if not candles:
                    break
                
                all_data.extend(candles)
                after = candles[-1][0]  # 使用最后一条的时间戳作为分页参数
                remaining -= len(candles)
                
                if len(candles) < batch_size:
                    break  # 没有更多数据
                    
            except Exception as e:
                self.log_error(f"[历史数据] {symbol} 获取失败: {e}")
                break
        
        if not all_data:
            return pd.DataFrame()
        
        # 转换为DataFrame
        # OKX返回格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        df = pd.DataFrame(all_data, columns=[
            "timestamp", "open", "high", "low", "close", 
            "vol", "volCcy", "volCcyQuote", "confirm"
        ])
        
        df["instId"] = symbol
        df["timestamp"] = pd.to_numeric(df["timestamp"])
        for col in ["open", "high", "low", "close", "vol", "volCcy", "volCcyQuote"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 按时间升序排列
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        return df
    
    def _fetch_all_history_data(self) -> pd.DataFrame:
        """并行获取所有币种的历史数据"""
        self.log_info(f"[历史数据] 开始获取 {len(self.symbols)} 个币种的历史K线...")
        start_time = time.time()
        
        all_dfs = []
        failed_symbols = []
        
        # 使用线程池并行获取
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self._fetch_history_klines, symbol, HISTORY_BARS): symbol 
                for symbol in self.symbols
            }
            
            for i, future in enumerate(as_completed(futures)):
                symbol = futures[future]
                try:
                    df = future.result()
                    if not df.empty:
                        all_dfs.append(df)
                    else:
                        failed_symbols.append(symbol)
                except Exception as e:
                    self.log_error(f"[历史数据] {symbol} 处理失败: {e}")
                    failed_symbols.append(symbol)
                
                # 进度日志
                if (i + 1) % 50 == 0:
                    self.log_info(f"[历史数据] 进度: {i + 1}/{len(self.symbols)}")
        
        elapsed = time.time() - start_time
        
        if all_dfs:
            combined_df = pd.concat(all_dfs, ignore_index=True)
            self.log_info(f"[历史数据] 完成: {len(all_dfs)} 个币种, "
                         f"{len(combined_df)} 条数据, 耗时 {elapsed:.1f}s")
            if failed_symbols:
                self.log_info(f"[历史数据] 失败: {len(failed_symbols)} 个币种")
            return combined_df
        else:
            self.log_error("[历史数据] 获取失败，无有效数据")
            return pd.DataFrame()
    
    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """准备GNN模型输入数据格式"""
        # 重命名列以匹配GNN模型要求
        df = df.rename(columns={
            "instId": "Ticker",
            "timestamp": "Time",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volCcy": "Volume"
        })
        
        # 转换时间
        df["Time"] = pd.to_datetime(df["Time"], unit="ms")
        
        return df[["Ticker", "Time", "Open", "High", "Low", "Close", "Volume"]]
    
    def on_init(self):
        """策略初始化"""
        print("=" * 60)
        print("       GNN策略 - 测试版本")
        print("=" * 60)
        print()
        print(f"⚠️  测试模式: 每 {SCHEDULE_INTERVAL} 执行一次")
        print(f"⚠️  仓位金额: {self.position_size_usdt} USDT (小仓位测试)")
        print(f"⚠️  Dry Run: {'是' if self.dry_run else '否'}")
        print()
        print(f"币种数量: {len(self.symbols)}")
        print(f"分层数量: {self.n_layers}")
        print()
        print("-" * 60)
        
        # 1. 加载GNN模型
        self.log_info("[初始化] 加载GNN模型...")
        try:
            model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model")
            self.gnn = GNN_Strategy(model_dir=model_dir, seeds=SEEDS, top_k_graph=TOP_K_GRAPH)
            self.log_info("[初始化] GNN模型加载成功")
        except Exception as e:
            self.log_error(f"[初始化] GNN模型加载失败: {e}")
            return
        
        # 2. 获取历史数据
        self.log_info("[初始化] 获取历史K线数据...")
        self.history_df = self._fetch_all_history_data()
        if self.history_df.empty:
            self.log_error("[初始化] 历史数据获取失败")
            return
        
        self.history_df = self._prepare_dataframe(self.history_df)
        self.data_ready = True
        self.log_info(f"[初始化] 历史数据准备完成: {len(self.history_df)} 条")
        
        # 3. 注册账户
        self.log_info("[初始化] 注册账户...")
        self.register_account(
            api_key=self.api_key,
            secret_key=self.secret_key,
            passphrase=self.passphrase,
            is_testnet=self.is_testnet
        )
        
        # 4. 注册定时任务（每10分钟执行一次）
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
            self.log_info(f"[账户] ✓ 注册成功, USDT余额: {usdt:.2f}")
            
            # 首次执行策略
            if self.data_ready:
                self.log_info("[策略] 首次执行策略计算...")
                self.execute_strategy()
        else:
            self.log_error(f"[账户] ✗ 注册失败: {error_msg}")
    
    def execute_strategy(self):
        """执行策略（定时任务调用）"""
        self.execution_count += 1
        
        if not self.account_ready:
            self.log_info(f"[策略#{self.execution_count}] 跳过: 账户未就绪")
            return
        
        if not self.data_ready or self.history_df is None or self.history_df.empty:
            self.log_info(f"[策略#{self.execution_count}] 跳过: 数据未就绪")
            return
        
        self.log_info("=" * 60)
        self.log_info(f"[策略#{self.execution_count}] 开始执行GNN策略计算...")
        start_time = time.time()
        
        try:
            # 1. 刷新历史数据（获取最新数据）
            self.log_info("[策略] 刷新历史数据...")
            new_df = self._fetch_all_history_data()
            if not new_df.empty:
                self.history_df = self._prepare_dataframe(new_df)
            
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
                self.log_info(f"  📈 {symbol}: {weight*100:.2f}%")
            
            self.log_info(f"[策略] 空头仓位 ({len(short_positions)}个):")
            for symbol, weight in sorted(short_positions.items(), key=lambda x: x[1]):
                self.log_info(f"  📉 {symbol}: {weight*100:.2f}%")
            
            # 4. 执行调仓
            if not self.dry_run:
                self._adjust_positions()
            else:
                self.log_info("[策略] ⚠️ Dry Run模式，不实际下单")
            
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
        
        # 测试版本：使用固定小仓位
        allocation = min(self.position_size_usdt, usdt_available * 0.5)  # 最多用一半余额
        
        # 计算目标持仓数量
        order_count = 0
        for symbol, weight in self.target_positions.items():
            target_value = allocation * abs(weight)
            side = "buy" if weight > 0 else "sell"
            
            # 获取当前价格
            symbol_df = self.history_df[self.history_df["Ticker"] == symbol]
            if symbol_df.empty:
                continue
            
            current_price = float(symbol_df["Close"].iloc[-1])
            if current_price <= 0:
                continue
            
            # 计算目标张数（假设每张0.01个币）
            target_contracts = int(target_value / current_price / 0.01)
            if target_contracts <= 0:
                continue
            
            # 获取当前仓位
            current_qty = 0
            if symbol in current_pos_map:
                current_qty = current_pos_map[symbol].quantity
            
            # 计算差额
            if weight > 0:
                diff = target_contracts - current_qty
            else:
                diff = -target_contracts - current_qty
            
            if abs(diff) < 1:
                continue
            
            # 下单
            order_side = "buy" if diff > 0 else "sell"
            order_qty = abs(int(diff))
            
            self.log_info(f"[调仓] {symbol} {order_side} {order_qty}张 "
                         f"(权重: {weight*100:.2f}%, 价格: {current_price:.2f})")
            
            # 发送订单
            order_id = self.send_swap_market_order(symbol, order_side, order_qty, "net")
            if order_id:
                self.log_info(f"[调仓] ✓ 订单ID: {order_id}")
                order_count += 1
            else:
                self.log_error(f"[调仓] ✗ 订单发送失败: {symbol}")
            
            # 限制每次调仓的订单数量（测试用）
            if order_count >= 5:
                self.log_info("[调仓] 达到测试订单上限(5单)，停止调仓")
                break
    
    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        symbol = report.get("symbol", "")
        side = report.get("side", "")
        
        if status == "filled":
            filled_qty = report.get("filled_quantity", 0)
            filled_price = report.get("filled_price", 0)
            self.log_info(f"[成交] ✓ {symbol} {side} {filled_qty}张 @ {filled_price:.2f}")
        elif status == "rejected":
            error_msg = report.get("error_msg", "")
            self.log_error(f"[拒绝] ✗ {symbol} {side} | {error_msg}")
        elif status == "accepted":
            self.log_info(f"[接受] {symbol} {side}")
    
    def on_stop(self):
        """策略停止"""
        print()
        print("=" * 60)
        print("[策略] 停止")
        print(f"[策略] 总执行次数: {self.execution_count}")
        if self.last_execution_time:
            print(f"[策略] 最后执行: {self.last_execution_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        # 打印当前持仓
        positions = self.get_active_positions()
        if positions:
            print(f"[策略] 当前持仓: {len(positions)} 个")
            for p in positions:
                print(f"  - {p.symbol}: {p.quantity}张 @ {p.avg_price:.2f}")
        
        print("=" * 60)


def main():
    strategy = GNNTestStrategy()
    
    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())
    
    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()

