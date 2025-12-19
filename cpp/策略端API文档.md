# Sequence 策略端 API 手册

## Sequence 策略端简介

Sequence 策略端是一个基于 Python 的实盘交易策略开发工具包。它为量化交易者提供了简洁高效的 API 接口，通过 ZeroMQ 与 C++ 高性能交易服务器通信，实现微秒级的行情数据接收和订单执行。

### 为什么选择 Sequence？

* **超低延迟**: 行情延迟 < 100μs，订单延迟 < 100μs（基于 ZeroMQ IPC）
* **简单易用**: 仅需几行代码即可接收行情、下单交易
* **高性能**: C++ 核心 + Python 策略，兼顾性能与开发效率
* **多策略支持**: 支持多个策略进程同时运行，自动 CPU 绑核优化
* **生产级稳定**: 完善的错误处理、日志记录、资源管理

### Sequence 为您提供的功能

* **实时行情数据**: 接收 OKX 交易所推送的实时 trades、tickers、K线等行情数据
* **订单管理**: 支持市价单、限价单的下单、撤单、改单操作
* **账户查询**: 实时查询账户余额、持仓信息
* **风控支持**: 持仓限制、订单频率限制等
* **回测支持**: 相同的策略代码可用于回测和实盘

## 文档目录

* #### Sequence 使用说明
  * **架构概述** 了解系统的整体架构和数据流向
  * **通信机制** 了解 ZeroMQ IPC 的工作原理
  * **快速上手** 5分钟写出第一个策略
  
* #### API 参考
  * **StrategyClient 类** 策略客户端类，负责与交易服务器通信
  * **BaseStrategy 类** 策略基类，提供事件驱动的策略开发框架
  * **数据结构** 行情数据、订单数据的详细说明
  * **辅助函数** 工具函数和常量定义

* #### 完整示例
  * **示例1: Hello World** 最简单的策略，打印行情
  * **示例2: 定时下单** 每隔N秒自动下单
  * **示例3: 价格突破** 监控价格突破并交易
  * **示例4: 网格策略** 完整的网格交易策略
  * **示例5: 多策略部署** 如何部署多个策略进程

* #### 进阶主题
  * **性能优化** CPU 绑核、实时调度、NUMA 优化
  * **错误处理** 如何处理连接断开、订单失败等异常
  * **日志和监控** 如何记录日志、监控策略运行状态
  * **风险控制** 如何实现仓位管理、止损止盈

* #### 更新履历

---

## 使用说明

### 架构概述

Sequence 采用分层架构，将高性能的交易执行（C++）与灵活的策略开发（Python）分离：

```
┌─────────────────────────────────────────────────────────────────┐
│                         OKX 交易所                               │
│     REST API (下单/撤单/查询)  +  WebSocket (行情/订单推送)        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ Internet (50-200ms)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  C++ Trading Server (核心层)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ REST API     │  │  WebSocket   │  │    ZeroMQ Server     │  │
│  │ 订单执行      │  │  行情接收     │  │    消息分发          │  │
│  │              │  │              │  │                      │  │
│  │ - 下单       │  │ - Ticker     │  │ - PUB 行情 (100μs)   │  │
│  │ - 撤单       │  │ - Trades     │  │ - PULL 订单          │  │
│  │ - 改单       │  │ - K线        │  │ - PUB 回报           │  │
│  │ - 查询       │  │ - 订单薄     │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└───────────────────────────────────┬─────────────────────────────┘
                                    │
                                    │ IPC (Unix Socket, <100μs)
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│              Python Strategy Layer (策略层)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Strategy 1   │  │ Strategy 2   │  │ Strategy N           │  │
│  │              │  │              │  │                      │  │
│  │ - 接收行情   │  │ - 接收行情   │  │ - 接收行情           │  │
│  │ - 计算信号   │  │ - 计算信号   │  │ - 计算信号           │  │
│  │ - 发送订单   │  │ - 发送订单   │  │ - 发送订单           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**数据流向：**
1. **行情流**: OKX → WebSocket → C++ Server → ZeroMQ → Python Strategy
2. **订单流**: Python Strategy → ZeroMQ → C++ Server → REST API → OKX
3. **回报流**: OKX → WebSocket → C++ Server → ZeroMQ → Python Strategy

### 通信机制详解

Sequence 使用 ZeroMQ 进行进程间通信（IPC），提供三个独立的通道：

#### 1. 行情通道 (Market Data Channel)

```
C++ Server (PUB)  ─────>  Python Strategy (SUB)
                  行情数据
```

- **模式**: PUB-SUB（发布-订阅）
- **地址**: `ipc:///tmp/trading_md.ipc`
- **数据**: Trades, Tickers, K线等
- **延迟**: < 100μs
- **特点**: 
  - 单向推送，服务器主动发送
  - 多个策略可同时订阅
  - 非阻塞接收

#### 2. 订单通道 (Order Channel)

```
Python Strategy (PUSH)  ─────>  C++ Server (PULL)
                        订单请求
```

- **模式**: PUSH-PULL（推送-拉取）
- **地址**: `ipc:///tmp/trading_order.ipc`
- **数据**: 下单、撤单、改单请求
- **延迟**: < 100μs
- **特点**:
  - 单向推送，策略主动发送
  - 多个策略共享同一通道
  - 自动负载均衡

#### 3. 回报通道 (Report Channel)

```
C++ Server (PUB)  ─────>  Python Strategy (SUB)
                  订单回报
```

- **模式**: PUB-SUB（发布-订阅）
- **地址**: `ipc:///tmp/trading_report.ipc`
- **数据**: 订单状态更新、成交回报
- **延迟**: < 100μs
- **特点**:
  - 单向推送，服务器主动发送
  - 每个策略只接收自己的回报（通过 strategy_id 过滤）
  - 非阻塞接收

### 延迟指标

| 链路 | 协议 | 典型延迟 | 说明 |
|------|------|----------|------|
| OKX WebSocket → C++ | WSS | 10-50 ms | 网络延迟 |
| C++ → Python (行情) | IPC | 30-100 μs | 进程间通信 |
| Python → C++ (订单) | IPC | 30-100 μs | 进程间通信 |
| C++ → OKX REST API | HTTPS | 50-200 ms | 网络延迟 |
| **总延迟（行情到策略）** | - | **< 100 μs** | 不含网络 |
| **总延迟（策略到下单）** | - | **50-200 ms** | 含网络 |

---

## 快速上手

### 环境准备

#### 1. 安装 Python 依赖

```bash
# 必需依赖
pip install pyzmq

# 可选依赖（用于数据分析）
pip install pandas numpy
```

#### 2. 启动交易服务器

在运行策略之前，必须先启动 C++ 交易服务器：

```bash
# 进入构建目录
cd /path/to/Real-account-trading-framework/cpp/build

# 启动服务器
./trading_server_live
```

