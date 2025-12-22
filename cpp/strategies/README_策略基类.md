# 策略基类使用指南（模块化设计）

## 架构概述

策略基类采用模块化设计，将功能拆分为三个独立模块：

```
┌─────────────────────────────────────────────────────────────┐
│                       StrategyBase                          │
│                     (Python 策略基类)                        │
├───────────────────┬─────────────────────┬───────────────────┤
│  MarketDataModule │    TradingModule    │   AccountModule   │
│    行情数据模块     │      交易模块        │     账户模块      │
├───────────────────┼─────────────────────┼───────────────────┤
│ • K线订阅/存储    │ • 市价/限价下单     │ • 账户注册/注销   │
│ • Trades订阅      │ • 撤单             │ • 余额查询        │
│ • 历史数据查询    │ • 订单状态管理     │ • 持仓查询        │
│ • 回调通知        │ • 订单回报处理     │ • 账户更新通知    │
└───────────────────┴─────────────────────┴───────────────────┘
```

## 模块详解

### 1. MarketDataModule - 行情数据模块

负责行情数据的订阅、接收、存储和查询。

#### 订阅接口

```python
# 订阅 K 线
self.subscribe_kline("BTC-USDT-SWAP", "1s")   # 1秒K线
self.subscribe_kline("ETH-USDT-SWAP", "1m")   # 1分钟K线

# 订阅逐笔成交
self.subscribe_trades("BTC-USDT-SWAP")

# 取消订阅
self.unsubscribe_kline("BTC-USDT-SWAP", "1s")
self.unsubscribe_trades("BTC-USDT-SWAP")
```

#### 数据查询接口

```python
# 获取所有 K 线
klines = self.get_klines("BTC-USDT-SWAP", "1s")

# 获取 OHLCV 数组（用于技术分析）
closes = self.get_closes("BTC-USDT-SWAP", "1s")
opens = self.get_opens("BTC-USDT-SWAP", "1s")
highs = self.get_highs("BTC-USDT-SWAP", "1s")
lows = self.get_lows("BTC-USDT-SWAP", "1s")
volumes = self.get_volumes("BTC-USDT-SWAP", "1s")

# 获取最近 N 根 K 线
recent = self.get_recent_klines("BTC-USDT-SWAP", "1s", 20)

# 获取最后一根 K 线
last_bar = self.get_last_kline("BTC-USDT-SWAP", "1s")

# 获取 K 线数量
count = self.get_kline_count("BTC-USDT-SWAP", "1s")
```

#### 回调函数

```python
def on_kline(self, symbol: str, interval: str, bar: KlineBar):
    """K线回调 - 每收到一根新K线时调用"""
    print(f"K线: {symbol} {interval} 收盘价={bar.close}")

def on_trade(self, symbol: str, trade: TradeData):
    """逐笔成交回调"""
    print(f"成交: {symbol} {trade.side} {trade.quantity} @ {trade.price}")
```

---

### 2. TradingModule - 交易模块

负责订单的发送、撤销和状态管理。

#### 下单接口

```python
# 市价单（合约）
order_id = self.send_swap_market_order(
    symbol="BTC-USDT-SWAP",
    side="buy",           # "buy" 或 "sell"
    quantity=1,           # 张数
    pos_side="net"        # "net"(单向持仓), "long", "short"(双向持仓)
)

# 限价单（合约）
order_id = self.send_swap_limit_order(
    symbol="BTC-USDT-SWAP",
    side="sell",
    quantity=2,
    price=100000.0,
    pos_side="net"
)
```

#### 撤单接口

```python
# 撤销单个订单
self.cancel_order("BTC-USDT-SWAP", client_order_id)

# 撤销所有订单
self.cancel_all_orders()                    # 所有
self.cancel_all_orders("BTC-USDT-SWAP")     # 指定交易对
```

#### 订单查询

```python
# 获取所有活跃订单
orders = self.get_active_orders()

# 获取未完成订单数量
count = self.pending_order_count()
```

#### 回调函数

```python
def on_order_report(self, report: dict):
    """订单回报回调"""
    status = report.get("status")
    
    if status == "accepted":
        print("订单已接受")
    elif status == "filled":
        print(f"订单成交: {report.get('filled_quantity')}张 @ {report.get('filled_price')}")
    elif status == "rejected":
        print(f"订单被拒: {report.get('error_msg')}")
    elif status == "cancelled":
        print("订单已撤销")
```

---

### 3. AccountModule - 账户模块

负责账户的注册、余额和持仓管理。

#### 账户注册

