# C++ Python绑定

## 📋 概述

使用PyBind11将C++实盘框架暴露给Python，实现Web服务与C++引擎的高效通信。

## 🏗️ 架构

```
Python Web服务
    ↓ import trading_cpp
PyBind11绑定层 (本目录)
    ↓ C++接口调用
C++实盘框架 (EventEngine, Order, etc.)
```

## 🔧 编译

### 1. 安装依赖

```bash
# Ubuntu/Debian
sudo apt-get install python3-dev

# macOS
brew install python

# Windows
# 安装Visual Studio Build Tools
```

### 2. 编译绑定

```bash
cd cpp
mkdir build && cd build

# 配置（启用Python绑定）
cmake .. -DBUILD_PYTHON_BINDINGS=ON

# 编译
cmake --build . --target trading_cpp

# 测试
python -c "import trading_cpp; print('✅ 导入成功')"
```

### 3. 安装到系统

```bash
# 方式1：复制到site-packages
cp trading_cpp*.so $(python -c "import site; print(site.getsitepackages()[0])")

# 方式2：使用pip安装
pip install .
```

## 📝 使用示例

### Python中使用C++类

```python
import trading_cpp

# 创建EventEngine
engine = trading_cpp.EventEngine()

# 创建订单
order = trading_cpp.Order.buy_limit("BTC-USDT-SWAP", 0.1, 42500.0)

# 查询订单属性
print(f"订单ID: {order.order_id}")
print(f"交易对: {order.symbol}")
print(f"状态: {order.state_str()}")

# 推送事件
engine.put(order)

# 注册监听器
def on_order(order):
    print(f"收到订单: {order.symbol} {order.state_str()}")

engine.register_listener(trading_cpp.Order, on_order)
```

### 在Web服务中使用

```python
# web_server/services/cpp_bridge.py

from services.cpp_bridge import cpp_bridge

# 初始化
cpp_bridge.init()

# 下单
result = await cpp_bridge.place_order({
    'symbol': 'BTC-USDT-SWAP',
    'side': 'BUY',
    'type': 'LIMIT',
    'price': 42500.0,
    'quantity': 0.1
})

# 监听C++事件
cpp_bridge.on('order', lambda order: print(order))
```

## 🎯 暴露的C++接口

### Event类
- `timestamp` - 时间戳
- `type_name()` - 类型名称

### Order类
- `order_id` - 订单ID
- `symbol` - 交易对
- `side` - 买卖方向
- `state` - 订单状态
- `price` - 价格
- `quantity` - 数量
- `filled_quantity` - 已成交数量
- `is_filled()` - 是否完全成交
- `buy_limit()` - 创建限价买单
- `sell_limit()` - 创建限价卖单

### TickerData类
- `symbol` - 交易对
- `last_price` - 最新价
- `bid_price` - 买一价
- `ask_price` - 卖一价
- `mid_price()` - 中间价
- `spread()` - 价差

### EventEngine类
- `put(event)` - 推送事件
- `register_listener(type, callback)` - 注册监听器
- `inject(name, func)` - 注入接口
- `call(name)` - 调用接口

## ⚡ 性能

### 调用延迟

| 操作 | 延迟 |
|-----|------|
| Python调用C++方法 | <0.01ms |
| C++回调Python函数 | <0.05ms |
| 事件推送 | <0.1ms |

### 对比

| 方式 | 延迟 |
|-----|------|
| **PyBind11** | <0.01ms ⚡⚡⚡ |
| ZeroMQ | <1ms ⚡⚡ |
| HTTP | 5-20ms ⚡ |
| WebSocket | 10-30ms |

## 🐛 故障排查

### 导入失败

```python
import trading_cpp
# ModuleNotFoundError: No module named 'trading_cpp'
```

**解决**：
1. 检查是否编译：`ls cpp/build/trading_cpp*.so`
2. 检查Python路径：`python -c "import sys; print(sys.path)"`
3. 重新编译：`cd cpp/build && cmake --build .`

### 符号未找到

```
undefined symbol: _ZN...
```

**解决**：
1. 检查C++编译选项
2. 确保所有依赖都链接
3. 使用`ldd`检查依赖：`ldd trading_cpp.so`

## 📚 参考

- [PyBind11文档](https://pybind11.readthedocs.io/)
- [C++框架README](../README.md)
- [Web服务文档](../../web_server/README_WEB_SERVER.md)

