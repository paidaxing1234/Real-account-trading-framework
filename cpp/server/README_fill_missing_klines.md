# K线数据补全工具使用说明

## 功能介绍

`fill_missing_klines.py` 是一个自动补全Binance和OKX合约缺失K线数据的工具。

### 主要功能

1. **自动扫描**：扫描Redis中所有的K线数据键
2. **缺失检测**：检测每个合约在指定时间范围内的缺失时间点
3. **数据补全**：从交易所REST API获取缺失的K线数据并写入Redis
4. **详细报告**：生成补全统计报告

## 使用方法

### 基本用法

```bash
# 检测所有合约的缺失情况（不补全）
python3 fill_missing_klines.py --dry-run

# 补全所有合约的缺失数据
python3 fill_missing_klines.py

# 只补全Binance的合约
python3 fill_missing_klines.py --exchange binance

# 只补全OKX的合约
python3 fill_missing_klines.py --exchange okx

# 只补全指定交易对
python3 fill_missing_klines.py --symbol BTCUSDT

# 检查最近30天的数据
python3 fill_missing_klines.py --days 30

# 详细输出模式
python3 fill_missing_klines.py --verbose
```

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--redis-host` | Redis主机地址 | 127.0.0.1 |
| `--redis-port` | Redis端口 | 6379 |
| `--redis-password` | Redis密码 | 无 |
| `--exchange` | 指定交易所 (binance/okx/all) | all |
| `--symbol` | 指定交易对 | 所有 |
| `--interval` | K线周期 | 1m |
| `--days` | 检查最近N天的数据 | 60 |
| `--dry-run` | 只检测不补全 | false |
| `--verbose` | 详细输出 | false |

## 使用场景

### 场景1：定期检查数据完整性

```bash
# 每天运行一次，检查最近7天的数据
python3 fill_missing_klines.py --days 7 --dry-run
```

### 场景2：补全历史数据

```bash
# 补全最近60天的所有缺失数据
python3 fill_missing_klines.py --days 60
```

### 场景3：针对性补全

```bash
# 只补全Binance BTC的缺失数据
python3 fill_missing_klines.py --exchange binance --symbol BTCUSDT
```

### 场景4：大规模补全

```bash
# 补全所有Binance合约（可能需要较长时间）
python3 fill_missing_klines.py --exchange binance --verbose
```

## 输出示例

### Dry-run模式输出

```
======================================================================
K线数据补全工具
======================================================================
Redis: 127.0.0.1:6379
检查周期: 最近 60 天
K线周期: 1m
运行模式: DRY-RUN (仅检测)

找到 150 个合约

[1/150] 处理: kline:binance:BTCUSDT:1m
检查合约: binance:BTCUSDT
  发现 4 个缺失点
  [DRY-RUN] 跳过补全

[2/150] 处理: kline:binance:ETHUSDT:1m
检查合约: binance:ETHUSDT
  ✓ 无缺失数据

...

======================================================================
补全统计
======================================================================
总合约数:       150
已检查:         150
有缺失的合约:   12
总缺失数:       245
======================================================================
```

### 补全模式输出

```
======================================================================
K线数据补全工具
======================================================================
Redis: 127.0.0.1:6379
检查周期: 最近 60 天
K线周期: 1m
运行模式: 补全模式

找到 150 个合约

[1/150] 处理: kline:binance:BTCUSDT:1m
检查合约: binance:BTCUSDT
  发现 4 个缺失点
  从API获取到 4 条缺失数据
  ✓ 成功补全 4 条，失败 0 条

...

======================================================================
补全统计
======================================================================
总合约数:       150
已检查:         150
有缺失的合约:   12
总缺失数:       245
成功补全:       243
补全失败:       2
补全成功率:     99.18%
======================================================================
```

## 注意事项

### 1. API限流

- **Binance**: 单次最多返回1500条K线，有请求频率限制
- **OKX**: 单次最多返回300条K线，有请求频率限制
- 脚本已内置限流机制（每次请求间隔0.2秒）

### 2. 时间范围

- 默认检查最近60天的数据
- 可通过 `--days` 参数调整
- 时间范围越大，运行时间越长

### 3. 网络要求

- 需要能够访问Binance和OKX的API
- 如果使用代理，请确保代理配置正确
- 网络不稳定可能导致部分数据补全失败

### 4. Redis配置

- 确保Redis服务正常运行
- 确保有足够的存储空间
- 补全的数据会自动设置60天过期时间

### 5. 运行时间

- 合约数量越多，运行时间越长
- 缺失数据越多，运行时间越长
- 建议先用 `--dry-run` 模式评估缺失情况

## 定时任务配置

可以使用cron定时运行补全任务：

```bash
# 编辑crontab
crontab -e

# 每天凌晨2点补全最近7天的数据
0 2 * * * cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/server && python3 fill_missing_klines.py --days 7 >> /tmp/fill_klines.log 2>&1
```

## 故障排查

### 问题1：Redis连接失败

```
[ERROR] Redis连接失败
```

**解决方法**：
- 检查Redis服务是否运行：`redis-cli ping`
- 检查Redis配置：`--redis-host` 和 `--redis-port`
- 检查Redis密码：`--redis-password`

### 问题2：API请求失败

```
[ERROR] Binance API错误: 429
```

**解决方法**：
- 等待一段时间后重试
- 减少并发请求（脚本已自动处理）
- 检查网络连接

### 问题3：补全失败

```
[ERROR] 写入Redis失败
```

**解决方法**：
- 检查Redis存储空间
- 检查Redis权限
- 查看详细错误日志

## 技术细节

### 数据格式

补全的K线数据格式：

```json
{
    "type": "kline",
    "exchange": "binance",
    "symbol": "BTCUSDT",
    "interval": "1m",
    "timestamp": 1769411880000,
    "open": 88198.9,
    "high": 88236.2,
    "low": 88168.6,
    "close": 88177.5,
    "volume": 2274.42
}
```

### Redis存储

- **Key格式**: `kline:{exchange}:{symbol}:{interval}`
- **数据结构**: Sorted Set (score=timestamp)
- **过期时间**: 60天

### API端点

- **Binance**: `https://fapi.binance.com/fapi/v1/klines`
- **OKX**: `https://www.okx.com/api/v5/market/candles`

## 更新日志

### v1.0 (2026-01-27)

- 初始版本
- 支持Binance和OKX
- 支持1分钟K线补全
- 支持dry-run模式
- 支持详细日志输出

## 作者

Sequence Team

## 许可证

内部使用