**预期输出：**
```
========================================
    Sequence 实盘交易服务器 (Live)
    OKX WebSocket + ZeroMQ
========================================

[配置] 交易模式: 模拟盘
[初始化] OKX REST API 已创建
[初始化] ZeroMQ 通道:
  - 行情: ipc:///tmp/trading_md.ipc
  - 订单: ipc:///tmp/trading_order.ipc
  - 回报: ipc:///tmp/trading_report.ipc

[WebSocket] 连接中...
[WebSocket] ✓ 连接成功
[WebSocket] 订阅 trades 频道...
[WebSocket] ✓ 订阅成功: {"channel":"trades","instId":"BTC-USDT"}

========================================
  服务器启动完成！
  等待策略连接...
  按 Ctrl+C 停止
========================================
```

#### 3. 验证连接

检查 IPC 文件是否存在：

```bash
ls -la /tmp/trading_*.ipc
```

应该看到三个文件：
```
srwxrwxrwx 1 user user 0 Dec 18 10:00 /tmp/trading_md.ipc
srwxrwxrwx 1 user user 0 Dec 18 10:00 /tmp/trading_order.ipc
srwxrwxrwx 1 user user 0 Dec 18 10:00 /tmp/trading_report.ipc
```

### 第一个策略：Hello World

创建文件 `hello_strategy.py`：

```python
"""
最简单的策略示例
功能：接收行情数据并打印
"""

from strategy_client import StrategyClient, BaseStrategy, TradeData

class HelloStrategy(BaseStrategy):
    """Hello World 策略"""
    
    def __init__(self):
        # 调用父类构造函数
        super().__init__()
        # 策略的内部状态变量
        self.trade_count = 0
    
    def on_start(self):
        """
        策略启动时调用（只调用一次）
        用于初始化策略、加载配置等
        """
        self.log("=" * 60)
        self.log("Hello Strategy 启动!")
        self.log("准备接收行情数据...")
        self.log("=" * 60)
    
    def on_trade(self, trade: TradeData):
        """
        收到成交数据时调用
        
        参数:
            trade: TradeData 对象，包含成交信息
        """
        # 计数器
        self.trade_count += 1
        
        # 每收到 10 条打印一次
        if self.trade_count % 10 == 0:
            self.log(f"收到第 {self.trade_count} 条成交:")
            self.log(f"  交易对: {trade.symbol}")
            self.log(f"  方向: {trade.side}")
            self.log(f"  价格: {trade.price}")
            self.log(f"  数量: {trade.quantity}")
            self.log("-" * 60)
    
    def on_stop(self):
        """
        策略停止时调用（只调用一次）
        用于清理资源、保存状态等
        """
        self.log("=" * 60)
        self.log(f"Hello Strategy 停止!")
        self.log(f"总共处理了 {self.trade_count} 条成交数据")
        self.log("=" * 60)

# ============================================================
# 主程序入口
# ============================================================

if __name__ == "__main__":
    # 导入运行函数
    from strategy_client import run_strategy
    
    # 创建策略实例
    strategy = HelloStrategy()
    
    # 运行策略
    # strategy_id 是策略的唯一标识符，用于区分不同的策略
    run_strategy(strategy, strategy_id="hello_strategy")
```

运行策略：

```bash
python3 hello_strategy.py
```

**预期输出：**
```
============================================================
    Sequence ZeroMQ 策略客户端
============================================================

[配置] 策略 ID: hello_strategy
[连接] 行情通道: ipc:///tmp/trading_md.ipc
[连接] 订单通道: ipc:///tmp/trading_order.ipc
[连接] 回报通道: ipc:///tmp/trading_report.ipc
[连接] ✓ 所有通道连接成功

============================================================
  策略启动！
  按 Ctrl+C 停止
============================================================

[hello_strategy] ============================================================
[hello_strategy] Hello Strategy 启动!
[hello_strategy] 准备接收行情数据...
[hello_strategy] ============================================================
[hello_strategy] 收到第 10 条成交:
[hello_strategy]   交易对: BTC-USDT
[hello_strategy]   方向: buy
[hello_strategy]   价格: 104250.50
[hello_strategy]   数量: 0.001
[hello_strategy] ------------------------------------------------------------
...
```

**停止策略：** 按 `Ctrl+C`

---

## API 参考

### StrategyClient 类

`StrategyClient` 是策略客户端类，负责与交易服务器通信。通常不需要直接使用，而是通过 `BaseStrategy` 间接调用。

#### 构造函数

```python
client = StrategyClient(strategy_id="my_strategy")
```

**参数:**
- `strategy_id` (str): 策略唯一标识符，用于过滤订单回报

#### 连接管理方法

| 方法 | 说明 | 返回值 | 示例 |
|------|------|--------|------|
| `connect()` | 连接到交易服务器的所有通道 | bool | `client.connect()` |
| `disconnect()` | 断开所有通道连接，清理资源 | None | `client.disconnect()` |
| `is_connected()` | 检查是否已连接 | bool | `if client.is_connected():` |

**示例：手动管理连接**
```python
client = StrategyClient(strategy_id="my_strategy")

# 连接
if client.connect():
    print("连接成功")
else:
    print("连接失败")
    exit(1)

# ... 策略逻辑 ...

# 断开连接
client.disconnect()
```

#### 数据接收方法（非阻塞）

| 方法 | 说明 | 返回值 | 阻塞 |
|------|------|--------|------|
| `recv_trade()` | 接收一条成交数据 | `Optional[TradeData]` | 否 |
| `recv_report()` | 接收一条订单回报 | `Optional[OrderReport]` | 否 |

**重要说明:**
- 这些方法是**非阻塞**的，如果没有数据会立即返回 `None`
- 通常在循环中调用，快速轮询

**示例：手动轮询**
```python
import time

while True:
    # 接收成交数据（非阻塞）
    trade = client.recv_trade()
    if trade:
        print(f"收到成交: {trade.symbol} @ {trade.price}")
    
    # 接收订单回报（非阻塞）
    report = client.recv_report()
    if report:
        print(f"订单回报: {report.status}")
    
    # 避免 CPU 100%，可以短暂休眠
    time.sleep(0.001)  # 1ms
```

#### 订单发送方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `send_order(order)` | 发送订单请求 | `str` (订单ID) |
| `send_market_order(symbol, side, quantity)` | 发送市价单 | `str` |
| `send_limit_order(symbol, side, quantity, price)` | 发送限价单 | `str` |

**参数说明:**
- `symbol` (str): 交易对，如 `"BTC-USDT"`
- `side` (str): 方向，`"buy"` 或 `"sell"`
- `quantity` (float): 数量
- `price` (float): 价格（限价单必填）

**示例：发送订单**
```python
# 方式1：使用便捷方法发送市价单
order_id = client.send_market_order(
    symbol="BTC-USDT",
    side="buy",
    quantity=0.001
)
print(f"订单已发送，ID: {order_id}")

# 方式2：使用便捷方法发送限价单
order_id = client.send_limit_order(
    symbol="BTC-USDT",
    side="sell",
    quantity=0.001,
    price=105000.0
)

# 方式3：使用 OrderRequest 对象（更灵活）
from strategy_client import OrderRequest

order = OrderRequest(
    symbol="BTC-USDT",
    side="buy",
    order_type="limit",
    quantity=0.001,
    price=104000.0
)
order_id = client.send_order(order)
```

