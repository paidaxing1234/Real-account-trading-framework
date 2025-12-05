# OKX WebSocket 登录测试

## 快速开始

### 1. 安装依赖

```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/backend
pip install -r requirements.txt
```

### 2. 运行测试

```bash
python okx_login_test.py
```

## 预期输出

### 成功情况：
```
✅ 登录成功！
   连接ID: a4d3ae55
   状态码: 0
```

### 失败情况：
```
❌ 登录失败！
   错误码: 60009
   错误信息: Login failed.
```

## 常见错误码

| 错误码 | 说明 | 解决方案 |
|-------|------|---------|
| 60009 | 登录失败 | 检查 API Key、Secret Key、Passphrase 是否正确 |
| 50103 | API Key 不存在 | 确认 API Key 是否有效 |
| 50111 | Passphrase 错误 | 检查 Passphrase 是否正确 |
| 50113 | 签名无效 | 检查时间戳和签名算法 |

## 注意事项

1. **实盘 vs 模拟盘**：
   - 当前配置为**实盘**模式
   - 如需切换到模拟盘，修改 `is_demo=True`

2. **API 权限**：
   - 确保 API Key 已启用"交易"权限
   - 检查 IP 白名单设置

3. **时间同步**：
   - 确保本地系统时间准确
   - 时间偏差过大会导致签名失败

