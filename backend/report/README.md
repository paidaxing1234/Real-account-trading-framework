# OKX 适配器

OKX交易所的REST API和WebSocket适配器实现。

---

## 📁 文件结构

```
okx/
├── __init__.py          # 模块导出
├── rest_api.py          # REST API封装 ✅
├── websocket.py         # WebSocket连接 ⏳
├── adapter.py           # 统一适配器组件 ⏳
├── API接口文档.md        # 详细API文档
└── README.md            # 本文档
```

---

## 🚀 快速开始

### 安装依赖

```bash
pip install requests websockets
```

### 使用REST API

```python
from adapters.okx import OKXRestAPI

# 创建客户端
client = OKXRestAPI(
    api_key="your_api_key",
    secret_key="your_secret_key",
    passphrase="your_passphrase",
    is_demo=True  # 模拟盘
)

# 获取行情
ticker = client.get_ticker("BTC-USDT")

# 下单
order = client.place_order(
    inst_id="BTC-USDT",
    td_mode="cash",
    side="buy",
    ord_type="limit",
    px="93300",
    sz="0.01"
)

# 查询订单
order_info = client.get_order(
    inst_id="BTC-USDT",
    ord_id=order['data'][0]['ordId']
)

# 撤单
client.cancel_order(
    inst_id="BTC-USDT",
    ord_id=order['data'][0]['ordId']
)

# 批量下单
batch_orders = [
    {
        "instId": "BTC-USDT",
        "tdMode": "cash",
        "side": "buy",
        "ordType": "limit",
        "px": "50000",
        "sz": "0.01"
    },
    {
        "instId": "ETH-USDT",
        "tdMode": "cash",
        "side": "buy",
        "ordType": "limit",
        "px": "2000",
        "sz": "0.1"
    }
]
batch_result = client.place_batch_orders(batch_orders)

# 修改订单
amend_result = client.amend_order(
    inst_id="BTC-USDT",
    ord_id=order['data'][0]['ordId'],
    new_px="50100"  # 修改价格
)
```

---

## 📋 已实现接口

### 交易接口（9个）
- ✅ `place_order()` - 下单（已测试）
- ✅ `place_batch_orders()` - 批量下单（已实现，最多20个）
- ✅ `cancel_order()` - 撤单（已测试）
- ✅ `cancel_batch_orders()` - 批量撤单（已实现，最多20个）
- ✅ `amend_order()` - 修改订单（已测试）
- ✅ `amend_batch_orders()` - 批量修改订单（已实现，最多20个）
- ✅ `get_order()` - 查询订单详情（已测试）
- ✅ `get_orders_pending()` - 查询未成交订单（已完善，支持更多参数）
- ✅ `get_orders_history()` - 查询历史订单（近7天，已测试）

### 账户接口（6个）
- ✅ `get_balance()` - 查询余额（已测试）
- ✅ `get_positions()` - 查询持仓（已完善，新增posId参数）
- ✅ `get_positions_history()` - 查询历史持仓（近3个月，已测试）
- ✅ `get_account_instruments()` - 获取账户可交易产品信息（已测试）
- ✅ `get_bills()` - 账单流水查询（近7天，已测试）
- ✅ `get_bills_archive()` - 账单流水查询（近3个月，已测试）

### 行情接口（2个）
- ✅ `get_ticker()` - 获取行情（已测试）
- ✅ `get_instruments()` - 获取产品信息（公共，已测试）

**总计**: 17个接口，核心功能已完成 ✅

详细文档：
- [API接口文档.md](./API接口文档.md) - 完整API参考
- [测试报告.md](./测试报告.md) - 测试结果汇总

---

## 🧪 测试

```bash
# 测试完整下单流程
python test_okx_place_order.py

# 测试补充接口（未成交订单、持仓、产品信息）
python test_okx_additional_apis.py

# 测试批量操作和修改订单
python test_okx_batch_apis.py

# 测试订单查询接口（查询订单、未成交订单、历史订单）
python test_okx_order_query_apis.py

# 测试账户接口（余额、可交易产品信息）
python test/test_okx_account_apis.py

# 测试账单流水查询接口（近7天、近3个月）
python test/test_okx_bills_apis.py

# 测试持仓信息查询接口（持仓、历史持仓）
python test/test_okx_positions_apis.py
```

**测试状态**: 所有接口已测试 ✅  
**测试覆盖率**: 100% (17/17)  
**测试报告**: 查看 [测试报告.md](./测试报告.md) 和 [API接口文档.md](./API接口文档.md)

---

## 📝 开发计划

- [x] REST API基础框架
- [x] 签名算法实现（含GET请求签名修复）
- [x] 交易接口（下单、撤单、查询）
- [x] 批量操作（批量下单、批量撤单、批量修改）
- [x] 订单查询（详情、未成交、历史）
- [x] 账户接口（余额、持仓）
- [x] 行情接口
- [x] 所有接口测试通过
- [x] API文档完善
- [x] 测试报告生成
- [ ] WebSocket连接
- [ ] WebSocket订阅（行情、订单、账户）
- [ ] 适配器组件（整合REST和WebSocket）
- [ ] 错误重试机制
- [ ] 限流管理

---

**状态**: REST API完整功能完成 ✅ | WebSocket待开发 ⏳  
**接口数量**: 17个接口已实现  
**测试覆盖率**: 100%  
**文档完整度**: 100%