#### 查询方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `query_balance(currency)` | 查询指定币种余额 | `dict` |
| `query_positions(symbol)` | 查询指定交易对持仓 | `dict` |
| `query_order(order_id)` | 查询订单状态 | `dict` |

**示例：查询账户信息**
```python
# 查询 USDT 余额
balance = client.query_balance("USDT")
if balance:
    print(f"USDT 余额: {balance['available']}")

# 查询 BTC-USDT 持仓
position = client.query_positions("BTC-USDT")
if position:
    print(f"BTC 持仓: {position['amount']}")
```

---

### BaseStrategy 类

`BaseStrategy` 是策略基类，提供事件驱动的策略开发框架。**所有策略都应该继承这个类。**

#### 为什么使用 BaseStrategy？

- **简化开发**: 不需要手动管理连接、循环、信号处理
- **事件驱动**: 通过回调函数响应行情和订单事件
- **自动化**: 自动处理连接、断开、错误处理
- **统一接口**: 所有策略使用相同的接口，便于管理

#### 基本用法

```python
from strategy_client import BaseStrategy, TradeData, OrderReport

class MyStrategy(BaseStrategy):
    """我的策略"""
    
    def __init__(self):
        super().__init__()  # 必须调用父类构造函数
        # 初始化策略的状态变量
        self.position = 0.0
        self.last_price = 0.0
    
    def on_start(self):
        """策略启动时调用"""
        self.log("策略启动")
    
    def on_trade(self, trade: TradeData):
        """收到成交数据时调用"""
        self.log(f"收到成交: {trade.price}")
    
    def on_order(self, report: OrderReport):
        """收到订单回报时调用"""
        self.log(f"订单状态: {report.status}")
    
    def on_stop(self):
        """策略停止时调用"""
        self.log("策略停止")
```

#### 生命周期回调方法

| 方法 | 调用时机 | 是否必须实现 | 调用次数 |
|------|----------|--------------|----------|
| `on_start()` | 策略启动时，连接成功后 | 否 | 1次 |
| `on_trade(trade)` | 收到成交数据时 | 否 | 多次 |
| `on_order(report)` | 收到订单回报时 | 否 | 多次 |
| `on_stop()` | 策略停止时，断开连接前 | 否 | 1次 |

**生命周期示意图：**
```
启动策略
   │
   ├─> connect()           # 连接到服务器
   │
   ├─> on_start()          # 【回调】策略启动
   │
   ├─> ┌─────────────────┐
   │   │  主循环开始      │
   │   │                 │
   │   │  while True:    │
   │   │    recv_trade() ──> on_trade()   # 【回调】收到行情
   │   │    recv_report()──> on_order()   # 【回调】收到回报
   │   │                 │
   │   └─────────────────┘
   │
   ├─> on_stop()           # 【回调】策略停止
   │
   └─> disconnect()        # 断开连接
```

#### 下单便捷方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `buy_market(symbol, quantity)` | 市价买入 | `str` (订单ID) |
| `sell_market(symbol, quantity)` | 市价卖出 | `str` |
| `buy_limit(symbol, quantity, price)` | 限价买入 | `str` |
| `sell_limit(symbol, quantity, price)` | 限价卖出 | `str` |
| `cancel_order(order_id)` | 撤销订单 | `bool` |

**示例：在策略中下单**
```python
class TradingStrategy(BaseStrategy):
    
    def on_trade(self, trade: TradeData):
        """收到行情时下单"""
        
        # 市价买入
        order_id = self.buy_market("BTC-USDT", 0.001)
        self.log(f"市价买入订单: {order_id}")
        
        # 限价卖出（以当前价格 + 100 USDT 挂单）
        order_id = self.sell_limit("BTC-USDT", 0.001, trade.price + 100)
        self.log(f"限价卖出订单: {order_id}")
    
    def on_order(self, report: OrderReport):
        """收到订单回报"""
        if report.is_filled():
            self.log("订单成交!")
            # 如果是买单成交，可以立即下卖单止盈
            if report.side == "buy":
                profit_price = report.filled_price * 1.02  # 2% 止盈
                self.sell_limit(report.symbol, report.filled_quantity, profit_price)
```

#### 查询便捷方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `get_balance(currency)` | 获取币种余额 | `float` |
| `get_position(symbol)` | 获取持仓数量 | `float` |

**示例：查询账户信息**
```python
class BalanceStrategy(BaseStrategy):
    
    def on_start(self):
        """启动时查询账户"""
        usdt_balance = self.get_balance("USDT")
        btc_balance = self.get_balance("BTC")
        
        self.log(f"USDT 余额: {usdt_balance}")
        self.log(f"BTC 余额: {btc_balance}")
        
        # 查询持仓
        btc_position = self.get_position("BTC-USDT")
        self.log(f"BTC-USDT 持仓: {btc_position}")
```

#### 日志方法

| 方法 | 说明 | 日志级别 |
|------|------|----------|
| `log(message)` | 打印日志（自动添加时间戳和策略ID） | INFO |
| `log_info(message)` | 打印信息级别日志 | INFO |
| `log_warning(message)` | 打印警告级别日志 | WARNING |
| `log_error(message)` | 打印错误级别日志 | ERROR |

**示例：使用日志**
```python
class LoggingStrategy(BaseStrategy):
    
    def on_trade(self, trade: TradeData):
        # 普通日志
        self.log(f"收到成交: {trade.price}")
        
        # 信息日志
        self.log_info("处理行情数据中...")
        
        # 警告日志
        if trade.price > 110000:
            self.log_warning("价格过高，暂停交易")
        
        # 错误日志
        if trade.price <= 0:
            self.log_error("价格数据异常!")
```

**日志输出格式：**
```
[2025-12-18 10:30:25] [my_strategy] 收到成交: 104250.50
[2025-12-18 10:30:25] [my_strategy] 处理行情数据中...
[2025-12-18 10:30:26] [my_strategy] [WARNING] 价格过高，暂停交易
[2025-12-18 10:30:27] [my_strategy] [ERROR] 价格数据异常!
```

---

### 数据结构

#### TradeData（成交数据）

表示交易所推送的一笔成交数据。

**类定义：**
```python
class TradeData:
    """成交数据"""
    symbol: str          # 交易对，如 "BTC-USDT"
    price: float         # 成交价格
    quantity: float      # 成交数量
    side: str            # 方向: "buy" 或 "sell"
    timestamp: int       # 时间戳(毫秒)
    trade_id: str        # 成交ID
```

**字段说明：**

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `symbol` | str | 交易对 | `"BTC-USDT"` |
| `price` | float | 成交价格 | `104250.50` |
| `quantity` | float | 成交数量 | `0.001` |
| `side` | str | 成交方向 | `"buy"` 或 `"sell"` |
| `timestamp` | int | 时间戳（毫秒） | `1702876543210` |
| `trade_id` | str | 交易所成交ID | `"123456789"` |

