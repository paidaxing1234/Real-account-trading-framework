# 如何查看K线数据

本文档介绍了多种查看Redis中K线数据的方法。

## 方法1: 使用 view_klines.py 脚本（推荐）

这是最方便的方法，提供了格式化的输出和多种查看选项。

### 1.1 列出所有币种

```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/server
python3 view_klines.py list
```

**输出示例：**
```
================================================================================
Redis中的K线数据概览
================================================================================

共有 648 个币种:

  BTC-USDT-SWAP        周期: 15m, 1m, 1s, 5m
  ETH-USDT-SWAP        周期: 1m, 1s, 5m
  SOL-USDT-SWAP        周期: 15m, 1m, 1s, 5m
  ...
```

### 1.2 查看最新的N根K线

```bash
# 查看最新10根K线（默认）
python3 view_klines.py BTC-USDT-SWAP 1m

# 查看最新20根K线
python3 view_klines.py BTC-USDT-SWAP 1m 20

# 查看最新5根5分钟K线
python3 view_klines.py ETH-USDT-SWAP 5m 5
```

**输出示例：**
```
================================================================================
币种: BTC-USDT-SWAP | 周期: 1m | 最新 5 根K线
================================================================================

时间                   开盘           最高           最低           收盘           成交量
-----------------------------------------------------------------------------------------------
2026-01-18 08:12:00  95002.50     95002.50     95002.40     95002.50     206.51
2026-01-18 08:13:00  95002.40     95002.50     95002.40     95002.50     549.44
2026-01-18 08:14:00  95002.50     95008.90     95002.40     95008.80     494.63
2026-01-18 08:15:00  95008.80     95008.90     95002.00     95002.50     550.89
2026-01-18 08:16:00  95002.50     95002.50     94995.60     94995.60     463.60
```

### 1.3 查看最新K线的详细信息

```bash
python3 view_klines.py BTC-USDT-SWAP 1m detail
```

**输出示例：**
```
============================================================
K线详细信息: BTC-USDT-SWAP 1m
============================================================

  类型:         kline
  交易所:       okx
  币种:         BTC-USDT-SWAP
  周期:         1m
  时间戳:       1768724160000 (2026-01-18 08:16:00)
  纳秒时间戳:   1768724221111717566

  OHLCV:
    开盘价 (O): 95002.50
    最高价 (H): 95002.50
    最低价 (L): 94995.60
    收盘价 (C): 94995.60
    成交量 (V): 463.60

  涨跌幅:       -0.01%
```

### 1.4 验证聚合K线逻辑

```bash
python3 view_klines.py BTC-USDT-SWAP compare
```

**输出示例：**
```
================================================================================
聚合验证: BTC-USDT-SWAP 15m K线 vs 3根 5m K线
================================================================================

15分钟聚合K线:
  时间: 2026-01-18 08:00:00
  O=94990.30, H=95021.80, L=94979.10, C=95008.80, V=9888.06

对应的3根5分钟K线:
  K1 [2026-01-18 08:00:00]: O=94990.30, H=95017.90, L=94979.10, C=94985.60, V=3973.59
  K2 [2026-01-18 08:05:00]: O=94985.60, H=95010.70, L=94981.60, C=95010.60, V=3533.87
  K3 [2026-01-18 08:10:00]: O=95010.70, H=95021.80, L=95002.40, C=95008.80, V=2380.60

聚合逻辑验证:
  ✓ Open (第1根的open): 94990.30 == 94990.30
  ✓ Close (第3根的close): 95008.80 == 95008.80
  ✓ High (3根中最大的high): 95021.80 == 95021.80
  ✓ Low (3根中最小的low): 94979.10 == 94979.10
  ✓ Volume (3根volume之和): 9888.06 == 9888.06

✅ 聚合逻辑验证通过！
```

## 方法2: 使用 Redis CLI

### 2.1 查看所有K线Key

