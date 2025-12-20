/**
 * @file py_strategy_bindings.cpp
 * @brief pybind11 绑定 - 将 C++ 策略基类暴露给 Python
 * 
 * 编译后生成 strategy_base.so 模块，Python 可以直接 import
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>

#include "py_strategy_base.h"

namespace py = pybind11;
using namespace trading;


// ============================================================
// Python 可继承的策略类（使用 trampoline 模式）
// ============================================================

/**
 * @brief PyStrategyBase 的 trampoline 类
 * 
 * 允许 Python 类继承并重写虚函数
 */
class PyStrategyTrampoline : public PyStrategyBase {
public:
    using PyStrategyBase::PyStrategyBase;  // 继承构造函数
    
    void on_init() override {
        PYBIND11_OVERRIDE(void, PyStrategyBase, on_init);
    }
    
    void on_stop() override {
        PYBIND11_OVERRIDE(void, PyStrategyBase, on_stop);
    }
    
    void on_tick() override {
        PYBIND11_OVERRIDE(void, PyStrategyBase, on_tick);
    }
    
    void on_kline(const std::string& symbol, const std::string& interval,
                 const KlineBar& bar) override {
        PYBIND11_OVERRIDE(void, PyStrategyBase, on_kline, symbol, interval, bar);
    }
    
    void on_order_report(const nlohmann::json& report) override {
        // 将 JSON 转换为 Python dict
        PYBIND11_OVERRIDE(void, PyStrategyBase, on_order_report, report);
    }
    
    void on_register_report(bool success, const std::string& error_msg) override {
        PYBIND11_OVERRIDE(void, PyStrategyBase, on_register_report, success, error_msg);
    }
};


// ============================================================
// nlohmann::json 与 Python dict 的转换
// ============================================================

namespace pybind11 { namespace detail {

// JSON -> Python
template <>
struct type_caster<nlohmann::json> {
public:
    PYBIND11_TYPE_CASTER(nlohmann::json, _("json"));
    
    // Python -> C++
    bool load(handle src, bool) {
        try {
            // 使用 Python json 模块序列化，然后转为 std::string
            auto json_module = py::module::import("json");
            std::string json_str = json_module.attr("dumps")(src).cast<std::string>();
            value = nlohmann::json::parse(json_str);
            return true;
        } catch (...) {
            return false;
        }
    }
    
    // C++ -> Python
    static handle cast(const nlohmann::json& src, return_value_policy, handle) {
        auto json_module = py::module::import("json");
        return json_module.attr("loads")(src.dump()).release();
    }
};

}} // namespace pybind11::detail


// ============================================================
// Python 模块定义
// ============================================================

