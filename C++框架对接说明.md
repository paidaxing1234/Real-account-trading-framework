# C++实盘框架对接说明

## 🎯 对接架构

```
┌───────────────────────────────────────────────────────────┐
│              前端 (Vue 3)                                  │
│           http://localhost:3000                           │
└────────────────────┬──────────────────────────────────────┘
                     │ SSE流(3-10ms) + HTTP
┌────────────────────▼──────────────────────────────────────┐
│         Python FastAPI Web服务                             │
│           http://localhost:8000                           │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  CppBridge (C++桥接器) ⚡                           │ │
│  │  ┌─────────────┐         ┌─────────────┐           │ │
│  │  │  命令通道    │ REQ-REP │  事件通道    │  PUB-SUB │ │
│  │  │  5555端口   │◄───────►│  5556端口   │◄─────────┤ │
│  │  └─────────────┘         └─────────────┘           │ │
│  └──────┬────────────────────────────▲─────────────────┘ │
└─────────┼────────────────────────────┼───────────────────┘
          │ ZeroMQ(<1ms)               │ ZeroMQ(<1ms)
┌─────────▼────────────────────────────┴───────────────────┐
│              C++ 实盘框架                                  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  ZeroMQ服务器                                        │ │
│  │  - 命令监听器 (REP, 5555端口)                        │ │
│  │  - 事件发布器 (PUB, 5556端口)                        │ │
│  └─────────────┬───────────────────┬───────────────────┘ │
│                │                   │                      │
│  ┌─────────────▼───────────┐  ┌───▼──────────────────┐  │
│  │  EventEngine            │  │  命令处理器           │  │
│  │  - 订单事件             │  │  - 启动策略           │  │
│  │  - 行情事件             │  │  - 停止策略           │  │
│  │  - 持仓事件             │  │  - 下单/撤单          │  │
│  └─────────────────────────┘  └──────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

## 📊 通信协议设计

### 1. 命令通道（Python → C++）

**模式**: ZeroMQ REQ-REP  
**端口**: 5555  
**延迟**: <1ms

#### 命令格式

```json
{
  "action": "start_strategy" | "stop_strategy" | "place_order" | "cancel_order",
  "data": {
    // 具体参数
  }
}
```

#### 响应格式

```json
{
  "success": true | false,
  "data": {
    // 返回数据
  },
  "error": "错误信息（如果失败）"
}
```

#### 支持的命令

| 命令 | 参数 | 响应 |
|-----|------|-----|
| `start_strategy` | `{strategy_id, config}` | `{success, strategy_id}` |
| `stop_strategy` | `{strategy_id}` | `{success}` |
| `place_order` | `{symbol, side, type, price, quantity}` | `{success, order_id}` |
| `cancel_order` | `{order_id}` | `{success}` |
| `get_account` | `{account_id}` | `{success, data}` |

### 2. 事件通道（C++ → Python）

**模式**: ZeroMQ PUB-SUB  
**端口**: 5556  
**延迟**: <1ms

#### 事件格式

```json
{
  "type": "Order" | "TickerData" | "Position" | "Account",
  "data": {
    // 事件数据
  },
  "timestamp": 1702345678123  // 毫秒时间戳
}
```

#### 订单事件

```json
{
  "type": "Order",
  "data": {
    "id": 1001,
    "symbol": "BTC-USDT-SWAP",
    "side": "BUY",
    "state": "FILLED",
    "price": 42500.0,
    "quantity": 0.1,
    "filled_quantity": 0.1
  },
  "timestamp": 1702345678123
}
```

#### 行情事件

```json
{
  "type": "TickerData",
  "data": {
    "symbol": "BTC-USDT-SWAP",
    "last_price": 42500.0,
    "bid_price": 42499.0,
    "ask_price": 42501.0,
    "volume_24h": 1234567.89
  },
  "timestamp": 1702345678123
}
```

---

## 🔧 C++端实现示例

### 1. 添加ZeroMQ支持

**CMakeLists.txt**:
```cmake
# 查找ZeroMQ
find_package(cppzmq REQUIRED)

# 链接
target_link_libraries(trading_engine
    PRIVATE cppzmq
)
```

### 2. 创建ZeroMQ服务器

**文件**: `cpp/utils/zmq_server.h`

```cpp
#pragma once
#include <zmq.hpp>
#include <nlohmann/json.hpp>
#include <thread>
#include "core/event_engine.h"

