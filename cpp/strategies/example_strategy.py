#!/usr/bin/env python3
"""
示例策略 - 展示模块化 C++ 策略基类的用法

演示三个模块的使用：
1. MarketDataModule - 行情数据（K线订阅、存储）
2. TradingModule - 交易操作（下单、撤单）
3. AccountModule - 账户管理（登录、余额、持仓）

@author Sequence Team
@date 2025-12
"""

import sys
import signal
import time

# 导入 C++ 策略基类及数据结构
try:
    from strategy_base import (
        StrategyBase,
        KlineBar,
        TradeData,
        PositionInfo,
        BalanceInfo,
        OrderInfo
    )
except ImportError:
    print("错误: 未找到 strategy_base 模块")
    print("请先编译 C++ 模块:")
    print("  cd cpp/build && cmake .. && make strategy_base")
    sys.exit(1)


class ExampleStrategy(StrategyBase):
    """
    示例策略
    
    演示如何使用模块化的策略基类：
    - 行情订阅与回调
    - 下单与订单回报
    - 账户余额与持仓查询
    """
    
    def __init__(self, strategy_id: str, symbol: str):
        # 初始化基类（存储最近 7200 根 K 线 = 2 小时 1s 数据）
        super().__init__(strategy_id, max_kline_bars=7200)
        self.symbol = symbol
        self.kline_received = 0
    
    # ==================== 生命周期回调 ====================
    
    def on_init(self):
        """策略初始化 - 在主循环开始前调用"""
        self.log_info("=" * 50)
        self.log_info("示例策略初始化")
        self.log_info("=" * 50)
        
        # 1. 账户模块：注册账户
        self.log_info("\n[账户模块] 注册账户...")
        self.register_account(
            api_key="your-api-key",
            secret_key="your-secret-key",
            passphrase="your-passphrase",
            is_testnet=True
        )
        time.sleep(1)
        
        # 2. 行情模块：订阅 K 线
        self.log_info("\n[行情模块] 订阅K线...")
        self.subscribe_kline(self.symbol, "1s")
        
        # 3. 行情模块：也可以订阅逐笔成交
        # self.subscribe_trades(self.symbol)
        
        self.log_info("\n初始化完成，等待行情数据...")
    
    def on_stop(self):
        """策略停止 - 在主循环结束后调用"""
        self.log_info("\n策略停止，打印统计信息:")
        
        # 行情模块：获取历史数据统计
        kline_count = self.get_kline_count(self.symbol, "1s")
        self.log_info(f"  总共接收 K 线: {kline_count} 根")
        
        # 账户模块：获取余额
        usdt = self.get_usdt_available()
        self.log_info(f"  USDT 可用: {usdt:.2f}")
        
        # 账户模块：获取持仓
        positions = self.get_active_positions()
        if positions:
            self.log_info("  当前持仓:")
            for pos in positions:
                self.log_info(f"    {pos.symbol}: {pos.quantity}张")
    
    # ==================== 行情回调 ====================
    
    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K线回调"""
        if symbol != self.symbol:
            return
        
        self.kline_received += 1
        
        # 每 10 根 K 线打印一次
        if self.kline_received % 10 == 0:
            # 获取最近 20 根收盘价
            closes = self.get_closes(symbol, interval)
            recent_closes = closes[-20:] if len(closes) >= 20 else closes
            avg_price = sum(recent_closes) / len(recent_closes) if recent_closes else 0
            
            self.log_info(f"[K线] {symbol} | 收盘:{bar.close:.2f} | "
                         f"20均价:{avg_price:.2f} | 总数:{len(closes)}")
    
    def on_trade(self, symbol: str, trade: TradeData):
        """逐笔成交回调"""
        self.log_info(f"[Trade] {symbol} | {trade.side} {trade.quantity} @ {trade.price}")
    
    # ==================== 订单回调 ====================
    
    def on_order_report(self, report: dict):
        """订单回报回调"""
        status = report.get("status", "")
        symbol = report.get("symbol", "")
        side = report.get("side", "")
        
        if status == "filled":
            filled_qty = report.get("filled_quantity", 0)
            filled_price = report.get("filled_price", 0)
            self.log_info(f"[成交] {symbol} {side} {filled_qty}张 @ {filled_price}")
        elif status == "rejected":
            error = report.get("error_msg", "未知错误")
            self.log_error(f"[拒绝] {symbol} {side} | 原因: {error}")
    
    # ==================== 账户回调 ====================
    
    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.log_info("[账户] ✓ 注册成功")
            
            # 查询账户信息
            usdt = self.get_usdt_available()
            equity = self.get_total_equity()
            self.log_info(f"  USDT可用: {usdt:.2f}")
            self.log_info(f"  总权益:   {equity:.2f}")
            
            # 查询所有余额
            balances = self.get_all_balances()
            if balances:
                self.log_info("  余额列表:")
                for bal in balances:
                    if bal.total > 0:
                        self.log_info(f"    {bal.currency}: {bal.available:.4f}")
        else:
            self.log_error(f"[账户] ✗ 注册失败: {error_msg}")
    
    def on_position_update(self, position: PositionInfo):
        """持仓更新回调"""
        if position.quantity != 0:
            self.log_info(f"[持仓] {position.symbol} {position.pos_side}: "
                         f"{position.quantity}张 @ {position.avg_price:.2f} "
                         f"盈亏: {position.unrealized_pnl:.2f}")
    
    def on_balance_update(self, balance: BalanceInfo):
        """余额更新回调"""
        if balance.currency == "USDT":
            self.log_info(f"[余额] USDT: 可用={balance.available:.2f}")
    
    # ==================== 示例：下单操作 ====================
    
    def demo_place_order(self):
        """演示下单操作（交易模块）"""
        self.log_info("\n[交易模块] 下单演示...")
        
        # 市价买入 1 张
        order_id = self.send_swap_market_order(
            symbol=self.symbol,
            side="buy",
            quantity=1,
            pos_side="net"  # 单向持仓模式
        )
        self.log_info(f"  买入订单ID: {order_id}")
        
        time.sleep(2)
        
        # 市价卖出 1 张
        order_id = self.send_swap_market_order(
            symbol=self.symbol,
            side="sell",
            quantity=1
        )
        self.log_info(f"  卖出订单ID: {order_id}")
    
    def demo_query_data(self):
        """演示数据查询"""
        self.log_info("\n[数据查询演示]")
        
        # 行情数据
        klines = self.get_klines(self.symbol, "1s")
        closes = self.get_closes(self.symbol, "1s")
        opens = self.get_opens(self.symbol, "1s")
        highs = self.get_highs(self.symbol, "1s")
        lows = self.get_lows(self.symbol, "1s")
        volumes = self.get_volumes(self.symbol, "1s")
        
        self.log_info(f"  K线数量: {len(klines)}")
        if closes:
            self.log_info(f"  最新收盘价: {closes[-1]:.2f}")
            self.log_info(f"  最高价(最近): {max(highs[-20:]) if len(highs) >= 20 else max(highs) if highs else 0:.2f}")
            self.log_info(f"  最低价(最近): {min(lows[-20:]) if len(lows) >= 20 else min(lows) if lows else 0:.2f}")
        
        # 账户数据
        usdt = self.get_usdt_available()
        positions = self.get_active_positions()
        orders = self.get_active_orders()
        
        self.log_info(f"  USDT可用: {usdt:.2f}")
        self.log_info(f"  活跃持仓: {len(positions)} 个")
        self.log_info(f"  活跃订单: {len(orders)} 个")


def main():
    print()
    print("╔" + "═" * 50 + "╗")
    print("║" + "  示例策略 (模块化 C++ 基类)".center(44) + "║")
    print("╚" + "═" * 50 + "╝")
    print()
    
    # 创建策略
    strategy = ExampleStrategy("example", "BTC-USDT-SWAP")
    
    # 信号处理
    def signal_handler(signum, frame):
        print("\n收到停止信号...")
        strategy.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()
