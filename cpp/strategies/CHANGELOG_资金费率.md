# 资金费率行情数据实现说明

> 更新日期: 2025-12-17

## 已实现功能

### 1. WebSocket API 支持

✅ **资金费率频道：**
- 频道名称：`funding-rate`
- 推送频率：30秒到90秒内推送一次数据
- 适用产品：永续合约（SWAP）

### 2. 实盘服务器集成

✅ **trading_server_full.cpp 更新：**
- 添加资金费率统计计数 `g_funding_rate_count`
- 添加资金费率订阅管理 `g_subscribed_funding_rates`
- 在 `setup_websocket_callbacks()` 中添加资金费率回调处理
- 在 `handle_subscription()` 中添加资金费率订阅管理
- 发布资金费率数据到 ZeroMQ
- 更新状态打印，显示资金费率统计

### 3. 策略端客户端库

✅ **strategy_client.py 更新：**
- 添加 `subscribe_funding_rate()` 方法
- 添加 `unsubscribe_funding_rate()` 方法
- 添加 `recv_funding_rate()` 方法
- 添加 `on_funding_rate()` 回调支持
- 添加 `funding_rate_count` 统计属性
- 在 `recv_market()` 中添加资金费率计数
- 在 `run_strategy()` 中添加资金费率处理

## 使用方法

### 订阅资金费率

```python
from strategy_client import StrategyClient, BaseStrategy

client = StrategyClient("my_strategy")
client.connect()

# 订阅永续合约资金费率
client.subscribe_funding_rate("BTC-USDT-SWAP")
client.subscribe_funding_rate("ETH-USDT-SWAP")
```

### 接收资金费率数据

```python
# 方式1: 使用 BaseStrategy（推荐）
class MyStrategy(BaseStrategy):
    def on_funding_rate(self, funding_rate: dict):
        symbol = funding_rate["symbol"]
        rate = funding_rate["funding_rate"]
        next_rate = funding_rate["next_funding_rate"]
        funding_time = funding_rate["funding_time"]
        
        print(f"资金费率: {symbol}")
        print(f"  当前费率: {rate}")
        print(f"  下一期费率: {next_rate}")
        print(f"  资金费时间: {funding_time}")

# 方式2: 手动接收
funding_rate = client.recv_funding_rate()
if funding_rate:
    rate = funding_rate["funding_rate"]
    print(f"当前资金费率: {rate}")
```

## 资金费率数据格式

```python
{
    "type": "funding_rate",
    "symbol": "BTC-USDT-SWAP",
    "inst_type": "SWAP",
    "funding_rate": 0.0001,              # 当前资金费率
    "next_funding_rate": 0.0002,           # 下一期预测资金费率
    "funding_time": 1702000000000,        # 资金费时间（毫秒）
    "next_funding_time": 1702008000000,   # 下一期资金费时间（毫秒）
    "min_funding_rate": -0.00375,         # 资金费率下限
    "max_funding_rate": 0.00375,          # 资金费率上限
    "interest_rate": 0.0001,               # 利率
    "impact_value": 1000000.0,            # 深度加权金额
    "premium": 0.00005,                    # 溢价指数
    "sett_state": "settled",               # 结算状态：processing/settled
    "sett_funding_rate": 0.0001,          # 结算资金费率
    "method": "current_period",            # 资金费收取逻辑：current_period/next_period
    "formula_type": "withRate",            # 公式类型：noRate/withRate
    "timestamp": 1702000000000,            # 数据更新时间（毫秒）
    "timestamp_ns": 1702000000000000000    # 纳秒时间戳
}
```

## 完整示例

```python
#!/usr/bin/env python3
"""
资金费率监控策略示例
"""

from strategy_client import BaseStrategy, run_strategy

class FundingRateMonitorStrategy(BaseStrategy):
    """资金费率监控策略"""
    
    def __init__(self):
        super().__init__(strategy_id="funding_rate_monitor")
        self.symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
    
    def on_start(self):
        self.log("资金费率监控策略启动")
        
        # 订阅多个合约的资金费率
        for symbol in self.symbols:
            self.client.subscribe_funding_rate(symbol)
            self.log(f"已订阅资金费率: {symbol}")
    
    def on_funding_rate(self, funding_rate: dict):
        """处理资金费率数据"""
        symbol = funding_rate["symbol"]
        rate = funding_rate["funding_rate"]
        next_rate = funding_rate["next_funding_rate"]
        
        # 计算年化费率（假设每8小时收取一次）
        annual_rate = rate * 3 * 365  # 每天3次，一年365天
        
        self.log(f"[资金费率] {symbol}")
        self.log(f"  当前费率: {rate:.6f} ({annual_rate*100:.2f}% 年化)")
        self.log(f"  下一期费率: {next_rate:.6f}")
        
        # 如果费率过高，发出警告
        if abs(rate) > 0.01:  # 1%
            self.log(f"  ⚠️ 警告：资金费率异常高！")
        
        # 统计
        if self.client.funding_rate_count % 10 == 0:
            self.log(f"  已接收 {self.client.funding_rate_count} 条资金费率数据")

if __name__ == "__main__":
    run_strategy(FundingRateMonitorStrategy())
```

## 注意事项

1. **适用产品：**
   - 资金费率仅适用于永续合约（SWAP）
   - 现货和交割合约没有资金费率

2. **推送频率：**
   - 30秒到90秒内推送一次数据
   - 不是固定频率，取决于市场变化

3. **费率计算：**
   - 资金费率通常以小数形式表示（如 0.0001 = 0.01%）
   - 年化费率 = 费率 × 3 × 365（假设每8小时收取一次）

4. **费率方向：**
   - 正费率：多头支付空头
   - 负费率：空头支付多头

5. **订阅限制：**
   - 可以同时订阅多个合约的资金费率
   - 建议订阅自己正在交易的合约

## 测试

运行资金费率监控示例：

```bash
# 启动实盘服务器
./trading_server_full

# 运行策略（需要创建示例文件）
python3 funding_rate_monitor.py
```

## 相关文件

- `trading_server_full.cpp` - 实盘服务器（已更新）
- `strategy_client.py` - 策略客户端库（已更新）
- `okx_websocket.h/cpp` - WebSocket API（已支持）

