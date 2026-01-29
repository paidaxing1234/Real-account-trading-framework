# 策略日志功能说明

## 功能概述

策略运行时会自动将所有终端输出（包括 print 和日志）保存到日志文件中。日志文件会持久保存，策略重启后会继续追加写入，不会丢失历史记录。

## 日志文件命名规则

日志文件名格式：`<交易所>_<策略ID>.txt`

**示例：**
- Grid策略（OKX）：`okx_grid_btc_main.txt`
- GNN策略（Binance）：`binance_gnn_strategy.txt`
- 多账户Grid策略：`okx_grid_btc_account1.txt`, `okx_grid_btc_account2.txt`

## 日志文件位置

所有日志文件保存在：
```
/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies/log/
```

## 使用方法

### 1. 运行策略（自动记录日志）

**Grid策略：**
```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies
python3 grid_strategy_cpp.py --config configs/grid_btc_main.json
```

**GNN策略：**
```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies/GNN_model/trading
python3 GNNstr/gnn_strategy_config.py --config ../../configs/gnn_multi_coin.json
```

策略启动后会自动：
1. 创建日志文件（如果不存在）
2. 在日志文件中写入启动时间和分隔符
3. 将所有终端输出同时保存到日志文件
4. 策略停止时写入停止时间

### 2. 查看日志

**方法1：使用日志查看器（推荐）**
```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies
./view_strategy_logs.sh
```

功能：
- 列出所有日志文件（显示大小、行数、修改时间）
- 查看最近100/500行
- 实时跟踪日志（tail -f）
- 查看全部日志
- 搜索关键词

**方法2：直接使用命令行**
```bash
# 查看最近100行
tail -100 log/okx_grid_btc_main.txt

# 实时跟踪
tail -f log/okx_grid_btc_main.txt

# 搜索关键词
grep "成交" log/okx_grid_btc_main.txt

# 查看全部
cat log/okx_grid_btc_main.txt
```

## 日志格式

每条日志包含时间戳：
```
[2026-01-28 04:30:15.123] [INFO] 策略启动
[2026-01-28 04:30:16.456] [INFO] ✓ 账户注册成功
[2026-01-28 04:30:17.789] [INFO] [成交] okx|BTC-USDT-SWAP buy 0.01 @ 89000.00
```

## 日志文件结构

```
================================================================================
策略启动时间: 2026-01-28 04:30:15 | 交易所: okx | 策略ID: grid_btc_main
================================================================================
[2026-01-28 04:30:15.123] [INFO] 策略参数: BTC-USDT-SWAP | 网格:20x2 | 间距:0.100% | 金额:100U
[2026-01-28 04:30:16.456] [INFO] ✓ 账户注册成功
...
[2026-01-28 05:00:00.789] [INFO] 收到停止信号...
================================================================================
策略停止时间: 2026-01-28 05:00:01
================================================================================

================================================================================
策略启动时间: 2026-01-28 06:00:00 | 交易所: okx | 策略ID: grid_btc_main
================================================================================
[2026-01-28 06:00:00.123] [INFO] 策略重新启动
...
```

## 多账户运行

如果同一个策略在多个账户上运行，**必须使用不同的 strategy_id**：

**账户1配置（config_account1.json）：**
```json
{
  "strategy_id": "grid_btc_account1",
  "api_key": "account1_key",
  ...
}
```

**账户2配置（config_account2.json）：**
```json
{
  "strategy_id": "grid_btc_account2",
  "api_key": "account2_key",
  ...
}
```

这样会生成两个独立的日志文件：
- `okx_grid_btc_account1.txt`
- `okx_grid_btc_account2.txt`

## 日志管理

### 清理旧日志
```bash
# 删除所有日志
rm log/*.txt

# 删除特定策略的日志
rm log/okx_grid_btc_main.txt

# 备份日志
cp -r log log_backup_$(date +%Y%m%d)
```

### 日志大小管理

日志文件会持续增长，建议定期备份和清理：

```bash
# 查看日志文件大小
du -h log/*.txt

# 压缩旧日志
gzip log/okx_grid_btc_main.txt

# 只保留最近N行
tail -10000 log/okx_grid_btc_main.txt > log/okx_grid_btc_main_recent.txt
mv log/okx_grid_btc_main_recent.txt log/okx_grid_btc_main.txt
```

## 故障排查

### 问题1：日志文件没有创建

**原因：** 日志目录不存在或没有写入权限

**解决：**
```bash
mkdir -p /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies/log
chmod 755 /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies/log
```

### 问题2：日志没有实时更新

**原因：** Python输出缓冲

**解决：** 日志工具已经设置了 `buffering=1`（行缓冲），每行都会立即写入文件。

### 问题3：日志文件过大

**解决：** 定期清理或使用日志轮转工具（logrotate）

## 技术实现

日志功能通过 `strategy_logger.py` 实现：

1. **StrategyLogger类**：管理日志文件的打开、写入、关闭
2. **TeeOutput类**：重定向 stdout/stderr，同时输出到终端和文件
3. **setup_strategy_logging()函数**：初始化日志系统

所有策略的 print() 输出都会自动记录到日志文件中。

## 示例输出

```bash
$ python3 grid_strategy_cpp.py --config configs/grid_btc_main.json
✓ 日志文件: /home/xyc/.../log/okx_grid_btc_main.txt

╔══════════════════════════════════════════════════╗
║  网格策略 (模块化 C++ 基类版)                      ║
╚══════════════════════════════════════════════════╝

策略配置:
  策略ID:     grid_btc_main
  交易对:     BTC-USDT-SWAP
  网格数量:   20
  网格间距:   0.100%
  下单金额:   100 USDT
  交易环境:   测试网
...
```

所有这些输出都会同时保存到日志文件中。
