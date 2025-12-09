# 📊 策略目录说明

本目录包含基于OKX实盘交易框架开发的交易策略示例。

---

## 📁 目录结构

```
strategies/
├── README.md                          # 本说明文件
├── simple_trend_strategy.py           # 简单趋势跟踪策略
├── strategy_log_*.log                 # 策略运行日志
└── strategy_run_*.log                 # 完整运行输出
```

---

## 🎯 现有策略

### 1. Simple Trend Strategy (简单趋势跟踪策略)

**文件**: `simple_trend_strategy.py`

**策略逻辑**:
- 使用1分钟K线判断短期趋势
- 结合实时订单流分析买卖力量
- 双重确认后生成交易信号

**特点**:
- ✅ 完整的事件驱动架构
- ✅ 实时数据接收（K线、行情、成交）
- ✅ 止盈止损风险控制
- ✅ 详细日志记录

**使用方法**:
```bash
# 激活conda环境
conda activate sequence

# 运行策略（默认2分钟）
cd /path/to/backend
python strategies/simple_trend_strategy.py
```

**配置参数**:
```python
strategy = SimpleTrendStrategy(
    event_engine=engine,
    rest_client=rest_client,
    symbol="BTC-USDT",       # 交易对
    max_position=0.01,       # 最大持仓 0.01 BTC
    stop_loss_pct=0.01,      # 止损 1%
    take_profit_pct=0.02     # 止盈 2%
)
```

**运行时长设置**:
```python
# 在main函数中
asyncio.run(run_strategy(duration=120))  # 120秒 = 2分钟
```

---

## 🚀 开发新策略

### 基础模板

```python
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import EventEngine, TickerData, KlineData, TradeData
from adapters.okx import OKXMarketDataAdapter, OKXRestAPI


class MyStrategy:
    """我的策略"""
    
    def __init__(self, event_engine: EventEngine, rest_client: OKXRestAPI):
        self.engine = event_engine
        self.rest = rest_client
        
        # 注册事件监听
        self.engine.register(TickerData, self.on_ticker)
        self.engine.register(KlineData, self.on_kline)
        self.engine.register(TradeData, self.on_trade)
    
    def on_ticker(self, event: TickerData):
        """处理行情数据"""
        print(f"行情: {event.symbol} @ {event.last_price}")
    
    def on_kline(self, event: KlineData):
        """处理K线数据"""
        print(f"K线: {event.symbol} 收盘价 {event.close}")
    
    def on_trade(self, event: TradeData):
        """处理交易数据"""
        print(f"成交: {event.symbol} {event.side} {event.quantity} @ {event.price}")


async def run_my_strategy():
    # 1. 创建组件
    engine = EventEngine()
    rest_client = OKXRestAPI(
        api_key="YOUR_API_KEY",
        secret_key="YOUR_SECRET_KEY",
        passphrase="YOUR_PASSPHRASE",
        is_demo=True
    )
    ws_adapter = OKXMarketDataAdapter(event_engine=engine, is_demo=True)
    
    # 2. 创建策略
    strategy = MyStrategy(engine, rest_client)
    
    # 3. 启动适配器
    await ws_adapter.start()
    
    # 4. 订阅数据
    await ws_adapter.subscribe_ticker("BTC-USDT")
    await ws_adapter.subscribe_candles("BTC-USDT", "1m")
    await ws_adapter.subscribe_trades_all("BTC-USDT")
    
    # 5. 运行
    await asyncio.sleep(60)  # 运行60秒
    
    # 6. 停止
    await ws_adapter.stop()


if __name__ == "__main__":
    asyncio.run(run_my_strategy())
```

---

## 📊 可用数据源

### 1. TickerData (行情快照)

```python
def on_ticker(self, event: TickerData):
    print(f"最新价: {event.last_price}")
    print(f"买一价: {event.bid_price}")
    print(f"卖一价: {event.ask_price}")
    print(f"24h成交量: {event.volume_24h}")
```

**订阅方式**:
```python
await ws_adapter.subscribe_ticker("BTC-USDT")
```

### 2. KlineData (K线数据)

```python
def on_kline(self, event: KlineData):
    print(f"开: {event.open}")
    print(f"高: {event.high}")
    print(f"低: {event.low}")
    print(f"收: {event.close}")
    print(f"量: {event.volume}")
    print(f"间隔: {event.interval}")
```

**订阅方式**:
```python
# 支持的间隔: 1m, 3m, 5m, 15m, 30m, 1H, 4H, 1D等
await ws_adapter.subscribe_candles("BTC-USDT", "1m")
```

### 3. TradeData (逐笔成交)

```python
def on_trade(self, event: TradeData):
    print(f"交易ID: {event.trade_id}")
    print(f"价格: {event.price}")
    print(f"数量: {event.quantity}")
    print(f"方向: {event.side}")  # buy/sell
```

**订阅方式**:
```python
# trades: 可能聚合多笔
await ws_adapter.subscribe_trades("BTC-USDT")

# trades-all: 每次仅一笔
await ws_adapter.subscribe_trades_all("BTC-USDT")
```

---

## 📝 交易接口

### 1. 下单

```python
result = rest_client.place_order(
    inst_id="BTC-USDT",
    td_mode="cash",          # 现货模式
    side="buy",              # buy/sell
    ord_type="limit",        # limit/market
    px="90000",              # 价格
    sz="0.01",               # 数量
    cl_ord_id=f"my_{uuid.uuid4().hex[:16]}"  # 客户订单ID
)
```

### 2. 查询订单