```bash
redis-cli KEYS "kline:*"
```

### 2.2 查看某个币种某个周期的K线数量

```bash
redis-cli ZCARD "kline:BTC-USDT-SWAP:1m"
```

### 2.3 查看最新的一根K线（原始JSON）

```bash
redis-cli ZRANGE "kline:BTC-USDT-SWAP:1m" -1 -1
```

### 2.4 查看最新的一根K线（格式化JSON）

```bash
redis-cli ZRANGE "kline:BTC-USDT-SWAP:1m" -1 -1 | python3 -m json.tool
```

**输出示例：**
```json
{
    "close": 95002.5,
    "exchange": "okx",
    "high": 95002.5,
    "interval": "1m",
    "low": 95002.4,
    "open": 95002.5,
    "symbol": "BTC-USDT-SWAP",
    "timestamp": 1768723920000,
    "timestamp_ns": 1768723981019903609,
    "type": "kline",
    "volume": 206.51
}
```

### 2.5 查看最新的N根K线

```bash
# 查看最新10根K线
redis-cli ZRANGE "kline:BTC-USDT-SWAP:1m" -10 -1

# 查看最新5根K线
redis-cli ZRANGE "kline:BTC-USDT-SWAP:5m" -5 -1
```

### 2.6 查看指定时间范围的K线

```bash
# 查看时间戳在 1768720000000 到 1768723600000 之间的K线
redis-cli ZRANGEBYSCORE "kline:BTC-USDT-SWAP:1m" 1768720000000 1768723600000
```

## 方法3: 使用 Python 脚本

### 3.1 简单查询

```python
import redis
import json

# 连接Redis
r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=False)

# 获取最新10根K线
klines_raw = r.zrange("kline:BTC-USDT-SWAP:1m", -10, -1)

# 解析并打印
for kline_raw in klines_raw:
    kline = json.loads(kline_raw)
    print(f"{kline['timestamp']}: O={kline['open']}, H={kline['high']}, "
          f"L={kline['low']}, C={kline['close']}, V={kline['volume']}")
```

### 3.2 查询指定时间范围

```python
import redis
import json
from datetime import datetime

r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=False)

# 时间范围（毫秒时间戳）
start_ts = int(datetime(2026, 1, 18, 8, 0, 0).timestamp() * 1000)
end_ts = int(datetime(2026, 1, 18, 9, 0, 0).timestamp() * 1000)

# 查询
klines_raw = r.zrangebyscore("kline:BTC-USDT-SWAP:1m", start_ts, end_ts)

print(f"找到 {len(klines_raw)} 根K线")
for kline_raw in klines_raw:
    kline = json.loads(kline_raw)
    dt = datetime.fromtimestamp(kline['timestamp'] / 1000)
    print(f"{dt}: {kline['close']}")
```

## 方法4: 使用 monitor_klines.sh 实时监控

```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/server
./monitor_klines.sh
```

这个脚本会每5秒刷新一次，显示：
- 原始K线数量（1s, 1m, 5m, 1H）
- 聚合K线数量（15m, 30m, 4H, 1D）
- 聚合进度（例如：15m需要3根5m，当前有2根）

**输出示例：**
```
╔════════════════════════════════════════════════════════════╗
║        K线数据实时监控 - BTC-USDT-SWAP
╚════════════════════════════════════════════════════════════╝

Sat Jan 18 08:16:45 UTC 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
原始K线（从交易所获取）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1s  :    256 根
  1m  :      5 根
  5m  :      2 根
  1H  :      0 根

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━���━━━━━━━━━━━━━
聚合K线（本地计算）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  15m:      1 根 ✓
  30m:      0 根 (等待中...)
  4H :      0 根 (等待中...)
  1D :      0 根 (等待中...)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
聚合进度
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  15m: ✓ 已生成 1 根
  30m: 2/6 根5m K线 (还需 4 根)
  4H:  0/4 根1H K线 (还需 4 根)
  1D:  0/24 根1H K线 (还需 24 根)

按 Ctrl+C 停止监控
```

