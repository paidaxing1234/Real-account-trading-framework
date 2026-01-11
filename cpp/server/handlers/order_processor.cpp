/**
 * @file order_processor.cpp
 * @brief 订单处理模块实现 - 支持 OKX 和 Binance
 */

#include "order_processor.h"
#include "../config/server_config.h"
#include "../managers/account_manager.h"
#include "../../trading/account_registry.h"
#include "../../adapters/okx/okx_rest_api.h"
#include "../../adapters/binance/binance_rest_api.h"
#include "../../core/logger.h"
#include "../../network/websocket_server.h"
#include <iostream>
#include <chrono>
#include <algorithm>

using namespace trading::core;

namespace trading {
namespace server {

void process_place_order(ZmqServer& server, const nlohmann::json& order) {
    g_order_count++;

    std::string strategy_id = order.value("strategy_id", "unknown");
    std::string exchange = order.value("exchange", "okx");  // 默认 OKX
    std::string client_order_id = order.value("client_order_id", "");
    std::string symbol = order.value("symbol", "BTC-USDT");
    std::string side = order.value("side", "buy");
    std::string order_type = order.value("order_type", "limit");
    double price = order.value("price", 0.0);
    double quantity = order.value("quantity", 0.0);
    std::string td_mode = order.value("td_mode", "cash");
    std::string pos_side = order.value("pos_side", "");
    std::string tgt_ccy = order.value("tgt_ccy", "");

    // 转换为小写进行比较
    std::string exchange_lower = exchange;
    std::transform(exchange_lower.begin(), exchange_lower.end(),
                   exchange_lower.begin(), ::tolower);

    LOG_ORDER(client_order_id, "RECEIVED", "strategy=" + strategy_id + " exchange=" + exchange + " symbol=" + symbol + " side=" + side + " qty=" + std::to_string(quantity));
    LOG_AUDIT("ORDER_SUBMIT", "strategy=" + strategy_id + " exchange=" + exchange + " order_id=" + client_order_id + " symbol=" + symbol);

    std::cout << "[下单] " << strategy_id << " | " << exchange << " | " << symbol
              << " | " << side << " " << order_type
              << " | 数量: " << quantity << "\n";

    // 检查是否为模拟交易（策略ID以 paper_ 开头）
    bool is_paper_trading = (strategy_id.find("paper_") == 0);

    if (is_paper_trading) {
        // 模拟交易：直接返回成功回报
        std::cout << "[模拟下单] ✓ " << client_order_id << " | " << side << " " << quantity << "\n";
        LOG_ORDER(client_order_id, "PAPER_FILLED", "模拟成交");
        g_order_success++;

        nlohmann::json report = make_order_report(
            strategy_id, client_order_id, "PAPER_" + client_order_id, symbol,
            "filled", price > 0 ? price : 93700.0, quantity, 0.0, ""
        );
        report["side"] = side;  // 添加方向字段
        report["exchange"] = exchange;
        server.publish_report(report);

        // 同时发送到前端 WebSocket
        if (g_frontend_server) {
            g_frontend_server->send_event("order_report", report);
        }
        return;
    }

    // ==================== Binance 下单 ====================
    if (exchange_lower == "binance") {
        binance::BinanceRestAPI* api = get_binance_api_for_strategy(strategy_id);
        if (!api) {
            std::string error_msg = "策略 " + strategy_id + " 未注册 Binance 账户，且无默认账户";
            std::cout << "[下单] ✗ " << error_msg << "\n";
            LOG_ORDER(client_order_id, "REJECTED", "reason=" + error_msg);
            g_order_failed++;

            nlohmann::json report = make_order_report(
                strategy_id, client_order_id, "", symbol,
                "rejected", price, quantity, 0.0, error_msg
            );
            report["exchange"] = exchange;
            server.publish_report(report);
            return;
        }

        bool success = false;
        std::string exchange_order_id;
        std::string error_msg;

        try {
            // 转换订单方向
            binance::OrderSide binance_side = (side == "buy" || side == "BUY") ?
                binance::OrderSide::BUY : binance::OrderSide::SELL;

            // 转换订单类型
            binance::OrderType binance_type = binance::OrderType::LIMIT;
            if (order_type == "market" || order_type == "MARKET") {
                binance_type = binance::OrderType::MARKET;
            }

            // 转换持仓方向
            binance::PositionSide binance_pos_side = binance::PositionSide::BOTH;
            if (pos_side == "long" || pos_side == "LONG") {
                binance_pos_side = binance::PositionSide::LONG;
            } else if (pos_side == "short" || pos_side == "SHORT") {
                binance_pos_side = binance::PositionSide::SHORT;
            }

            auto send_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();

            std::string price_str = price > 0 ? std::to_string(price) : "";
            auto response = api->place_order(
                symbol,
                binance_side,
                binance_type,
                std::to_string(quantity),
                price_str,
                binance::TimeInForce::GTC,
                binance_pos_side,
                client_order_id
            );

            auto resp_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();

            // Binance 成功响应包含 orderId
            if (response.contains("orderId")) {
                success = true;
                exchange_order_id = std::to_string(response["orderId"].get<int64_t>());
                g_order_success++;
                LOG_ORDER(client_order_id, "ACCEPTED", "exchange_id=" + exchange_order_id);
                std::cout << "[Binance响应] 时间戳: " << resp_ns << " ns | 订单ID: " << client_order_id
                          << " | 往返: " << (resp_ns - send_ns) / 1000000 << " ms | ✓\n";
            } else {
                // 错误响应
                error_msg = response.value("msg", "Unknown error");
                int code = response.value("code", 0);
                error_msg = "Code " + std::to_string(code) + ": " + error_msg;
                g_order_failed++;
                LOG_ORDER(client_order_id, "REJECTED", "error=" + error_msg);
                std::cout << "[Binance响应] 时间戳: " << resp_ns << " ns | 订单ID: " << client_order_id
                          << " | 往返: " << (resp_ns - send_ns) / 1000000 << " ms | ✗ " << error_msg << "\n";
            }
        } catch (const std::exception& e) {
            error_msg = std::string("异常: ") + e.what();
            g_order_failed++;
            LOG_ORDER(client_order_id, "ERROR", error_msg);
        }

        nlohmann::json report = make_order_report(
            strategy_id, client_order_id, exchange_order_id, symbol,
            success ? "accepted" : "rejected",
            price, quantity, 0.0, error_msg
        );
        report["exchange"] = exchange;
        server.publish_report(report);
        return;
    }

    // ==================== OKX 下单（默认） ====================
    okx::OKXRestAPI* api = get_okx_api_for_strategy(strategy_id);
    if (!api) {
        std::string error_msg = "策略 " + strategy_id + " 未注册账户，且无默认账户";
        std::cout << "[下单] ✗ " << error_msg << "\n";
        LOG_ORDER(client_order_id, "REJECTED", "reason=" + error_msg);
        g_order_failed++;

        nlohmann::json report = make_order_report(
            strategy_id, client_order_id, "", symbol,
            "rejected", price, quantity, 0.0, error_msg
        );
        server.publish_report(report);
        return;
    }

    bool success = false;
    std::string exchange_order_id;
    std::string error_msg;

    try {
        okx::PlaceOrderRequest req;
        req.inst_id = symbol;
        req.td_mode = td_mode;
        req.side = side;
        req.ord_type = order_type;
        req.sz = std::to_string(quantity);
        if (price > 0) req.px = std::to_string(price);
        if (!pos_side.empty()) req.pos_side = pos_side;
        if (!tgt_ccy.empty()) req.tgt_ccy = tgt_ccy;
        if (!client_order_id.empty()) req.cl_ord_id = client_order_id;

        if (order.contains("tag") && !order["tag"].is_null()) {
            req.tag = order["tag"].get<std::string>();
        }

        if (order.contains("attach_algo_ords") && order["attach_algo_ords"].is_array()) {
            for (const auto& algo_json : order["attach_algo_ords"]) {
                okx::AttachAlgoOrder algo;
                if (algo_json.contains("tp_trigger_px") && !algo_json["tp_trigger_px"].is_null()) {
                    algo.tp_trigger_px = algo_json["tp_trigger_px"].get<std::string>();
                    algo.tp_ord_px = algo_json.value("tp_ord_px", "-1");
                    algo.tp_trigger_px_type = algo_json.value("tp_trigger_px_type", "last");
                }
                if (algo_json.contains("sl_trigger_px") && !algo_json["sl_trigger_px"].is_null()) {
                    algo.sl_trigger_px = algo_json["sl_trigger_px"].get<std::string>();
                    algo.sl_ord_px = algo_json.value("sl_ord_px", "-1");
                    algo.sl_trigger_px_type = algo_json.value("sl_trigger_px_type", "last");
                }
                if (!algo.tp_trigger_px.empty() || !algo.sl_trigger_px.empty()) {
                    req.attach_algo_ords.push_back(algo);
                }
            }
        }

        auto send_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        auto response = api->place_order_advanced(req);
        auto resp_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();

        if (response.is_success()) {
            success = true;
            exchange_order_id = response.ord_id;
            g_order_success++;
            LOG_ORDER(client_order_id, "ACCEPTED", "exchange_id=" + exchange_order_id);
            std::cout << "[OKX响应] 时间戳: " << resp_ns << " ns | 订单ID: " << client_order_id
                      << " | 往返: " << (resp_ns - send_ns) / 1000000 << " ms | ✓\n";
        } else {
            error_msg = response.s_msg.empty() ? response.msg : response.s_msg;
            g_order_failed++;
            LOG_ORDER(client_order_id, "REJECTED", "error=" + error_msg);
            std::cout << "[OKX响应] 时间戳: " << resp_ns << " ns | 订单ID: " << client_order_id
                      << " | 往返: " << (resp_ns - send_ns) / 1000000 << " ms | ✗ " << error_msg << "\n";
        }
    } catch (const std::exception& e) {
        error_msg = std::string("异常: ") + e.what();
        g_order_failed++;
        LOG_ORDER(client_order_id, "ERROR", error_msg);
    }

    nlohmann::json report = make_order_report(
        strategy_id, client_order_id, exchange_order_id, symbol,
        success ? "accepted" : "rejected",
        price, quantity, 0.0, error_msg
    );
    server.publish_report(report);
}

void process_batch_orders(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string batch_id = request.value("batch_id", "");

    std::cout << "[批量下单] " << strategy_id << " | " << batch_id << "\n";

    okx::OKXRestAPI* api = get_okx_api_for_strategy(strategy_id);
    if (!api) {
        nlohmann::json report = {
            {"type", "batch_report"}, {"strategy_id", strategy_id},
            {"batch_id", batch_id}, {"status", "rejected"},
            {"error_msg", "策略未注册账户"}, {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }

    if (!request.contains("orders") || !request["orders"].is_array()) {
        nlohmann::json report = {
            {"type", "batch_report"}, {"strategy_id", strategy_id},
            {"batch_id", batch_id}, {"status", "rejected"},
            {"error_msg", "无效的订单数组"}, {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }

    std::vector<okx::PlaceOrderRequest> orders;
    for (const auto& ord : request["orders"]) {
        okx::PlaceOrderRequest req;
        req.inst_id = ord.value("symbol", "BTC-USDT-SWAP");
        req.td_mode = ord.value("td_mode", "cross");
        req.side = ord.value("side", "buy");
        req.ord_type = ord.value("order_type", "limit");
        req.sz = std::to_string(ord.value("quantity", 0.0));

        double px = ord.value("price", 0.0);
        if (px > 0) req.px = std::to_string(px);

        req.pos_side = ord.value("pos_side", "");
        req.cl_ord_id = ord.value("client_order_id", "");

        if (ord.contains("tag") && !ord["tag"].is_null()) {
            req.tag = ord["tag"].get<std::string>();
        }

        if (ord.contains("attach_algo_ords") && ord["attach_algo_ords"].is_array()) {
            for (const auto& algo_json : ord["attach_algo_ords"]) {
                okx::AttachAlgoOrder algo;
                if (algo_json.contains("tp_trigger_px") && !algo_json["tp_trigger_px"].is_null()) {
                    algo.tp_trigger_px = algo_json["tp_trigger_px"].get<std::string>();
                    algo.tp_ord_px = algo_json.value("tp_ord_px", "-1");
                    algo.tp_trigger_px_type = algo_json.value("tp_trigger_px_type", "last");
                }
                if (algo_json.contains("sl_trigger_px") && !algo_json["sl_trigger_px"].is_null()) {
                    algo.sl_trigger_px = algo_json["sl_trigger_px"].get<std::string>();
                    algo.sl_ord_px = algo_json.value("sl_ord_px", "-1");
                    algo.sl_trigger_px_type = algo_json.value("sl_trigger_px_type", "last");
                }
                if (!algo.tp_trigger_px.empty() || !algo.sl_trigger_px.empty()) {
                    req.attach_algo_ords.push_back(algo);
                }
            }
        }

        orders.push_back(req);
    }

    try {
        auto response = api->place_batch_orders(orders);

        int success_count = 0, fail_count = 0;
        nlohmann::json results = nlohmann::json::array();

        if (response.contains("data") && response["data"].is_array()) {
            for (const auto& data : response["data"]) {
                bool ok = data["sCode"] == "0";
                if (ok) success_count++; else fail_count++;

                results.push_back({
                    {"client_order_id", data.value("clOrdId", "")},
                    {"exchange_order_id", data.value("ordId", "")},
                    {"status", ok ? "accepted" : "rejected"},
                    {"error_msg", data.value("sMsg", "")}
                });
            }
        }

        g_order_count += orders.size();
        g_order_success += success_count;
        g_order_failed += fail_count;

        std::cout << "[批量下单] 成功: " << success_count << " 失败: " << fail_count << "\n";

        nlohmann::json report = {
            {"type", "batch_report"}, {"strategy_id", strategy_id},
            {"batch_id", batch_id},
            {"status", fail_count == 0 ? "accepted" : (success_count > 0 ? "partial" : "rejected")},
            {"results", results}, {"success_count", success_count}, {"fail_count", fail_count},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);

    } catch (const std::exception& e) {
        nlohmann::json report = {
            {"type", "batch_report"}, {"strategy_id", strategy_id},
            {"batch_id", batch_id}, {"status", "rejected"},
            {"error_msg", std::string("异常: ") + e.what()},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
    }
}

void process_cancel_order(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string exchange = request.value("exchange", "okx");  // 默认 OKX
    std::string symbol = request.value("symbol", "");
    std::string order_id = request.value("order_id", "");
    std::string client_order_id = request.value("client_order_id", "");

    std::string exchange_lower = exchange;
    std::transform(exchange_lower.begin(), exchange_lower.end(),
                   exchange_lower.begin(), ::tolower);

    std::string cancel_id = order_id.empty() ? client_order_id : order_id;
    LOG_ORDER(cancel_id, "CANCEL_REQUEST", "strategy=" + strategy_id + " exchange=" + exchange + " symbol=" + symbol);
    LOG_AUDIT("ORDER_CANCEL", "strategy=" + strategy_id + " exchange=" + exchange + " order_id=" + cancel_id);

    std::cout << "[撤单] " << strategy_id << " | " << exchange << " | " << symbol
              << " | " << cancel_id << "\n";

    // ==================== Binance 撤单 ====================
    if (exchange_lower == "binance") {
        binance::BinanceRestAPI* api = get_binance_api_for_strategy(strategy_id);
        if (!api) {
            nlohmann::json report = {
                {"type", "cancel_report"}, {"strategy_id", strategy_id},
                {"exchange", exchange},
                {"order_id", order_id}, {"client_order_id", client_order_id},
                {"status", "rejected"}, {"error_msg", "策略未注册 Binance 账户"},
                {"timestamp", current_timestamp_ms()}
            };
            server.publish_report(report);
            return;
        }

        bool success = false;
        std::string error_msg;

        try {
            int64_t binance_order_id = 0;
            if (!order_id.empty()) {
                try {
                    binance_order_id = std::stoll(order_id);
                } catch (...) {}
            }

            auto response = api->cancel_order(symbol, binance_order_id, client_order_id);

            // Binance 成功响应包含 orderId
            if (response.contains("orderId")) {
                success = true;
                LOG_ORDER(cancel_id, "CANCELLED", "success");
                std::cout << "[撤单] ✓ Binance 成功\n";
            } else {
                error_msg = response.value("msg", "Unknown error");
                int code = response.value("code", 0);
                error_msg = "Code " + std::to_string(code) + ": " + error_msg;
                LOG_ORDER(cancel_id, "CANCEL_FAILED", "error=" + error_msg);
            }
        } catch (const std::exception& e) {
            error_msg = std::string("异常: ") + e.what();
            LOG_ORDER(cancel_id, "CANCEL_ERROR", error_msg);
        }

        if (!success) std::cout << "[撤单] ✗ " << error_msg << "\n";

        nlohmann::json report = {
            {"type", "cancel_report"}, {"strategy_id", strategy_id},
            {"exchange", exchange},
            {"order_id", order_id}, {"client_order_id", client_order_id},
            {"status", success ? "cancelled" : "rejected"},
            {"error_msg", error_msg}, {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }

    // ==================== OKX 撤单（默认） ====================
    okx::OKXRestAPI* api = get_okx_api_for_strategy(strategy_id);
    if (!api) {
        nlohmann::json report = {
            {"type", "cancel_report"}, {"strategy_id", strategy_id},
            {"order_id", order_id}, {"client_order_id", client_order_id},
            {"status", "rejected"}, {"error_msg", "策略未注册账户"},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }

    bool success = false;
    std::string error_msg;

    try {
        auto response = api->cancel_order(symbol, order_id, client_order_id);

        if (response["code"] == "0" && response.contains("data") && !response["data"].empty()) {
            auto& data = response["data"][0];
            if (data["sCode"] == "0") {
                success = true;
                LOG_ORDER(cancel_id, "CANCELLED", "success");
                std::cout << "[撤单] ✓ 成功\n";
            } else {
                error_msg = data.value("sMsg", "Unknown error");
                LOG_ORDER(cancel_id, "CANCEL_FAILED", "error=" + error_msg);
            }
        } else {
            error_msg = response.value("msg", "API error");
            LOG_ORDER(cancel_id, "CANCEL_FAILED", "error=" + error_msg);
        }
    } catch (const std::exception& e) {
        error_msg = std::string("异常: ") + e.what();
        LOG_ORDER(cancel_id, "CANCEL_ERROR", error_msg);
    }

    if (!success) std::cout << "[撤单] ✗ " << error_msg << "\n";

    nlohmann::json report = {
        {"type", "cancel_report"}, {"strategy_id", strategy_id},
        {"order_id", order_id}, {"client_order_id", client_order_id},
        {"status", success ? "cancelled" : "rejected"},
        {"error_msg", error_msg}, {"timestamp", current_timestamp_ms()}
    };
    server.publish_report(report);
}

void process_batch_cancel(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string symbol = request.value("symbol", "");

    okx::OKXRestAPI* api = get_okx_api_for_strategy(strategy_id);
    if (!api) {
        nlohmann::json report = {
            {"type", "batch_cancel_report"}, {"strategy_id", strategy_id},
            {"status", "rejected"}, {"error_msg", "策略未注册账户"},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }

    std::vector<std::string> order_ids;
    if (request.contains("order_ids") && request["order_ids"].is_array()) {
        for (const auto& id : request["order_ids"]) {
            order_ids.push_back(id.get<std::string>());
        }
    }

    std::cout << "[批量撤单] " << strategy_id << " | " << symbol
              << " | " << order_ids.size() << "个订单\n";

    try {
        auto response = api->cancel_batch_orders(order_ids, symbol);

        int success_count = 0, fail_count = 0;
        nlohmann::json results = nlohmann::json::array();

        if (response.contains("data") && response["data"].is_array()) {
            for (const auto& data : response["data"]) {
                bool ok = data["sCode"] == "0";
                if (ok) success_count++; else fail_count++;

                results.push_back({
                    {"order_id", data.value("ordId", "")},
                    {"status", ok ? "cancelled" : "rejected"},
                    {"error_msg", data.value("sMsg", "")}
                });
            }
        }

        std::cout << "[批量撤单] 成功: " << success_count << " 失败: " << fail_count << "\n";

        nlohmann::json report = {
            {"type", "batch_cancel_report"}, {"strategy_id", strategy_id},
            {"symbol", symbol}, {"results", results},
            {"success_count", success_count}, {"fail_count", fail_count},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);

    } catch (const std::exception& e) {
        nlohmann::json report = {
            {"type", "batch_cancel_report"}, {"strategy_id", strategy_id},
            {"status", "rejected"}, {"error_msg", std::string("异常: ") + e.what()},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
    }
}

void process_amend_order(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string symbol = request.value("symbol", "");
    std::string order_id = request.value("order_id", "");
    std::string client_order_id = request.value("client_order_id", "");
    std::string new_px = request.value("new_price", "");
    std::string new_sz = request.value("new_quantity", "");

    std::cout << "[修改订单] " << strategy_id << " | " << symbol << "\n";

    okx::OKXRestAPI* api = get_okx_api_for_strategy(strategy_id);
    if (!api) {
        nlohmann::json report = {
            {"type", "amend_report"}, {"strategy_id", strategy_id},
            {"order_id", order_id}, {"client_order_id", client_order_id},
            {"status", "rejected"}, {"error_msg", "策略未注册账户"},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }

    bool success = false;
    std::string error_msg;

    try {
        auto response = api->amend_order(symbol, order_id, client_order_id, new_sz, new_px);

        if (response["code"] == "0" && response.contains("data") && !response["data"].empty()) {
            auto& data = response["data"][0];
            if (data["sCode"] == "0") {
                success = true;
                std::cout << "[修改订单] ✓ 成功\n";
            } else {
                error_msg = data.value("sMsg", "Unknown error");
            }
        } else {
            error_msg = response.value("msg", "API error");
        }
    } catch (const std::exception& e) {
        error_msg = std::string("异常: ") + e.what();
    }

    if (!success) std::cout << "[修改订单] ✗ " << error_msg << "\n";

    nlohmann::json report = {
        {"type", "amend_report"}, {"strategy_id", strategy_id},
        {"order_id", order_id}, {"client_order_id", client_order_id},
        {"status", success ? "amended" : "rejected"},
        {"error_msg", error_msg}, {"timestamp", current_timestamp_ms()}
    };
    server.publish_report(report);
}

void process_register_account(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "");
    std::string exchange = request.value("exchange", "okx");
    std::string api_key = request.value("api_key", "");
    std::string secret_key = request.value("secret_key", "");
    std::string passphrase = request.value("passphrase", "");
    bool is_testnet = request.value("is_testnet", true);

    LOG_AUDIT("ACCOUNT_REGISTER", "strategy=" + strategy_id + " exchange=" + exchange + " testnet=" + (is_testnet ? "true" : "false"));
    std::cout << "[账户注册] 策略: " << strategy_id << " | 交易所: " << exchange << "\n";

    nlohmann::json report;
    report["type"] = "register_report";
    report["strategy_id"] = strategy_id;
    report["exchange"] = exchange;
    report["timestamp"] = current_timestamp_ms();

    if (api_key.empty() || secret_key.empty()) {
        report["status"] = "rejected";
        report["error_msg"] = "缺少必要参数 (api_key, secret_key)";
        std::cout << "[账户注册] ✗ 参数不完整\n";
    } else {
        ExchangeType ex_type = string_to_exchange_type(exchange);
        bool success = false;

        if (strategy_id.empty()) {
            if (ex_type == ExchangeType::OKX) {
                g_account_registry.set_default_okx_account(api_key, secret_key, passphrase, is_testnet);
                success = true;
            } else if (ex_type == ExchangeType::BINANCE) {
                g_account_registry.set_default_binance_account(api_key, secret_key, is_testnet);
                success = true;
            }
            std::cout << "[账户注册] ✓ 默认账户注册成功\n";
        } else {
            success = g_account_registry.register_account(
                strategy_id, ex_type, api_key, secret_key, passphrase, is_testnet
            );
            if (success) {
                std::cout << "[账户注册] ✓ 策略 " << strategy_id << " 注册成功\n";
            }
        }

        if (success) {
            report["status"] = "registered";
            report["error_msg"] = "";
        } else {
            report["status"] = "rejected";
            report["error_msg"] = "注册失败";
        }
    }

    server.publish_report(report);
}

void process_unregister_account(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "");
    std::string exchange = request.value("exchange", "okx");

    std::cout << "[账户注销] 策略: " << strategy_id << " | 交易所: " << exchange << "\n";

    nlohmann::json report;
    report["type"] = "unregister_report";
    report["strategy_id"] = strategy_id;
    report["exchange"] = exchange;
    report["timestamp"] = current_timestamp_ms();

    if (strategy_id.empty()) {
        report["status"] = "rejected";
        report["error_msg"] = "缺少 strategy_id";
    } else {
        ExchangeType ex_type = string_to_exchange_type(exchange);
        bool success = g_account_registry.unregister_account(strategy_id, ex_type);
        report["status"] = success ? "unregistered" : "rejected";
        report["error_msg"] = success ? "" : "策略未找到";
    }

    server.publish_report(report);
}

void process_order_request(ZmqServer& server, const nlohmann::json& request) {
    std::string type = request.value("type", "order_request");

    if (type == "order_request") {
        process_place_order(server, request);
    } else if (type == "batch_order_request") {
        process_batch_orders(server, request);
    } else if (type == "cancel_request") {
        process_cancel_order(server, request);
    } else if (type == "batch_cancel_request") {
        process_batch_cancel(server, request);
    } else if (type == "amend_request") {
        process_amend_order(server, request);
    } else if (type == "register_account") {
        process_register_account(server, request);
    } else if (type == "unregister_account") {
        process_unregister_account(server, request);
    } else {
        std::cout << "[订单] 未知请求类型: " << type << "\n";
    }
}

} // namespace server
} // namespace trading