**使用示例：**
```python
def on_trade(self, trade: TradeData):
    """处理成交数据"""
    # 访问字段
    symbol = trade.symbol           # "BTC-USDT"
    price = trade.price             # 104250.50
    quantity = trade.quantity       # 0.001
    side = trade.side               # "buy"
    
    # 打印成交信息
    self.log(f"{symbol} 成交: {side} {quantity} @ {price}")
    
    # 判断方向
    if trade.side == "buy":
        self.log("这是一笔买单成交")
    else:
        self.log("这是一笔卖单成交")
    
    # 计算成交金额
    amount = trade.price * trade.quantity
    self.log(f"成交金额: {amount} USDT")
```

#### OrderReport（订单回报）

表示订单状态更新或成交回报。

**类定义：**
```python
class OrderReport:
    """订单回报"""
    client_order_id: str      # 客户端订单ID
    exchange_order_id: str    # 交易所订单ID
    symbol: str               # 交易对
    side: str                 # 方向: "buy" 或 "sell"
    order_type: str           # 类型: "market" 或 "limit"
    status: str               # 状态: "accepted", "filled", "partial", "cancelled", "rejected"
    quantity: float           # 订单总数量
    filled_quantity: float    # 已成交数量
    filled_price: float       # 成交均价
    fee: float                # 手续费
    error_msg: str            # 错误信息（如果有）
    timestamp: int            # 时间戳（毫秒）
```

**字段说明：**

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `client_order_id` | str | 客户端订单ID（策略生成） | `"my_strategy1702876543210"` |
| `exchange_order_id` | str | 交易所订单ID | `"3130138109650751488"` |
| `symbol` | str | 交易对 | `"BTC-USDT"` |
| `side` | str | 方向 | `"buy"` 或 `"sell"` |
| `order_type` | str | 订单类型 | `"market"` 或 `"limit"` |
| `status` | str | 订单状态 | 见下表 |
| `quantity` | float | 订单总数量 | `0.001` |
| `filled_quantity` | float | 已成交数量 | `0.0005` |
| `filled_price` | float | 成交均价 | `104250.50` |
| `fee` | float | 手续费 | `0.00001` |
| `error_msg` | str | 错误信息 | `"余额不足"` |
| `timestamp` | int | 时间戳（毫秒） | `1702876543210` |

**订单状态：**

| 状态 | 说明 | 含义 |
|------|------|------|
| `accepted` | 已接受 | 订单已被交易所接受，等待成交 |
| `filled` | 完全成交 | 订单已全部成交 |
| `partial` | 部分成交 | 订单部分成交，剩余未成交 |
| `cancelled` | 已取消 | 订单已被取消（主动撤单或超时） |
| `rejected` | 被拒绝 | 订单被交易所拒绝（余额不足、参数错误等） |

**便捷方法：**

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `is_filled()` | 是否完全成交 | `bool` |
| `is_partial()` | 是否部分成交 | `bool` |
| `is_cancelled()` | 是否已取消 | `bool` |
| `is_rejected()` | 是否被拒绝 | `bool` |
| `is_success()` | 是否成功（accepted/filled/partial） | `bool` |

**使用示例：**
```python
def on_order(self, report: OrderReport):
    """处理订单回报"""
    
    # 方式1：使用便捷方法判断状态
    if report.is_filled():
        self.log("✓ 订单完全成交!")
        self.log(f"  成交数量: {report.filled_quantity}")
        self.log(f"  成交均价: {report.filled_price}")
        self.log(f"  手续费: {report.fee}")
    
    elif report.is_partial():
        self.log("◐ 订单部分成交")
        self.log(f"  已成交: {report.filled_quantity}")
        self.log(f"  未成交: {report.quantity - report.filled_quantity}")
    
    elif report.is_cancelled():
        self.log("✗ 订单已取消")
    
    elif report.is_rejected():
        self.log("✗ 订单被拒绝")
        self.log(f"  原因: {report.error_msg}")
    
    # 方式2：直接判断 status 字段
    if report.status == "accepted":
        self.log("订单已被交易所接受，等待成交...")
    
    # 计算成交金额
    if report.is_filled() or report.is_partial():
        amount = report.filled_quantity * report.filled_price
        self.log(f"成交金额: {amount} USDT")
```

#### OrderRequest（订单请求）

创建订单请求时使用的数据结构。

**类定义：**
```python
class OrderRequest:
    """订单请求"""
    symbol: str          # 交易对
    side: str            # 方向: "buy" 或 "sell"
    order_type: str      # 类型: "market" 或 "limit"
    quantity: float      # 数量
    price: float         # 价格（限价单必填，市价单可选）
```

**使用示例：**
```python
from strategy_client import OrderRequest

# 创建限价买单
order = OrderRequest(
    symbol="BTC-USDT",
    side="buy",
    order_type="limit",
    quantity=0.001,
    price=104000.0
)

# 发送订单
order_id = self.client.send_order(order)
```

**通常不需要直接使用，可以用便捷方法：**
```python
# 等价于上面的代码
order_id = self.buy_limit("BTC-USDT", 0.001, 104000.0)
```

---

## 完整示例

### 示例1：Hello World（最简单）

**目标：** 接收行情数据并打印

```python
"""
示例1: Hello World
功能：接收行情并打印
"""

from strategy_client import BaseStrategy, TradeData, run_strategy

class HelloStrategy(BaseStrategy):
    
    def __init__(self):
        super().__init__()
        self.count = 0
    
    def on_trade(self, trade: TradeData):
        self.count += 1
        if self.count % 10 == 0:
            self.log(f"第 {self.count} 条: {trade.symbol} @ {trade.price}")

if __name__ == "__main__":
    run_strategy(HelloStrategy(), strategy_id="hello")
```

### 示例2：定时下单

**目标：** 每隔 N 秒自动下一笔订单

```python
"""
示例2: 定时下单
功能：每10秒自动下一笔小额订单
"""

from strategy_client import BaseStrategy, TradeData, OrderReport, run_strategy
import time

class TimerStrategy(BaseStrategy):
    
    def __init__(self, interval: int = 10):
        super().__init__()
        self.interval = interval          # 下单间隔（秒）
        self.last_order_time = 0          # 上次下单时间
        self.last_price = 0.0             # 最新价格
    
    def on_start(self):
        self.log(f"定时下单策略启动，间隔 {self.interval} 秒")
    
    def on_trade(self, trade: TradeData):
        # 更新最新价格
        self.last_price = trade.price
        
        # 检查是否到了下单时间
        now = time.time()
        if now - self.last_order_time >= self.interval:
            self.place_order()
            self.last_order_time = now
    
    def place_order(self):
        """执行下单"""
        if self.last_price <= 0:
            return
        
        # 以略低于市价的价格挂限价买单
        limit_price = self.last_price * 0.999
        order_id = self.buy_limit("BTC-USDT", 0.001, limit_price)
        
        self.log("=" * 60)
        self.log(f"已下单:")
        self.log(f"  订单ID: {order_id}")
        self.log(f"  数量: 0.001 BTC")
        self.log(f"  价格: {limit_price:.2f} USDT")
        self.log("=" * 60)
    
    def on_order(self, report: OrderReport):
        """处理订单回报"""
        if report.is_filled():
            self.log("✓ 订单成交!")
            self.log(f"  成交价: {report.filled_price:.2f}")
            self.log(f"  手续费: {report.fee}")
        
        elif report.is_rejected():
            self.log("✗ 订单被拒绝")
            self.log(f"  原因: {report.error_msg}")

if __name__ == "__main__":
    # 每10秒下单一次
    strategy = TimerStrategy(interval=10)
    run_strategy(strategy, strategy_id="timer")
```

