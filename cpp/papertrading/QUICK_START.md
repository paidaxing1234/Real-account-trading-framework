# PaperTrading 快速开始

## 🚀 三步启动

### 1. 编译服务器

```bash
cd cpp/papertrading
./build.sh
```

### 2. 启动服务器

```bash
cd ../../build
./papertrading_server
```

**看到以下输出表示成功**:
```
[PaperTradingServer] 前端WebSocket服务器已启动（端口8001，独立线程运行）
[ZMQ通道]
  行情: ipc:///tmp/trading_md.ipc
  订单: ipc:///tmp/trading_order.ipc
  ...
```

### 3. 启动前端（新终端）

```bash
cd 实盘框架前端页面
npm run dev
```

浏览器访问：`http://localhost:3000/papertrading`

## 🐍 运行Python策略

### 创建策略文件

```python
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
        # 订阅行情
        self.client.subscribe_trades(self.symbol)
        self.client.subscribe_kline(self.symbol, "1m")
        print(f"[策略] 已订阅 {self.symbol}")
    
    def on_trade(self, trade):
        print(f"[成交] {trade.symbol} {trade.price}")
        # 在这里添加你的交易逻辑
    
    def on_report(self, report):
        if report.is_filled():
            print(f"[成交] 订单已成交")

if __name__ == "__main__":
    run_strategy(MyStrategy())
```

### 运行策略

```bash
python3 my_strategy.py
```

## 📋 完整流程

```
终端1: 启动服务器
  └─> ./papertrading_server

终端2: 启动前端（可选）
  └─> npm run dev
  └─> 浏览器访问 http://localhost:3000/papertrading

终端3: 运行策略
  └─> python3 my_strategy.py
```

## ✅ 验证

1. **服务器**: 看到 "模拟交易服务器启动完成"
2. **前端**: WebSocket连接状态显示"已连接"
3. **策略**: 开始接收行情数据

## 📚 详细文档

- 完整启动指南: `START_GUIDE.md`
- 架构说明: `ARCHITECTURE.md`
- 实现状态: `IMPLEMENTATION_STATUS.md`

