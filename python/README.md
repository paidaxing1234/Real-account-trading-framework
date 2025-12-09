# OKX实盘交易框架

**版本**: v2.2.0  
**更新日期**: 2025-12-05  
**状态**: 🚧 开发中（完成度：40%）

---

## 📚 文档导航

### 🚀 快速开始

1. **⚡ 5分钟了解框架** → [`QUICK_SUMMARY.md`](QUICK_SUMMARY.md)
   - 当前状态概览
   - 核心问题说明
   - 立即行动建议

2. **📊 深入分析（50页）** → [`FRAMEWORK_ANALYSIS.md`](FRAMEWORK_ANALYSIS.md)
   - 详细功能评估
   - 完整代码示例
   - 开发路线图

3. **📋 待办清单** → [`TODO.md`](TODO.md)
   - 按优先级分类
   - 详细任务清单
   - 时间估算

### 📖 使用指南

- **策略开发指南** → [`strategies/README.md`](strategies/README.md)
- **API文档** → [`report/README.md`](report/README.md)
- **示例代码** → [`examples/`](examples/)
- **测试说明** → [`test/README.md`](test/README.md)

### 🎯 演示与报告

- **策略演示** → [`STRATEGY_DEMO_SUMMARY.md`](STRATEGY_DEMO_SUMMARY.md)
- **更新日志** → [`report/CHANGELOG.md`](report/CHANGELOG.md)
- **项目交付** → [`PROJECT_DELIVERY.md`](PROJECT_DELIVERY.md)

---

## ⚠️  重要提醒

### 当前状态

```
✅ 已完成（40%）:
   - 事件驱动架构
   - OKX REST API（17个接口）
   - OKX WebSocket公共频道（4个）
   - 基础文档和示例

❌ 缺失（60%）:
   - 订单管理系统 ⚠️  阻塞实盘
   - 账户/持仓管理 ⚠️  阻塞实盘
   - 风险管理模块 ⚠️  阻塞实盘
   - WebSocket私有频道
   - 自动重连机制
   - 请求限流保护
```

### ⚠️  使用建议

| 场景 | 建议 | 风险 |
|------|------|------|
| **模拟盘测试** | ✅ 可以使用 | 低 |
| **小额实盘** | ⚠️  谨慎使用，需手动管理 | 中 |
| **正式实盘** | ❌ 不建议，等待完善 | 高 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/backend
pip install -r requirements.txt

# 或使用conda环境
conda activate sequence
```

### 2. 运行示例策略

```bash
# 简单趋势策略（模拟盘）
python strategies/simple_trend_strategy.py

# 查看日志
tail -f strategies/strategy_log_*.log
```

### 3. 测试API连接

```bash
# 测试OKX登录
python test/okx_login_test.py

# 测试WebSocket
python test/test_okx_websocket.py
```

---

## 📊 目录结构

```
backend/
├── core/                    # 核心模块
│   ├── event_engine.py     # 事件引擎
│   ├── order.py            # 订单模型
│   └── data.py             # 数据模型
│
├── adapters/                # 交易所适配器
│   └── okx/
│       ├── rest_api.py     # REST API
│       ├── websocket.py    # WebSocket公共频道
│       └── adapter.py      # 行情适配器
│
├── strategies/              # 策略示例
│   ├── simple_trend_strategy.py
│   └── README.md
│
├── test/                    # 测试文件
├── examples/                # 示例代码
├── report/                  # 文档报告
│
├── QUICK_SUMMARY.md         # ⚡ 快速总结
├── FRAMEWORK_ANALYSIS.md    # 📊 详细分析
├── TODO.md                  # 📋 待办清单
└── README.md                # 📖 本文件
```

---

## 🎯 核心功能

### ✅ 已实现

#### 1. 事件驱动架构
```python
from core import EventEngine, TickerData, KlineData

engine = EventEngine()

def on_ticker(event: TickerData):
    print(f"行情: {event.symbol} @ {event.last_price}")

engine.register(TickerData, on_ticker)
```

#### 2. REST API（17个接口）
```python
from adapters.okx import OKXRestAPI

rest = OKXRestAPI(api_key, secret_key, passphrase, is_demo=True)