### 示例3：价格突破策略

**目标：** 监控价格，当突破最高价时买入

```python
"""
示例3: 价格突破策略
功能：监控价格突破并交易
"""

from strategy_client import BaseStrategy, TradeData, OrderReport, run_strategy

class BreakoutStrategy(BaseStrategy):
    
    def __init__(self, breakout_threshold: float = 1.01):
        super().__init__()
        self.high_price = 0.0                 # 历史最高价
        self.breakout_threshold = breakout_threshold  # 突破阈值（1.01 = 1%）
        self.position = 0.0                   # 当前持仓
        self.pending_buy = False              # 是否有未完成买单
    
    def on_start(self):
        self.log("价格突破策略启动")
        self.log(f"突破阈值: {(self.breakout_threshold - 1) * 100:.1f}%")
    
    def on_trade(self, trade: TradeData):
        # 更新历史最高价
        if trade.price > self.high_price:
            self.high_price = trade.price
            self.log(f"更新最高价: {self.high_price:.2f}")
        
        # 检查突破条件
        if not self.pending_buy and self.position == 0:
            if trade.price >= self.high_price * self.breakout_threshold:
                self.on_breakout(trade)
    
    def on_breakout(self, trade: TradeData):
        """处理突破信号"""
        self.log("=" * 60)
        self.log("🚀 检测到价格突破!")
        self.log(f"  当前价: {trade.price:.2f}")
        self.log(f"  历史高: {self.high_price:.2f}")
        self.log(f"  突破幅度: {(trade.price / self.high_price - 1) * 100:.2f}%")
        self.log("=" * 60)
        
        # 市价买入
        order_id = self.buy_market("BTC-USDT", 0.001)
        self.pending_buy = True
        self.log(f"已发送买单: {order_id}")
    
    def on_order(self, report: OrderReport):
        """处理订单回报"""
        if report.side == "buy":
            if report.is_filled():
                self.position += report.filled_quantity
                self.pending_buy = False
                
                self.log("✓ 买单成交!")
                self.log(f"  成交价: {report.filled_price:.2f}")
                self.log(f"  持仓: {self.position}")
                
                # 设置止盈单（2% 止盈）
                profit_price = report.filled_price * 1.02
                self.sell_limit("BTC-USDT", report.filled_quantity, profit_price)
                self.log(f"已设置止盈单 @ {profit_price:.2f}")
        
        elif report.side == "sell":
            if report.is_filled():
                self.position -= report.filled_quantity
                
                self.log("✓ 卖单成交（止盈）!")
                self.log(f"  成交价: {report.filled_price:.2f}")
                self.log(f"  持仓: {self.position}")
                
                # 重置状态，等待下一次突破
                self.high_price = 0.0
                self.log("重置策略，等待下一次突破...")

if __name__ == "__main__":
    # 突破1%时买入
    strategy = BreakoutStrategy(breakout_threshold=1.01)
    run_strategy(strategy, strategy_id="breakout")
```

### 示例4：网格策略（完整版）

**目标：** 实现完整的网格交易策略

```python
"""
示例4: 网格交易策略
功能：在指定价格区间创建网格，自动买低卖高
"""

from strategy_client import BaseStrategy, TradeData, OrderReport, run_strategy
from typing import Dict

class GridStrategy(BaseStrategy):
    
    def __init__(
        self,
        symbol: str = "BTC-USDT",
        center_price: float = 104000.0,
        grid_spacing: float = 100.0,
        grid_num: int = 5,
        quantity_per_grid: float = 0.001
    ):
        super().__init__()
        
        # 配置参数
        self.symbol = symbol
        self.center_price = center_price
        self.grid_spacing = grid_spacing
        self.grid_num = grid_num
        self.quantity = quantity_per_grid
        
        # 运行状态
        self.buy_orders: Dict[str, float] = {}   # 买单: order_id -> price
        self.sell_orders: Dict[str, float] = {}  # 卖单: order_id -> price
        self.position = 0.0
        
        # 统计
        self.total_profit = 0.0
        self.trade_count = 0
    
    def on_start(self):
        """策略启动"""
        self.log("=" * 60)
        self.log("网格策略启动")
        self.log(f"交易对: {self.symbol}")
        self.log(f"中心价: {self.center_price}")
        self.log(f"网格间距: {self.grid_spacing}")
        self.log(f"网格数量: {self.grid_num} (单边)")
        self.log(f"每格数量: {self.quantity}")
        self.log("=" * 60)
        
        # 初始化网格
        self.initialize_grid()
    
    def initialize_grid(self):
        """创建初始网格订单"""
        self.log("初始化网格...")
        
        # 创建买单网格（低于中心价）
        for i in range(1, self.grid_num + 1):
            price = self.center_price - i * self.grid_spacing
            order_id = self.buy_limit(self.symbol, self.quantity, price)
            self.buy_orders[order_id] = price
            self.log(f"  买单 {i}: {self.quantity} @ {price:.2f}")
        
        # 创建卖单网格（高于中心价）
        for i in range(1, self.grid_num + 1):
            price = self.center_price + i * self.grid_spacing
            order_id = self.sell_limit(self.symbol, self.quantity, price)
            self.sell_orders[order_id] = price
            self.log(f"  卖单 {i}: {self.quantity} @ {price:.2f}")
        
        self.log(f"网格初始化完成，共 {len(self.buy_orders) + len(self.sell_orders)} 个订单")
    
    def on_order(self, report: OrderReport):
        """处理订单成交"""
        if not report.is_filled():
            return  # 只处理完全成交
        
        order_id = report.client_order_id
        
        # 买单成交
        if order_id in self.buy_orders:
            buy_price = self.buy_orders.pop(order_id)
            self.on_buy_filled(report, buy_price)
        
        # 卖单成交
        elif order_id in self.sell_orders:
            sell_price = self.sell_orders.pop(order_id)
            self.on_sell_filled(report, sell_price)
    
    def on_buy_filled(self, report: OrderReport, buy_price: float):
        """买单成交处理"""
        self.position += report.filled_quantity
        self.trade_count += 1
        
        self.log("=" * 60)
        self.log(f"✓ 买单成交 #{self.trade_count}")
        self.log(f"  挂单价: {buy_price:.2f}")
        self.log(f"  成交价: {report.filled_price:.2f}")
        self.log(f"  数量: {report.filled_quantity}")
        self.log(f"  手续费: {report.fee}")
        self.log(f"  当前持仓: {self.position}")
        
        # 在上方挂新卖单
        sell_price = buy_price + 2 * self.grid_spacing
        new_order_id = self.sell_limit(self.symbol, report.filled_quantity, sell_price)
        self.sell_orders[new_order_id] = sell_price
        
        self.log(f"  → 新挂卖单 @ {sell_price:.2f}")
        self.log("=" * 60)
    
    def on_sell_filled(self, report: OrderReport, sell_price: float):
        """卖单成交处理"""
        self.position -= report.filled_quantity
        self.trade_count += 1
        
        # 计算盈利
        profit = (sell_price - (sell_price - 2 * self.grid_spacing)) * report.filled_quantity
        profit -= report.fee  # 扣除手续费
        self.total_profit += profit
        
        self.log("=" * 60)
        self.log(f"✓ 卖单成交 #{self.trade_count}")
        self.log(f"  挂单价: {sell_price:.2f}")
        self.log(f"  成交价: {report.filled_price:.2f}")
        self.log(f"  数量: {report.filled_quantity}")
        self.log(f"  手续费: {report.fee}")
        self.log(f"  本次盈利: {profit:.2f} USDT")
        self.log(f"  累计盈利: {self.total_profit:.2f} USDT")
        self.log(f"  当前持仓: {self.position}")
        
        # 在下方挂新买单
        buy_price = sell_price - 2 * self.grid_spacing
        new_order_id = self.buy_limit(self.symbol, report.filled_quantity, buy_price)
        self.buy_orders[new_order_id] = buy_price
        
        self.log(f"  → 新挂买单 @ {buy_price:.2f}")
        self.log("=" * 60)
    
    def on_stop(self):
        """策略停止"""
        self.log("=" * 60)
        self.log("网格策略停止")
        self.log(f"总交易次数: {self.trade_count}")
        self.log(f"累计盈利: {self.total_profit:.2f} USDT")
        self.log(f"最终持仓: {self.position}")
        self.log(f"未完成买单: {len(self.buy_orders)}")
        self.log(f"未完成卖单: {len(self.sell_orders)}")
        self.log("=" * 60)

if __name__ == "__main__":
    # 配置参数
    strategy = GridStrategy(
        symbol="BTC-USDT",
        center_price=104000.0,   # 网格中心价
        grid_spacing=100.0,      # 网格间距（100 USDT）
        grid_num=5,              # 网格数量（单边5个，总共10个）
        quantity_per_grid=0.001  # 每格数量（0.001 BTC）
    )
    
    run_strategy(strategy, strategy_id="grid")
```

