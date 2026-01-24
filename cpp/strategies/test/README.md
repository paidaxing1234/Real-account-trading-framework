# 策略配置系统测试

本目录包含策略配置系统的测试脚本。

## 测试模式

### 1. MOCK 模式（推荐）

纯逻辑测试，不连接真实交易所，使用模拟API密钥。

**特点**:
- ✅ 最安全，不会产生任何真实交易
- ✅ 无需API密钥
- ✅ 测试速度快
- ✅ 适合开发和CI/CD

**运行方式**:
```bash
python3 test_strategy_config.py --mode mock
```

### 2. TESTNET 模式

连接到OKX测试网，使用虚拟资金进行测试。

**特点**:
- ✅ 使用虚拟资金，无真实资金风险
- ✅ 测试真实的API连接和交易流程
- ⚠️ 需要OKX测试网API密钥
- ⚠️ 需要网络连接

**运行方式**:

方式1：交互式运行（推荐）
```bash
python3 run_testnet_test.py
```

方式2：直接运行（需要先设置环境变量）
```bash
export OKX_TESTNET_API_KEY='your_api_key'
export OKX_TESTNET_SECRET_KEY='your_secret_key'
export OKX_TESTNET_PASSPHRASE='your_passphrase'
python3 test_strategy_config.py --mode testnet
```

**详细指南**: 查看 [TESTNET_GUIDE.md](TESTNET_GUIDE.md)

### 3. LIVE_SMALL 模式（谨慎使用）

使用真实账户进行小额测试。

**特点**:
- ⚠️ 使用真实资金
- ⚠️ 使用最小下单量
- ⚠️ 需要真实API密钥
- ⚠️ 需要人工确认

**运行方式**:
```bash
python3 test_strategy_config.py --mode live_small
```

**注意**: 此模式暂未实现，请先使用TESTNET模式。

### 4. LIVE 模式（危险）

使用真实账户进行正式测试。

**特点**:
- 🚫 使用真实资金
- 🚫 可能产生较大损失
- 🚫 仅用于生产环境验证

**注意**: 此模式暂未实现，不建议使用。

## 测试脚本

### test_strategy_config.py

完整的集成测试脚本，测试所有功能。

**测试内容**:
1. 配置文件加载
2. 账户注册验证
3. 策略配置查询（风控端接口）
4. 策略隔离性验证

**运行时间**: 约30-60秒

### test_config_quick.py

快速配置验证脚本，仅验证配置文件格式。

**测试内容**:
1. JSON格式验证
2. 必填字段检查
3. 联系人信息验证

**运行时间**: 约1秒

**运行方式**:
```bash
python3 test_config_quick.py
```

### test_simple.py

简化的测试脚本，用于调试和快速验证。

**运行方式**:
```bash
python3 test_simple.py
```

### run_testnet_test.py

测试网测试的交互式启动脚本。

**运行方式**:
```bash
python3 run_testnet_test.py
```

### test_account_consistency.py

**账户一致性验证测试**（测试网专用）

这是一个专门用于验证策略账户一致性的测试脚本，确保每个策略使用正确的账户进行所有操作。

**测试内容**:
1. ✅ 账户注册验证 - 验证所有策略账户已正确注册
2. ✅ 余额查询一致性 - 验证每个策略查询到正确的账户余额
3. ✅ 订单账户一致性 - 验证订单使用正确的策略账户
4. ✅ 策略隔离性 - 验证不同策略之间的账户隔离

**特点**:
- ✅ 使用现有配置文件（不创建临时配置）
- ✅ 在测试网上发送真实API请求
- ✅ 使用极小数量的测试订单（不会成交）
- ✅ 自动加载所有启用的测试网策略
- ⚠️ 需要配置有效的测试网API密钥

**前置条件**:
1. 至少配置一个启用的测试网策略（`enabled: true`, `is_testnet: true`）
2. 配置有效的测试网API密钥（多个策略可共享同一个密钥）
3. 编译好服务器: `cd ../../build && cmake .. && make`
4. 安装依赖: `pip3 install pyzmq`

