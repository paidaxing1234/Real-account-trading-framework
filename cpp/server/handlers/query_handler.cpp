/**
 * @file query_handler.cpp
 * @brief 查询处理模块实现 - 支持 OKX 和 Binance
 */

#include "query_handler.h"
#include "../config/server_config.h"
#include "../managers/account_manager.h"
#include "../managers/paper_trading_manager.h"
#include "../../adapters/okx/okx_rest_api.h"
#include "../../adapters/binance/binance_rest_api.h"
#include <iostream>
#include <algorithm>

namespace trading {
namespace server {

nlohmann::json handle_query(const nlohmann::json& request) {
    g_query_count++;

    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string exchange = request.value("exchange", "okx");  // 默认 OKX
    std::string query_type = request.value("query_type", "");
    auto params = request.value("params", nlohmann::json::object());

    std::string exchange_lower = exchange;
    std::transform(exchange_lower.begin(), exchange_lower.end(),
                   exchange_lower.begin(), ::tolower);

    std::cout << "[查询] 策略: " << strategy_id << " | 交易所: " << exchange
              << " | 类型: " << query_type << "\n";

    // PaperTrading 相关请求（不需要 API 认证）
    if (query_type == "start_paper_strategy") {
        return process_start_paper_strategy(request);
    }
    else if (query_type == "stop_paper_strategy") {
        return process_stop_paper_strategy(request);
    }
    else if (query_type == "get_paper_strategy_status") {
        return process_get_paper_strategy_status(request);
    }
    else if (query_type == "registered_accounts") {
        return {{"code", 0}, {"query_type", query_type},
                {"total_count", get_registered_strategy_count()},
                {"okx_count", get_okx_account_count()},
                {"binance_count", get_binance_account_count()}};
    }

    // ==================== Binance 查询 ====================
    if (exchange_lower == "binance") {
        binance::BinanceRestAPI* api = get_binance_api_for_strategy(strategy_id);
        if (!api) {
            return {{"code", -1}, {"error", "策略 " + strategy_id + " 未注册 Binance 账户"}};
        }

        try {
            if (query_type == "account" || query_type == "balance") {
                auto result = api->get_account_balance();
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "account_info") {
                auto result = api->get_account_info();
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "positions") {
                std::string symbol = params.value("symbol", "");
                auto result = api->get_positions(symbol);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "pending_orders" || query_type == "orders" || query_type == "open_orders") {
                std::string symbol = params.value("symbol", "");
                auto result = api->get_open_orders(symbol);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "order") {
                std::string symbol = params.value("symbol", "");
                int64_t order_id = params.value("order_id", int64_t(0));
                std::string client_order_id = params.value("client_order_id", "");
                auto result = api->get_order(symbol, order_id, client_order_id);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "all_orders") {
                std::string symbol = params.value("symbol", "");
                int64_t start_time = params.value("start_time", int64_t(0));
                int64_t end_time = params.value("end_time", int64_t(0));
                int limit = params.value("limit", 500);
                auto result = api->get_all_orders(symbol, start_time, end_time, limit);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "exchange_info" || query_type == "instruments") {
                std::string symbol = params.value("symbol", "");
                auto result = api->get_exchange_info(symbol);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "ticker") {
                std::string symbol = params.value("symbol", "");
                auto result = api->get_ticker_price(symbol);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "klines") {
                std::string symbol = params.value("symbol", "");
                std::string interval = params.value("interval", "1m");
                int limit = params.value("limit", 500);
                auto result = api->get_klines(symbol, interval, 0, 0, limit);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "depth") {
                std::string symbol = params.value("symbol", "");
                int limit = params.value("limit", 100);
                auto result = api->get_depth(symbol, limit);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "funding_rate") {
                std::string symbol = params.value("symbol", "");
                int limit = params.value("limit", 100);
                auto result = api->get_funding_rate(symbol, limit);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "leverage") {
                std::string symbol = params.value("symbol", "");
                int leverage = params.value("leverage", 1);
                auto result = api->change_leverage(symbol, leverage);
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else if (query_type == "position_mode") {
                auto result = api->get_position_mode();
                return {{"code", 0}, {"query_type", query_type}, {"exchange", "binance"}, {"data", result}};
            }
            else {
                return {{"code", -1}, {"error", "Binance 不支持的查询类型: " + query_type}};
            }
        } catch (const std::exception& e) {
            return {{"code", -1}, {"error", std::string("Binance 查询异常: ") + e.what()}};
        }
    }

    // ==================== OKX 查询（默认） ====================
    okx::OKXRestAPI* api = get_okx_api_for_strategy(strategy_id);
    if (!api) {
        return {{"code", -1}, {"error", "策略 " + strategy_id + " 未注册 OKX 账户"}};
    }

    try {
        if (query_type == "account" || query_type == "balance") {
            std::string ccy = params.value("currency", "");
            auto result = api->get_account_balance(ccy);
            return {{"code", 0}, {"query_type", query_type}, {"exchange", "okx"}, {"data", result}};
        }
        else if (query_type == "positions") {
            std::string inst_type = params.value("inst_type", "SWAP");
            std::string symbol = params.value("symbol", "");
            auto result = api->get_positions(inst_type, symbol);
            return {{"code", 0}, {"query_type", query_type}, {"exchange", "okx"}, {"data", result}};
        }
        else if (query_type == "pending_orders" || query_type == "orders") {
            std::string inst_type = params.value("inst_type", "SPOT");
            std::string symbol = params.value("symbol", "");
            auto result = api->get_pending_orders(inst_type, symbol);
            return {{"code", 0}, {"query_type", query_type}, {"exchange", "okx"}, {"data", result}};
        }
        else if (query_type == "order") {
            std::string symbol = params.value("symbol", "");
            std::string order_id = params.value("order_id", "");
            std::string client_order_id = params.value("client_order_id", "");
            auto result = api->get_order(symbol, order_id, client_order_id);
            return {{"code", 0}, {"query_type", query_type}, {"exchange", "okx"}, {"data", result}};
        }
        else if (query_type == "instruments") {
            std::string inst_type = params.value("inst_type", "SPOT");
            auto result = api->get_account_instruments(inst_type);
            return {{"code", 0}, {"query_type", query_type}, {"exchange", "okx"}, {"data", result}};
        }
        else {
            return {{"code", -1}, {"error", "OKX 不支持的查询类型: " + query_type}};
        }
    } catch (const std::exception& e) {
        return {{"code", -1}, {"error", std::string("OKX 查询异常: ") + e.what()}};
    }
}

} // namespace server
} // namespace trading