**网格策略工作原理：**

```
价格
  ↑
  │
105000 ────── [卖单5]
  │
104500 ────── [卖单4]
  │
104400 ────── [卖单3]
  │
104300 ────── [卖单2]
  │
104200 ────── [卖单1]
  │
104100 ────── [卖单0]
  │
104000 ====== [中心价]  ← 不挂单
  │
103900 ────── [买单0]
  │
103800 ────── [买单1]
  │
103700 ────── [买单2]
  │
103600 ────── [买单3]
  │
103500 ────── [买单4]
  │
103000 ────── [买单5]
  │
  ↓
```

**成交逻辑：**
1. 价格下跌，买单成交 → 在上方挂新卖单
2. 价格上涨，卖单成交 → 在下方挂新买单
3. 来回震荡，赚取差价

### 示例5：多策略部署

**目标：** 同时运行多个策略实例

**创建脚本 `multi_strategy.py`：**

```python
"""
示例5: 多策略部署
功能：同时运行多个策略，每个绑定不同 CPU
"""

import subprocess
import sys
import os
import signal
import time

# 策略配置
STRATEGIES = [
    {
        "name": "grid_1",
        "script": "grid_strategy.py",
        "cpu": 4,
        "args": ["--center-price", "104000", "--grid-spacing", "100"]
    },
    {
        "name": "grid_2",
        "script": "grid_strategy.py",
        "cpu": 5,
        "args": ["--center-price", "105000", "--grid-spacing", "200"]
    },
    {
        "name": "breakout",
        "script": "breakout_strategy.py",
        "cpu": 6,
        "args": []
    }
]

# 进程列表
processes = []

def start_strategies():
    """启动所有策略"""
    print("=" * 60)
    print("启动多策略部署...")
    print("=" * 60)
    
    for config in STRATEGIES:
        print(f"\n启动策略: {config['name']}")
        print(f"  脚本: {config['script']}")
        print(f"  CPU: {config['cpu']}")
        
        # 构造命令
        cmd = [
            "taskset", "-c", str(config['cpu']),  # CPU 绑定
            "python3", config['script'],
            "--strategy-id", config['name']
        ] + config['args']
        
        # 启动进程
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        processes.append({
            "name": config['name'],
            "process": proc
        })
        
        print(f"  ✓ 已启动 (PID: {proc.pid})")
    
    print("\n" + "=" * 60)
    print(f"所有策略已启动，共 {len(processes)} 个")
    print("按 Ctrl+C 停止所有策略")
    print("=" * 60)

def stop_strategies():
    """停止所有策略"""
    print("\n" + "=" * 60)
    print("停止所有策略...")
    print("=" * 60)
    
    for item in processes:
        print(f"停止策略: {item['name']}")
        item['process'].send_signal(signal.SIGINT)
        item['process'].wait()
        print(f"  ✓ 已停止")
    
    print("=" * 60)
    print("所有策略已停止")
    print("=" * 60)

def main():
    """主函数"""
    # 信号处理
    def signal_handler(signum, frame):
        stop_strategies()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动策略
    start_strategies()
    
    # 等待
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
```

**使用方法：**

```bash
# 启动所有策略
python3 multi_strategy.py

# 输出：
# ============================================================
# 启动多策略部署...
# ============================================================
# 
# 启动策略: grid_1
#   脚本: grid_strategy.py
#   CPU: 4
#   ✓ 已启动 (PID: 12345)
# 
# 启动策略: grid_2
#   脚本: grid_strategy.py
#   CPU: 5
#   ✓ 已启动 (PID: 12346)
# 
# 启动策略: breakout
#   脚本: breakout_strategy.py
#   CPU: 6
#   ✓ 已启动 (PID: 12347)
# 
# ============================================================
# 所有策略已启动，共 3 个
# 按 Ctrl+C 停止所有策略
# ============================================================
```

**手动启动（不使用脚本）：**

```bash
# 终端1：启动网格策略1
taskset -c 4 python3 grid_strategy.py --strategy-id grid_1 &

# 终端2：启动网格策略2
taskset -c 5 python3 grid_strategy.py --strategy-id grid_2 &

# 终端3：启动突破策略
taskset -c 6 python3 breakout_strategy.py --strategy-id breakout &

# 查看进程
ps aux | grep python

# 停止所有策略
pkill -f "python3.*strategy"
```

---

## 进阶主题

### 性能优化

#### 1. CPU 绑核

将策略进程绑定到特定 CPU 核心，避免上下文切换：

