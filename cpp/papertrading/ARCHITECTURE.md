# PaperTrading 架构说明

## 线程架构

### 设计原则
- **所有组件都在独立线程中运行，不阻塞主线程**
- **线程安全的消息传递**
- **异步操作，避免阻塞**

### 线程结构

```
主线程 (main)
  ├─ PaperTradingServer::start() [快速返回，不阻塞]
  │
  ├─ order_thread_ [独立线程]
  │   └─ 处理ZMQ订单请求
  │
  ├─ query_thread_ [独立线程]
  │   └─ 处理ZMQ查询请求
  │
  ├─ subscribe_thread_ [独立线程]
  │   └─ 处理ZMQ订阅请求
  │
  └─ frontend_server_ [独立线程]
      ├─ server_thread_ [WebSocket服务器线程]
      │   └─ 处理WebSocket连接和消息
      │
      └─ snapshot_thread_ [快照推送线程]
          └─ 定时生成和推送快照（100ms）
```

## 组件说明

### 1. WebSocket服务器 (`core/websocket_server.h`)

**位置**: `cpp/core/websocket_server.h/cpp`

**特性**:
- 在独立线程中运行，不阻塞主线程
- 线程安全的消息发送和接收
- 异步消息队列，避免阻塞
- 自动管理客户端连接

**线程**:
- `server_thread_`: WebSocket服务器主线程
- `snapshot_thread_`: 快照推送线程

**关键方法**:
- `start()`: 启动服务器（快速返回，在独立线程中运行）
- `send_response()`: 异步发送响应（线程安全）
- `send_event()`: 异步广播事件（线程安全）
- `send_log()`: 异步发送日志（线程安全）

### 2. PaperTrading服务器 (`papertrading_server.h`)

**位置**: `cpp/papertrading/papertrading_server.h/cpp`

**特性**:
- `start()` 方法快速返回，不阻塞主线程
- 所有工作都在独立线程中执行
- 线程安全的状态管理

**线程**:
- `order_thread_`: 处理订单请求
- `query_thread_`: 处理查询请求
- `subscribe_thread_`: 处理订阅请求
- `frontend_server_`: WebSocket服务器（内部有2个线程）

## 消息流程

### 前端 → 后端

```
前端WebSocket客户端
  ↓
WebSocket服务器 (server_thread_)
  ↓ [异步消息队列]
消息回调 (handle_frontend_command)
  ↓
PaperTradingServer处理
  ↓
响应 (send_response) [异步]
  ↓
WebSocket服务器发送给客户端
```

### 后端 → 前端

```
PaperTradingServer
  ↓
send_event() / send_log() [异步]
  ↓
消息队列
  ↓
WebSocket服务器 (server_thread_)
  ↓
广播给所有客户端
```

### 快照推送

```
snapshot_thread_ (每100ms)
  ↓
generate_snapshot()
  ↓
消息队列
  ↓
WebSocket服务器广播
```

## 线程安全保证

### 1. WebSocket服务器
- 使用 `std::mutex` 保护客户端连接
- 使用 `std::mutex` 保护回调函数
- 使用消息队列 + `std::condition_variable` 实现异步发送

### 2. PaperTrading服务器
- 使用 `std::atomic<bool>` 管理运行状态
- 每个工作线程独立运行，互不干扰
- 共享数据通过锁保护

## 性能考虑

1. **非阻塞设计**: 所有操作都是异步的，不会阻塞主线程
2. **独立线程**: 每个组件在独立线程中运行，互不影响
3. **消息队列**: 使用队列缓冲消息，避免丢失
4. **快照频率**: 100ms推送一次，平衡实时性和性能

## 使用示例

### 启动PaperTrading服务器

```cpp
// 创建服务器（不阻塞）
PaperTradingServer server(config);

// 启动服务器（快速返回，所有工作在独立线程中）
if (server.start()) {
    // 主线程可以继续做其他事情
    // 服务器在后台运行
    
    // 等待停止信号
    while (running) {
        std::this_thread::sleep_for(milliseconds(100));
    }
    
    // 停止服务器
    server.stop();
}
```

### 发送消息（线程安全）

```cpp
// 在任何线程中都可以安全调用
frontend_server_->send_response(client_id, true, "操作成功");
frontend_server_->send_event("order_filled", order_data);
frontend_server_->send_log("info", "订单已成交");
```

## 注意事项

1. **不要在主线程中执行耗时操作**: 所有耗时操作都应该在独立线程中执行
2. **线程安全**: 访问共享数据时需要使用锁
3. **资源清理**: 停止服务器时会自动清理所有线程和资源
4. **异常处理**: 每个线程都有独立的异常处理，不会影响其他线程