**运行方式**:
```bash
python3 test_account_consistency.py
```

**测试流程**:
1. 确认提示（输入 `y` 继续）
2. 自动加载所有启用的测试网策略
3. 启动服务器并等待就绪（最多30秒）
4. 依次运行4个测试
5. 显示测试结果
6. 自动停止服务器

**测试详解**:

**测试1：账户注册验证**
- 查询服务器已注册的账户总数
- 验证每个策略是否已注册
- 检查策略配置信息（交易所、API密钥前缀）

**测试2：账户余额查询一致性**
- 对每个策略发送余额查询请求
- 验证返回的余额数据
- 检查账户ID是否与策略匹配

**测试3：订单账户一致性**
- 发送测试订单（价格1.0 USDT，数量0.001，不会成交）
- 接收订单回报
- 验证回报中的策略ID与发送订单的策略ID一致
- 注意：订单被拒绝是正常的，重点是验证路由正确

**测试4：策略账户隔离性**
- 策略A尝试查询策略B的配置信息
- 验证敏感信息（API密钥）是否被脱敏

**查看日志**:
```bash
tail -100 ../../build/account_consistency_test.log
```

**常见问题**:
- **没有找到启用的测试网策略**: 检查配置文件中 `enabled: true` 和 `is_testnet: true`
- **服务器启动超时**: 检查服务器是否已编译，清理IPC文件 `rm -f /tmp/seq_*.ipc`
- **订单被拒绝**: 这是正常的，测试订单使用极低价格，只要策略ID正确就算通过
- **多个策略可以共享API密钥吗**: 可以，测试网环境下推荐共享密钥简化配置

**运行时间**: 约30-60秒

## 测试结果

所有测试通过后会显示：

```
============================================================
  测试结果
============================================================
通过: 15
失败: 0

✓ 所有测试通过
```

## 故障排查

### 服务器启动超时

**症状**: 测试卡在"等待服务器就绪"

**解决方案**:
1. 检查服务器是否已编译: `ls -lh ../../build/trading_server_full`
2. 检查Redis是否运行: `redis-cli ping`
3. 查看服务器日志: `tail -100 ../../build/test_server.log`

### IPC地址占用

**症状**: 服务器启动失败，提示"Address already in use"

**解决方案**:
```bash
rm -f /tmp/seq_*.ipc /tmp/trading_*.ipc
```

### API密钥错误

**症状**: 测试网模式提示"API密钥未设置"

**解决方案**:
查看 [TESTNET_GUIDE.md](TESTNET_GUIDE.md) 了解如何设置API密钥。

## 文件说明

```
test/
├── README.md                              # 本文件
├── TESTNET_GUIDE.md                      # 测试网测试详细指南
├── ACCOUNT_CONSISTENCY_TEST_GUIDE.md     # 账户一致性测试指南
├── test_strategy_config.py               # 完整集成测试
├── test_account_consistency.py           # 账户一致性验证测试（测试网）
├── test_config_quick.py                  # 快速配置验证
├── test_simple.py                        # 简化测试脚本
└── run_testnet_test.py                   # 测试网交互式启动脚本
```

## 推荐测试流程

1. **开发阶段**: 使用 `test_config_quick.py` 快速验证配置格式
2. **功能测试**: 使用 `test_strategy_config.py --mode mock` 测试完整功能
3. **集成测试**: 使用 `test_strategy_config.py --mode existing` 测试现有配置
4. **测试网验证**: 使用 `run_testnet_test.py` 在测试网验证基本功能
5. **账户一致性验证**: 使用 `test_account_consistency.py` 验证账户路由正确性
6. **生产部署**: 手动验证配置文件，逐步启动策略

## 相关文档

- [策略配置使用说明](../configs/README.md)
- [策略映射文档](../STRATEGY_MAPPING.md)
- [测试报告](../TEST_REPORT.md)
- [测试网指南](TESTNET_GUIDE.md)

## 联系支持

如有问题，请联系：
- 技术支持: tech@example.com
- 测试团队: test@example.com