```python
import os

def set_cpu_affinity(cpu_id: int):
    """
    绑定到指定 CPU 核心
    
    参数:
        cpu_id: CPU 核心 ID (0-95)
    """
    try:
        os.sched_setaffinity(0, {cpu_id})
        print(f"[绑核] 进程已绑定到 CPU {cpu_id}")
        return True
    except Exception as e:
        print(f"[绑核] 绑定失败: {e}")
        return False

# 在策略启动前调用
if __name__ == "__main__":
    # 绑定到 CPU 4
    set_cpu_affinity(4)
    
    # 运行策略
    run_strategy(MyStrategy(), strategy_id="my_strategy")
```

**使用命令行绑核：**
```bash
# 方式1：使用 taskset
taskset -c 4 python3 my_strategy.py

# 方式2：使用 numactl（推荐，同时绑定内存）
numactl --physcpubind=4 --membind=0 python3 my_strategy.py
```

**CPU 分配建议（NUMA Node 0）：**
```
CPU 0:     系统保留
CPU 1:     C++ 服务器主线程
CPU 2:     C++ 服务器订单线程
CPU 3:     备用
CPU 4-11:  策略进程（最多8个策略）
```

#### 2. 实时调度优先级

提高进程优先级，减少调度延迟：

```python
import os

def set_realtime_priority(priority: int = 50):
    """
    设置实时调度优先级
    
    参数:
        priority: 优先级 (1-99)，数字越大优先级越高
    
    注意:
        需要 root 权限
    """
    try:
        # SCHED_FIFO = 1
        param = os.sched_param(priority)
        os.sched_setscheduler(0, 1, param)
        print(f"[调度] 已设置为 SCHED_FIFO，优先级 {priority}")
        return True
    except PermissionError:
        print(f"[调度] 设置失败，需要 root 权限")
        print(f"[调度] 请使用: sudo python3 my_strategy.py")
        return False

# 使用
if __name__ == "__main__":
    set_cpu_affinity(4)
    set_realtime_priority(50)
    run_strategy(MyStrategy(), strategy_id="my_strategy")
```

**使用命令行设置：**
```bash
# 使用 chrt 命令
sudo chrt -f 50 python3 my_strategy.py

# 结合 CPU 绑核
sudo numactl --physcpubind=4 --membind=0 chrt -f 50 python3 my_strategy.py
```

#### 3. NUMA 优化

确保策略和服务器在同一 NUMA 节点：

```bash
# 查看 NUMA 节点
numactl --hardware

# 绑定到 NUMA Node 0
numactl --cpunodebind=0 --membind=0 python3 my_strategy.py
```

#### 4. 减少日志输出

生产环境减少日志频率：

```python
class OptimizedStrategy(BaseStrategy):
    
    def __init__(self):
        super().__init__()
        self.trade_count = 0
    
    def on_trade(self, trade: TradeData):
        self.trade_count += 1
        
        # 每1000条打印一次，而不是每条
        if self.trade_count % 1000 == 0:
            self.log(f"已处理 {self.trade_count} 条行情")
```

### 错误处理

#### 1. 连接错误

```python
from strategy_client import StrategyClient

client = StrategyClient(strategy_id="my_strategy")

# 检查连接
if not client.connect():
    print("[错误] 无法连接到交易服务器")
    print("请检查:")
    print("  1. trading_server_live 是否已启动")
    print("  2. IPC 文件是否存在: ls /tmp/trading_*.ipc")
    print("  3. 文件权限是否正确")
    exit(1)

print("连接成功!")
```

#### 2. 订单错误

```python
class SafeStrategy(BaseStrategy):
    
    def on_order(self, report: OrderReport):
        """处理订单回报，包括错误"""
        
        if report.is_rejected():
            # 订单被拒绝
            self.log_error(f"订单被拒: {report.error_msg}")
            
            # 根据错误类型处理
            if "余额不足" in report.error_msg:
                self.log_error("余额不足，停止下单")
                # 可以选择停止策略或调整仓位
            
            elif "价格不合法" in report.error_msg:
                self.log_error("价格参数错误，检查订单参数")
            
            else:
                self.log_error(f"未知错误: {report.error_msg}")
```

#### 3. 异常捕获

```python
class RobustStrategy(BaseStrategy):
    
    def on_trade(self, trade: TradeData):
        """带异常处理的 on_trade"""
        try:
            # 策略逻辑
            self.process_trade(trade)
        
        except Exception as e:
            # 捕获所有异常
            self.log_error(f"处理行情时发生异常: {e}")
            # 可以选择记录到文件、发送告警等
    
    def process_trade(self, trade: TradeData):
        """实际的处理逻辑"""
        # ... 你的代码 ...
        pass
```

### 日志和监控

#### 1. 文件日志

```python
import logging
from datetime import datetime

class LoggingStrategy(BaseStrategy):
    
    def __init__(self):
        super().__init__()
        
        # 配置文件日志
        log_file = f"strategy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()  # 同时输出到终端
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def on_trade(self, trade: TradeData):
        # 使用 logger
        self.logger.info(f"收到成交: {trade.symbol} @ {trade.price}")
```

#### 2. 性能监控

```python
import time

class MonitoredStrategy(BaseStrategy):
    
    def __init__(self):
        super().__init__()
        self.start_time = time.time()
        self.trade_count = 0
        self.order_count = 0
    
    def on_trade(self, trade: TradeData):
        self.trade_count += 1
    
    def on_order(self, report: OrderReport):
        self.order_count += 1
    
    def print_stats(self):
        """打印统计信息"""
        elapsed = time.time() - self.start_time
        tps = self.trade_count / elapsed if elapsed > 0 else 0
        
        self.log("=" * 60)
        self.log("策略统计:")
        self.log(f"  运行时间: {elapsed:.2f} 秒")
        self.log(f"  处理行情: {self.trade_count} 条")
        self.log(f"  处理订单: {self.order_count} 个")
        self.log(f"  行情速率: {tps:.2f} 条/秒")
        self.log("=" * 60)
```

### 风险控制

#### 1. 仓位管理

```python
class RiskManagedStrategy(BaseStrategy):
    
    def __init__(self, max_position: float = 0.01):
        super().__init__()
        self.max_position = max_position  # 最大持仓（BTC）
        self.position = 0.0
    
    def buy_with_limit(self, symbol: str, quantity: float, price: float):
        """带仓位检查的买入"""
        # 检查是否超过仓位限制
        if self.position + quantity > self.max_position:
            self.log_warning(f"仓位超限，当前: {self.position}，限制: {self.max_position}")
            return None
        
        # 执行买入
        order_id = self.buy_limit(symbol, quantity, price)
        return order_id
    
    def on_order(self, report: OrderReport):
        """更新持仓"""
        if report.is_filled():
            if report.side == "buy":
                self.position += report.filled_quantity
            else:
                self.position -= report.filled_quantity
            
            self.log(f"当前持仓: {self.position}")
```

#### 2. 止损止盈

