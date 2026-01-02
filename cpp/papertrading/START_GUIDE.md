# PaperTrading 启动指南

## 📋 目录

1. [系统架构](#系统架构)
2. [编译服务器](#编译服务器)
3. [启动服务器](#启动服务器)
4. [启动前端](#启动前端)
5. [运行Python策略](#运行python策略)
6. [完整示例](#完整示例)

## 🏗️ 系统架构

```
┌─────────────────┐
│  Python策略     │
│  (ZMQ Client)   │
└────────┬────────┘
         │ ZMQ (IPC)
         │
┌────────▼────────────────────────┐
│  PaperTrading服务器              │
│  - ZMQ服务器 (订单/行情)        │
│  - WebSocket服务器 (前端)        │
│  - MockAccountEngine (模拟账户)  │
│  - OrderExecutionEngine (订单执行)│
└────────┬───────────────────────┘
         │
         ├─── WebSocket (8001) ────► Vue前端
         │
         └─── WebSocket ───────────► OKX交易所 (行情)
```

## 🔨 编译服务器

### 方式1: 使用构建脚本（推荐）

```bash
cd cpp/papertrading
./build.sh
```

### 方式2: 手动编译

```bash
cd cpp
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make papertrading_server -j$(nproc)
```

编译完成后，可执行文件位于：`cpp/build/papertrading_server`

## 🚀 启动服务器

### 1. 准备配置文件

确保 `cpp/papertrading/papertrading_config.json` 存在：

```json
{
  "account": {
    "initial_balance": 100000.0,
    "default_leverage": 1.0
  },
  "fees": {
    "maker_fee_rate": 0.0002,
    "taker_fee_rate": 0.0005
  },
  "trading": {
    "market_order_slippage": 0.0001,
    "default_contract_value": 1.0
  },
  "market_data": {
    "is_testnet": true
  }
}
```

### 2. 启动服务器

```bash
cd cpp/build
./papertrading_server --config ../papertrading/papertrading_config.json
```

或者使用默认配置：

```bash
./papertrading_server
```

### 3. 命令行参数

```bash
# 使用默认配置
./papertrading_server

# 指定配置文件
./papertrading_server --config /path/to/config.json

# 覆盖初始余额
./papertrading_server --balance 50000

# 使用实盘行情（默认是测试网）
./papertrading_server --prod

# 组合使用
./papertrading_server --config config.json --balance 100000 --testnet
```

### 4. 启动成功标志

看到以下输出表示启动成功：

```
========================================
    Sequence 模拟交易服务器
    Paper Trading Server
========================================

[PaperTradingServer] 正在启动模拟交易服务器...
[PaperTradingServer] 模拟账户引擎已初始化，初始余额: 100000 USDT
[PaperTradingServer] 订单执行引擎已初始化
[PaperTradingServer] ZMQ服务器已启动
[PaperTradingServer] 前端WebSocket服务器已启动（端口8001，独立线程运行）
[PaperTradingServer] WebSocket客户端已创建（模式: 模拟盘）
[PaperTradingServer] WebSocket Public 已连接
[PaperTradingServer] WebSocket Business 已连接

========================================
  模拟交易服务器启动完成！
  等待策略连接...
  按 Ctrl+C 停止
========================================

[ZMQ通道]
  行情: ipc:///tmp/trading_md.ipc
  订单: ipc:///tmp/trading_order.ipc
  回报: ipc:///tmp/trading_report.ipc
  查询: ipc:///tmp/trading_query.ipc
  订阅: ipc:///tmp/trading_sub.ipc
```

## 🖥️ 启动前端

### 1. 进入前端目录

```bash
cd 实盘框架前端页面
```

### 2. 安装依赖（首次运行）

```bash
npm install
```

### 3. 启动开发服务器

```bash
npm run dev
```

### 4. 访问前端

浏览器打开：`http://localhost:3000`（或终端显示的端口）

### 5. 访问模拟交易页面

- 登录系统（如果需要）
- 点击侧边栏的"模拟交易"菜单
- 或直接访问：`http://localhost:3000/papertrading`

### 6. 前端功能

- ✅ 查看账户信息（余额、净值、盈亏、收益率）
- ✅ 查看持仓列表
- ✅ 查看订单列表
- ✅ 查看交易历史
- ✅ 配置账户（初始资金、手续费率、滑点）
- ✅ 重置账户
- ✅ 平仓
- ✅ 撤单

## 🐍 运行Python策略

### 1. 策略客户端库

Python策略使用 `strategy_client.py` 连接服务器。

**位置**: `cpp/strategies/strategy_client.py`

### 2. 创建策略示例

创建文件 `my_strategy.py`:

```python
#!/usr/bin/env python3
"""
我的模拟交易策略
"""

import sys
import os

# 添加策略客户端路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cpp', 'strategies'))

from strategy_client import BaseStrategy, TradeData, OrderRequest, run_strategy

class MyStrategy(BaseStrategy):
    """我的策略"""
    
    def __init__(self):
        super().__init__(strategy_id="my_strategy")
        self.symbol = "BTC-USDT-SWAP"
    
    def on_init(self):
        """策略初始化"""
        # 订阅行情
        self.client.subscribe_trades(self.symbol)
        self.client.subscribe_kline(self.symbol, "1m")
        
        print(f"[策略] 已订阅 {self.symbol}")
    
    def on_trade(self, trade: TradeData):
        """处理成交数据"""
        if trade.symbol != self.symbol:
            return
        
        # 策略逻辑：简单示例
        # 这里可以添加你的交易逻辑
        print(f"[成交] {trade.symbol} {trade.side} {trade.quantity} @ {trade.price}")
    
    def on_kline(self, kline):
        """处理K线数据"""
        if kline.symbol != self.symbol:
            return
        
        # 策略逻辑：简单示例
        # 这里可以添加你的交易逻辑
        print(f"[K线] {kline.symbol} {kline.interval} 收盘:{kline.close}")
    
    def on_report(self, report):
        """处理订单回报"""
        if report.is_filled():
            print(f"[成交] 订单 {report.client_order_id} 已成交")
        elif report.is_rejected():
            print(f"[拒绝] 订单 {report.client_order_id} 被拒绝: {report.error_msg}")

if __name__ == "__main__":
    strategy = MyStrategy()
    run_strategy(strategy)
```

### 3. 运行策略

```bash
python3 my_strategy.py
```

### 4. 策略连接流程

1. **连接ZMQ服务器**
   - 自动连接到 `ipc:///tmp/trading_*.ipc`
   - 如果连接失败，检查服务器是否启动

2. **订阅行情**
   - 在 `on_init()` 中调用 `subscribe_trades()` 或 `subscribe_kline()`
   - 服务器会推送行情数据

3. **接收行情**
   - `on_trade()`: 接收逐笔成交
   - `on_kline()`: 接收K线数据

4. **下单**
   - 使用 `send_order()` 或便捷方法：
     - `buy_market()`, `sell_market()`
     - `buy_limit()`, `sell_limit()`
     - `swap_buy_market()`, `swap_sell_market()` (合约)

5. **接收回报**
   - `on_report()`: 接收订单状态更新

### 5. 策略示例（完整版）

```python
#!/usr/bin/env python3
"""
完整策略示例
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cpp', 'strategies'))

from strategy_client import BaseStrategy, TradeData, OrderRequest, run_strategy

class SimpleStrategy(BaseStrategy):
    """简单策略示例"""
    
    def __init__(self):
        super().__init__(strategy_id="simple_strategy")
        self.symbol = "BTC-USDT-SWAP"
        self.last_price = 0.0
        self.position = 0  # 持仓数量（张）
    
    def on_init(self):
        """初始化"""
        # 订阅行情
        if not self.client.subscribe_trades(self.symbol):
            print("[错误] 订阅失败")
            return
        
        if not self.client.subscribe_kline(self.symbol, "1m"):
            print("[错误] 订阅K线失败")
            return
        
        print(f"[策略] 已启动，订阅 {self.symbol}")
    
    def on_trade(self, trade: TradeData):
        """处理成交"""
        if trade.symbol != self.symbol:
            return
        
        self.last_price = trade.price
        
        # 简单策略：价格低于某个值时买入
        if trade.price < 40000 and self.position == 0:
            order_id = self.client.swap_buy_market(self.symbol, 1)
            print(f"[下单] 买入 1张，订单ID: {order_id}")
            self.position = 1
        
        # 价格高于某个值时卖出
        elif trade.price > 45000 and self.position > 0:
            order_id = self.client.swap_sell_market(self.symbol, 1)
            print(f"[下单] 卖出 1张，订单ID: {order_id}")
            self.position = 0
    
    def on_kline(self, kline):
        """处理K线"""
        if kline.symbol != self.symbol:
            return
        
        # 可以在这里添加基于K线的策略逻辑
        pass
    
    def on_report(self, report):
        """处理订单回报"""
        if report.is_filled():
            print(f"[成交] {report.symbol} {report.filled_quantity}张 @ {report.filled_price}")
        elif report.is_rejected():
            print(f"[拒绝] {report.error_msg}")
    
    def on_stop(self):
        """停止时清理"""
        # 取消订阅
        self.client.unsubscribe_trades(self.symbol)
        self.client.unsubscribe_kline(self.symbol, "1m")
        print("[策略] 已停止")

if __name__ == "__main__":
    strategy = SimpleStrategy()
    run_strategy(strategy)
```

## 📝 完整示例

### 场景：启动完整系统并运行策略

#### 步骤1: 启动PaperTrading服务器

**终端1**:
```bash
cd cpp/build
./papertrading_server --config ../papertrading/papertrading_config.json
```

等待看到：
```
[PaperTradingServer] 前端WebSocket服务器已启动（端口8001，独立线程运行）
[ZMQ通道]
  行情: ipc:///tmp/trading_md.ipc
  订单: ipc:///tmp/trading_order.ipc
  ...
```

#### 步骤2: 启动前端（可选）

**终端2**:
```bash
cd 实盘框架前端页面
npm run dev
```

浏览器访问：`http://localhost:3000/papertrading`

#### 步骤3: 运行Python策略

**终端3**:
```bash
# 创建策略文件
cat > my_strategy.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, 'cpp/strategies')
from strategy_client import BaseStrategy, run_strategy

class MyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("my_strategy")
        self.symbol = "BTC-USDT-SWAP"
    
    def on_init(self):
        self.client.subscribe_trades(self.symbol)
        print(f"[策略] 已订阅 {self.symbol}")
    
    def on_trade(self, trade):
        print(f"[成交] {trade.symbol} {trade.price}")

if __name__ == "__main__":
    run_strategy(MyStrategy())
EOF

# 运行策略
python3 my_strategy.py
```

## 🔍 验证系统运行

### 1. 检查ZMQ通道

```bash
# 检查IPC文件是否存在
ls -la /tmp/trading_*.ipc

# 应该看到：
# /tmp/trading_md.ipc
# /tmp/trading_order.ipc
# /tmp/trading_report.ipc
# /tmp/trading_query.ipc
# /tmp/trading_sub.ipc
```

### 2. 检查WebSocket服务器

```bash
# 检查端口8001是否监听
netstat -tlnp | grep 8001
# 或
ss -tlnp | grep 8001
```

### 3. 检查前端连接

- 打开浏览器开发者工具（F12）
- 查看Console，应该看到：
  ```
  ✅ WebSocket连接已建立
  C++ UI服务器已连接
  ```

### 4. 测试策略连接

运行策略后，服务器终端应该显示：
```
[PaperTradingServer] 收到订阅请求: trades BTC-USDT-SWAP
```

## ⚠️ 常见问题

### 1. ZMQ连接失败

**错误**: `zmq.error.ZMQError: No such file or directory`

**解决**:
- 确保PaperTrading服务器已启动
- 检查 `/tmp/trading_*.ipc` 文件是否存在
- 检查文件权限：`chmod 666 /tmp/trading_*.ipc`

### 2. WebSocket连接失败

**错误**: 前端显示"未连接"

**解决**:
- 检查服务器是否启动
- 检查端口8001是否被占用
- 检查防火墙设置

### 3. 策略无法接收行情

**原因**:
- 未订阅行情
- 服务器未连接到OKX WebSocket
- 交易对名称错误

**解决**:
- 在策略的 `on_init()` 中调用 `subscribe_trades()`
- 检查服务器日志，确认WebSocket连接成功
- 确认交易对名称正确（如 "BTC-USDT-SWAP"）

### 4. 订单无法成交

**原因**:
- 账户余额不足
- 订单价格不合理
- 订单类型错误

**解决**:
- 检查账户余额（前端或查询接口）
- 检查订单价格是否合理
- 确认订单类型（market/limit）

## 📚 相关文件

- **服务器**: `cpp/papertrading/papertrading_server.h/cpp`
- **配置**: `cpp/papertrading/papertrading_config.json`
- **主程序**: `cpp/papertrading/main.cpp`
- **Python客户端**: `cpp/strategies/strategy_client.py`
- **前端页面**: `实盘框架前端页面/src/views/Papertrading.vue`
- **前端API**: `实盘框架前端页面/src/api/papertrading.js`

## 🎯 快速开始（一键启动）

### 方式1: 使用脚本

```bash
# 启动服务器
cd cpp/papertrading
./build.sh && cd ../../build && ./papertrading_server &

# 启动前端（新终端）
cd 实盘框架前端页面
npm run dev &

# 运行策略（新终端）
python3 my_strategy.py
```

### 方式2: 手动启动

1. **终端1**: 启动服务器
   ```bash
   cd cpp/build
   ./papertrading_server
   ```

2. **终端2**: 启动前端（可选）
   ```bash
   cd 实盘框架前端页面
   npm run dev
   ```

3. **终端3**: 运行策略
   ```bash
   python3 my_strategy.py
   ```

## 📊 监控和调试

### 服务器日志

服务器会输出详细日志：
- `[PaperTradingServer]`: 服务器状态
- `[WebSocketServer]`: WebSocket连接
- `[ZMQ]`: ZMQ消息
- `[订单]`: 订单处理

### 前端监控

- 账户信息实时更新
- 订单状态实时更新
- WebSocket连接状态显示

### 策略调试

- 使用 `print()` 输出日志
- 检查 `on_report()` 接收订单回报
- 使用 `query_account()` 查询账户

## 🎉 完成！

现在你已经可以：
- ✅ 启动PaperTrading服务器
- ✅ 通过前端查看和管理模拟账户
- ✅ 运行Python策略进行模拟交易

享受模拟交易的乐趣！🚀