```python
# 注册账户
self.register_account(
    api_key="your-api-key",
    secret_key="your-secret-key",
    passphrase="your-passphrase",
    is_testnet=True  # True=模拟盘, False=实盘
)

# 注销账户
self.unregister_account()

# 检查注册状态
if self.is_account_registered():
    print("账户已注册")
```

#### 余额查询

```python
# 获取 USDT 可用余额
usdt = self.get_usdt_available()

# 获取总权益（USD）
equity = self.get_total_equity()

# 获取所有余额
balances = self.get_all_balances()
for bal in balances:
    print(f"{bal.currency}: 可用={bal.available}, 冻结={bal.frozen}")
```

#### 持仓查询

```python
# 获取所有持仓
positions = self.get_all_positions()

# 获取有效持仓（数量不为0）
active_positions = self.get_active_positions()

# 获取指定持仓
position = self.get_position("BTC-USDT-SWAP", pos_side="net")
if position:
    print(f"持仓: {position.quantity}张 @ {position.avg_price}")
```

#### 刷新数据

```python
# 请求刷新账户信息
self.refresh_account()

# 请求刷新持仓信息
self.refresh_positions()
```

#### 回调函数

```python
def on_register_report(self, success: bool, error_msg: str):
    """账户注册回报"""
    if success:
        print("注册成功")
    else:
        print(f"注册失败: {error_msg}")

def on_position_update(self, position: PositionInfo):
    """持仓更新回调"""
    print(f"持仓更新: {position.symbol} {position.quantity}张")

def on_balance_update(self, balance: BalanceInfo):
    """余额更新回调"""
    print(f"余额更新: {balance.currency} 可用={balance.available}")
```

---

## 完整示例

```python
from strategy_base import (
    StrategyBase, 
    KlineBar, 
    PositionInfo, 
    BalanceInfo
)

class MyStrategy(StrategyBase):
    def __init__(self):
        super().__init__("my_strategy", max_kline_bars=7200)
        self.symbol = "BTC-USDT-SWAP"
    
    def on_init(self):
        """初始化"""
        # 1. 注册账户
        self.register_account(
            api_key="xxx",
            secret_key="xxx",
            passphrase="xxx",
            is_testnet=True
        )
        
        # 2. 订阅行情
        self.subscribe_kline(self.symbol, "1s")
    
    def on_kline(self, symbol, interval, bar):
        """K线回调"""
        # 获取历史收盘价
        closes = self.get_closes(symbol, interval)
        if len(closes) < 20:
            return
        
        # 计算均价
        ma20 = sum(closes[-20:]) / 20
        
        # 简单策略逻辑
        if bar.close < ma20 * 0.99:
            self.send_swap_market_order(symbol, "buy", 1)
        elif bar.close > ma20 * 1.01:
            self.send_swap_market_order(symbol, "sell", 1)
    
    def on_order_report(self, report):
        """订单回报"""
        if report.get("status") == "filled":
            self.log_info(f"成交: {report}")
    
    def on_stop(self):
        """停止"""
        # 打印统计
        positions = self.get_active_positions()
        for pos in positions:
            self.log_info(f"持仓: {pos.symbol} {pos.quantity}张")

# 运行
strategy = MyStrategy()
strategy.run()
```

---

## 编译指南

```bash
# 进入 build 目录
cd cpp/build

# 编译
cmake ..
make strategy_base

# 生成的模块在 build 目录下
# strategy_base.cpython-xxx.so
```

---

## 数据结构

### KlineBar
```python
bar.timestamp  # 时间戳（毫秒）
bar.open       # 开盘价
bar.high       # 最高价
bar.low        # 最低价
bar.close      # 收盘价
bar.volume     # 成交量
```

### PositionInfo
```python
pos.symbol         # 交易对
pos.pos_side       # 持仓方向 ("net", "long", "short")
pos.quantity       # 持仓数量（张）
pos.avg_price      # 持仓均价
pos.mark_price     # 标记价格
pos.unrealized_pnl # 未实现盈亏
pos.margin         # 保证金
pos.leverage       # 杠杆倍数
```

### BalanceInfo
```python
bal.currency   # 币种
bal.available  # 可用余额
bal.frozen     # 冻结余额
bal.total      # 总余额
bal.usd_value  # USD估值
```

### OrderInfo
```python
order.client_order_id    # 客户端订单ID
order.exchange_order_id  # 交易所订单ID
order.symbol             # 交易对
order.side               # 买卖方向
order.order_type         # 订单类型
order.quantity           # 数量
order.filled_quantity    # 已成交数量
order.filled_price       # 成交均价
```
