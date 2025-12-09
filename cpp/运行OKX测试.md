# 运行 OKX API 测试

## 🚀 快速运行（5步）

### 1. 安装依赖

```bash
# macOS
brew install curl openssl nlohmann-json

# Ubuntu/Debian (如果需要)
# sudo apt install libcurl4-openssl-dev libssl-dev nlohmann-json3-dev
```

### 2. 修改 CMakeLists.txt

编辑 `CMakeLists.txt`，取消注释 OKX API 测试部分：

找到这些行（第133行左右）：
```cmake
# OKX API 测试程序（需要额外依赖）
# 取消注释以下内容来编译 OKX API 测试
# find_package(CURL QUIET)
# find_package(OpenSSL QUIET)
...
```

将所有 `#` 删除（取消注释），变成：
```cmake
# OKX API 测试程序（需要额外依赖）
# 取消注释以下内容来编译 OKX API 测试
find_package(CURL QUIET)
find_package(OpenSSL QUIET)
if(CURL_FOUND AND OPENSSL_FOUND AND HAS_JSON)
    message(STATUS "Building OKX API test")
    add_library(okx_rest_api adapters/okx/okx_rest_api.cpp)
    target_link_libraries(okx_rest_api
        PUBLIC trading_core
        PRIVATE CURL::libcurl
        PRIVATE OpenSSL::SSL
        PRIVATE OpenSSL::Crypto
        PRIVATE nlohmann_json::nlohmann_json
    )
    
    add_executable(test_okx_api examples/test_okx_api.cpp)
    target_link_libraries(test_okx_api
        PRIVATE okx_rest_api
        PRIVATE nlohmann_json::nlohmann_json
    )
else()
    message(STATUS "OKX API test skipped - missing dependencies (CURL/OpenSSL/JSON)")
endif()
```

### 3. 编译

```bash
cd Real-account-trading-framework/cpp/build
cmake ..
cmake --build .
```

### 4. 运行测试

```bash
./test_okx_api
```

### 5. 查看结果

应该看到类似输出：

```
========================================
  OKX REST API - 获取交易产品信息测试
========================================

1️⃣ 测试：查询现货产品列表
   调用: get_account_instruments("SPOT")
   ✅ 请求成功！
   产品数量: 500

   前5个产品信息：
   -----------------------------------------------------------------------
   产品ID         基础货币    计价货币    状态        最小下单量     
   -----------------------------------------------------------------------
   BTC-USDT       BTC        USDT       live        0.00001       
   ETH-USDT       ETH        USDT       live        0.0001        
   ...

2️⃣ 测试：查询BTC-USDT产品信息
   ...

========================================
  测试完成！
========================================
```

## 📋 完整命令（一次性）

```bash
# 1. 安装依赖（如果还没安装）
brew install curl openssl nlohmann-json

# 2. 进入项目目录
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/cpp

# 3. 编辑 CMakeLists.txt（手动取消注释 OKX 测试部分）
# 或者用这个命令自动处理：
sed -i '' 's/^# \(find_package(CURL\)/\1/' CMakeLists.txt
sed -i '' 's/^# \(find_package(OpenSSL\)/\1/' CMakeLists.txt
sed -i '' 's/^# \(if(CURL_FOUND\)/\1/' CMakeLists.txt
sed -i '' 's/^#     /    /' CMakeLists.txt
sed -i '' 's/^# \(else()\)/\1/' CMakeLists.txt
sed -i '' 's/^# \(endif()\)/\1/' CMakeLists.txt

# 4. 编译
cd build
cmake ..
cmake --build .

# 5. 运行测试
./test_okx_api
```

## 🐛 常见问题

### 问题1：找不到 nlohmann-json

**错误**：
```
CMake Error: Could not find a package configuration file provided by "nlohmann_json"
```

**解决**：
```bash
brew install nlohmann-json
```

### 问题2：找不到 CURL

**错误**：
```
CMake Error: Could not find CURL
```

**解决**：
```bash
brew install curl
# 如果还不行，添加环境变量
export CURL_DIR=/opt/homebrew/opt/curl
```

### 问题3：找不到 OpenSSL

**错误**：
```
CMake Error: Could not find OpenSSL
```

**解决**：
```bash
brew install openssl
export OPENSSL_ROOT_DIR=/opt/homebrew/opt/openssl@3
```

### 问题4：编译错误

**错误**：
```
error: 'nlohmann/json.hpp' file not found
```

**解决**：
确保已安装 nlohmann-json 并重新运行 cmake：
```bash
brew install nlohmann-json
cd build
rm -rf *
cmake ..
cmake --build .
```

### 问题5：运行时错误 - API 错误

**错误**：
```
❌ 请求失败！
错误码: 50113
错误信息: Invalid sign
```

**原因**：
- API 凭证不正确
- 时间不同步

**解决**：
1. 检查 API Key、Secret、Passphrase 是否正确
2. 确保系统时间正确：`date`

## 🔍 验证安装

运行以下命令检查依赖：

```bash
# 检查 CURL
curl-config --version

# 检查 OpenSSL
openssl version

# 检查 nlohmann-json
brew list nlohmann-json

# 检查编译器
c++ --version
```

## 📊 测试内容

测试程序会执行以下操作：

1. ✅ 查询所有现货产品列表
2. ✅ 查询 BTC-USDT 产品详细信息
3. ✅ 查询永续合约产品列表

每个测试都会显示：
- 请求是否成功
- 返回的数据
- 格式化的输出

## 🎯 预期结果

如果一切正常，你会看到：

```
========================================
  OKX REST API - 获取交易产品信息测试
========================================

1️⃣ 测试：查询现货产品列表
   ✅ 请求成功！
   产品数量: 500+

2️⃣ 测试：查询BTC-USDT产品信息
   ✅ 请求成功！
   
   BTC-USDT 详细信息：
   --------------------------------------------------
   产品ID:        BTC-USDT
   状态:          live
   价格精度:      0.1
   数量精度:      0.00000001
   最小下单量:    0.00001
   ...

3️⃣ 测试：查询永续合约产品
   ✅ 请求成功！
   永续合约产品数量: 200+

========================================
  测试完成！
========================================
```

## ⚠️ 重要提示

1. **API 凭证已配置**：凭证已经写入 `test_okx_api.cpp`
2. **使用模拟盘**：当前使用的可能是模拟盘凭证
3. **限速注意**：API 有调用频率限制（20次/2s）
4. **网络要求**：需要能够访问 OKX API（https://www.okx.com）

## 🔗 相关文档

- [OKX API 使用说明](adapters/okx/OKX_API使用说明.md)
- [OKX 适配器 README](adapters/okx/README.md)
- [OKX 官方文档](https://www.okx.com/docs-v5/zh/)

---

**准备好了就运行吧！** 🚀

