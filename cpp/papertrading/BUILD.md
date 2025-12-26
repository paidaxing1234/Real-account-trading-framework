# 模拟交易服务器编译和运行指南

## 前置依赖

### 必需依赖

1. **CMake** (3.15+)
   ```bash
   # Ubuntu/Debian
   sudo apt install cmake
   
   # macOS
   brew install cmake
   ```

2. **C++17 编译器**
   ```bash
   # Ubuntu/Debian
   sudo apt install build-essential g++
   
   # macOS (Xcode Command Line Tools)
   xcode-select --install
   ```

3. **ZeroMQ**
   ```bash
   # Ubuntu/Debian
   sudo apt install libzmq3-dev libcppzmq-dev
   
   # macOS
   brew install zeromq cppzmq
   ```

4. **nlohmann/json** (JSON库)
   ```bash
   # Ubuntu/Debian
   sudo apt install nlohmann-json3-dev
   
   # macOS
   brew install nlohmann-json
   ```

5. **OpenSSL**
   ```bash
   # Ubuntu/Debian
   sudo apt install libssl-dev
   
   # macOS (通常已预装)
   ```

6. **libcurl**
   ```bash
   # Ubuntu/Debian
   sudo apt install libcurl4-openssl-dev
   
   # macOS (通常已预装)
   ```

7. **WebSocket++ 和 ASIO** (用于WebSocket连接)
   ```bash
   # Ubuntu/Debian
   sudo apt install libwebsocketpp-dev libasio-dev
   
   # macOS
   brew install websocketpp asio
   ```

### 可选依赖

- **Boost** (如果ASIO standalone不可用，可以使用Boost.ASIO)
  ```bash
  # Ubuntu/Debian
  sudo apt install libboost-all-dev
  ```

## 编译步骤

### 1. 进入项目目录

```bash
cd /home/llx/Real-account-trading-framework/cpp
```

### 2. 创建构建目录

```bash
mkdir -p build
cd build
```

### 3. 运行CMake配置

```bash
cmake .. -DCMAKE_BUILD_TYPE=Release
```

或者使用Debug模式（用于调试）：

```bash
cmake .. -DCMAKE_BUILD_TYPE=Debug
```

### 4. 编译

```bash
# 编译所有目标
make -j$(nproc)  # Linux
make -j$(sysctl -n hw.ncpu)  # macOS

# 或者只编译模拟交易服务器
make papertrading_server -j$(nproc)
```

### 5. 编译输出

编译成功后，可执行文件位于：
```
build/papertrading_server
```

## 运行

### 1. 准备配置文件

确保配置文件 `papertrading_config.json` 存在于运行目录：

```bash
# 如果配置文件不在当前目录，可以复制默认配置
cp papertrading/papertrading_config.json .
```

### 2. 运行服务器

#### 使用默认配置

```bash
cd build
./papertrading_server
```

#### 指定配置文件

```bash
./papertrading_server --config /path/to/papertrading_config.json
```

#### 使用命令行参数覆盖

```bash
# 覆盖初始余额
./papertrading_server --balance 50000

# 使用实盘行情（覆盖配置文件中的测试网设置）
./papertrading_server --prod

# 组合使用
./papertrading_server --config my_config.json --balance 100000 --prod
```

### 3. 查看帮助

```bash
./papertrading_server --help
```

## 配置文件说明

默认配置文件：`cpp/papertrading/papertrading_config.json`

配置文件包含以下设置：

- **账户配置**：初始余额、默认杠杆
- **手续费配置**：Maker/Taker费率
- **交易配置**：滑点、合约面值
- **行情配置**：测试网/实盘设置
- **交易对特定配置**：不同交易对的合约面值和杠杆

详细说明请参考 `README_CONFIG.md`

## 常见问题

### 1. 编译错误：找不到 websocketpp

**错误信息**：
```
WebSocket++ not found. Install with: brew install websocketpp asio
```

**解决方法**：
```bash
# Ubuntu/Debian
sudo apt install libwebsocketpp-dev libasio-dev

# macOS
brew install websocketpp asio
```

### 2. 编译错误：找不到 ZeroMQ

**错误信息**：
```
ZeroMQ not found. Install with: brew install zeromq cppzmq
```

**解决方法**：
```bash
# Ubuntu/Debian
sudo apt install libzmq3-dev libcppzmq-dev

# macOS
brew install zeromq cppzmq
```

### 3. 运行时错误：找不到配置文件

**错误信息**：
```
[错误] 无法打开配置文件: papertrading_config.json
[警告] 配置文件加载失败，使用默认配置
```

**解决方法**：
- 确保配置文件存在于运行目录
- 或使用 `--config` 参数指定配置文件路径

### 4. 运行时错误：WebSocket连接失败

**可能原因**：
- 网络连接问题
- OKX API服务不可用
- 防火墙阻止连接

**解决方法**：
- 检查网络连接
- 确认OKX服务状态
- 检查防火墙设置

### 5. 运行时错误：ZMQ地址已占用

**错误信息**：
```
Address already in use
```

**解决方法**：
- 检查是否有其他实例正在运行
- 修改 `server/zmq_server.h` 中的IPC地址

## 快速开始脚本

创建一个快速编译和运行的脚本：

```bash
#!/bin/bash
# build_and_run.sh

set -e

echo "=========================================="
echo "  编译模拟交易服务器"
echo "=========================================="

# 进入cpp目录
cd "$(dirname "$0")/cpp"

# 创建构建目录
mkdir -p build
cd build

# 运行CMake
echo "运行CMake..."
cmake .. -DCMAKE_BUILD_TYPE=Release

# 编译
echo "编译中..."
make papertrading_server -j$(nproc 2>/dev/null || sysctl -n hw.ncpu)

echo ""
echo "=========================================="
echo "  编译完成！"
echo "=========================================="
echo ""
echo "运行服务器："
echo "  cd build && ./papertrading_server"
echo ""
```

使用方法：
```bash
chmod +x build_and_run.sh
./build_and_run.sh
```

## 性能优化

### 编译优化选项

CMakeLists.txt 中已包含优化选项：
- `-O3`：最高优化级别
- `-march=native`：针对当前CPU架构优化

### 运行时优化

1. **CPU绑定**：可以将进程绑定到特定CPU核心
2. **实时优先级**：可以设置更高的进程优先级（需要root权限）

## 开发模式

### Debug编译

```bash
cmake .. -DCMAKE_BUILD_TYPE=Debug
make papertrading_server
```

### 启用调试信息

在代码中添加调试输出，或使用调试器：

```bash
gdb ./papertrading_server
```

## 下一步

编译运行成功后，可以：

1. 查看 `README_CONFIG.md` 了解配置选项
2. 编写策略连接到模拟交易服务器
3. 查看日志输出了解服务器状态
4. 使用ZMQ客户端测试连接

## 相关文档

- `README_CONFIG.md` - 配置系统详细说明
- `../README.md` - 项目总体说明
- `../strategies/README.md` - 策略开发指南

