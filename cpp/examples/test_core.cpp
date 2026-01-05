/**
 * @file test_core.cpp
 * @brief 核心模块测试程序
 * 
 * 测试内容：
 * 1. EventEngine 事件注册和分发
 * 2. Order 订单模型
 * 3. Data 数据模型
 * 4. Component 生命周期
 */

#include "../core/event_engine.h"
#include "../trading/order.h"
#include "../core/data.h"
#include <iostream>
#include <cassert>

using namespace trading;

// 测试计数器
int ticker_count = 0;
int order_count = 0;
int global_count = 0;

// 测试监听器
void on_ticker(const Event::Ptr& e) {
    auto ticker = std::dynamic_pointer_cast<TickerData>(e);
    std::cout << "on_ticker: " << ticker->to_string() << std::endl;
    ticker_count++;
}

void on_order(const Event::Ptr& e) {
    auto order = std::dynamic_pointer_cast<Order>(e);
    std::cout << "on_order: " << order->to_string() << std::endl;
    order_count++;
}

void on_global(const Event::Ptr& e) {
    std::cout << "on_global: " << e->type_name() << std::endl;
    global_count++;
}

// 测试组件
class TestComponent : public Component {
public:
    bool started = false;
    bool stopped = false;
    
    virtual void start(EventEngine* engine) override {
        engine_ = engine;
        started = true;
        std::cout << "TestComponent started" << std::endl;
    }
    
    virtual void stop() override {
        stopped = true;
        std::cout << "TestComponent stopped" << std::endl;
    }
};

void test_event_engine() {
    std::cout << "\n" << std::string(60, '=') << std::endl;
    std::cout << "测试 EventEngine" << std::endl;
    std::cout << std::string(60, '=') << std::endl;
    
    EventEngine engine;
    
    // 注册监听器
    std::cout << "\n1. 注册监听器..." << std::endl;
    engine.register_listener(typeid(TickerData), on_ticker);
    engine.register_listener(typeid(Order), on_order);
    engine.register_global_listener(on_global, false, true);
    
    // 推送行情事件
    std::cout << "\n2. 推送行情事件..." << std::endl;
    auto ticker = std::make_shared<TickerData>("BTC-USDT-SWAP", 50000.0);
    ticker->set_bid_price(49999.0);
    ticker->set_ask_price(50001.0);
    ticker->set_timestamp(Event::current_timestamp());
    engine.put(ticker);
    
    // 推送订单事件
    std::cout << "\n3. 推送订单事件..." << std::endl;
    auto order = Order::buy_limit("BTC-USDT-SWAP", 0.01, 50000.0);
    order->set_timestamp(Event::current_timestamp());
    engine.put(order);
    
    // 验证
    assert(ticker_count == 1);
    assert(order_count == 1);
    assert(global_count == 2);  // 两个事件都会触发全局监听器
    
    std::cout << "\n✅ EventEngine 测试通过" << std::endl;
}

void test_order() {
    std::cout << "\n" << std::string(60, '=') << std::endl;
    std::cout << "测试 Order" << std::endl;
    std::cout << std::string(60, '=') << std::endl;
    
    // 测试限价买单
    std::cout << "\n1. 创建限价买单..." << std::endl;
    auto order1 = Order::buy_limit("BTC-USDT-SWAP", 0.01, 50000.0);
    std::cout << order1->to_string() << std::endl;
    
    assert(order1->is_buy());
    assert(!order1->is_sell());
    assert(order1->order_type() == OrderType::LIMIT);
    assert(order1->side() == OrderSide::BUY);
    assert(order1->price() == 50000.0);
    assert(order1->quantity() == 0.01);
    assert(order1->state() == OrderState::CREATED);
    
    // 测试市价卖单
    std::cout << "\n2. 创建市价卖单..." << std::endl;
    auto order2 = Order::sell_market("BTC-USDT-SWAP", 0.01);
    std::cout << order2->to_string() << std::endl;
    
    assert(!order2->is_buy());
    assert(order2->is_sell());
    assert(order2->order_type() == OrderType::MARKET);
    
    // 测试状态更新
    std::cout << "\n3. 更新订单状态..." << std::endl;
    order1->set_state(OrderState::ACCEPTED);
    std::cout << "  状态: " << order_state_to_string(order1->state()) << std::endl;
    assert(order1->is_active());
    
    order1->set_state(OrderState::FILLED);
    order1->set_filled_quantity(0.01);
    order1->set_filled_price(50100.0);
    std::cout << "  状态: " << order_state_to_string(order1->state()) << std::endl;
    assert(order1->is_filled());
    assert(order1->is_final());
    assert(order1->remaining_quantity() == 0.0);
    
    std::cout << "\n✅ Order 测试通过" << std::endl;
}

