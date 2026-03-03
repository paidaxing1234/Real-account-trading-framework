# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

请使用中文回复我

## 项目概述

这是一个加密货币实盘交易框架，支持 OKX 和 Binance 交易所。核心架构是 C++ 高性能服务器 + Python 策略层，通过 pybind11 绑定实现低延迟通信。

## 架构

```
交易所 (OKX/Binance)
    │ WebSocket + REST API
    ▼
C++ 实盘服务器 (trading_server_full)
    │ pybind11 绑定 / ZeroMQ IPC
    ▼
Python 策略层 (strategy_base.so)
    │
    ▼
策略实现 (cpp/strategies/implementations/)
```

关键组件：
- `cpp/server/` - C++ 交易服务器主程序
- `cpp/adapters/binance/` 和 `cpp/adapters/okx/` - 交易所适配器
- `cpp/strategies/` - Python 策略基类和实现
- `实盘框架前端页面/` - Vue 前端，WebSocket 连接 C++ UI Server

## 常用命令

### 编译 C++ 模块

```bash
cd cpp/build
cmake ..
make strategy_base -j$(nproc)  # 编译 Python 绑定模块
make trading_server_full       # 编译实盘服务器
```

### 运行策略

```bash
# 使用配置文件运行策略
python cpp/strategies/implementations/5_mom_factor_cs/live/five_mom_factor_live.py --config config.json

# 策略配置文件在 cpp/strategies/configs/
```

### 前端开发

```bash
cd 实盘框架前端页面
npm install
npm run dev
```

### K线数据工具

```bash
# 下载 Binance K线数据到 Redis
python cpp/scripts/download_binance_1m_klines.py --interval 1m,1h

# 预加载 K线到 Redis
python cpp/scripts/preload_klines_to_redis.py
```

## Redis 数据格式

K线数据存储在 Redis Sorted Set 中：
- Key: `kline:{exchange}:{symbol}:{interval}` (如 `kline:binance:BTCUSDT:1m`)
- Score: timestamp (毫秒)
- Value: JSON 格式 `{"exchange","symbol","interval","timestamp","open","high","low","close","volume"}`

## 策略开发

继承 `StrategyBase` 类，实现回调方法：

```python
from strategy_base import StrategyBase, KlineBar

class MyStrategy(StrategyBase):
    def on_init(self):
        self.register_account(api_key, secret_key, passphrase, is_testnet)
        self.subscribe_kline("BTCUSDT", "1m")

    def on_kline(self, symbol, interval, bar: KlineBar):
        # 策略逻辑
        pass

    def on_order_report(self, report):
        # 订单回报处理
        pass
```

关键方法：
- `get_active_positions()` - 获取当前持仓（注意：依赖回调，可能需要先调用 `refresh_positions()`）
- `send_swap_market_order()` / `send_swap_limit_order()` - 下单
- `get_closes()` / `get_klines()` - 获取历史K线数据

## 注意事项

### Python/C++ 混合调试
修改与 C++ 模块交互的 Python 代码时，先检查 C++ 绑定是否支持相关参数，避免 Python 层修复无效。

### 持仓数据
`get_active_positions()` 依赖 WebSocket 回调更新。如果返回空，考虑使用 `refresh_positions()` 主动查询。

### Binance API
网络访问 Binance API 可能超时，脚本应实现重试逻辑和错误处理。
