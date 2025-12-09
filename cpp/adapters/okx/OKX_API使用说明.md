# OKX REST API - C++ 实现说明

## 新增接口：get_account_instruments

### 功能描述

获取交易产品基础信息（账户维度），获取当前账户可交易产品的信息列表。

### 接口信息

- **端点**: `GET /api/v5/account/instruments`
- **限速**: 20次/2s
- **权限**: 读取

### 接口签名

```cpp
nlohmann::json get_account_instruments(
    const std::string& inst_type,      // 产品类型（必填）
    const std::string& inst_family,    // 交易品种（可选）
    const std::string& inst_id         // 产品ID（可选）
);
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| inst_type | string | 是 | 产品类型：SPOT（币币）、MARGIN（杠杆）、SWAP（永续）、FUTURES（交割）、OPTION（期权） |
| inst_family | string | 否 | 交易品种，仅适用于交割/永续/期权，期权必填 |
| inst_id | string | 否 | 产品ID，如 BTC-USDT |

### 返回值

返回 `nlohmann::json` 对象，结构如下：

```json
{
    "code": "0",
    "msg": "",
    "data": [
        {
            "instId": "BTC-USDT",
            "instType": "SPOT",
            "baseCcy": "BTC",
            "quoteCcy": "USDT",
            "state": "live",
            "tickSz": "0.1",
            "lotSz": "0.00000001",
            "minSz": "0.00001",
            "maxLmtSz": "9999999999",
            "maxMktSz": "1000000",
            // ... 更多字段
        }
    ]
}
```

### 使用示例

#### 示例1：查询所有现货产品

```cpp
#include "adapters/okx/okx_rest_api.h"

using namespace trading::okx;

// 创建API客户端
OKXRestAPI api(api_key, secret_key, passphrase, false);

// 查询现货产品
auto result = api.get_account_instruments("SPOT");

if (result["code"] == "0") {
    std::cout << "产品数量: " << result["data"].size() << std::endl;
    
    for (const auto& item : result["data"]) {
        std::cout << "产品ID: " << item["instId"] << std::endl;
        std::cout << "状态: " << item["state"] << std::endl;
    }
}
```

#### 示例2：查询特定产品

```cpp
// 查询BTC-USDT产品信息
auto result = api.get_account_instruments("SPOT", "", "BTC-USDT");

if (result["code"] == "0" && !result["data"].empty()) {
    auto btc_usdt = result["data"][0];
    
    std::cout << "产品ID: " << btc_usdt["instId"] << std::endl;
    std::cout << "价格精度: " << btc_usdt["tickSz"] << std::endl;
    std::cout << "数量精度: " << btc_usdt["lotSz"] << std::endl;
    std::cout << "最小下单量: " << btc_usdt["minSz"] << std::endl;
}
```

#### 示例3：查询永续合约

```cpp
// 查询永续合约产品
auto result = api.get_account_instruments("SWAP");

if (result["code"] == "0") {
    std::cout << "永续合约数量: " << result["data"].size() << std::endl;
    
    for (const auto& item : result["data"]) {
        std::cout << item["instId"] << " - " 
                  << "结算币种: " << item["settleCcy"] << std::endl;
    }
}
```

#### 示例4：查询期权产品

```cpp
// 查询期权产品（需要指定交易品种）
auto result = api.get_account_instruments("OPTION", "BTC-USD");

