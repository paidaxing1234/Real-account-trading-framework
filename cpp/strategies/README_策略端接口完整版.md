# Sequence 策略端接口文档 - 完整版

> 版本: 2.0.0  
> 更新日期: 2025-12-17  
> 本文档面向策略开发人员，提供与实盘服务器通信的完整接口说明

---

## 目录

1. [快速开始](#1-快速开始)
2. [架构说明](#2-架构说明)
3. [行情接口](#3-行情接口)
4. [交易接口](#4-交易接口)
5. [查询接口](#5-查询接口)
6. [完整示例](#6-完整示例)

---

## 1. 快速开始

### 1.1 环境准备

```bash
# 安装依赖
pip install pyzmq

# 确保实盘服务器已启动
./trading_server_full
```

### 1.2 最简示例

```python
from strategy_client import StrategyClient, BaseStrategy, TradeData, run_strategy

class MyStrategy(BaseStrategy):
    def on_trade(self, trade: TradeData):
        print(f"价格: {trade.price}")
        
        # 下单
        self.buy_market("BTC-USDT", 1)

if __name__ == "__main__":
    run_strategy(MyStrategy())
```

---

## 2. 架构说明

```
OKX 交易所
     │
     │ WebSocket (行情/订单推送) + REST API (交易/查询)
     ▼
┌───────────────────────────────────┐
│     实盘服务器 (C++)              │
│     trading_server_full           │
└───────────────────────────────────┘
     │
     │ IPC (ZeroMQ, 延迟 30-100μs)
     ▼
┌───────────────────────────────────┐
│     策略进程 (Python)              │
│     your_strategy.py              │
└───────────────────────────────────┘
```

**通信延迟**

| 路径 | 延迟 |
|------|------|
| 策略 ↔ 实盘 | 30-100 μs |
| 实盘 ↔ OKX | 50-200 ms |

---

## 3. 行情接口

### 3.1 Trades 数据（逐笔成交）

#### 订阅

```python
client = StrategyClient("my_strategy")
client.connect()

# 订阅单个交易对
client.subscribe_trades("BTC-USDT")

# 订阅多个交易对
client.subscribe_trades("ETH-USDT")
client.subscribe_trades("BTC-USDT-SWAP")  # 合约也可以
```

#### 接收

```python
# 方式1: 使用 BaseStrategy（推荐）
class MyStrategy(BaseStrategy):
    def on_trade(self, trade: TradeData):
        print(f"成交: {trade.symbol} @ {trade.price} x {trade.quantity}")

# 方式2: 手动接收
trade = client.recv_trade()
if trade:
    print(f"价格: {trade.price}, 数量: {trade.quantity}, 方向: {trade.side}")
```

**TradeData 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | str | 交易对 |
| trade_id | str | 成交ID |
| price | float | 成交价格 |
| quantity | float | 成交数量 |
| side | str | 方向 ("buy"/"sell") |
| timestamp | int | 时间戳（毫秒） |

### 3.2 K线数据

#### 订阅

```python
# 订阅 1分钟K线
client.subscribe_kline("BTC-USDT", "1m")

# 订阅 5分钟K线
client.subscribe_kline("BTC-USDT", "5m")

# 订阅 1小时K线
client.subscribe_kline("BTC-USDT", "1H")

# 订阅 1天K线
client.subscribe_kline("BTC-USDT", "1D")
```

**支持的K线周期**

| 周期 | 说明 |
|------|------|
| 1s | 1秒 |
| 1m | 1分钟 |
| 3m | 3分钟 |
| 5m | 5分钟 |
| 15m | 15分钟 |
| 30m | 30分钟 |
| 1H | 1小时 |
| 2H | 2小时 |
| 4H | 4小时 |
| 6H | 6小时 |
| 12H | 12小时 |
| 1D | 1天 |
| 1W | 1周 |
| 1M | 1月 |

#### 接收

```python
# 方式1: 使用 BaseStrategy
class MyStrategy(BaseStrategy):
    def on_kline(self, kline: KlineData):
        print(f"K线: {kline.symbol} [{kline.interval}]")
        print(f"  O:{kline.open} H:{kline.high} L:{kline.low} C:{kline.close}")
        print(f"  成交量: {kline.volume}")

# 方式2: 手动接收
kline = client.recv_kline()
if kline:
    print(f"收盘价: {kline.close}, 成交量: {kline.volume}")
```

**KlineData 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | str | 交易对 |
| interval | str | K线周期 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| timestamp | int | 时间戳（毫秒） |

### 3.3 深度数据（Orderbook）

#### 订阅

```python
# 订阅 5档深度（推荐，推送频率100ms）
client.subscribe_orderbook("BTC-USDT", "books5")

# 订阅 400档深度（推送频率100ms）
client.subscribe_orderbook("BTC-USDT", "books")

# 订阅 1档最优价（推送频率10ms，最快）
client.subscribe_orderbook("BTC-USDT", "bbo-tbt")

# 订阅 50档深度（推送频率10ms，VIP5+）
client.subscribe_orderbook("BTC-USDT", "books50-l2-tbt")

# 订阅 400档深度（推送频率10ms，VIP6+）
client.subscribe_orderbook("BTC-USDT", "books-l2-tbt")
```

**深度频道类型**

| 频道 | 档数 | 推送频率 | 说明 |
|------|------|----------|------|
| books5 | 5档 | 100ms | 推荐使用，数据量小 |
| books | 400档 | 100ms | 完整深度 |
| bbo-tbt | 1档 | 10ms | 最优买卖价，最快 |
| books50-l2-tbt | 50档 | 10ms | 需要VIP5+ |
| books-l2-tbt | 400档 | 10ms | 需要VIP6+ |
| books-elp | 400档 | 100ms | 仅ELP订单 |

#### 接收

```python
# 方式1: 使用 BaseStrategy
class MyStrategy(BaseStrategy):
    def on_orderbook(self, orderbook: dict):
        symbol = orderbook["symbol"]
        best_bid = orderbook.get("best_bid_price", 0)
        best_ask = orderbook.get("best_ask_price", 0)
        spread = orderbook.get("spread", 0)
        
        print(f"深度: {symbol} | 买一: {best_bid} | 卖一: {best_ask} | 价差: {spread}")
        
        # 获取前5档买盘
        bids = orderbook.get("bids", [])
        for i, bid in enumerate(bids[:5]):
            price, size = bid
            print(f"  买{i+1}: {price} x {size}")

# 方式2: 手动接收
orderbook = client.recv_orderbook()
if orderbook:
    bids = orderbook["bids"]  # [[price, size], ...]
    asks = orderbook["asks"]  # [[price, size], ...]
    best_bid_price = orderbook.get("best_bid_price")
    best_ask_price = orderbook.get("best_ask_price")
```

**深度数据格式**

```python
{
    "type": "orderbook",
    "symbol": "BTC-USDT",
    "bids": [[50000.0, 1.5], [49999.0, 2.0], ...],  # [价格, 数量]
    "asks": [[50001.0, 1.2], [50002.0, 3.0], ...],
    "best_bid_price": 50000.0,
    "best_bid_size": 1.5,
    "best_ask_price": 50001.0,
    "best_ask_size": 1.2,
    "mid_price": 50000.5,
    "spread": 1.0,
    "timestamp": 1702000000000,
    "timestamp_ns": 1702000000000000000
}
```

---

## 4. 交易接口

### 4.1 现货下单

#### 市价单

```python
# 市价买入（以计价货币指定数量）
order_id = client.buy_market("BTC-USDT", 10)  # 买入10 USDT的BTC

# 市价卖出（以基础货币指定数量）
order_id = client.sell_market("BTC-USDT", 0.001)  # 卖出0.001 BTC
```

#### 限价单

```python
# 限价买入
order_id = client.buy_limit("BTC-USDT", quantity=0.001, price=50000)

# 限价卖出
order_id = client.sell_limit("BTC-USDT", quantity=0.001, price=100000)
```

### 4.2 合约下单（永续合约）

```python
# 合约市价开多（1张）
order_id = client.swap_buy_market("BTC-USDT-SWAP", 1)

# 合约市价开空（1张）
order_id = client.swap_sell_market("BTC-USDT-SWAP", 1)

# 合约限价开多（1张 @ 50000）
order_id = client.swap_buy_limit("BTC-USDT-SWAP", 1, 50000)

# 合约限价开空（1张 @ 100000）
order_id = client.swap_sell_limit("BTC-USDT-SWAP", 1, 100000)

# 双向持仓模式（需要指定 pos_side）
order_id = client.swap_buy_market("BTC-USDT-SWAP", 1, pos_side="long")
```

**合约参数说明**

| 参数 | 说明 |
|------|------|
| symbol | 合约交易对，如 "BTC-USDT-SWAP" |
| quantity | 张数（不是币数量） |
| pos_side | 持仓方向："long"（多）/ "short"（空），双向持仓模式需要 |

### 4.3 批量下单（最多20个）

```python
from strategy_client import OrderRequest

# 构造批量订单
orders = [
    # 订单1: 合约开多
    OrderRequest(
        symbol="BTC-USDT-SWAP",
        side="buy",
        order_type="limit",
        quantity=1,  # 1张
        price=50000,
        td_mode="cross",
        pos_side="long"
    ),
    # 订单2: 合约开空
    OrderRequest(
        symbol="BTC-USDT-SWAP",
        side="sell",
        order_type="limit",
        quantity=1,
        price=100000,
        td_mode="cross",
        pos_side="short"
    ),
    # 订单3: 现货买入
    OrderRequest(
        symbol="BTC-USDT",
        side="buy",
        order_type="market",
        quantity=10,  # 10 USDT
        td_mode="cash",
        tgt_ccy="quote_ccy"
    )
]

# 批量下单
batch_id = client.batch_orders(orders)
print(f"批量订单ID: {batch_id}")
```

**批量订单回报**

```python
report = client.recv_report()
if report and report.type == "batch_report":
    print(f"批量状态: {report.status}")  # accepted/partial/rejected
    print(f"成功: {report.success_count}, 失败: {report.fail_count}")
    
    # 查看每个订单的结果
    for result in report.results:
        print(f"  订单: {result['client_order_id']} | {result['status']}")
```

### 4.4 撤单

#### 单个撤单

```python
# 使用交易所订单ID撤单
client.cancel_order("BTC-USDT", order_id="12345678")

# 使用客户端订单ID撤单
client.cancel_order("BTC-USDT", client_order_id="my_order_123")
```

#### 批量撤单

```python
# 批量撤单（最多20个）
order_ids = ["12345678", "12345679", "12345680"]
request_id = client.batch_cancel("BTC-USDT", order_ids)
```

### 4.5 修改订单

```python
# 修改订单价格和数量
request_id = client.amend_order(
    symbol="BTC-USDT",
    order_id="12345678",
    new_price=51000,      # 新价格
    new_quantity=0.002   # 新数量
)

# 只修改价格
request_id = client.amend_order(
    symbol="BTC-USDT",
    client_order_id="my_order_123",
    new_price=51000
)
```

### 4.6 接收订单回报

```python
# 方式1: 使用 BaseStrategy
class MyStrategy(BaseStrategy):
    def on_report(self, report: OrderReport):
        if report.type == "order_report":
            if report.is_filled():
                print(f"订单成交: {report.exchange_order_id}")
                print(f"  成交价: {report.filled_price}")
                print(f"  成交量: {report.filled_quantity}")
            elif report.is_rejected():
                print(f"订单被拒: {report.error_msg}")
        
        elif report.type == "batch_report":
            print(f"批量订单: 成功={report.success_count}, 失败={report.fail_count}")
        
        elif report.type == "cancel_report":
            print(f"撤单: {report.status}")

# 方式2: 手动接收
report = client.recv_report()
if report:
    print(f"状态: {report.status}")
    if report.is_filled():
        print(f"成交价: {report.filled_price}")
```

**订单回报类型**

| type | 说明 |
|------|------|
| order_report | 单个订单回报 |
| batch_report | 批量订单回报 |
| cancel_report | 撤单回报 |
| amend_report | 修改订单回报 |
| order_update | 订单状态更新（WebSocket推送） |

---

## 5. 查询接口

### 5.1 账户余额

```python
# 查询所有币种余额
account = client.query_account()
if account and account.get("code") == 0:
    data = account["data"]
    # OKX原始格式，包含 totalEq, details 等

# 查询指定币种余额
account = client.query_account("USDT")
```

**账户数据格式（OKX原始格式）**

```json
{
    "code": "0",
    "data": [{
        "totalEq": "10000.5",
        "details": [{
            "ccy": "USDT",
            "eq": "10000.5",
            "cashBal": "10000.5",
            "availBal": "9000.0",
            "frozenBal": "1000.0"
        }]
    }]
}
```

### 5.2 持仓信息

```python
# 查询所有合约持仓
positions = client.query_positions(inst_type="SWAP")

# 查询指定合约持仓
positions = client.query_positions(inst_type="SWAP", symbol="BTC-USDT-SWAP")

# 查询杠杆持仓
positions = client.query_positions(inst_type="MARGIN")
```

**持仓数据格式（OKX原始格式）**

```json
{
    "code": "0",
    "data": [{
        "instId": "BTC-USDT-SWAP",
        "pos": "1",
        "posSide": "long",
        "avgPx": "50000",
        "upl": "100.5",
        "margin": "1000.0"
    }]
}
```

### 5.3 未成交订单

```python
# 查询所有未成交订单
orders = client.query_pending_orders(inst_type="SPOT")

# 查询指定交易对的未成交订单
orders = client.query_pending_orders(inst_type="SWAP", symbol="BTC-USDT-SWAP")
```

### 5.4 单个订单查询

```python
# 使用交易所订单ID查询
order = client.query_order("BTC-USDT", order_id="12345678")

# 使用客户端订单ID查询
order = client.query_order("BTC-USDT", client_order_id="my_order_123")
```

---

## 6. 完整示例

### 6.1 完整功能演示策略

```python
#!/usr/bin/env python3
"""
完整功能演示策略

展示所有接口的使用：
- 订阅行情（trades, K线, 深度）
- 下单（现货、合约、批量）
- 撤单、修改订单
- 查询账户、持仓
"""

from strategy_client import (
    BaseStrategy, TradeData, KlineData, OrderReport,
    OrderRequest, run_strategy
)
import time
from datetime import datetime

class FullFeatureStrategy(BaseStrategy):
    """完整功能演示策略"""
    
    def __init__(self):
        super().__init__(strategy_id="full_demo")
        self.demo_step = 0
        self.last_demo_time = 0
        self.pending_orders = {}  # 跟踪未完成订单
    
    def on_start(self):
        self.log("完整功能演示策略启动")
        
        # 订阅行情
        self.client.subscribe_trades("BTC-USDT")
        self.client.subscribe_kline("BTC-USDT", "1m")
        self.client.subscribe_orderbook("BTC-USDT", "books5")
        
        self.log("已订阅: trades, K线(1m), 深度(books5)")
    
    def on_trade(self, trade: TradeData):
        """处理成交数据"""
        # 每100条打印一次
        if self.client.trade_count % 100 == 0:
            self.log(f"[Trades] {trade.symbol} @ {trade.price} | 方向: {trade.side}")
    
    def on_kline(self, kline: KlineData):
        """处理K线数据"""
        if self.client.kline_count % 10 == 0:
            self.log(f"[K线] {kline.symbol} [{kline.interval}] "
                    f"C:{kline.close} V:{kline.volume}")
    
    def on_orderbook(self, orderbook: dict):
        """处理深度数据"""
        if self.client.orderbook_count % 50 == 0:
            best_bid = orderbook.get("best_bid_price", 0)
            best_ask = orderbook.get("best_ask_price", 0)
            spread = orderbook.get("spread", 0)
            self.log(f"[深度] 买一: {best_bid} | 卖一: {best_ask} | 价差: {spread}")
    
    def on_report(self, report: OrderReport):
        """处理订单回报"""
        if report.type == "order_report":
            status_emoji = "✓" if report.is_success() else "✗"
            self.log(f"[回报] {status_emoji} {report.status} | ID: {report.exchange_order_id}")
            
            if report.is_filled():
                self.log(f"       成交: {report.filled_quantity} @ {report.filled_price}")
            
            # 从 pending_orders 中移除
            if report.client_order_id in self.pending_orders:
                del self.pending_orders[report.client_order_id]
        
        elif report.type == "batch_report":
            self.log(f"[批量回报] 成功: {report.success_count}, 失败: {report.fail_count}")
    
    def run_demo(self):
        """定时执行演示步骤"""
        current_time = time.time()
        
        if current_time - self.last_demo_time >= 30:
            self.last_demo_time = current_time
            self._execute_demo_step()
    
    def _execute_demo_step(self):
        """执行演示步骤"""
        self.demo_step += 1
        
        print()
        print("=" * 60)
        print(f"  演示步骤 {self.demo_step}")
        print("=" * 60)
        
        if self.demo_step == 1:
            # 演示1: 查询账户
            self.log("[演示] 查询账户余额")
            account = self.query_account("USDT")
            if account and account.get("code") == 0:
                self.log(f"       查询成功")
            else:
                self.log(f"       查询失败")
        
        elif self.demo_step == 2:
            # 演示2: 查询持仓
            self.log("[演示] 查询合约持仓")
            positions = self.query_positions(inst_type="SWAP")
            if positions and positions.get("code") == 0:
                self.log(f"       查询成功")
            else:
                self.log(f"       查询失败")
        
        elif self.demo_step == 3:
            # 演示3: 现货市价买入
            self.log("[演示] 现货市价买入 1 USDT 的 BTC")
            order_id = self.buy_market("BTC-USDT", 1)
            if order_id:
                self.pending_orders[order_id] = {"symbol": "BTC-USDT", "type": "buy"}
                self.log(f"       订单ID: {order_id}")
        
        elif self.demo_step == 4:
            # 演示4: 合约限价开多
            self.log("[演示] 合约限价开多 1张 BTC-USDT-SWAP @ 50000")
            order_id = self.swap_buy("BTC-USDT-SWAP", 1, 50000)
            if order_id:
                self.pending_orders[order_id] = {"symbol": "BTC-USDT-SWAP", "type": "buy"}
                self.log(f"       订单ID: {order_id}")
        
        elif self.demo_step == 5:
            # 演示5: 批量下单（合约）
            self.log("[演示] 批量下单（2个合约订单）")
            orders = [
                OrderRequest(
                    symbol="BTC-USDT-SWAP",
                    side="buy",
                    order_type="limit",
                    quantity=1,
                    price=50000,
                    td_mode="cross"
                ),
                OrderRequest(
                    symbol="BTC-USDT-SWAP",
                    side="sell",
                    order_type="limit",
                    quantity=1,
                    price=100000,
                    td_mode="cross"
                )
            ]
            batch_id = self.client.batch_orders(orders)
            self.log(f"       批量ID: {batch_id}")
        
        elif self.demo_step == 6:
            # 演示6: 查询未成交订单
            self.log("[演示] 查询未成交订单")
            orders = self.client.query_pending_orders(inst_type="SWAP")
            if orders and orders.get("code") == 0:
                self.log(f"       查询成功")
            else:
                self.log(f"       查询失败")
        
        elif self.demo_step == 7:
            # 演示7: 撤单（如果有未完成订单）
            if self.pending_orders:
                order_id = list(self.pending_orders.keys())[0]
                order_info = self.pending_orders[order_id]
                self.log(f"[演示] 撤销订单: {order_id}")
                req_id = self.cancel_order(order_info["symbol"], client_order_id=order_id)
                self.log(f"       请求ID: {req_id}")
            else:
                self.log("[演示] 没有待撤销的订单")
        
        else:
            # 重置演示
            self.demo_step = 0
            self.log("[演示] 演示完成，将重新开始")
        
        print()

# 运行策略（需要手动调用 run_demo）
if __name__ == "__main__":
    strategy = FullFeatureStrategy()
    
    if not strategy.client.connect():
        print("[错误] 无法连接到交易服务器")
        exit(1)
    
    strategy.on_init()
    strategy.on_start()
    
    print("\n策略已启动，每30秒执行一个演示步骤")
    print("按 Ctrl+C 停止\n")
    
    try:
        while strategy.client.running:
            # 接收行情
            data = strategy.client.recv_market()
            if data:
                if data.get("type") == "trade":
                    strategy.on_trade(TradeData.from_dict(data))
                elif data.get("type") == "kline":
                    strategy.on_kline(KlineData.from_dict(data))
                elif data.get("type") == "orderbook":
                    strategy.on_orderbook(data)
            
            # 接收回报
            report = strategy.client.recv_report()
            if report:
                strategy.on_report(report)
            
            # 执行演示步骤
            strategy.run_demo()
            
            time.sleep(0.001)
    
    except KeyboardInterrupt:
        print("\n收到停止信号...")
    
    finally:
        strategy.on_stop()
        strategy.client.disconnect()
        print("\n策略已停止")
```

### 6.2 合约交易策略示例

```python
#!/usr/bin/env python3
"""
合约交易策略示例

功能：
- 订阅合约 trades 和深度数据
- 根据价格变化进行合约交易
- 批量下单
- 查询持仓
"""

from strategy_client import BaseStrategy, TradeData, OrderRequest, run_strategy
from collections import deque

class SwapTradingStrategy(BaseStrategy):
    """合约交易策略"""
    
    def __init__(self):
        super().__init__(strategy_id="swap_trader")
        
        # 参数
        self.symbol = "BTC-USDT-SWAP"
        self.trade_amount = 1  # 每次交易1张
        self.price_threshold = 100  # 价格变化阈值（USDT）
        
        # 数据
        self.prices = deque(maxlen=100)  # 最近100个价格
        self.last_price = 0.0
        self.position = 0.0  # 当前持仓（张数）
        
    def on_start(self):
        self.log("合约交易策略启动")
        
        # 订阅合约行情
        self.client.subscribe_trades(self.symbol)
        self.client.subscribe_orderbook(self.symbol, "books5")
        
        self.log(f"已订阅: {self.symbol} trades + 深度")
    
    def on_trade(self, trade: TradeData):
        """处理成交数据"""
        if trade.symbol != self.symbol:
            return
        
        self.prices.append(trade.price)
        self.last_price = trade.price
        
        # 每50条打印一次
        if self.client.trade_count % 50 == 0:
            self.log(f"价格: {trade.price} | 持仓: {self.position}张")
        
        # 策略逻辑：价格变化超过阈值时交易
        if len(self.prices) >= 2:
            price_change = self.prices[-1] - self.prices[0]
            
            if abs(price_change) >= self.price_threshold:
                if price_change > 0:
                    # 价格上涨，开多
                    if self.position <= 0:
                        order_id = self.swap_buy(self.symbol, self.trade_amount)
                        self.log(f"[开多] 价格变化: +{price_change:.2f} | 订单: {order_id}")
                else:
                    # 价格下跌，开空
                    if self.position >= 0:
                        order_id = self.swap_sell(self.symbol, self.trade_amount)
                        self.log(f"[开空] 价格变化: {price_change:.2f} | 订单: {order_id}")
    
    def on_orderbook(self, orderbook: dict):
        """处理深度数据"""
        best_bid = orderbook.get("best_bid_price", 0)
        best_ask = orderbook.get("best_ask_price", 0)
        
        if best_bid > 0 and best_ask > 0:
            mid_price = (best_bid + best_ask) / 2
            spread = best_ask - best_bid
            
            # 每100条打印一次
            if self.client.orderbook_count % 100 == 0:
                self.log(f"[深度] 中间价: {mid_price:.2f} | 价差: {spread:.2f}")
    
    def on_report(self, report: OrderReport):
        """处理订单回报"""
        if report.is_filled():
            # 更新持仓（简化处理）
            if "buy" in report.symbol or report.side == "buy":
                self.position += report.filled_quantity
            else:
                self.position -= report.filled_quantity
            
            self.log(f"[成交] {report.symbol} | 数量: {report.filled_quantity} | 持仓: {self.position}张")
        
        elif report.type == "batch_report":
            self.log(f"[批量] 成功: {report.success_count}, 失败: {report.fail_count}")

if __name__ == "__main__":
    run_strategy(SwapTradingStrategy())
```

### 6.3 批量下单策略示例

```python
#!/usr/bin/env python3
"""
批量下单策略示例

展示如何：
- 批量下单（合约）
- 批量撤单
- 修改订单
"""

from strategy_client import BaseStrategy, TradeData, OrderRequest, run_strategy
import time

class BatchOrderStrategy(BaseStrategy):
    """批量下单策略"""
    
    def __init__(self):
        super().__init__(strategy_id="batch_order")
        self.symbol = "BTC-USDT-SWAP"
        self.last_batch_time = 0
        self.pending_order_ids = []
    
    def on_start(self):
        self.log("批量下单策略启动")
        self.client.subscribe_trades(self.symbol)
    
    def on_trade(self, trade: TradeData):
        """定时批量下单"""
        current_time = time.time()
        
        # 每60秒执行一次批量下单
        if current_time - self.last_batch_time >= 60:
            self.last_batch_time = current_time
            self._place_batch_orders()
    
    def _place_batch_orders(self):
        """批量下单"""
        self.log("[批量下单] 准备提交3个订单")
        
        # 获取当前价格（简化：使用固定价格）
        base_price = 50000
        
        orders = [
            # 订单1: 开多
            OrderRequest(
                symbol=self.symbol,
                side="buy",
                order_type="limit",
                quantity=1,
                price=base_price - 100,
                td_mode="cross"
            ),
            # 订单2: 开多（更高价格）
            OrderRequest(
                symbol=self.symbol,
                side="buy",
                order_type="limit",
                quantity=1,
                price=base_price - 50,
                td_mode="cross"
            ),
            # 订单3: 开空
            OrderRequest(
                symbol=self.symbol,
                side="sell",
                order_type="limit",
                quantity=1,
                price=base_price + 100,
                td_mode="cross"
            )
        ]
        
        batch_id = self.client.batch_orders(orders)
        self.log(f"       批量ID: {batch_id}")
        
        # 保存订单ID用于后续撤单
        for order in orders:
            if order.client_order_id:
                self.pending_order_ids.append(order.client_order_id)
    
    def on_report(self, report: OrderReport):
        """处理订单回报"""
        if report.type == "batch_report":
            self.log(f"[批量回报] 状态: {report.status}")
            self.log(f"       成功: {report.success_count}, 失败: {report.fail_count}")
            
            # 保存成功的订单ID
            for result in report.results:
                if result["status"] == "accepted":
                    order_id = result.get("exchange_order_id") or result.get("client_order_id")
                    if order_id:
                        self.pending_order_ids.append(order_id)
            
            # 如果有未完成订单，30秒后批量撤单
            if self.pending_order_ids:
                time.sleep(30)
                self._batch_cancel()
        
        elif report.type == "order_report" and report.is_filled():
            self.log(f"[成交] {report.exchange_order_id} | 价格: {report.filled_price}")
    
    def _batch_cancel(self):
        """批量撤单"""
        if not self.pending_order_ids:
            return
        
        self.log(f"[批量撤单] 撤销 {len(self.pending_order_ids)} 个订单")
        
        # 批量撤单（最多20个）
        order_ids = self.pending_order_ids[:20]
        request_id = self.client.batch_cancel(self.symbol, order_ids)
        self.log(f"       请求ID: {request_id}")
        
        # 清空列表
        self.pending_order_ids.clear()

if __name__ == "__main__":
    run_strategy(BatchOrderStrategy())
```

---

## 7. 接口汇总

### 7.1 行情接口

| 接口 | 方法 | 说明 |
|------|------|------|
| 订阅 trades | `subscribe_trades(symbol)` | 订阅逐笔成交 |
| 订阅 K线 | `subscribe_kline(symbol, interval)` | 订阅K线数据 |
| 订阅深度 | `subscribe_orderbook(symbol, channel)` | 订阅深度数据 |
| 接收 trades | `recv_trade()` | 接收成交数据 |
| 接收 K线 | `recv_kline()` | 接收K线数据 |
| 接收深度 | `recv_orderbook()` | 接收深度数据 |

### 7.2 交易接口

| 接口 | 方法 | 说明 |
|------|------|------|
| 现货市价买入 | `buy_market(symbol, quantity)` | 市价买入 |
| 现货市价卖出 | `sell_market(symbol, quantity)` | 市价卖出 |
| 现货限价买入 | `buy_limit(symbol, quantity, price)` | 限价买入 |
| 现货限价卖出 | `sell_limit(symbol, quantity, price)` | 限价卖出 |
| 合约开多 | `swap_buy(symbol, quantity, price=0)` | 合约买入 |
| 合约开空 | `swap_sell(symbol, quantity, price=0)` | 合约卖出 |
| 批量下单 | `batch_orders(orders)` | 批量下单（最多20个） |
| 撤单 | `cancel_order(symbol, order_id, client_order_id)` | 撤销单个订单 |
| 批量撤单 | `batch_cancel(symbol, order_ids)` | 批量撤单 |
| 修改订单 | `amend_order(symbol, order_id, new_price, new_quantity)` | 修改订单 |

### 7.3 查询接口

| 接口 | 方法 | 说明 |
|------|------|------|
| 查询账户 | `query_account(currency)` | 查询账户余额 |
| 查询持仓 | `query_positions(inst_type, symbol)` | 查询持仓信息 |
| 查询未成交订单 | `query_pending_orders(inst_type, symbol)` | 查询未成交订单 |
| 查询单个订单 | `query_order(symbol, order_id, client_order_id)` | 查询单个订单 |

---

## 8. 常见问题

### Q: 如何订阅多个交易对？

```python
# 依次订阅即可
client.subscribe_trades("BTC-USDT")
client.subscribe_trades("ETH-USDT")
client.subscribe_trades("BTC-USDT-SWAP")
```

### Q: 合约下单时 quantity 是什么单位？

**A:** 合约下单的 `quantity` 是**张数**，不是币数量。例如：
- `quantity=1` 表示 1 张合约
- 1 张合约约等于一定数量的 BTC（取决于合约面值）

### Q: 批量下单失败怎么办？

**A:** 查看批量回报中的 `results` 数组，每个订单都有独立的 `status` 和 `error_msg`：

```python
report = client.recv_report()
if report.type == "batch_report":
    for result in report.results:
        if result["status"] == "rejected":
            print(f"订单失败: {result['error_msg']}")
```

### Q: 深度数据是增量还是全量？

**A:** 
- `books5` 和 `bbo-tbt` 是**定量推送**（每次推送完整数据）
- `books`、`books-l2-tbt`、`books50-l2-tbt` 是**增量推送**（首次快照，后续增量）

策略端需要自己维护全量深度（合并增量数据）。

### Q: 如何判断订单是否成交？

**A:** 通过订单回报的 `status` 字段：

```python
if report.status == "filled":
    # 完全成交
elif report.status == "partial":
    # 部分成交
elif report.status == "accepted":
    # 已接受，等待成交
```

---

## 9. 文件说明

| 文件 | 说明 |
|------|------|
| `strategy_client.py` | 策略客户端库（完整版） |
| `README_策略端接口完整版.md` | 本文档 |

---

## 10. 联系方式

如有问题，请联系实盘框架开发组。

