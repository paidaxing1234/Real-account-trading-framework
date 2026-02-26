# 风控管理工具使用说明

## 功能概述

`risk_control.py` 是一个通过WebSocket与trading_server通信的命令行工具，用于：
1. 查看实时风控状态
2. 解除kill switch（紧急止损）

## 前置条件

1. trading_server必须正在运行
2. WebSocket服务器监听在端口8002（默认）
3. 安装Python 3和websocket-client库：
   ```bash
   pip3 install websocket-client
   ```

## 使用方法

### 1. 查看风控状态

```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/tools
python3 risk_control.py status
```

输出示例：
```
正在查询风控状态...

============================================================
风控状态报告
============================================================
查询时间: 2026-02-24 10:30:15

🔴 Kill Switch: 已激活 (所有订单被拒绝)

挂单数量: 5
每日盈亏: -8500.00 USDT
总敞口: 45000.00 USDT
持仓品种数: 2

策略统计:
  - ret_skew_okx_btc_main:
      当日峰值: 100000.00 USDT
      当日初值: 95000.00 USDT
============================================================
```

### 2. 解除kill switch（交互式）

```bash
python3 risk_control.py deactivate
```

会先显示当前状态，然后询问确认：
```
确认要解除kill switch吗? (yes/no): yes
正在解除kill switch...
✅ Kill switch已解除，交易已恢复
```

### 3. 自动解除（无需确认）

```bash
python3 risk_control.py auto
```

如果kill switch已激活，会自动解除；如果未激活，则不做任何操作。

### 4. 指定服务器地址

```bash
# 连接到远程服务器
python3 risk_control.py status --host 192.168.1.100 --port 8002
```

## Kill Switch 触发条件

Kill switch会在以下情况自动触发：

1. **最大回撤超限**
   - 当前配置：10%（`max_drawdown_pct: 0.1`）
   - 回撤模式：`daily_peak`（相对于当日峰值）
   - 每天自动重置峰值

2. **手动激活**
   - 通过代码调用 `activate_kill_switch()`

## Kill Switch 影响

触发后：
- ❌ 所有新订单被拒绝
- 📞 发送CRITICAL级别告警（电话+短信+邮件+钉钉）
- 📧 发送邮件到策略负责人邮箱
- ⚠️ 策略无法继续交易

## 解除方式对比

| 方式 | 操作 | 影响范围 | 恢复时间 | 适用场景 |
|------|------|---------|---------|---------|
| 方式1 | 重启trading_server | 断开所有连接、清空缓存 | 30-60秒 | 需要完全重置 |
| 方式2 | 使用risk_control.py | 仅解除kill switch | <1秒 | 快速恢复交易 |

## 常见问题

### Q1: 连接失败怎么办？

```
❌ 连接失败: [Errno 111] Connection refused
```

**解决方法**：
1. 确认trading_server正在运行：`ps aux | grep trading_server`
2. 确认WebSocket端口8002已开启：`netstat -tlnp | grep 8002`
3. 检查防火墙设置

### Q2: Kill switch解除后又立即触发？

**原因**：账户权益仍然低于触发阈值

**解决方法**：
1. 检查当前账户权益和回撤情况
2. 考虑调整风控配置：
   - 提高 `max_drawdown_pct`（如改为0.15 = 15%）
   - 或切换到 `daily_initial` 模式

### Q3: 如何修改风控配置？

编辑配置文件：
```bash
vim /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/risk_config.json
```

修改后需要重启trading_server才能生效。

## 技术细节

### WebSocket通信协议

**查询风控状态**：
```json
{
    "type": "command",
    "action": "get_risk_status",
    "data": {}
}
```

**解除kill switch**：
```json
{
    "type": "command",
    "action": "deactivate_kill_switch",
    "data": {}
}
```

### 响应格式

```json
{
    "success": true,
    "type": "risk_status",
    "data": {
        "kill_switch": true,
        "open_orders": 5,
        "daily_pnl": -8500.0,
        "strategy_stats": {...},
        "total_exposure": 45000.0,
        "position_count": 2
    }
}
```

## 安全建议

1. **谨慎解除kill switch**：确认风险已经控制后再解除
2. **定期检查风控状态**：可以设置定时任务监控
3. **保留告警记录**：所有kill switch触发都会发送告警，注意查收
4. **合理设置阈值**：根据策略特点调整回撤阈值

## 相关文件

- 风控配置：`/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/risk_config.json`
- 风控管理器：`/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/trading/risk_manager.h`
- 前端命令处理：`/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/server/handlers/frontend_command_handler.cpp`