namespace trading {

class ZmqServer {
public:
    ZmqServer(EventEngine* engine) 
        : engine_(engine)
        , context_(1)
        , command_socket_(context_, zmq::socket_type::rep)
        , event_socket_(context_, zmq::socket_type::pub)
    {
        // 绑定端口
        command_socket_.bind("tcp://*:5555");
        event_socket_.bind("tcp://*:5556");
    }
    
    void start() {
        running_ = true;
        
        // 启动命令监听线程
        command_thread_ = std::thread(&ZmqServer::listen_commands, this);
        
        // 注册事件监听（推送给Python）
        engine_->register_listener(typeid(Order), [this](const Event::Ptr& e) {
            this->publish_event(e);
        });
        
        engine_->register_listener(typeid(TickerData), [this](const Event::Ptr& e) {
            this->publish_event(e);
        });
    }
    
    void stop() {
        running_ = false;
        if (command_thread_.joinable()) {
            command_thread_.join();
        }
    }
    
private:
    void listen_commands() {
        // 监听命令（REQ-REP模式）
        while (running_) {
            zmq::message_t request;
            
            try {
                // 接收命令（阻塞）
                command_socket_.recv(request, zmq::recv_flags::none);
                
                // 解析JSON
                std::string req_str = request.to_string();
                auto cmd = nlohmann::json::parse(req_str);
                
                // 处理命令
                auto response = handle_command(cmd);
                
                // 发送响应
                std::string resp_str = response.dump();
                zmq::message_t reply(resp_str.size());
                memcpy(reply.data(), resp_str.c_str(), resp_str.size());
                command_socket_.send(reply, zmq::send_flags::none);
                
            } catch (const std::exception& e) {
                // 发送错误响应
                nlohmann::json error_resp = {
                    {"success", false},
                    {"error", e.what()}
                };
                std::string err_str = error_resp.dump();
                zmq::message_t reply(err_str.size());
                memcpy(reply.data(), err_str.c_str(), err_str.size());
                command_socket_.send(reply, zmq::send_flags::none);
            }
        }
    }
    
    nlohmann::json handle_command(const nlohmann::json& cmd) {
        std::string action = cmd["action"];
        auto data = cmd["data"];
        
        if (action == "start_strategy") {
            // 启动策略
            int strategy_id = data["strategy_id"];
            // TODO: 实际启动逻辑
            return {{"success", true}, {"strategy_id", strategy_id}};
        }
        else if (action == "stop_strategy") {
            // 停止策略
            int strategy_id = data["strategy_id"];
            // TODO: 实际停止逻辑
            return {{"success", true}};
        }
        else if (action == "place_order") {
            // 下单
            std::string symbol = data["symbol"];
            std::string side = data["side"];
            double price = data["price"];
            double quantity = data["quantity"];
            
            // 创建订单并推送到EventEngine
            auto order = Order::create(symbol, side, "LIMIT", price, quantity);
            engine_->put(order);
            
            return {
                {"success", true},
                {"order_id", order->order_id()},
                {"exchange_order_id", order->exchange_order_id()}
            };
        }
        else {
            return {{"success", false}, {"error", "未知命令"}};
        }
    }
    
    void publish_event(const Event::Ptr& event) {
        // 发布事件给Python（PUB模式）
        try {
            nlohmann::json j = {
                {"type", event->type_name()},
                {"data", event->to_json()},
                {"timestamp", event->timestamp()}
            };
            
            std::string msg = j.dump();
            zmq::message_t message(msg.size());
            memcpy(message.data(), msg.c_str(), msg.size());
            event_socket_.send(message, zmq::send_flags::dontwait);
            
        } catch (const std::exception& e) {
            // 忽略发送失败（不阻塞主流程）
        }
    }
    
    EventEngine* engine_;
    zmq::context_t context_;
    zmq::socket_t command_socket_;
    zmq::socket_t event_socket_;
    std::thread command_thread_;
    bool running_ = false;
};

} // namespace trading
```

### 3. 在主程序中启动

**文件**: `cpp/examples/main_with_web.cpp`

```cpp
#include "core/event_engine.h"
#include "utils/zmq_server.h"
#include "strategies/demo_strategy.h"
#include "adapters/okx/okx_adapter.h"

using namespace trading;