void test_data() {
    std::cout << "\n" << std::string(60, '=') << std::endl;
    std::cout << "测试 Data" << std::endl;
    std::cout << std::string(60, '=') << std::endl;
    
    // 测试 TickerData
    std::cout << "\n1. TickerData..." << std::endl;
    auto ticker = std::make_shared<TickerData>("BTC-USDT-SWAP", 50000.0);
    ticker->set_bid_price(49999.0);
    ticker->set_ask_price(50001.0);
    ticker->set_bid_size(1.5);
    ticker->set_ask_size(2.0);
    std::cout << ticker->to_string() << std::endl;
    
    auto mid = ticker->mid_price();
    auto spread = ticker->spread();
    assert(mid && *mid == 50000.0);
    assert(spread && *spread == 2.0);
    std::cout << "  中间价: " << *mid << ", 价差: " << *spread << std::endl;
    
    // 测试 TradeData
    std::cout << "\n2. TradeData..." << std::endl;
    auto trade = std::make_shared<TradeData>("BTC-USDT-SWAP", "12345", 50000.0, 0.01);
    trade->set_side("buy");
    std::cout << trade->to_string() << std::endl;
    
    // 测试 OrderBookData
    std::cout << "\n3. OrderBookData..." << std::endl;
    std::vector<std::pair<double, double>> bids = {
        {49999.0, 1.0}, {49998.0, 2.0}, {49997.0, 1.5}
    };
    std::vector<std::pair<double, double>> asks = {
        {50001.0, 1.5}, {50002.0, 2.0}, {50003.0, 1.0}
    };
    auto orderbook = std::make_shared<OrderBookData>("BTC-USDT-SWAP", bids, asks);
    std::cout << orderbook->to_string() << std::endl;
    
    auto best_bid = orderbook->best_bid();
    auto best_ask = orderbook->best_ask();
    assert(best_bid && best_bid->first == 49999.0);
    assert(best_ask && best_ask->first == 50001.0);
    std::cout << "  最优买价: " << best_bid->first << ", 最优卖价: " << best_ask->first << std::endl;
    
    // 测试 KlineData
    std::cout << "\n4. KlineData..." << std::endl;
    auto kline = std::make_shared<KlineData>("BTC-USDT-SWAP", "1m", 49900, 50100, 49800, 50000, 100.5);
    std::cout << kline->to_string() << std::endl;
    
    std::cout << "\n✅ Data 测试通过" << std::endl;
}

void test_component() {
    std::cout << "\n" << std::string(60, '=') << std::endl;
    std::cout << "测试 Component" << std::endl;
    std::cout << std::string(60, '=') << std::endl;
    
    EventEngine engine;
    TestComponent component;
    
    // 启动组件
    std::cout << "\n1. 启动组件..." << std::endl;
    component.start(&engine);
    assert(component.started);
    
    // 停止组件
    std::cout << "\n2. 停止组件..." << std::endl;
    component.stop();
    assert(component.stopped);
    
    std::cout << "\n✅ Component 测试通过" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "       C++ 实盘交易框架 - 核心模块测试" << std::endl;
    std::cout << "==================================================" << std::endl;
    
    try {
        test_event_engine();
        test_order();
        test_data();
        test_component();
        
        std::cout << "\n" << std::string(60, '=') << std::endl;
        std::cout << "✅ 所有测试通过！" << std::endl;
        std::cout << std::string(60, '=') << std::endl;
        
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 测试失败: " << e.what() << std::endl;
        return 1;
    }
}

