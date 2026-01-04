/**
 * @file test_binance_futures_ws_order_testnet.cpp
 * @brief Binance FUTURES WebSocket 下单测试（合约测试网）
 * 
 * 端点：wss://testnet.binancefuture.com/ws-fapi/v1
 * 
 * 功能：
 * - WebSocket 连接
 * - 限价单下单
 * - 修改订单（改价格和数量）
 * - 撤单
 * - 查单
 * 
 * 仿照 OKX test_okx_ws_order.cpp 的结构
 */

#include "../adapters/binance/binance_websocket.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <condition_variable>
#include <atomic>
#include <mutex>

using namespace trading::binance;

int main() {
    std::cout << "========================================\n";
    std::cout << "  Binance FUTURES WebSocket 下单测试\n";
    std::cout << "========================================\n";

    // ==================== API密钥配置 ====================
    // ⚠️ 这里填入你的【合约测试网】API Key/Secret
    std::string api_key = "txMIDVQyFksbCVfDkgDQgmkxmy24zwKrsEffJqHadqX5wOB9o6YFiXVhMFN6h10q";
    std::string secret_key = "EiVtWX34yO9Xgb28eC2zwJ7jWPtW6Cwk39sse0axMrfIeeIP5DqpZczNwuprJMZp";

    if (api_key == "YOUR_FUTURES_TESTNET_API_KEY") {
        std::cerr << "❌ 请先填入合约测试网 API 密钥\n";
        std::cerr << "   端点: wss://testnet.binancefuture.com/ws-fapi/v1\n";
        std::cerr << "   REST: https://demo-fapi.binance.com\n";
        return 1;
    }

    std::cout << "✅ API密钥已配置\n";
    std::cout << "   API Key: " << api_key.substr(0, 8) << "...\n";

    // ==================== 步骤1：创建并连接 ====================

    std::cout << "\n[1] 创建 WebSocket Trading 客户端（FUTURES Testnet）...\n";

    auto ws = create_trading_ws(api_key, secret_key, MarketType::FUTURES, true);

    // 设置下单响应回调（仿照 OKX）
    std::atomic<int> response_count{0};
    std::mutex order_mtx;
    std::condition_variable order_cv;

    ws->set_order_response_callback([&](const nlohmann::json& response) {
        std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
        std::cout << "📨 [WebSocket 下单响应]\n";
        std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
        std::cout << "  请求ID: " << response.value("id", "") << "\n";
        std::cout << "  HTTP状态: " << response.value("status", 0) << "\n";

        if (response.value("status", 0) == 200 && response.contains("result")) {
            auto result = response["result"];
            std::cout << "\n✅ 操作成功\n";
            std::cout << "  交易对: " << result.value("symbol", "") << "\n";
            std::cout << "  订单ID: " << result.value("orderId", 0) << "\n";
            std::cout << "  客户订单ID: " << result.value("clientOrderId", "") << "\n";
            std::cout << "  订单状态: " << result.value("status", "") << "\n";
            std::cout << "  订单类型: " << result.value("type", "") << "\n";
            std::cout << "  方向: " << result.value("side", "") << "\n";
            std::cout << "  持仓方向: " << result.value("positionSide", "") << "\n";
            std::cout << "  价格: " << result.value("price", "") << "\n";
            std::cout << "  数量: " << result.value("origQty", "") << "\n";
            std::cout << "  已成交: " << result.value("executedQty", "") << "\n";
        } else {
            std::cout << "\n❌ 操作失败\n";
            if (response.contains("error")) {
                auto error = response["error"];
                std::cout << "  错误码: " << error.value("code", 0) << "\n";
                std::cout << "  错误信息: " << error.value("msg", "") << "\n";
            }
        }
        std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";

        response_count++;
        order_cv.notify_one();
    });

    // 连接
    std::cout << "\n[2] 连接到 WebSocket...\n";
    if (!ws->connect()) {
        std::cerr << "❌ 连接失败\n";
        return 1;
    }
    std::cout << "✅ 连接成功\n";

    std::this_thread::sleep_for(std::chrono::seconds(2));

    // ==================== 步骤2：限价单测试 ====================

    std::cout << "\n[3] 测试限价单下单...\n";
    std::cout << "    交易对: BTCUSDT\n";
    std::cout << "    方向: BUY\n";
    std::cout << "    类型: LIMIT\n";
    std::cout << "    数量: 0.3\n";
    std::cout << "    价格: 20000 (低于市价，不会成交)\n";
    std::cout << "    持仓方向: LONG (双向持仓)\n";

    std::string req_id1 = ws->place_order_ws(
        "BTCUSDT",
        OrderSide::BUY,
        OrderType::LIMIT,
        "0.3",
        "20000",
        TimeInForce::GTC,
        PositionSide::LONG,  // 双向持仓模式下必须是 LONG 或 SHORT
        "wsfuttest001"
    );

    if (req_id1.empty()) {
        std::cerr << "❌ 发送下单请求失败\n";
    } else {
        std::cout << "✅ 下单请求已发送，请求ID: " << req_id1 << "\n";
    }

    // 等待响应
    {
        std::unique_lock<std::mutex> lock(order_mtx);
        order_cv.wait_for(lock, std::chrono::seconds(5), [&]{ return response_count.load() >= 1; });
    }

    std::this_thread::sleep_for(std::chrono::seconds(5));

    // ==================== 步骤3：修改订单测试 ====================

    std::cout << "\n[4] 测试修改订单（改价格+数量）...\n";
    std::cout << "    新价格: 25000\n";
    std::cout << "    新数量: 0.2\n";

    std::string req_id2 = ws->modify_order_ws(
        "BTCUSDT",
        OrderSide::BUY,
        "0.1",        // 新数量
        "25000",      // 新价格
        0,
        "wsfuttest001",
        PositionSide::LONG
    );

    if (req_id2.empty()) {
        std::cerr << "❌ 发送修改订单请求失败\n";
    } else {
        std::cout << "✅ 修改订单请求已发送，请求ID: " << req_id2 << "\n";
    }

    // 等待修改订单响应
    {
        std::unique_lock<std::mutex> lock(order_mtx);
        order_cv.wait_for(lock, std::chrono::seconds(5), [&]{ return response_count.load() >= 2; });
    }

    std::this_thread::sleep_for(std::chrono::seconds(5));

    // ==================== 步骤4：撤单测试 ====================

    std::cout << "\n[5] 测试撤单（通过 clientOrderId）...\n";

    std::string req_id3 = ws->cancel_order_ws("BTCUSDT", 0, "wsfuttest001");

    if (req_id3.empty()) {
        std::cerr << "❌ 发送撤单请求失败\n";
    } else {
        std::cout << "✅ 撤单请求已发送，请求ID: " << req_id3 << "\n";
    }

    // 等待撤单响应
    {
        std::unique_lock<std::mutex> lock(order_mtx);
        order_cv.wait_for(lock, std::chrono::seconds(5), [&]{ return response_count.load() >= 3; });
    }

    std::this_thread::sleep_for(std::chrono::seconds(2));

    // ==================== 步骤5：查单测试 ====================

    std::cout << "\n[6] 测试查询订单（通过 clientOrderId）...\n";

    std::string req_id4 = ws->query_order_ws("BTCUSDT", 0, "wsfuttest001");

    if (req_id4.empty()) {
        std::cerr << "❌ 发送查单请求失败\n";
    } else {
        std::cout << "✅ 查单请求已发送，请求ID: " << req_id4 << "\n";
    }

    // 等待查单响应
    {
        std::unique_lock<std::mutex> lock(order_mtx);
        order_cv.wait_for(lock, std::chrono::seconds(5), [&]{ return response_count.load() >= 4; });
    }

    // ==================== 清理 ====================

    std::cout << "\n[7] 断开连接...\n";
    ws->disconnect();

    std::cout << "\n========================================\n";
    std::cout << "  测试完成\n";
    std::cout << "  收到响应数: " << response_count.load() << "\n";
    std::cout << "========================================\n";

    std::cout << "\n💡 WebSocket vs REST：\n";
    std::cout << "  - WebSocket 延迟: 10-50ms\n";
    std::cout << "  - REST 延迟: 100-300ms\n";
    std::cout << "  - WebSocket 适合高频交易\n";

    return 0;
}