# 下单
result = rest.place_order(
    inst_id="BTC-USDT",
    td_mode="cash",
    side="buy",
    ord_type="limit",
    px="90000",
    sz="0.01"
)

# 查询余额
balance = rest.get_balance(ccy="USDT")

# 查询持仓
positions = rest.get_positions(inst_id="BTC-USDT")
```

#### 3. WebSocket实时数据
```python
from adapters.okx import OKXMarketDataAdapter

ws = OKXMarketDataAdapter(engine, is_demo=True)
await ws.start()

# 订阅数据
await ws.subscribe_ticker("BTC-USDT")
await ws.subscribe_candles("BTC-USDT", "1m")
await ws.subscribe_trades_all("BTC-USDT")
```

### ❌ 待实现（关键）

1. **订单管理系统** (OrderManager) - ⚠️  阻塞实盘
2. **账户/持仓管理** (AccountManager) - ⚠️  阻塞实盘
3. **风险管理模块** (RiskManager) - ⚠️  阻塞实盘
4. **WebSocket私有频道** - 实时订单更新
5. **自动重连机制** - 提高稳定性
6. **请求限流保护** - 避免被封禁

详见 [`FRAMEWORK_ANALYSIS.md`](FRAMEWORK_ANALYSIS.md)

---

## 💡 示例代码

### 基础策略模板

```python
import asyncio
from core import EventEngine, TickerData, KlineData
from adapters.okx import OKXMarketDataAdapter, OKXRestAPI


class MyStrategy:
    def __init__(self, engine, rest):
        self.engine = engine
        self.rest = rest
        
        # 注册事件
        engine.register(TickerData, self.on_ticker)
        engine.register(KlineData, self.on_kline)
    
    def on_ticker(self, event: TickerData):
        print(f"行情: {event.last_price}")
    
    def on_kline(self, event: KlineData):
        print(f"K线: {event.close}")


async def main():
    # 创建组件
    engine = EventEngine()
    rest = OKXRestAPI(..., is_demo=True)
    ws = OKXMarketDataAdapter(engine, is_demo=True)
    
    # 创建策略
    strategy = MyStrategy(engine, rest)
    
    # 启动
    await ws.start()
    await ws.subscribe_ticker("BTC-USDT")
    await ws.subscribe_candles("BTC-USDT", "1m")
    
    # 运行
    await asyncio.sleep(60)
    await ws.stop()


asyncio.run(main())
```

更多示例: [`examples/`](examples/) 和 [`strategies/`](strategies/)

---

## 📈 开发路线

### Phase 1: 核心功能（2周）⏰
- [ ] 订单管理系统
- [ ] 账户/持仓管理
- [ ] 风险管理模块
- [ ] 异常处理完善

**目标**: 可以安全地进行小额实盘测试

### Phase 2: 稳定性增强（2周）
- [ ] WebSocket私有频道
- [ ] 自动重连机制
- [ ] 请求限流保护
- [ ] 配置管理系统

**目标**: 可以进行中等规模实盘

### Phase 3: 功能完善（2-3周）
- [ ] 订单簿数据
- [ ] 性能监控
- [ ] 单元测试框架
- [ ] 数据存储

**目标**: 生产级可用

详见 [`TODO.md`](TODO.md)

---

## 🤝 贡献指南

欢迎贡献代码和建议！

### 开发流程
1. Fork项目
2. 创建功能分支 (`git checkout -b feature/订单管理`)
3. 提交代码 (`git commit -m '实现订单管理'`)
4. 推送分支 (`git push origin feature/订单管理`)
5. 创建Pull Request

### 代码规范
- 使用类型提示
- 编写单元测试
- 更新文档
- 遵循PEP8

---

## 📞 联系方式

- **问题反馈**: GitHub Issues
- **技术讨论**: 内部讨论群
- **紧急联系**: 开发负责人

---

## ⚖️  免责声明

- 本框架仅供学习和研究使用
- 不构成投资建议
- 实盘交易风险自负
- 请充分测试后再使用

---

## 📄 许可证

[添加许可证信息]

---

**最后更新**: 2025-12-05  
**维护者**: Development Team

🚀 **框架正在积极开发中，欢迎反馈和建议！**

