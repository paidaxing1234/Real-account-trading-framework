#pragma once

#include <atomic>
#include <cstdint>
#include <cstring>

namespace trading {
namespace journal {

// ============================================================
// 跨编译器 packed 支持
// ============================================================
// GCC/Clang: 使用 __attribute__((packed))
// MSVC: 使用 #pragma pack(push, 1) / #pragma pack(pop)
#if defined(_MSC_VER)
  #define TRADING_JOURNAL_PACKED
  #pragma pack(push, 1)
#else
  #define TRADING_JOURNAL_PACKED __attribute__((packed))
#endif

// ============================================================
// 页头：管理写入和读取位置
// ============================================================
struct PageHeader {
    std::atomic<uint32_t> write_cursor;  // 写入位置（原子操作）
    std::atomic<uint32_t> read_cursor;   // 读取位置（用于流控，可选）
    uint32_t capacity;                    // 页面容量
    uint32_t version;                     // 版本号
    char padding[48];                     // 填充到64字节（避免伪共享）
    
    PageHeader() 
        : write_cursor(sizeof(PageHeader))
        , read_cursor(sizeof(PageHeader))
        , capacity(0)
        , version(1) {
        memset(padding, 0, sizeof(padding));
    }
};

static_assert(sizeof(PageHeader) == 64, "PageHeader must be 64 bytes");

// ============================================================
// 帧头：每个事件的头部信息
// ============================================================
struct FrameHeader {
    uint32_t length;          // 数据长度（不包含FrameHeader）
    uint32_t msg_type;        // 消息类型（1=TICKER, 2=ORDER, 3=TRADE）
    uint64_t gen_time_ns;     // 生成时间（纳秒）
    uint64_t trigger_time_ns; // 触发时间（纳秒）
    uint32_t source;          // 数据源
    uint32_t dest;            // 目标
} TRADING_JOURNAL_PACKED;

static_assert(sizeof(FrameHeader) == 32, "FrameHeader must be 32 bytes");

// ============================================================
// Ticker事件：行情快照（128字节）
// ============================================================
struct TickerFrame {
    FrameHeader header;       // 32字节
    char symbol[24];          // 24字节
    double last_price;        // 8字节
    double bid_price;         // 8字节
    double ask_price;         // 8字节
    double volume;            // 8字节
    double bid_volume;        // 8字节
    double ask_volume;        // 8字节
    char padding[24];         // 24字节（填充到128字节：32+24+48+24=128）
    
    TickerFrame() {
        memset(this, 0, sizeof(TickerFrame));
        header.msg_type = 1;  // TICKER
        header.length = sizeof(TickerFrame) - sizeof(FrameHeader);
    }
} TRADING_JOURNAL_PACKED;

static_assert(sizeof(TickerFrame) == 128, "TickerFrame must be 128 bytes");

// ============================================================
// Order事件：订单（256字节）
// ============================================================
struct OrderFrame {
    FrameHeader header;           // 32字节
    char symbol[24];              // 24字节
    uint64_t order_id;            // 8字节
    uint32_t side;                // 4字节（0=BUY, 1=SELL）
    uint32_t order_type;          // 4字节（0=LIMIT, 1=MARKET）
    uint32_t state;               // 4字节（订单状态）
    uint32_t padding1;            // 4字节（对齐）
    double price;                 // 8字节
    double quantity;              // 8字节
    double filled_quantity;       // 8字节
    double filled_price;          // 8字节
    double avg_price;             // 8字节
    uint64_t create_time_ns;      // 8字节
    uint64_t update_time_ns;      // 8字节
    char client_order_id[48];     // 48字节
    char exchange_order_id[32];   // 32字节
    char padding2[40];            // 40字节（填充到256字节：32+24+8+16+40+16+80+40=256）
    
    OrderFrame() {
        memset(this, 0, sizeof(OrderFrame));
        header.msg_type = 2;  // ORDER
        header.length = sizeof(OrderFrame) - sizeof(FrameHeader);
    }
} TRADING_JOURNAL_PACKED;

static_assert(sizeof(OrderFrame) == 256, "OrderFrame must be 256 bytes");

// ============================================================
// Trade事件：成交（128字节）
// ============================================================
struct TradeFrame {
    FrameHeader header;       // 32字节
    char symbol[24];          // 24字节
    uint64_t trade_id;        // 8字节
    uint64_t order_id;        // 8字节
    double price;             // 8字节
    double quantity;          // 8字节
    uint64_t trade_time_ns;   // 8字节
    uint32_t side;            // 4字节
    uint32_t padding1;        // 4字节
    char padding2[24];        // 24字节（填充到128字节：32+24+48+24=128）
    
    TradeFrame() {
        memset(this, 0, sizeof(TradeFrame));
        header.msg_type = 3;  // TRADE
        header.length = sizeof(TradeFrame) - sizeof(FrameHeader);
    }
} TRADING_JOURNAL_PACKED;

static_assert(sizeof(TradeFrame) == 128, "TradeFrame must be 128 bytes");

// ============================================================
// 消息类型枚举
// ============================================================
enum class MessageType : uint32_t {
    NONE = 0,
    TICKER = 1,
    ORDER = 2,
    TRADE = 3,
};

#if defined(_MSC_VER)
  #pragma pack(pop)
#endif

} // namespace journal
} // namespace trading