if (result["code"] == "0") {
    for (const auto& item : result["data"]) {
        std::cout << item["instId"] << " - "
                  << "期权类型: " << item["optType"] << ", "
                  << "行权价: " << item["stk"] << std::endl;
    }
}
```

### 返回字段说明

#### 核心字段

| 字段 | 类型 | 说明 |
|------|------|------|
| instType | string | 产品类型 |
| instId | string | 产品ID |
| instFamily | string | 交易品种 |
| baseCcy | string | 基础货币（现货/杠杆） |
| quoteCcy | string | 计价货币（现货/杠杆） |
| settleCcy | string | 结算货币（合约） |
| state | string | 状态：live/suspend/preopen/test |

#### 交易参数

| 字段 | 类型 | 说明 |
|------|------|------|
| tickSz | string | 价格精度 |
| lotSz | string | 数量精度 |
| minSz | string | 最小下单量 |
| maxLmtSz | string | 限价单最大委托量 |
| maxMktSz | string | 市价单最大委托量 |
| maxLmtAmt | string | 限价单最大美元价值 |
| maxMktAmt | string | 市价单最大美元价值 |

#### 时间信息

| 字段 | 类型 | 说明 |
|------|------|------|
| listTime | string | 上线时间（Unix毫秒时间戳） |
| expTime | string | 产品下线时间 |
| contTdSwTime | string | 连续交易开始时间 |

#### 合约特定字段

| 字段 | 类型 | 说明 |
|------|------|------|
| ctVal | string | 合约面值 |
| ctMult | string | 合约乘数 |
| ctType | string | 合约类型：linear/inverse |
| lever | string | 最大杠杆倍数 |

#### 期权特定字段

| 字段 | 类型 | 说明 |
|------|------|------|
| optType | string | 期权类型：C（看涨）/P（看跌） |
| stk | string | 行权价格 |
| uly | string | 标的指数 |

### 错误处理

```cpp
try {
    auto result = api.get_account_instruments("SPOT");
    
    if (result["code"] != "0") {
        std::cerr << "API错误: " << result["msg"] << std::endl;
        return;
    }
    
    // 处理数据
    
} catch (const std::exception& e) {
    std::cerr << "异常: " << e.what() << std::endl;
}
```

### 常见错误码

| 错误码 | 说明 |
|--------|------|
| 0 | 成功 |
| 50000 | 请求体不能为空 |
| 50001 | 服务暂时不可用 |
| 50002 | JSON格式错误 |
| 50004 | 端点请求超时 |
| 50011 | 请求频率过高 |
| 51000 | 参数错误 |

### 编译依赖

需要以下库支持：

```cmake
# CMakeLists.txt
find_package(CURL REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(nlohmann_json REQUIRED)

target_link_libraries(your_target
    PRIVATE CURL::libcurl
    PRIVATE OpenSSL::SSL
    PRIVATE OpenSSL::Crypto
    PRIVATE nlohmann_json::nlohmann_json
)
```

### 安装依赖（macOS）

```bash
brew install curl openssl nlohmann-json
```

### 安装依赖（Ubuntu/Debian）

```bash
sudo apt install libcurl4-openssl-dev libssl-dev nlohmann-json3-dev
```

### 完整测试程序

参考 `examples/test_okx_api.cpp`，运行：

```bash
cd build
cmake ..
cmake --build .
./test_okx_api
```

### 注意事项

1. **API凭证安全**：不要将API Key硬编码在代码中，使用环境变量或配置文件
2. **限速控制**：该接口限速 20次/2s，注意控制请求频率
3. **参数验证**：inst_type 是必填参数，必须为有效值
4. **错误处理**：始终检查返回的 code 字段
5. **网络异常**：捕获并处理网络异常
6. **数据解析**：返回的数值字段可能是字符串类型，需要转换

### 与Python版本对比

| 特性 | Python | C++ |
|------|--------|-----|
| 依赖 | requests | libcurl + OpenSSL |
| JSON解析 | dict | nlohmann::json |
| 签名算法 | hmac库 | OpenSSL HMAC |
| 异常处理 | try-except | try-catch |
| 类型安全 | 运行时 | 编译时 |
| 性能 | 中等 | 高 |

### 参考资料

- [OKX API 官方文档](https://www.okx.com/docs-v5/zh/)
- [nlohmann/json 文档](https://json.nlohmann.me/)
- [libcurl 文档](https://curl.se/libcurl/)

---

**版本**: v1.0.0  
**更新时间**: 2025-12-08  
**状态**: ✅ 已实现