```python
class StopLossStrategy(BaseStrategy):
    
    def __init__(self, stop_loss_pct: float = 0.02, take_profit_pct: float = 0.05):
        super().__init__()
        self.stop_loss_pct = stop_loss_pct      # 止损比例（2%）
        self.take_profit_pct = take_profit_pct  # 止盈比例（5%）
        self.entry_price = 0.0
        self.position = 0.0
    
    def on_order(self, report: OrderReport):
        """买单成交后，设置止损止盈"""
        if report.side == "buy" and report.is_filled():
            self.entry_price = report.filled_price
            self.position = report.filled_quantity
            
            # 计算止损止盈价格
            stop_loss_price = self.entry_price * (1 - self.stop_loss_pct)
            take_profit_price = self.entry_price * (1 + self.take_profit_pct)
            
            self.log(f"买入成交 @ {self.entry_price:.2f}")
            self.log(f"  止损价: {stop_loss_price:.2f}")
            self.log(f"  止盈价: {take_profit_price:.2f}")
    
    def on_trade(self, trade: TradeData):
        """监控价格，触发止损止盈"""
        if self.position <= 0:
            return
        
        # 计算止损止盈价格
        stop_loss_price = self.entry_price * (1 - self.stop_loss_pct)
        take_profit_price = self.entry_price * (1 + self.take_profit_pct)
        
        # 检查止损
        if trade.price <= stop_loss_price:
            self.log_warning("触发止损!")
            self.sell_market(trade.symbol, self.position)
            self.position = 0.0
        
        # 检查止盈
        elif trade.price >= take_profit_price:
            self.log("触发止盈!")
            self.sell_market(trade.symbol, self.position)
            self.position = 0.0
```

---

## 常见问题 (FAQ)

### Q1: 如何查看策略运行在哪个 CPU 上?

```bash
# 查看进程的 CPU 亲和性
ps -eo pid,comm,psr | grep python

# 实时监控
htop  # 按 F5 显示树形结构，查看 CPU 列
```

### Q2: 连接失败怎么办?

**错误信息：**
```
[错误] 无法连接到交易服务器
```

**检查项：**

1. **交易服务器是否启动？**
   ```bash
   ps aux | grep trading_server_live
   ```

2. **IPC 文件是否存在？**
   ```bash
   ls -la /tmp/trading_*.ipc
   ```

3. **文件权限是否正确？**
   ```bash
   chmod 666 /tmp/trading_*.ipc
   ```

### Q3: 为什么收不到行情数据？

**可能原因：**

1. **服务器未成功连接到 OKX**
   - 检查服务器日志，看是否有连接错误
   - 检查网络连接

2. **服务器未订阅频道**
   - 确认服务器启动时订阅了 trades 频道

3. **当前时间没有交易**
   - BTC-USDT 通常很活跃，如果完全没有数据，检查服务器

### Q4: 订单失败怎么办？

**常见原因和解决方法：**

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| 余额不足 | 账户没有足够的资金 | 充值或减小订单数量 |
| 价格不合法 | 价格超出限制范围 | 检查价格参数，使用合理的价格 |
| 数量不合法 | 数量太小或格式错误 | 检查最小下单数量限制 |
| API 签名错误 | API 密钥配置错误 | 检查 C++ 服务器的 API 密钥配置 |
| 网络错误 | 无法连接到 OKX | 检查网络连接，检查代理设置 |

**调试方法：**
```python
def on_order(self, report: OrderReport):
    if report.is_rejected():
        self.log_error("=" * 60)
        self.log_error("订单被拒绝:")
        self.log_error(f"  订单ID: {report.client_order_id}")
        self.log_error(f"  交易对: {report.symbol}")
        self.log_error(f"  数量: {report.quantity}")
        self.log_error(f"  价格: {report.price if hasattr(report, 'price') else 'N/A'}")
        self.log_error(f"  错误: {report.error_msg}")
        self.log_error("=" * 60)
```

### Q5: 如何停止策略？

**优雅停止：**
```bash
# 按 Ctrl+C
# 策略会自动清理资源并退出
```

**强制停止：**
```bash
# 查找进程
ps aux | grep python | grep my_strategy

# 停止进程
kill -9 <PID>
```

### Q6: 如何在回测模式下运行？

目前 Sequence 主要用于实盘交易。回测功能正在开发中。

临时方案：可以录制历史行情数据，然后重放：

```python
# 录制行情（运行一段时间）
class RecorderStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.trades = []
    
    def on_trade(self, trade: TradeData):
        self.trades.append({
            "symbol": trade.symbol,
            "price": trade.price,
            "quantity": trade.quantity,
            "side": trade.side,
            "timestamp": trade.timestamp
        })
    
    def on_stop(self):
        import json
        with open("trades.json", "w") as f:
            json.dump(self.trades, f)
```

### Q7: 多个策略可以同时运行吗？

可以！每个策略使用不同的 `strategy_id`：

```bash
# 终端1
python3 strategy1.py --strategy-id strategy_1

# 终端2
python3 strategy2.py --strategy-id strategy_2

# 终端3
python3 strategy3.py --strategy-id strategy_3
```

所有策略共享行情数据，但订单回报会根据 `strategy_id` 自动过滤。

### Q8: 延迟有多低？

**测试结果（在本地服务器上）：**

| 链路 | 延迟 |
|------|------|
| OKX → C++ 服务器 | 10-50 ms（网络） |
| C++ → Python（行情） | 30-100 μs（IPC） |
| Python → C++（订单） | 30-100 μs（IPC） |
| C++ → OKX（下单） | 50-200 ms（网络） |

**从收到行情到发出订单：**
- 理想情况：< 1 ms（如果策略逻辑简单）
- 实际情况：1-10 ms（取决于策略复杂度）

---

## 更新履历

### v1.2.0 (2025-12-18)
- ✅ 新增 `BaseStrategy` 基类，简化策略开发
- ✅ 新增 `run_strategy()` 辅助函数
- ✅ 改进 CPU 绑核机制，自动分配策略 CPU
- ✅ 新增网格策略完整示例
- ✅ 新增多策略部署示例
- ✅ 完善文档，添加大量注释和说明
- ✅ 新增进阶主题：性能优化、错误处理、日志监控、风控

### v1.1.0 (2025-12-16)
- ✅ 新增订单查询接口
- ✅ 新增持仓查询接口
- ✅ 支持限价单修改
- ✅ 优化错误处理
- ✅ 改进日志输出

### v1.0.0 (2025-12-15)
- ✅ 基础 ZeroMQ 通信功能
- ✅ 行情数据接收
- ✅ 订单发送和回报接收
- ✅ CPU 绑核支持
- ✅ 基础策略模板

---

## 附录

### 推荐资源

**学习资料：**
- [ZeroMQ 指南](https://zguide.zeromq.org/)
- [OKX API 文档](https://www.okx.com/docs-v5/)
- [Python asyncio 教程](https://docs.python.org/3/library/asyncio.html)

**开发工具：**
- **htop**: 实时监控进程和 CPU 使用率
- **perf**: Linux 性能分析工具
- **valgrind**: 内存泄漏检测（用于 C++ 开发）

### 技术支持

如有问题，请查阅：
1. 本文档
2. `examples/` 目录下的示例代码
3. 项目 GitHub Issues

---

**最后更新**: 2025-12-18  
**版本**: v1.2.0  
**作者**: Sequence Team

**感谢使用 Sequence！祝交易顺利！** 🚀


