#pragma once

/**
 * @file events.h
 * @brief 环形总线上的固定大小事件结构体
 * 
 * 设计原则：
 * 1. 固定大小（对齐到缓存行）
 * 2. POD类型（可直接memcpy）
 * 3. 无动态内存分配
 * 4. 字段紧凑布局
 */

#include <cstdint>
#include <cstring>
#include <chrono>

namespace trading {
namespace disruptor {

// ============================================================
// 常量定义
// ============================================================
constexpr size_t SYMBOL_MAX_LEN = 24;
constexpr size_t CLIENT_ID_MAX_LEN = 32;
constexpr size_t EXCHANGE_ID_MAX_LEN = 32;

// ============================================================
// 事件类型枚举
// ============================================================
enum class EventType : uint8_t {
    NONE = 0,
    TICKER = 1,        // 行情快照
    TRADE = 2,         // 逐笔成交
    DEPTH = 3,         // 深度数据
    ORDER_REQ = 10,    // 订单请求（策略 -> OEMS）
    ORDER_ACK = 11,    // 订单确认（交易所 -> 策略）
    ORDER_FILL = 12,   // 订单成交
    ORDER_CANCEL = 13, // 订单取消
    POSITION = 20,     // 持仓更新
    ACCOUNT = 21,      // 账户更新
    HEARTBEAT = 99,    // 心跳
};

// ============================================================
// 订单方向和类型
// ============================================================
enum class Side : uint8_t {
    BUY = 0,
    SELL = 1,
};

enum class OrdType : uint8_t {
    LIMIT = 0,
    MARKET = 1,
    POST_ONLY = 2,
    FOK = 3,
    IOC = 4,
};

enum class OrdStatus : uint8_t {
    CREATED = 0,
    PENDING = 1,
    ACCEPTED = 2,
    PARTIAL_FILL = 3,
    FILLED = 4,
    CANCELLED = 5,
    REJECTED = 6,
};

// ============================================================
// 行情事件（64字节，1个缓存行）
// ============================================================
struct alignas(64) MarketEvent {
    // Header (16 bytes)
    int64_t timestamp_ns;      // 8: 纳秒时间戳
    EventType type;            // 1: 事件类型
    uint8_t exchange_id;       // 1: 交易所ID (0=OKX, 1=Binance, etc.)
    uint16_t symbol_id;        // 2: 交易对ID（预定义映射）
    uint32_t sequence;         // 4: 序列号
    
    // Data (40 bytes)
    double last_price;         // 8: 最新价
    double bid_price;          // 8: 买一价
    double ask_price;          // 8: 卖一价
    double volume;             // 8: 成交量
    double bid_size;           // 8: 买一量
    
    // Padding (8 bytes)
    char padding[8];
    
    // 初始化
    void clear() {
        memset(this, 0, sizeof(MarketEvent));
    }
    
    // 设置时间戳
    void set_timestamp() {
        using namespace std::chrono;
        timestamp_ns = duration_cast<nanoseconds>(
            steady_clock::now().time_since_epoch()
        ).count();
    }
    
    // 获取纳秒时间戳
    static int64_t now_ns() {
        using namespace std::chrono;
        return duration_cast<nanoseconds>(
            steady_clock::now().time_since_epoch()
        ).count();
    }
};

static_assert(sizeof(MarketEvent) == 64, "MarketEvent must be 64 bytes");

// ============================================================
// 深度事件（128字节，2个缓存行）
// ============================================================
struct alignas(64) DepthEvent {
    // Header (16 bytes)
    int64_t timestamp_ns;
    EventType type;
    uint8_t exchange_id;
    uint16_t symbol_id;
    uint8_t depth_levels;      // 深度档数
    uint8_t padding1[3];
    
    // Bids: 5档 (80 bytes)
    double bid_prices[5];      // 40: 买价
    double bid_sizes[5];       // 40: 买量
    
    // Asks: 5档 (80 bytes) - 会跨到下一个缓存行
    double ask_prices[5];      // 40: 卖价
    double ask_sizes[5];       // 40: 卖量
    
    // Padding
    char padding2[16];
    
    void clear() {
        memset(this, 0, sizeof(DepthEvent));
        type = EventType::DEPTH;
    }
};

static_assert(sizeof(DepthEvent) == 192, "DepthEvent size check");

// ============================================================
// 订单请求（策略 -> OEMS，128字节）
// ============================================================
struct alignas(64) OrderRequest {
    // Header (24 bytes)
    int64_t timestamp_ns;      // 8: 创建时间
    int64_t order_id;          // 8: 本地订单ID
    EventType type;            // 1: 事件类型
    uint8_t exchange_id;       // 1: 目标交易所
    uint16_t symbol_id;        // 2: 交易对ID
    uint8_t account_id;        // 1: 账户ID（多账户支持）
    Side side;                 // 1: 买卖方向
    OrdType ord_type;          // 1: 订单类型
    uint8_t flags;             // 1: 标志位（预留）
    
