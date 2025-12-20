# C++ 策略基类使用说明

## 概述

本模块提供了一个 C++ 实现的策略基类 `StrategyBase`，通过 pybind11 暴露给 Python。策略开发者可以通过继承这个基类来实现自己的交易策略，享受以下优势：

1. **低延迟**: ZMQ 通信和 K 线存储在 C++ 层实现
2. **简洁接口**: 只需重写几个回调函数即可
3. **自动存储**: 内置 K 线数据存储（2 小时滑动窗口）
4. **统一框架**: 账户注册、订阅管理、下单接口一应俱全

## 文件结构

```
strategies/
├── py_strategy_base.h        # C++ 策略基类头文件
├── py_strategy_bindings.cpp  # pybind11 绑定代码
├── CMakeLists.txt            # CMake 编译配置
├── build_strategy_base.sh    # 一键编译脚本
├── grid_strategy_cpp.py      # 网格策略示例
├── example_strategy.py       # 简单示例策略
└── README_策略基类.md         # 本说明文档
```

## 编译方法

### 依赖

- Python 3.8+
- pybind11: `pip install pybind11`
- ZeroMQ: 
  - macOS: `brew install zeromq cppzmq`
  - Ubuntu: `apt install libzmq3-dev`
- nlohmann_json:
  - macOS: `brew install nlohmann-json`
  - Ubuntu: `apt install nlohmann-json3-dev`

### 编译步骤

```bash
# 方法 1: 使用脚本
cd strategies
./build_strategy_base.sh

# 方法 2: 手动编译
cd strategies
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make

# 将模块复制到策略目录
cp strategy_base.cpython-*.so ../
```

编译完成后会生成 `strategy_base.cpython-*.so` 模块。

## 使用方法

### 基本结构

```python
from strategy_base import StrategyBase, KlineBar

class MyStrategy(StrategyBase):
    def __init__(self, strategy_id: str):
        # 初始化基类，设置 K 线存储容量
        super().__init__(strategy_id, max_kline_bars=7200)  # 2小时 1s K线
    
    def on_init(self):
        """策略初始化（连接成功后调用）"""
        # 订阅 K 线
        self.subscribe_kline("BTC-USDT-SWAP", "1s")
    
    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K 线回调（每收到一根 K 线调用）"""
        print(f"收到 K 线: {symbol} {interval} close={bar.close}")
        
        # 读取历史数据
        closes = self.get_closes(symbol, interval)
        if len(closes) >= 20:
            ma20 = sum(closes[-20:]) / 20
            print(f"MA20: {ma20:.2f}")
    
    def on_tick(self):
        """每次循环调用（可用于定时逻辑）"""
        pass
    
    def on_stop(self):
        """策略停止回调"""
        pass

# 运行策略
strategy = MyStrategy("my_strategy")
strategy.register_account(api_key, secret_key, passphrase, is_testnet=True)
strategy.run()
```

### 完整 API

#### 构造函数

```python
StrategyBase(strategy_id: str, max_kline_bars: int = 7200)
```

- `strategy_id`: 策略唯一标识
- `max_kline_bars`: 每个币种/周期 保存的最大 K 线数量（默认 7200 = 2 小时 1s K 线）

#### 连接管理

```python
connect() -> bool          # 连接实盘服务器
disconnect()               # 断开连接
run()                      # 运行策略（主循环）
stop()                     # 停止策略
```

#### 账户管理

```python
register_account(api_key, secret_key, passphrase, is_testnet=True) -> bool
unregister_account() -> bool
```

#### 订阅管理

```python
subscribe_kline(symbol, interval) -> bool     # 订阅 K 线
unsubscribe_kline(symbol, interval) -> bool   # 取消订阅
subscribe_trades(symbol) -> bool              # 订阅交易数据
unsubscribe_trades(symbol) -> bool
```

#### 下单接口

```python
# 合约市价单
send_swap_market_order(symbol, side, quantity, pos_side="") -> str

# 合约限价单
send_swap_limit_order(symbol, side, quantity, price, pos_side="") -> str
```

参数说明：
- `symbol`: 交易对，如 "BTC-USDT-SWAP"
- `side`: "buy" 或 "sell"
- `quantity`: 张数
- `pos_side`: "long" 或 "short"（可选，默认根据 side 推断）
- `price`: 限价单价格

返回：客户端订单 ID

#### K 线数据读取

```python
# 获取所有 K 线
get_klines(symbol, interval) -> List[KlineBar]

# 获取收盘价数组
get_closes(symbol, interval) -> List[float]

# 获取最近 n 根 K 线
get_recent_klines(symbol, interval, n) -> List[KlineBar]

# 获取最后一根 K 线
get_last_kline(symbol, interval) -> KlineBar or None

# 获取 K 线数量
get_kline_count(symbol, interval) -> int
```

#### 回调函数（供重写）

```python
def on_init(self):
    """策略初始化"""
    pass

def on_stop(self):
    """策略停止"""
    pass

def on_tick(self):
    """每次循环调用"""
    pass

def on_kline(self, symbol: str, interval: str, bar: KlineBar):
    """K 线回调"""
    pass

def on_order_report(self, report: dict):
    """订单回报回调"""
    pass

def on_register_report(self, success: bool, error_msg: str):
    """账户注册回报"""
    pass
```

#### 属性

```python
strategy_id: str           # 策略 ID
is_running: bool           # 是否运行中
is_account_registered: bool # 账户是否已注册
kline_count: int           # 接收的 K 线数量
order_count: int           # 发送的订单数量
report_count: int          # 收到的回报数量
```

#### 日志

```python
log_info(msg: str)         # 输出信息日志
log_error(msg: str)        # 输出错误日志
```

### KlineBar 结构

```python
class KlineBar:
    timestamp: int   # 时间戳（毫秒）
    open: float      # 开盘价
    high: float      # 最高价
    low: float       # 最低价
    close: float     # 收盘价
    volume: float    # 成交量
```

## 示例策略

### 1. 网格策略 (grid_strategy_cpp.py)

完整的网格交易策略，功能与 `grid_strategy_standalone.py` 相同：

```bash
python3 grid_strategy_cpp.py --symbol BTC-USDT-SWAP --grid-num 20
```

### 2. 简单示例 (example_strategy.py)

展示基本用法：

```bash
python3 example_strategy.py
```

## 与纯 Python 版本对比

| 特性 | 纯 Python | C++ 基类 |
|------|----------|---------|
| ZMQ 通信 | Python | C++ |
| K 线存储 | Python (numpy) | C++ |
| 回调延迟 | ~100μs | ~10μs |
| 代码量 | 较多 | 较少 |
| 灵活性 | 高 | 中 |

## 注意事项

1. **GIL 释放**: `run()` 方法内部已释放 GIL，允许多线程
2. **线程安全**: K 线存储使用互斥锁保护
3. **信号处理**: 需要在 Python 层设置信号处理器调用 `stop()`
4. **服务器**: 需要先启动 `trading_server_full` 实盘服务器

## 故障排查

1. **找不到模块**
   ```
   错误: 未找到 strategy_base 模块
   ```
   解决: 确保编译成功，并且 `.so` 文件在 Python 路径中

2. **连接失败**
   ```
   [xxx] ERROR: 连接失败
   ```
   解决: 确保实盘服务器 `trading_server_full` 正在运行

3. **编译错误**
   - 检查依赖是否安装完整
   - 检查 pybind11 版本（需要 2.6+）