## K线数据结构说明

每根K线包含以下字段：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| type | string | 数据类型，固定为"kline" | "kline" |
| exchange | string | 交易所名称 | "okx", "binance" |
| symbol | string | 交易对符号 | "BTC-USDT-SWAP" |
| interval | string | K线周期 | "1s", "1m", "5m", "15m", "1H", "4H", "1D" |
| timestamp | int64 | 毫秒时间戳（K线开始时间） | 1768723920000 |
| timestamp_ns | int64 | 纳秒时间戳（精确时间） | 1768723981019903609 |
| open | double | 开盘价 | 95002.5 |
| high | double | 最高价 | 95002.5 |
| low | double | 最低价 | 95002.4 |
| close | double | 收盘价 | 95002.5 |
| volume | double | 成交量 | 206.51 |

## 常用查询示例

### 查看BTC 1分钟K线的最新20根

```bash
python3 view_klines.py BTC-USDT-SWAP 1m 20
```

### 查看ETH 5分钟K线的详细信息

```bash
python3 view_klines.py ETH-USDT-SWAP 5m detail
```

### 查看SOL的15分钟聚合K线

```bash
python3 view_klines.py SOL-USDT-SWAP 15m 10
```

### 验证DOGE的聚合逻辑

```bash
python3 view_klines.py DOGE-USDT-SWAP compare
```

### 查看所有有数据的币种

```bash
python3 view_klines.py list
```

## 时间戳转换

### 毫秒时间戳 → 可读时间

```python
from datetime import datetime

timestamp_ms = 1768723920000
dt = datetime.fromtimestamp(timestamp_ms / 1000)
print(dt.strftime('%Y-%m-%d %H:%M:%S'))
# 输出: 2026-01-18 08:12:00
```

### 可读时间 → 毫秒时间戳

```python
from datetime import datetime

dt = datetime(2026, 1, 18, 8, 12, 0)
timestamp_ms = int(dt.timestamp() * 1000)
print(timestamp_ms)
# 输出: 1768723920000
```

## 聚合K线说明

data_recorder 会自动将小周期K线聚合成大周期K线：

| 聚合周期 | 基础周期 | 聚合倍数 | 等待时间 |
|----------|----------|----------|----------|
| 15m | 5m | 3 | 至少15分钟 |
| 30m | 5m | 6 | 至少30分钟 |
| 4H | 1H | 4 | 至少4小时 |
| 1D | 1H | 24 | 至少24小时 |

**聚合规则：**
- Open: 第一根基础K线的开盘价
- High: 所有基础K线中的最高价
- Low: 所有基础K线中的最低价
- Close: 最后一根基础K线的收盘价
- Volume: 所有基础K线的成交量之和

## 故障排查

### 问题1: 没有K线数据

```bash
# 检查Redis是否运行
redis-cli ping

# 检查data_recorder是否运行
ps aux | grep data_recorder

# 检查实盘服务器是否运行
ps aux | grep trading_server_full
```

### 问题2: 没有聚合K线

**原因：** 需要等待足够的时间积累基础K线

**解决：**
- 15m K线：至少等待15分钟
- 30m K线：至少等待30分钟
- 4H K线：至少等待4小时
- 1D K线：至少等待24小时

### 问题3: Python脚本报错

```bash
# 安装redis模块
pip3 install redis
```

## 总结

推荐使用顺序：
1. **快速查看** → `python3 view_klines.py <symbol> <interval>`
2. **详细信息** → `python3 view_klines.py <symbol> <interval> detail`
3. **验证聚合** → `python3 view_klines.py <symbol> compare`
4. **实时监控** → `./monitor_klines.sh`
5. **原始数据** → `redis-cli ZRANGE "kline:..." -1 -1 | python3 -m json.tool`

所有工具都位于：
```
/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/server/
```
