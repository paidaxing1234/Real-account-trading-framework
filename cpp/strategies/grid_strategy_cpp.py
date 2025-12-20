#!/usr/bin/env python3
"""
网格策略 - 基于 C++ 策略基类

使用 C++ 实现的 StrategyBase，通过继承实现网格交易策略
相比纯 Python 版本（grid_strategy_standalone.py），具有更低的延迟

使用方法:
    # 先编译 C++ 模块
    cd strategies && mkdir build && cd build && cmake .. && make
    
    # 运行策略
    python3 grid_strategy_cpp.py --symbol BTC-USDT-SWAP --grid-num 20

@author Sequence Team
@date 2025-12
"""

import sys
import signal
import argparse
import time
from typing import List, Dict

# 导入 C++ 策略基类
try:
    from strategy_base import StrategyBase, KlineBar
except ImportError:
    print("错误: 未找到 strategy_base 模块")
    print("请先编译 C++ 模块:")
    print("  cd strategies && mkdir build && cd build && cmake .. && make")
    sys.exit(1)


class GridStrategy(StrategyBase):
    """
    网格交易策略
    
    继承自 C++ StrategyBase，使用基类提供的：
    - ZMQ 通信
    - K线存储
    - 下单接口
    """
    
    def __init__(self,
                 strategy_id: str,
                 symbol: str,
                 grid_num: int,
                 grid_spread: float,
                 order_amount: float,
                 api_key: str = "",
                 secret_key: str = "",
                 passphrase: str = "",
                 is_testnet: bool = True):
        """
        初始化网格策略
        
        Args:
            strategy_id: 策略ID
            symbol: 交易对（如 BTC-USDT-SWAP）
            grid_num: 单边网格数量
            grid_spread: 网格间距比例（如 0.001 = 0.1%）
            order_amount: 单次下单金额（USDT）
            api_key: OKX API Key
            secret_key: OKX Secret Key
            passphrase: OKX Passphrase
            is_testnet: 是否模拟盘
        """
        # 初始化基类（7200 根 K 线 = 2 小时 1s 数据）
        super().__init__(strategy_id, max_kline_bars=7200)
        
        self.symbol = symbol
        self.grid_num = grid_num
        self.grid_spread = grid_spread
        self.order_amount = order_amount
        
        # 账户信息
        self._api_key = api_key
        self._secret_key = secret_key
        self._passphrase = passphrase
        self._is_testnet = is_testnet
        
        # 价格追踪
        self.current_price = 0.0
        self.base_price = 0.0
        
        # 网格
        self.buy_levels: List[float] = []
        self.sell_levels: List[float] = []
        self.triggered: Dict[float, bool] = {}
        
        # 统计
        self.buy_count = 0
        self.sell_count = 0
        
        # 判断是否为合约
        self.is_swap = "SWAP" in symbol.upper()
        
        self.log_info(f"策略参数: {symbol} | 网格:{grid_num}x2 | 间距:{grid_spread*100:.3f}% | 金额:{order_amount}U")
    
    # ==================== 生命周期回调 ====================
    
    def on_init(self):
        """策略初始化"""
        self.log_info("策略初始化...")
        
        # 注册账户
        if self._api_key and self._secret_key and self._passphrase:
            self.register_account(
                self._api_key, 
                self._secret_key, 
                self._passphrase, 
                self._is_testnet
            )
            time.sleep(0.5)  # 等待注册
        else:
            self.log_info("未提供账户信息，使用服务器默认账户")
        
        # 订阅 1s K 线
        self.subscribe_kline(self.symbol, "1s")
        self.log_info(f"已订阅 {self.symbol} 1s K线")
        
        time.sleep(1)  # 等待订阅生效
        self.log_info("初始化完成，等待行情数据...")
    
    def on_stop(self):
        """策略停止"""
        self.log_info("策略停止...")
        self.unsubscribe_kline(self.symbol, "1s")
        self.print_grid_summary()
    
    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.log_info("✓ 账户注册成功")
        else:
            self.log_error(f"✗ 账户注册失败: {error_msg}")
    
    # ==================== K线回调 ====================
    
    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K线回调"""
        if symbol != self.symbol:
            return
        
        # 更新当前价格
        self.current_price = bar.close
        
        # 初始化网格
        if self.base_price == 0:
            self.base_price = bar.close
            self.init_grids()
            return
        
        # 检查网格触发
        self.check_grid_triggers()
    
    # ==================== 订单回报 ====================
    
    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        side = report.get("side", "")
        
        if status == "filled":
            if side == "buy":
                self.buy_count += 1
            elif side == "sell":
                self.sell_count += 1
            
            self.log_info(f"[成交] {side.upper()} | 买入:{self.buy_count} 卖出:{self.sell_count}")
    
    # ==================== 网格逻辑 ====================
    
    def init_grids(self):
        """初始化网格"""
        self.buy_levels = []
        self.sell_levels = []
        self.triggered = {}
        
        # 买入网格（低价）
        for i in range(1, self.grid_num + 1):
            level = self.base_price * (1 - self.grid_spread * i)
            self.buy_levels.append(level)
            self.triggered[level] = False
        
        # 卖出网格（高价）
        for i in range(1, self.grid_num + 1):
            level = self.base_price * (1 + self.grid_spread * i)
            self.sell_levels.append(level)
            self.triggered[level] = False
        
        self.buy_levels.sort(reverse=True)
        self.sell_levels.sort()
        
        self.log_info(f"网格初始化: 基准={self.base_price:.2f} | "
                     f"买入:{self.buy_levels[-1]:.2f}~{self.buy_levels[0]:.2f} | "
                     f"卖出:{self.sell_levels[0]:.2f}~{self.sell_levels[-1]:.2f}")
    
    def check_grid_triggers(self):
        """检查网格触发"""
        # 检查买入网格
        for level in self.buy_levels:
            if self.triggered[level]:
                continue
            
            if self.current_price <= level:
                self.trigger_buy(level)
                break
        
        # 检查卖出网格
        for level in self.sell_levels:
            if self.triggered[level]:
                continue
            
            if self.current_price >= level:
                self.trigger_sell(level)
                break
        
        # 重置触发状态
        for level in self.buy_levels:
            if self.triggered[level] and self.current_price > level * 1.002:
                self.triggered[level] = False
        
        for level in self.sell_levels:
            if self.triggered[level] and self.current_price < level * 0.998:
                self.triggered[level] = False
    
    def trigger_buy(self, level: float):
        """触发买入"""
        self.triggered[level] = True
        
        # 合约：计算张数（1张=0.01BTC）
        contracts = int(self.order_amount / (self.current_price * 0.01))
        if contracts < 1:
            contracts = 1
        
        self.log_info(f"[触发] 买入开多 {contracts}张 @ {self.current_price:.2f}")
        self.send_swap_market_order(self.symbol, "buy", contracts, "long")
    
    def trigger_sell(self, level: float):
        """触发卖出"""
        self.triggered[level] = True
        
        # 合约：计算张数
        contracts = int(self.order_amount / (self.current_price * 0.01))
        if contracts < 1:
            contracts = 1
        
        self.log_info(f"[触发] 卖出开空 {contracts}张 @ {self.current_price:.2f}")
        self.send_swap_market_order(self.symbol, "sell", contracts, "short")
    
    def print_grid_summary(self):
        """打印网格统计"""
        print("\n" + "=" * 50)
        print("          网格策略统计")
        print("=" * 50)
        print(f"  交易对:     {self.symbol}")
        print(f"  基准价格:   {self.base_price:.2f}")
        print(f"  当前价格:   {self.current_price:.2f}")
        print(f"  买入成交:   {self.buy_count} 笔")
        print(f"  卖出成交:   {self.sell_count} 笔")
        print(f"  K线数量:    {self.get_kline_count(self.symbol, '1s')} 根")
        print("=" * 50)


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='网格策略（C++基类版）')
    parser.add_argument('--strategy-id', type=str, default='grid_cpp',
                       help='策略ID')
    parser.add_argument('--symbol', type=str, default='BTC-USDT-SWAP',
                       help='交易对')
    parser.add_argument('--grid-num', type=int, default=20,
                       help='单边网格数量')
    parser.add_argument('--grid-spread', type=float, default=0.001,
                       help='网格间距 (0.001 = 0.1%%)')
    parser.add_argument('--order-amount', type=float, default=100.0,
                       help='单次下单金额 USDT')
    
    # 账户参数
    parser.add_argument('--api-key', type=str, 
                       default='25fc280c-9f3a-4d65-a23d-59d42eeb7d7e',
                       help='OKX API Key')
    parser.add_argument('--secret-key', type=str, 
                       default='888CC77C745F1B49E75A992F38929992',
                       help='OKX Secret Key')
    parser.add_argument('--passphrase', type=str, 
                       default='Sequence2025.',
                       help='OKX Passphrase')
    parser.add_argument('--testnet', action='store_true', default=True,
                       help='使用模拟盘')
    parser.add_argument('--live', action='store_true',
                       help='使用实盘')
    
    args = parser.parse_args()
    
    # 确定是否使用模拟盘
    is_testnet = not args.live
    
    print()
    print("╔" + "═" * 50 + "╗")
    print("║" + "  网格策略 (C++ 基类版)".center(44) + "║")
    print("╚" + "═" * 50 + "╝")
    print()
    
    # 创建策略
    strategy = GridStrategy(
        strategy_id=args.strategy_id,
        symbol=args.symbol,
        grid_num=args.grid_num,
        grid_spread=args.grid_spread,
        order_amount=args.order_amount,
        api_key=args.api_key,
        secret_key=args.secret_key,
        passphrase=args.passphrase,
        is_testnet=is_testnet
    )
    
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