PYBIND11_MODULE(strategy_base, m) {
    m.doc() = R"doc(
        策略基类模块
        
        提供 C++ 实现的高性能策略基础设施，包括：
        - ZMQ 通信（连接实盘服务器）
        - K线数据存储（内存，2小时）
        - 下单接口（合约）
        
        使用方法：
        
            from strategy_base import StrategyBase, KlineBar
            
            class MyStrategy(StrategyBase):
                def on_init(self):
                    # 订阅 K 线
                    self.subscribe_kline("BTC-USDT-SWAP", "1s")
                
                def on_kline(self, symbol, interval, bar):
                    # K 线回调
                    print(f"K线: {symbol} {interval} close={bar.close}")
                
                def on_tick(self):
                    # 每次循环调用
                    pass
            
            strategy = MyStrategy("my_strategy")
            strategy.register_account(api_key, secret_key, passphrase)
            strategy.run()
    )doc";
    
    // ==================== KlineBar ====================
    py::class_<KlineBar>(m, "KlineBar", "K线数据结构")
        .def(py::init<>())
        .def(py::init<int64_t, double, double, double, double, double>(),
             py::arg("timestamp"), py::arg("open"), py::arg("high"),
             py::arg("low"), py::arg("close"), py::arg("volume"))
        .def_readwrite("timestamp", &KlineBar::timestamp, "时间戳（毫秒）")
        .def_readwrite("open", &KlineBar::open, "开盘价")
        .def_readwrite("high", &KlineBar::high, "最高价")
        .def_readwrite("low", &KlineBar::low, "最低价")
        .def_readwrite("close", &KlineBar::close, "收盘价")
        .def_readwrite("volume", &KlineBar::volume, "成交量")
        .def("__repr__", [](const KlineBar& bar) {
            return "KlineBar(ts=" + std::to_string(bar.timestamp) + 
                   ", o=" + std::to_string(bar.open) +
                   ", h=" + std::to_string(bar.high) +
                   ", l=" + std::to_string(bar.low) +
                   ", c=" + std::to_string(bar.close) +
                   ", v=" + std::to_string(bar.volume) + ")";
        });
    
    // ==================== StrategyBase ====================
    py::class_<PyStrategyBase, PyStrategyTrampoline>(m, "StrategyBase", R"doc(
        策略基类
        
        Python 策略应继承此类，重写以下方法：
        - on_init(): 策略初始化
        - on_stop(): 策略停止
        - on_tick(): 每次循环调用
        - on_kline(symbol, interval, bar): K线回调
        - on_order_report(report): 订单回报回调
        - on_register_report(success, error_msg): 账户注册回报
    )doc")
        // 构造函数
        .def(py::init<const std::string&, size_t>(),
             py::arg("strategy_id"),
             py::arg("max_kline_bars") = 7200,
             "创建策略实例\n\nArgs:\n    strategy_id: 策略ID\n    max_kline_bars: K线最大存储数量（默认7200，即2小时1s K线）")
        
        // 连接管理
        .def("connect", &PyStrategyBase::connect, "连接到实盘服务器")
        .def("disconnect", &PyStrategyBase::disconnect, "断开连接")
        
        // 账户管理
        .def("register_account", &PyStrategyBase::register_account,
             py::arg("api_key"), py::arg("secret_key"), 
             py::arg("passphrase"), py::arg("is_testnet") = true,
             "注册账户")
        .def("unregister_account", &PyStrategyBase::unregister_account, "注销账户")
        
        // 订阅管理
        .def("subscribe_kline", &PyStrategyBase::subscribe_kline,
             py::arg("symbol"), py::arg("interval"),
             "订阅K线数据")
        .def("unsubscribe_kline", &PyStrategyBase::unsubscribe_kline,
             py::arg("symbol"), py::arg("interval"),
             "取消订阅K线")
        .def("subscribe_trades", &PyStrategyBase::subscribe_trades,
             py::arg("symbol"),
             "订阅交易数据")
        .def("unsubscribe_trades", &PyStrategyBase::unsubscribe_trades,
             py::arg("symbol"),
             "取消订阅交易数据")
        
        // 下单接口
        .def("send_swap_market_order", &PyStrategyBase::send_swap_market_order,
             py::arg("symbol"), py::arg("side"), py::arg("quantity"),
             py::arg("pos_side") = "",
             R"doc(
发送合约市价订单

Args:
    symbol: 交易对（如 BTC-USDT-SWAP）
    side: "buy" 或 "sell"
    quantity: 张数
    pos_side: 持仓方向 "long" 或 "short"（可选，默认根据 side 自动推断）

Returns:
    客户端订单ID
             )doc")
        .def("send_swap_limit_order", &PyStrategyBase::send_swap_limit_order,
             py::arg("symbol"), py::arg("side"), py::arg("quantity"),
             py::arg("price"), py::arg("pos_side") = "",
             "发送合约限价订单")
        
        // K线数据读取
        .def("get_klines", &PyStrategyBase::get_klines,
             py::arg("symbol"), py::arg("interval"),
             "获取所有K线数据")
        .def("get_closes", &PyStrategyBase::get_closes,
             py::arg("symbol"), py::arg("interval"),
             "获取收盘价数组")
        .def("get_recent_klines", &PyStrategyBase::get_recent_klines,
             py::arg("symbol"), py::arg("interval"), py::arg("n"),
             "获取最近n根K线")
        .def("get_last_kline", [](const PyStrategyBase& self, 
                                  const std::string& symbol, 
                                  const std::string& interval) -> py::object {
            KlineBar bar;
            if (self.get_last_kline(symbol, interval, bar)) {
                return py::cast(bar);
            }
            return py::none();
        }, py::arg("symbol"), py::arg("interval"),
           "获取最后一根K线，无数据返回None")
        .def("get_kline_count", &PyStrategyBase::get_kline_count,
             py::arg("symbol"), py::arg("interval"),
             "获取K线数量")
        
        // 运行控制
        .def("run", &PyStrategyBase::run, py::call_guard<py::gil_scoped_release>(),
             "运行策略（主循环）")
        .def("stop", &PyStrategyBase::stop, "停止策略")
        
        // 虚函数（供 Python 重写）
        .def("on_init", &PyStrategyBase::on_init, "策略初始化回调")
        .def("on_stop", &PyStrategyBase::on_stop, "策略停止回调")
        .def("on_tick", &PyStrategyBase::on_tick, "每次循环回调")
        .def("on_kline", &PyStrategyBase::on_kline,
             py::arg("symbol"), py::arg("interval"), py::arg("bar"),
             "K线回调")
        .def("on_order_report", &PyStrategyBase::on_order_report,
             py::arg("report"), "订单回报回调")
        .def("on_register_report", &PyStrategyBase::on_register_report,
             py::arg("success"), py::arg("error_msg"),
             "账户注册回报回调")
        
        // 日志
        .def("log_info", &PyStrategyBase::log_info, py::arg("msg"), "输出信息日志")
        .def("log_error", &PyStrategyBase::log_error, py::arg("msg"), "输出错误日志")
        
        // 属性
        .def_property_readonly("strategy_id", &PyStrategyBase::strategy_id, "策略ID")
        .def_property_readonly("is_running", &PyStrategyBase::is_running, "是否运行中")
        .def_property_readonly("is_account_registered", &PyStrategyBase::is_account_registered, "账户是否已注册")
        .def_property_readonly("kline_count", &PyStrategyBase::kline_count, "接收的K线数量")
        .def_property_readonly("order_count", &PyStrategyBase::order_count, "发送的订单数量")
        .def_property_readonly("report_count", &PyStrategyBase::report_count, "收到的回报数量");
}

