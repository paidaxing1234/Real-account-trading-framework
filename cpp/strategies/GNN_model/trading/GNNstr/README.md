# GNN交易策略

基于图神经网络(GNN)的量化交易策略，使用C++策略基类框架。

## 文件说明

| 文件 | 说明 |
|------|------|
| `gnn_strategy.py` | **生产版本** - 每2周执行一次（UTC 00:00） |
| `gnn_strategy_test.py` | **测试版本** - 每10分钟执行一次 |

## 策略逻辑

1. **启动时**：通过OKX REST API获取全币种历史K线数据（1200条1分钟K线）
2. **定时执行**：
   - 刷新历史数据
   - 调用GNN模型计算目标仓位
   - 根据权重调整实际仓位
3. **仓位分配**：
   - 多头：预测排名前5%的币种，权重+0.5/k
   - 空头：预测排名后5%的币种，权重-0.5/k
   - 总权重绝对值之和 = 1.0

## 历史数据获取

由于等待实时推送获取1200条数据需要20小时，策略采用**OKX REST API**直接获取历史K线：

```python
# OKX历史K线接口
GET /api/v5/market/history-candles
参数: instId, bar="1m", limit=300
```

- 每次最多返回300条，需要分页请求
- 使用线程池并行获取253个币种
- 获取时间约2-3分钟

## 运行方式

### 1. 编译策略基类模块

```bash
cd Real-account-trading-framework/cpp/build
cmake ..
make strategy_base
```

### 2. 设置环境

确保以下文件存在：
- `../currency_pool_okx.txt` - 币种池
- `../model/diffgnn_*.pth` - GNN模型文件

### 3. 运行策略

**测试版本**（推荐先测试）：
```bash
cd GNN_model/trading/GNNstr
python gnn_strategy_test.py
```

**生产版本**：
```bash
python gnn_strategy.py
```

## 配置说明

### 生产版本配置
```python
HISTORY_BARS = 1200          # 历史K线数量
N_LAYERS = 20                # 分层数量（TOP_PCT = 5%）
POSITION_SIZE_USDT = 10000   # 仓位金额
SCHEDULE_INTERVAL = "14d"    # 每2周执行
```

### 测试版本配置
```python
HISTORY_BARS = 1200          # 历史K线数量
N_LAYERS = 20                # 分层数量
POSITION_SIZE_USDT = 100     # 小仓位测试
SCHEDULE_INTERVAL = "10m"    # 每10分钟执行
dry_run = False              # 设为True则只打印不下单
```

## API密钥配置

修改策略文件中的以下变量：
```python
self.api_key = "your-api-key"
self.secret_key = "your-secret-key"
self.passphrase = "your-passphrase"
self.is_testnet = True  # True=模拟盘, False=实盘
```

## 注意事项

1. **先用模拟盘测试**：设置 `is_testnet = True`
2. **测试版本Dry Run**：设置 `dry_run = True` 只打印不下单
3. **历史数据延迟**：首次获取数据需要2-3分钟
4. **合约规格**：代码假设每张合约=0.01个币，请根据实际情况调整
5. **网络要求**：需要能访问OKX API（如果在国内，可能需要代理）

## 输出示例

```
============================================================
       GNN策略 - 测试版本
============================================================

⚠️  测试模式: 每 10m 执行一次
⚠️  仓位金额: 100 USDT (小仓位测试)

币种数量: 253
分层数量: 20

------------------------------------------------------------
[gnn_test] [初始化] 加载GNN模型...
[gnn_test] [初始化] GNN模型加载成功
[gnn_test] [历史数据] 开始获取 253 个币种的历史K线...
[gnn_test] [历史数据] 进度: 50/253
[gnn_test] [历史数据] 进度: 100/253
[gnn_test] [历史数据] 进度: 150/253
[gnn_test] [历史数据] 进度: 200/253
[gnn_test] [历史数据] 进度: 250/253
[gnn_test] [历史数据] 完成: 253 个币种, 303600 条数据, 耗时 120.5s
[gnn_test] [策略] 计算目标仓位...
[gnn_test] [策略] 多头仓位 (12个):
  📈 SOL-USDT-SWAP: 4.17%
  📈 ETH-USDT-SWAP: 4.17%
  ...
[gnn_test] [策略] 空头仓位 (12个):
  📉 DOGE-USDT-SWAP: -4.17%
  📉 SHIB-USDT-SWAP: -4.17%
  ...
```