```python
# 查询单个订单
order = rest_client.get_order(ord_id="12345")

# 查询挂单
pending = rest_client.get_orders_pending(inst_id="BTC-USDT")

# 查询历史
history = rest_client.get_orders_history(inst_id="BTC-USDT")
```

### 3. 撤单

```python
result = rest_client.cancel_order(
    inst_id="BTC-USDT",
    ord_id="12345"
)
```

### 4. 查询余额

```python
balance = rest_client.get_balance(ccy="USDT")
```

### 5. 查询持仓

```python
positions = rest_client.get_positions(inst_id="BTC-USDT")
```

---

## ⚠️  重要注意事项

### 1. API密钥安全

**不要**将API密钥硬编码在代码中！建议使用环境变量：

```python
import os

API_KEY = os.environ.get("OKX_API_KEY")
SECRET_KEY = os.environ.get("OKX_SECRET_KEY")
PASSPHRASE = os.environ.get("OKX_PASSPHRASE")

rest_client = OKXRestAPI(
    api_key=API_KEY,
    secret_key=SECRET_KEY,
    passphrase=PASSPHRASE,
    is_demo=True
)
```

### 2. 模拟盘 vs 实盘

```python
# 模拟盘
rest_client = OKXRestAPI(..., is_demo=True)
ws_adapter = OKXMarketDataAdapter(..., is_demo=True)

# 实盘（小心使用！）
rest_client = OKXRestAPI(..., is_demo=False)
ws_adapter = OKXMarketDataAdapter(..., is_demo=False)
```

### 3. 客户订单ID

OKX要求客户订单ID（clOrdId）必须唯一：

```python
# ✅ 推荐：使用UUID
import uuid
cl_ord_id = f"my_{uuid.uuid4().hex[:16]}"

# ❌ 不推荐：可能重复
cl_ord_id = f"order_{int(time.time() * 1000)}"
```

### 4. 网络问题

如遇到网络超时，建议：

1. 增加重试机制
2. 增加超时时间
3. 检查网络连接
4. 使用代理

### 5. 风险控制

**始终设置**:
- ✅ 最大持仓限制
- ✅ 止损止盈
- ✅ 单次交易限额
- ✅ 日交易次数限制

```python
# 示例
MAX_POSITION = 0.01  # BTC
STOP_LOSS = 0.01     # 1%
TAKE_PROFIT = 0.02   # 2%
MAX_TRADES_PER_DAY = 10
```

---

## 📈 日志和监控

### 日志文件

每次运行策略会生成两个日志文件：

1. **策略日志** (`strategy_log_*.log`):
   - 策略内部日志
   - 信号生成
   - 交易决策

2. **运行日志** (`strategy_run_*.log`):
   - 完整输出
   - 系统消息
   - 错误信息

### 查看日志

```bash
# 查看最新的策略日志
tail -f strategies/strategy_log_*.log

# 查看所有日志
cat strategies/strategy_run_*.log
```

---

## 🧪 测试建议

### 开发阶段

1. **短时间测试**: 运行1-2分钟验证逻辑
2. **模拟盘测试**: 始终使用`is_demo=True`
3. **小额测试**: 使用最小交易量（如0.001 BTC）

### 正式运行前

1. **回测**: 使用历史数据验证策略
2. **压力测试**: 测试极端市场条件
3. **风险评估**: 计算最大回撤、胜率等指标

---

## 📚 参考资料

### 框架文档

- [API接口文档](../report/API接口文档.md)
- [快速参考](../report/API_Quick_Reference.md)
- [更新日志](../report/CHANGELOG.md)

### OKX文档

- [OKX官方API文档](https://www.okx.com/docs-v5/zh/)
- [WebSocket频道说明](https://www.okx.com/docs-v5/zh/#websocket-api)
- [REST API参考](https://www.okx.com/docs-v5/zh/#rest-api)

---

## 💡 常见问题

### Q1: 策略不执行交易？

**A**: 检查以下几点：
1. 信号生成逻辑是否正确
2. 余额是否充足
3. 订单参数是否合法
4. 查看日志中的错误信息

### Q2: WebSocket连接失败？

**A**: 可能原因：
1. 网络问题
2. API密钥错误（私有频道）
3. 模拟盘/实盘URL配置错误

### Q3: 下单失败：Parameter error?

**A**: 常见原因：
1. `clOrdId`重复 → 使用UUID
2. 价格/数量不符合规则
3. 余额不足
4. 交易对不存在

### Q4: 如何调试策略？

**A**: 建议方法：
1. 增加打印语句
2. 查看日志文件
3. 使用短时间测试
4. 单步测试各个模块

---

## 🎓 学习路径

1. **基础**: 运行`simple_trend_strategy.py`，理解框架结构
2. **修改**: 调整参数，观察策略行为变化
3. **开发**: 基于模板开发自己的策略
4. **优化**: 回测、优化参数
5. **实盘**: 小额测试 → 逐步增加规模

---

## 🤝 贡献

欢迎贡献新的策略示例！

**提交策略时请包含**:
1. 策略代码（带详细注释）
2. 策略说明（逻辑、参数）
3. 回测结果（如有）
4. 使用注意事项

---

## ⚖️  免责声明

- 本目录中的策略仅供学习和研究使用
- 不构成投资建议
- 实盘交易风险自负
- 请充分测试后再使用
- 建议从小额开始

---

**最后更新**: 2025-12-05  
**框架版本**: v2.2.0  
**维护者**: Development Team

🚀 祝您策略开发顺利！