    // Order params (40 bytes)
    double price;              // 8: 价格
    double quantity;           // 8: 数量
    double stop_price;         // 8: 止损价（如果有）
    char client_order_id[16];  // 16: 客户端订单ID
    
    // Strategy info (24 bytes)
    uint32_t strategy_id;      // 4: 策略ID
    uint32_t signal_id;        // 4: 信号ID
    char strategy_name[16];    // 16: 策略名称
    
    // Padding
    char padding[40];
    
    void clear() {
        memset(this, 0, sizeof(OrderRequest));
        type = EventType::ORDER_REQ;
    }
    
    void set_timestamp() {
        timestamp_ns = MarketEvent::now_ns();
    }
};

static_assert(sizeof(OrderRequest) == 128, "OrderRequest must be 128 bytes");

// ============================================================
// 订单回报（OEMS/交易所 -> 策略，128字节）
// ============================================================
struct alignas(64) OrderResponse {
    // Header (32 bytes)
    int64_t timestamp_ns;      // 8: 回报时间
    int64_t order_id;          // 8: 本地订单ID
    int64_t exchange_order_id; // 8: 交易所订单ID
    EventType type;            // 1: 事件类型 (ORDER_ACK/FILL/CANCEL)
    uint8_t exchange_id;       // 1
    uint16_t symbol_id;        // 2
    OrdStatus status;          // 1: 订单状态
    uint8_t account_id;        // 1
    uint8_t padding1[2];       // 2
    
    // Fill info (40 bytes)
    double filled_price;       // 8: 成交价
    double filled_qty;         // 8: 成交量
    double cum_qty;            // 8: 累计成交量
    double avg_price;          // 8: 平均成交价
    double fee;                // 8: 手续费
    
    // Status info (24 bytes)
    uint32_t error_code;       // 4: 错误码
    uint32_t strategy_id;      // 4: 策略ID
    char error_msg[16];        // 16: 错误信息
    
    // Timing (24 bytes)
    int64_t latency_ns;        // 8: 延迟（从请求到回报）
    int64_t exchange_time_ns;  // 8: 交易所时间
    char padding2[8];          // 8
    
    void clear() {
        memset(this, 0, sizeof(OrderResponse));
    }
};

static_assert(sizeof(OrderResponse) == 128, "OrderResponse must be 128 bytes");

// ============================================================
// 通用事件容器（用于混合类型的RingBuffer）
// ============================================================
union EventUnion {
    MarketEvent market;
    DepthEvent depth;
    OrderRequest order_req;
    OrderResponse order_resp;
    
    // 获取事件类型
    EventType type() const {
        return market.type;  // 所有事件的type字段位置相同
    }
    
    // 获取时间戳
    int64_t timestamp() const {
        return market.timestamp_ns;
    }
};

// ============================================================
// 交易对ID映射（高性能查找）
// ============================================================
class SymbolMapper {
public:
    static constexpr size_t MAX_SYMBOLS = 256;
    
    // 预定义的交易对ID
    static constexpr uint16_t BTC_USDT = 1;
    static constexpr uint16_t ETH_USDT = 2;
    static constexpr uint16_t BTC_USD = 3;
    static constexpr uint16_t ETH_USD = 4;
    
    // 根据ID获取符号名（用于日志等）
    static const char* get_symbol(uint16_t id) {
        static const char* symbols[] = {
            "UNKNOWN",
            "BTC-USDT",
            "ETH-USDT",
            "BTC-USD",
            "ETH-USD",
            // ... 可扩展
        };
        return id < sizeof(symbols)/sizeof(symbols[0]) ? symbols[id] : "UNKNOWN";
    }
    
    // 根据符号名获取ID（启动时初始化用）
    static uint16_t get_id(const char* symbol) {
        // 简单实现，实际应用中可以用哈希表
        if (strcmp(symbol, "BTC-USDT") == 0) return BTC_USDT;
        if (strcmp(symbol, "ETH-USDT") == 0) return ETH_USDT;
        if (strcmp(symbol, "BTC-USD") == 0) return BTC_USD;
        if (strcmp(symbol, "ETH-USD") == 0) return ETH_USD;
        return 0;  // UNKNOWN
    }
};

// ============================================================
// 交易所ID
// ============================================================
struct ExchangeId {
    static constexpr uint8_t OKX = 0;
    static constexpr uint8_t BINANCE = 1;
    static constexpr uint8_t HUOBI = 2;
    static constexpr uint8_t BYBIT = 3;
};

} // namespace disruptor
} // namespace trading

