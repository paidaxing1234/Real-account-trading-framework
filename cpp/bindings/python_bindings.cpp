/**
 * C++框架的Python绑定
 * 使用PyBind11将C++接口暴露给Python
 */

#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include "../core/event.h"
#include "../core/event_engine.h"
#include "../core/order.h"
#include "../core/data.h"

namespace py = pybind11;
using namespace trading;

PYBIND11_MODULE(trading_cpp, m) {
    m.doc() = "C++实盘交易框架的Python绑定";
    
    // ============================================
    // Event 基类
    // ============================================
    py::class_<Event, std::shared_ptr<Event>>(m, "Event")
        .def_property_readonly("timestamp", &Event::timestamp)
        .def("type_name", &Event::type_name);
    
    // ============================================
    // Order 订单类
    // ============================================
    py::class_<Order, Event, std::shared_ptr<Order>>(m, "Order")
        .def_property_readonly("order_id", &Order::order_id)
        .def_property_readonly("symbol", &Order::symbol)
        .def_property_readonly("side", &Order::side)
        .def_property_readonly("type", &Order::type)
        .def_property_readonly("state", &Order::state)
        .def_property_readonly("price", &Order::price)
        .def_property_readonly("quantity", &Order::quantity)
        .def_property_readonly("filled_quantity", &Order::filled_quantity)
        .def_property_readonly("filled_price", &Order::filled_price)
        
        // 字符串转换方法
        .def("side_str", &Order::side_str)
        .def("type_str", &Order::type_str)
        .def("state_str", &Order::state_str)
        .def("to_string", &Order::to_string)
        
        // 状态查询
        .def("is_filled", &Order::is_filled)
        .def("is_active", &Order::is_active)
        .def("is_cancelled", &Order::is_cancelled)
        
        // 工厂方法
        .def_static("buy_limit", &Order::buy_limit)
        .def_static("sell_limit", &Order::sell_limit)
        .def_static("buy_market", &Order::buy_market)
        .def_static("sell_market", &Order::sell_market);
    
    // 订单枚举
    py::enum_<OrderSide>(m, "OrderSide")
        .value("BUY", OrderSide::BUY)
        .value("SELL", OrderSide::SELL);
    
    py::enum_<OrderType>(m, "OrderType")
        .value("LIMIT", OrderType::LIMIT)
        .value("MARKET", OrderType::MARKET)
        .value("POST_ONLY", OrderType::POST_ONLY);
    
    py::enum_<OrderState>(m, "OrderState")
        .value("CREATED", OrderState::CREATED)
        .value("SUBMITTED", OrderState::SUBMITTED)
        .value("ACCEPTED", OrderState::ACCEPTED)
        .value("PARTIALLY_FILLED", OrderState::PARTIALLY_FILLED)
        .value("FILLED", OrderState::FILLED)
        .value("CANCELLED", OrderState::CANCELLED)
        .value("REJECTED", OrderState::REJECTED);
    
    // ============================================
    // TickerData 行情类
    // ============================================
    py::class_<TickerData, Event, std::shared_ptr<TickerData>>(m, "TickerData")
        .def(py::init<std::string, double>())
        .def_property_readonly("symbol", &TickerData::symbol)
        .def_property_readonly("last_price", &TickerData::last_price)
        .def_property_readonly("bid_price", &TickerData::bid_price)
        .def_property_readonly("ask_price", &TickerData::ask_price)
        .def_property_readonly("volume", &TickerData::volume)
        .def("mid_price", &TickerData::mid_price)
        .def("spread", &TickerData::spread);
    
    // ============================================
    // EventEngine 事件引擎
    // ============================================
    py::class_<EventEngine>(m, "EventEngine")
        .def(py::init<>())
        
        // 推送事件
        .def("put", [](EventEngine& self, std::shared_ptr<Event> event) {
            self.put(event);
        })
        
        // 注册监听器
        .def("register_listener", [](
            EventEngine& self,
            py::type event_type,
            py::function callback
        ) {
            // 获取C++类型信息
            std::type_index type_idx = py::type::of<Event>();
            
            // 包装Python回调
            auto listener = [callback](const Event::Ptr& event) {
                try {
                    py::gil_scoped_acquire acquire;
                    callback(event);
                } catch (const py::error_already_set& e) {
                    std::cerr << "Python回调错误: " << e.what() << std::endl;
                }
            };
            
            self.register_listener(type_idx, listener);
        })
        
        // 动态接口注入
        .def("inject", [](EventEngine& self, std::string name, py::function func) {
            self.inject<py::object>(name, [func]() {
                py::gil_scoped_acquire acquire;
                return func();
            });
        })
        
        // 调用注入的接口
        .def("call", [](EventEngine& self, std::string name) {
            return self.call<py::object>(name);
        });
    
    // ============================================
    // Component 组件基类（供Python策略继承）
    // ============================================
    py::class_<Component, std::shared_ptr<Component>>(m, "Component")
        .def("start", &Component::start)
        .def("stop", &Component::stop);
}