int main() {
    // 1. 创建事件引擎
    auto engine = std::make_unique<EventEngine>();
    
    // 2. 创建ZeroMQ服务器（连接Web服务）
    auto zmq_server = std::make_unique<ZmqServer>(engine.get());
    zmq_server->start();
    
    // 3. 创建OKX适配器
    auto okx = std::make_unique<OKXAdapter>(
        engine.get(),
        api_key, secret_key, passphrase
    );
    okx->start();
    
    // 4. 运行主循环
    std::cout << "🚀 C++实盘框架已启动" << std::endl;
    std::cout << "📡 ZeroMQ服务: tcp://*:5555 (命令)" << std::endl;
    std::cout << "📡 ZeroMQ服务: tcp://*:5556 (事件)" << std::endl;
    
    // 保持运行
    while (true) {
        engine->drain();  // 处理事件
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    
    // 5. 清理
    zmq_server->stop();
    okx->stop();
    
    return 0;
}
```

---

## ⚡ 完整数据流

### 前端下单流程

```
用户点击"下单"按钮
    ↓ (0ms)
Vue组件调用API
    ↓ (1ms - HTTP POST)
FastAPI接收请求
    ↓ (0.5ms - 参数验证)
CppBridge.place_order()
    ↓ (0.5ms - ZeroMQ发送)
C++ ZmqServer接收
    ↓ (0.1ms - 解析命令)
C++创建Order事件
    ↓ (0.1ms - 推送到EventEngine)
OKXAdapter接收订单
    ↓ (50ms - 发送给OKX)
OKX返回订单ID
    ↓ (50ms - 网络)
OKXAdapter更新订单状态
    ↓ (0.1ms - 推送到EventEngine)
ZmqServer发布事件
    ↓ (0.5ms - ZeroMQ PUB)
CppBridge接收事件
    ↓ (0.5ms - 转发)
SSEManager广播
    ↓ (2-5ms - SSE推送)
前端EventClient接收
    ↓ (1ms - 更新UI)
━━━━━━━━━━━━━━━━━━━━━
下单总延迟: ~110ms
状态更新延迟: ~60ms
```

### 行情更新流程（高频）

```
OKX推送行情
    ↓ (5ms)
C++ OKXAdapter接收
    ↓ (0.05ms - 创建TickerData)
EventEngine分发
    ↓ (0.05ms - 所有监听器)
    ├─→ Strategy.on_ticker()  # 策略处理
    └─→ ZmqServer.publish()   # 推送给Web
            ↓ (0.3ms - ZeroMQ)
        CppBridge接收
            ↓ (0.3ms - 转发)
        SSEManager广播
            ↓ (3ms - SSE)
        前端EventClient
━━━━━━━━━━━━━━━━━━━━━
行情延迟: ~9ms ⚡
```

---

## 📝 C++端需要添加的代码

### 最小实现（核心）

#### 1. 安装ZeroMQ

**Ubuntu/Debian**:
```bash
sudo apt-get install libzmq3-dev
sudo apt-get install libcppzmq-dev
```

**macOS**:
```bash
brew install zeromq
brew install cppzmq
```

#### 2. 添加到CMakeLists.txt

```cmake
# 查找ZeroMQ
find_package(cppzmq REQUIRED)

# 添加ZeroMQ服务器
add_executable(trading_engine_with_web
    examples/main_with_web.cpp
    # ... 其他源文件
)

target_link_libraries(trading_engine_with_web
    PRIVATE cppzmq
    PRIVATE trading_core
)
```

#### 3. 创建简化版ZeroMQ服务器

**最小化实现**（放在main.cpp中）:

```cpp
#include <zmq.hpp>
#include <thread>

// 全局变量
zmq::context_t g_context(1);
zmq::socket_t g_command_socket(g_context, zmq::socket_type::rep);
zmq::socket_t g_event_socket(g_context, zmq::socket_type::pub);

// 命令监听线程
void command_listener() {
    while (true) {
        zmq::message_t request;
        g_command_socket.recv(request);
        
        std::string req_str = request.to_string();
        auto cmd = nlohmann::json::parse(req_str);
        
        // 简单响应
        nlohmann::json response = {
            {"success", true},
            {"message", "received"}
        };
        
        std::string resp = response.dump();
        g_command_socket.send(zmq::buffer(resp), zmq::send_flags::none);
    }
}

int main() {
    // 绑定端口
    g_command_socket.bind("tcp://*:5555");
    g_event_socket.bind("tcp://*:5556");
    
    // 启动命令监听线程
    std::thread cmd_thread(command_listener);
    
    // 主循环
    while (true) {
        // 模拟订单事件
        nlohmann::json event = {
            {"type", "Order"},
            {"data", {
                {"id", 1001},
                {"symbol", "BTC-USDT"},
                {"state", "FILLED"}
            }},
            {"timestamp", std::chrono::system_clock::now().time_since_epoch().count()}
        };
        
        std::string msg = event.dump();
        g_event_socket.send(zmq::buffer(msg), zmq::send_flags::dontwait);
        
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    
    cmd_thread.join();
    return 0;
}
```

---

## 🚀 快速测试

### 方式1：完全Mock模式（当前）

**无需C++，直接运行**：
```bash
# 启动Web服务
cd web_server
python start.py

# 启动前端
cd ../实盘框架前端页面
npm run dev
```

**状态**: ✅ 立即可用，但没有真实交易

### 方式2：连接C++框架（生产）

**步骤**：

#### 1. 编译C++（添加ZeroMQ支持）
```bash
cd cpp
mkdir build && cd build
cmake ..
make
```

#### 2. 启动C++框架
```bash
./trading_engine_with_web
```

**应该看到**：
```
🚀 C++实盘框架已启动
📡 ZeroMQ命令服务: tcp://*:5555
📡 ZeroMQ事件服务: tcp://*:5556
```

#### 3. 启动Web服务
```bash
cd web_server
python start.py
```

**应该看到**：
```
✅ C++框架桥接器启动成功
✅ 命令通道已连接: tcp://localhost:5555
✅ 事件通道已连接: tcp://localhost:5556
```

#### 4. 启动前端
```bash
cd ../实盘框架前端页面
npm run dev
```

#### 5. 测试
- 浏览器访问 http://localhost:3000
- 登录后应该看到 🟢 "已连接"
- C++的事件会实时推送到前端！

---

## 📊 性能测试

### 测试延迟

**在C++端**:
```cpp
// 发送事件
auto start = std::chrono::high_resolution_clock::now();
publish_event(order);
auto end = std::chrono::high_resolution_clock::now();
auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
std::cout << "发送延迟: " << duration.count() << " μs" << std::endl;
```

**在Python端**:
```python
# 接收事件
start_time = time.perf_counter()
event = await bridge.recv_event()
elapsed = (time.perf_counter() - start_time) * 1000
print(f"接收延迟: {elapsed:.2f} ms")
```

**预期结果**：
```
C++发送: 0.1-0.5 ms
网络传输: 0.3-1 ms
Python接收: 0.2-0.5 ms
SSE推送: 2-5 ms
前端接收: 0.5-1 ms
━━━━━━━━━━━━━━━━━━
总延迟: 3-8 ms ⚡
```

---

## 🎯 开发优先级

### Phase 1: 基础连接（1-2天）✅ 已完成
- [x] Python Web服务
- [x] CppBridge接口
- [x] Mock模式运行

### Phase 2: C++集成（3-5天）
- [ ] C++添加ZeroMQ服务器
- [ ] 实现命令处理
- [ ] 实现事件发布
- [ ] 测试连通性

### Phase 3: 功能完善（1周）
- [ ] 策略加载逻辑
- [ ] OKX API真实交易
- [ ] 错误处理
- [ ] 性能优化

### Phase 4: 生产部署（3-5天）
- [ ] 配置文件
- [ ] 日志系统
- [ ] 监控告警
- [ ] 部署到Linux

---

## 📚 相关文档

- `services/cpp_bridge.py` - Python端桥接器实现 ✅
- `C++框架对接说明.md` - 本文档
- `前后端完整对接文档.md` - 完整架构

---

## 💡 总结

**现在系统架构完整了！**

```
前端(Vue) ←SSE(3-10ms)→ Web服务(Python) ←ZMQ(<1ms)→ C++框架
                            ↓
                      ClickHouse + Redis
```

**已完成**：
- ✅ 前端EventClient
- ✅ Python Web服务
- ✅ CppBridge接口
- ✅ 完整的API

**待完成**（C++端）：
- 🔧 添加ZeroMQ服务器（3-5天）
- 🔧 实现命令处理
- 🔧 实现事件发布

**总延迟**：端到端 5-15ms ⚡

---

**C++端代码我已经提供示例，需要我创建完整的C++文件吗？** 🚀

