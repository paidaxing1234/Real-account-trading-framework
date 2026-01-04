# PaperTrading 端口冲突修复

## 问题描述

PaperTrading 服务器无法启动，报错：
```
Address already in use
```

**根本原因**：实盘交易服务器和模拟交易服务器使用相同的 IPC 地址，导致端口冲突。

---

## 解决方案

### 1. 创建独立的 IPC 地址空间

在 `cpp/server/zmq_server.h` 中添加 `PaperTradingIpcAddresses` 结构体：

```cpp
struct PaperTradingIpcAddresses {
    static constexpr const char* MARKET_DATA = "ipc:///tmp/paper_md.ipc";
    static constexpr const char* ORDER = "ipc:///tmp/paper_order.ipc";
    static constexpr const char* REPORT = "ipc:///tmp/paper_report.ipc";
    static constexpr const char* QUERY = "ipc:///tmp/paper_query.ipc";
    static constexpr const char* SUBSCRIBE = "ipc:///tmp/paper_subscribe.ipc";
};
```

### 2. 修改 ZmqServer 支持模式选择

**头文件修改** (`cpp/server/zmq_server.h`):
- 构造函数添加参数：`ZmqServer(bool use_paper_trading = false)`
- 添加成员变量存储地址：
  ```cpp
  const char* market_data_addr_;
  const char* order_addr_;
  const char* report_addr_;
  const char* query_addr_;
  const char* subscribe_addr_;
  ```

**实现文件修改** (`cpp/server/zmq_server.cpp`):
- 构造函数根据模式选择地址
- `start()` 方法使用成员变量而非硬编码地址
- `stop()` 方法清理对应的 IPC 文件

### 3. 更新 PaperTrading 服务器

**papertrading_server.cpp**:
```cpp
void PaperTradingServer::init_zmq_server() {
    zmq_server_ = std::make_unique<server::ZmqServer>(true);  // true = 使用模拟盘地址
    if (!zmq_server_->start()) {
        throw std::runtime_error("ZMQ服务器启动失败");
    }
    log_info("ZMQ服务器已启动");
}
```

**main.cpp**:
```cpp
// 打印ZMQ通道信息
std::cout << "[ZMQ通道]\n";
std::cout << "  行情: " << PaperTradingIpcAddresses::MARKET_DATA << "\n";
std::cout << "  订单: " << PaperTradingIpcAddresses::ORDER << "\n";
std::cout << "  回报: " << PaperTradingIpcAddresses::REPORT << "\n";
std::cout << "  查询: " << PaperTradingIpcAddresses::QUERY << "\n";
std::cout << "  订阅: " << PaperTradingIpcAddresses::SUBSCRIBE << "\n";
```

---

## 地址分配

### 实盘交易服务器
- 行情: `ipc:///tmp/trading_md.ipc`
- 订单: `ipc:///tmp/trading_order.ipc`
- 回报: `ipc:///tmp/trading_report.ipc`
- 查询: `ipc:///tmp/trading_query.ipc`
- 订阅: `ipc:///tmp/trading_subscribe.ipc`

### 模拟交易服务器
- 行情: `ipc:///tmp/paper_md.ipc`
- 订单: `ipc:///tmp/paper_order.ipc`
- 回报: `ipc:///tmp/paper_report.ipc`
- 查询: `ipc:///tmp/paper_query.ipc`
- 订阅: `ipc:///tmp/paper_subscribe.ipc`

---

## 验证结果

✅ **编译成功**
```bash
cd /home/llx/Real-account-trading-framework/cpp/papertrading
./build.sh
```

✅ **启动成功**
```bash
cd /home/llx/Real-account-trading-framework/cpp/build
./papertrading_server
```

输出显示：
```
[ZmqServer] 初始化完成 (模式: 模拟盘)
[ZmqServer] 行情通道已绑定: ipc:///tmp/paper_md.ipc
[ZmqServer] 订单通道已绑定: ipc:///tmp/paper_order.ipc
[ZmqServer] 回报通道已绑定: ipc:///tmp/paper_report.ipc
[ZmqServer] 查询通道已绑定: ipc:///tmp/paper_query.ipc
[ZmqServer] 订阅通道已绑定: ipc:///tmp/paper_subscribe.ipc
[ZmqServer] 服务已启动
```

✅ **无端口冲突** - 可以同时运行实盘和模拟交易服务器

---

## 使用说明

### 启动模拟交易服务器
```bash
cd /home/llx/Real-account-trading-framework/cpp/build
./papertrading_server
```

### 策略连接到模拟交易服务器
策略需要连接到模拟盘的 IPC 地址：
```python
# Python 策略示例
import zmq

context = zmq.Context()

# 订阅行情
md_socket = context.socket(zmq.SUB)
md_socket.connect("ipc:///tmp/paper_md.ipc")
md_socket.subscribe("")

# 发送订单
order_socket = context.socket(zmq.PUSH)
order_socket.connect("ipc:///tmp/paper_order.ipc")

# 接收回报
report_socket = context.socket(zmq.SUB)
report_socket.connect("ipc:///tmp/paper_report.ipc")
report_socket.subscribe("")
```

---

## 修改文件清单

1. ✅ `cpp/server/zmq_server.h` - 添加 PaperTradingIpcAddresses，修改构造函数
2. ✅ `cpp/server/zmq_server.cpp` - 实现模式选择逻辑
3. ✅ `cpp/papertrading/papertrading_server.cpp` - 使用模拟盘模式
4. ✅ `cpp/papertrading/main.cpp` - 显示正确的 IPC 地址

---

**修复完成时间**: 2026-01-04
**状态**: ✅ 已解决
