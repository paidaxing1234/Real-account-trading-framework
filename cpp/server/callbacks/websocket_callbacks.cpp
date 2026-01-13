/**
 * @file websocket_callbacks.cpp
 * @brief WebSocket 回调设置模块实现
 */

#include "websocket_callbacks.h"
#include "../config/server_config.h"
#include "../managers/redis_recorder.h"
#include "../../adapters/okx/okx_websocket.h"
#include "../../adapters/binance/binance_websocket.h"
#include "../../network/websocket_server.h"

using namespace trading::okx;

namespace trading {
namespace server {

// 辅助函数：去掉 -SWAP 后缀用于前端显示
static std::string strip_swap_suffix(const std::string& symbol) {
    const std::string suffix = "-SWAP";
    if (symbol.size() > suffix.size() &&
        symbol.compare(symbol.size() - suffix.size(), suffix.size(), suffix) == 0) {
        return symbol.substr(0, symbol.size() - suffix.size());
    }
    return symbol;
}

void setup_websocket_callbacks(ZmqServer& zmq_server) {
    // Trades 回调（公共频道）
    if (g_ws_public) {
        // OKX Ticker 回调（原始JSON格式）
        g_ws_public->set_ticker_callback([&zmq_server](const nlohmann::json& raw) {
            g_okx_ticker_count++;

            std::string symbol = raw.value("instId", "");
            std::string display_symbol = strip_swap_suffix(symbol);

            nlohmann::json msg = {
                {"type", "ticker"},
                {"exchange", "okx"},
                {"symbol", display_symbol},
                {"timestamp_ns", current_timestamp_ns()}
            };

            // 从原始数据中提取字段
            if (raw.contains("last")) msg["price"] = std::stod(raw["last"].get<std::string>());
            if (raw.contains("ts")) msg["timestamp"] = std::stoll(raw["ts"].get<std::string>());
            if (raw.contains("high24h")) msg["high_24h"] = std::stod(raw["high24h"].get<std::string>());
            if (raw.contains("low24h")) msg["low_24h"] = std::stod(raw["low24h"].get<std::string>());
            if (raw.contains("open24h")) msg["open_24h"] = std::stod(raw["open24h"].get<std::string>());
            if (raw.contains("vol24h")) msg["volume_24h"] = std::stod(raw["vol24h"].get<std::string>());

            // 发布到 OKX 专用通道
            zmq_server.publish_okx_market(msg, MessageType::TICKER);
            // 同时发布到统一通道（兼容旧客户端）
            zmq_server.publish_ticker(msg);

            if (g_frontend_server) {
                g_frontend_server->send_event("ticker", msg);
            }
        });

        // OKX Trade 回调（原始JSON格式）
        g_ws_public->set_trade_callback([&zmq_server](const nlohmann::json& raw) {
            g_trade_count++;
            g_okx_trade_count++;

            std::string symbol = raw.value("symbol", raw.value("instId", ""));

            nlohmann::json msg = {
                {"type", "trade"},
                {"exchange", "okx"},
                {"symbol", symbol},
                {"timestamp_ns", current_timestamp_ns()}
            };

            if (raw.contains("tradeId")) msg["trade_id"] = raw["tradeId"].get<std::string>();
            if (raw.contains("px")) msg["price"] = std::stod(raw["px"].get<std::string>());
            if (raw.contains("sz")) msg["quantity"] = std::stod(raw["sz"].get<std::string>());
            if (raw.contains("side")) msg["side"] = raw["side"].get<std::string>();
            if (raw.contains("ts")) msg["timestamp"] = std::stoll(raw["ts"].get<std::string>());

            // 发布到 OKX 专用通道
            zmq_server.publish_okx_market(msg, MessageType::TRADE);
            // 同时发布到统一通道
            zmq_server.publish_ticker(msg);

            // Redis 录制 Trade 数据
            if (g_redis_recorder && g_redis_recorder->is_running()) {
                g_redis_recorder->record_trade(symbol, "okx", msg);
            }

            // 转发给前端 WebSocket（每10条发送一次，避免过多数据）
            static int trade_counter = 0;
            if (++trade_counter % 10 == 0 && g_frontend_server) {
                g_frontend_server->send_event("trade", msg);
            }
        });

        // OKX 深度数据回调（原始JSON格式）- 注意：目前OKX没有订阅深度
        g_ws_public->set_orderbook_callback([&zmq_server](const nlohmann::json& raw) {
            g_orderbook_count++;

            std::string symbol = raw.value("symbol", "");
            std::string channel = raw.value("channel", "books5");
            std::string action = raw.value("action", "snapshot");

            nlohmann::json bids = nlohmann::json::array();
            nlohmann::json asks = nlohmann::json::array();

            if (raw.contains("bids") && raw["bids"].is_array()) {
                for (const auto& bid : raw["bids"]) {
                    if (bid.is_array() && bid.size() >= 2) {
                        double price = std::stod(bid[0].get<std::string>());
                        double size = std::stod(bid[1].get<std::string>());
                        bids.push_back({price, size});
                    }
                }
            }

            if (raw.contains("asks") && raw["asks"].is_array()) {
                for (const auto& ask : raw["asks"]) {
                    if (ask.is_array() && ask.size() >= 2) {
                        double price = std::stod(ask[0].get<std::string>());
                        double size = std::stod(ask[1].get<std::string>());
                        asks.push_back({price, size});
                    }
                }
            }

            nlohmann::json msg = {
                {"type", "orderbook"},
                {"exchange", "okx"},
                {"symbol", symbol},
                {"channel", channel},
                {"action", action},
                {"bids", bids},
                {"asks", asks},
                {"timestamp_ns", current_timestamp_ns()}
            };

            if (raw.contains("ts")) msg["timestamp"] = std::stoll(raw["ts"].get<std::string>());

            // 计算最优价格
            if (!bids.empty()) {
                msg["best_bid_price"] = bids[0][0];
                msg["best_bid_size"] = bids[0][1];
            }
            if (!asks.empty()) {
                msg["best_ask_price"] = asks[0][0];
                msg["best_ask_size"] = asks[0][1];
            }
            if (!bids.empty() && !asks.empty()) {
                double best_bid = bids[0][0].get<double>();
                double best_ask = asks[0][0].get<double>();
                msg["mid_price"] = (best_bid + best_ask) / 2.0;
                msg["spread"] = best_ask - best_bid;
            }

            // 发布到 OKX 专用通道
            zmq_server.publish_okx_market(msg, MessageType::DEPTH);
            // 同时发布到统一通道
            zmq_server.publish_depth(msg);

            // Redis 录制 Orderbook 数据
            if (g_redis_recorder && g_redis_recorder->is_running()) {
                g_redis_recorder->record_orderbook(symbol, "okx", msg);
            }
        });

        // OKX 资金费率回调（原始JSON格式）
        g_ws_public->set_funding_rate_callback([&zmq_server](const nlohmann::json& raw) {
            g_funding_rate_count++;

            std::string inst_id = raw.value("instId", "");
            std::string inst_type = raw.value("instType", "");

            nlohmann::json msg = {
                {"type", "funding_rate"},
                {"exchange", "okx"},
                {"symbol", inst_id},
                {"inst_type", inst_type},
                {"timestamp_ns", current_timestamp_ns()}
            };

            // 从原始数据中提取字段（OKX资金费率字段）
            if (raw.contains("fundingRate")) msg["funding_rate"] = std::stod(raw["fundingRate"].get<std::string>());
            if (raw.contains("nextFundingRate")) msg["next_funding_rate"] = std::stod(raw["nextFundingRate"].get<std::string>());
            if (raw.contains("fundingTime")) msg["funding_time"] = std::stoll(raw["fundingTime"].get<std::string>());
            if (raw.contains("nextFundingTime")) msg["next_funding_time"] = std::stoll(raw["nextFundingTime"].get<std::string>());
            if (raw.contains("minFundingRate")) msg["min_funding_rate"] = std::stod(raw["minFundingRate"].get<std::string>());
            if (raw.contains("maxFundingRate")) msg["max_funding_rate"] = std::stod(raw["maxFundingRate"].get<std::string>());
            if (raw.contains("interestRate")) msg["interest_rate"] = std::stod(raw["interestRate"].get<std::string>());
            if (raw.contains("impactValue")) msg["impact_value"] = std::stod(raw["impactValue"].get<std::string>());
            if (raw.contains("premium")) msg["premium"] = std::stod(raw["premium"].get<std::string>());
            if (raw.contains("settState")) msg["sett_state"] = raw["settState"].get<std::string>();
            if (raw.contains("settFundingRate")) msg["sett_funding_rate"] = std::stod(raw["settFundingRate"].get<std::string>());
            if (raw.contains("method")) msg["method"] = raw["method"].get<std::string>();
            if (raw.contains("formulaType")) msg["formula_type"] = raw["formulaType"].get<std::string>();
            if (raw.contains("ts")) msg["timestamp"] = std::stoll(raw["ts"].get<std::string>());

            // 发布到 OKX 专用通道
            zmq_server.publish_okx_market(msg, MessageType::TICKER);
            // 同时发布到统一通道
            zmq_server.publish_ticker(msg);

            // Redis 录制 Funding Rate 数据
            if (g_redis_recorder && g_redis_recorder->is_running()) {
                g_redis_recorder->record_funding_rate(inst_id, "okx", msg);
            }
        });
    }

    // OKX K线回调（原始JSON格式）
    if (g_ws_business) {
        g_ws_business->set_kline_callback([&zmq_server](const nlohmann::json& raw) {
            // 检查是否为已确认的K线（confirm字段）
            if (raw.contains("confirm") && raw["confirm"].get<std::string>() != "1") {
                return;
            }

            g_kline_count++;
            g_okx_kline_count++;

            std::string symbol = raw.value("symbol", "");
            std::string interval = raw.value("interval", "");

            nlohmann::json msg = {
                {"type", "kline"},
                {"exchange", "okx"},
                {"symbol", symbol},
                {"interval", interval},
                {"timestamp_ns", current_timestamp_ns()}
            };

            // 从原始数据中提取字段
            if (raw.contains("o")) msg["open"] = std::stod(raw["o"].get<std::string>());
            if (raw.contains("h")) msg["high"] = std::stod(raw["h"].get<std::string>());
            if (raw.contains("l")) msg["low"] = std::stod(raw["l"].get<std::string>());
            if (raw.contains("c")) msg["close"] = std::stod(raw["c"].get<std::string>());
            if (raw.contains("vol")) msg["volume"] = std::stod(raw["vol"].get<std::string>());
            if (raw.contains("ts")) msg["timestamp"] = std::stoll(raw["ts"].get<std::string>());

            // 发布到 OKX 专用通道
            zmq_server.publish_okx_market(msg, MessageType::KLINE);
            // 同时发布到统一通道
            zmq_server.publish_kline(msg);

            // Redis 录制 K线 数据
            if (g_redis_recorder && g_redis_recorder->is_running()) {
                g_redis_recorder->record_kline(symbol, interval, "okx", msg);
            }
        });
    }

    // 订单推送回调（私有频道）
    if (g_ws_private) {
        g_ws_private->set_order_callback([&zmq_server](const Order::Ptr& order) {
            nlohmann::json msg = {
                {"type", "order_update"},
                {"exchange", "okx"},
                {"symbol", order->symbol()},
                {"exchange_order_id", order->exchange_order_id()},
                {"client_order_id", order->client_order_id()},
                {"side", order->side() == OrderSide::BUY ? "buy" : "sell"},
                {"order_type", order->order_type() == OrderType::MARKET ? "market" : "limit"},
                {"price", order->price()},
                {"quantity", order->quantity()},
                {"filled_quantity", order->filled_quantity()},
                {"filled_price", order->filled_price()},
                {"status", order_state_to_string(order->state())},
                {"timestamp", current_timestamp_ms()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            zmq_server.publish_report(msg);

            // 发送到前端 WebSocket（实盘订单更新）
            if (g_frontend_server) {
                g_frontend_server->send_event("order_update", msg);
            }
        });

        // 账户更新回调
        g_ws_private->set_account_callback([&zmq_server](const nlohmann::json& acc) {
            nlohmann::json msg = {
                {"type", "account_update"},
                {"exchange", "okx"},
                {"data", acc},
                {"timestamp", current_timestamp_ms()}
            };
            zmq_server.publish_report(msg);

            // 发送到前端 WebSocket（实盘账户更新）
            if (g_frontend_server) {
                g_frontend_server->send_event("account_update", msg);
            }
        });

        // 持仓更新回调
        g_ws_private->set_position_callback([&zmq_server](const nlohmann::json& pos) {
            nlohmann::json msg = {
                {"type", "position_update"},
                {"exchange", "okx"},
                {"data", pos},
                {"timestamp", current_timestamp_ms()}
            };
            zmq_server.publish_report(msg);

            // 发送到前端 WebSocket（实盘持仓更新）
            if (g_frontend_server) {
                g_frontend_server->send_event("position_update", msg);
            }
        });
    }
}

void setup_binance_websocket_callbacks(ZmqServer& zmq_server) {
    // Binance 回调（原始JSON格式）
    if (g_binance_ws_market) {
        // Binance Ticker 回调（原始JSON格式）- !ticker@arr
        g_binance_ws_market->set_ticker_callback([&zmq_server](const nlohmann::json& raw) {
            g_binance_ticker_count++;

            // Binance ticker 字段: s(symbol), c(close/last), h(high), l(low), o(open), v(volume), E(event time)
            std::string symbol = raw.value("s", "");

            nlohmann::json msg = {
                {"type", "ticker"},
                {"exchange", "binance"},
                {"symbol", symbol},
                {"timestamp_ns", current_timestamp_ns()}
            };

            if (raw.contains("c")) msg["price"] = std::stod(raw["c"].get<std::string>());
            if (raw.contains("E")) msg["timestamp"] = raw["E"].get<int64_t>();
            if (raw.contains("h")) msg["high_24h"] = std::stod(raw["h"].get<std::string>());
            if (raw.contains("l")) msg["low_24h"] = std::stod(raw["l"].get<std::string>());
            if (raw.contains("o")) msg["open_24h"] = std::stod(raw["o"].get<std::string>());
            if (raw.contains("v")) msg["volume_24h"] = std::stod(raw["v"].get<std::string>());

            // 发布到 Binance 专用通道
            zmq_server.publish_binance_market(msg, MessageType::TICKER);
            // 同时发布到统一通道
            zmq_server.publish_ticker(msg);

            if (g_frontend_server) {
                g_frontend_server->send_event("ticker", msg);
            }
        });

        // Binance Trade 回调（原始JSON格式）- 注意：目前Binance没有订阅trade
        g_binance_ws_market->set_trade_callback([&zmq_server](const nlohmann::json& raw) {
            g_trade_count++;

            // Binance trade 字段: s(symbol), t(trade id), p(price), q(quantity), m(is buyer maker), T(trade time)
            std::string symbol = raw.value("s", "");

            nlohmann::json msg = {
                {"type", "trade"},
                {"exchange", "binance"},
                {"symbol", symbol},
                {"timestamp_ns", current_timestamp_ns()}
            };

            if (raw.contains("t")) msg["trade_id"] = std::to_string(raw["t"].get<int64_t>());
            if (raw.contains("p")) msg["price"] = std::stod(raw["p"].get<std::string>());
            if (raw.contains("q")) msg["quantity"] = std::stod(raw["q"].get<std::string>());
            if (raw.contains("m")) msg["side"] = raw["m"].get<bool>() ? "sell" : "buy";
            if (raw.contains("T")) msg["timestamp"] = raw["T"].get<int64_t>();

            // 发布到 Binance 专用通道
            zmq_server.publish_binance_market(msg, MessageType::TRADE);
            // 同时发布到统一通道
            zmq_server.publish_ticker(msg);

            // Redis 录制 Trade 数据
            if (g_redis_recorder && g_redis_recorder->is_running()) {
                g_redis_recorder->record_trade(symbol, "binance", msg);
            }

            static int binance_trade_counter = 0;
            if (++binance_trade_counter % 10 == 0 && g_frontend_server) {
                g_frontend_server->send_event("trade", msg);
            }
        });

        // Binance K线回调（原始JSON格式）
        // 支持两种格式：普通 kline 和 continuous_kline（连续合约K线）
        g_binance_ws_market->set_kline_callback([&zmq_server](const nlohmann::json& raw) {
            g_kline_count++;
            g_binance_kline_count++;

            // continuous_kline 格式: ps(交易对), ct(合约类型), k(K线数据)
            // 普通 kline 格式: s(交易对), k(K线数据)
            std::string symbol = raw.value("ps", raw.value("s", ""));

            // 将 symbol 转换为大写（Binance 格式）
            std::transform(symbol.begin(), symbol.end(), symbol.begin(), ::toupper);

            nlohmann::json msg = {
                {"type", "kline"},
                {"exchange", "binance"},
                {"symbol", symbol},
                {"timestamp_ns", current_timestamp_ns()}
            };

            if (raw.contains("k")) {
                const auto& k = raw["k"];
                if (k.contains("i")) msg["interval"] = k["i"].get<std::string>();
                if (k.contains("o")) msg["open"] = std::stod(k["o"].get<std::string>());
                if (k.contains("h")) msg["high"] = std::stod(k["h"].get<std::string>());
                if (k.contains("l")) msg["low"] = std::stod(k["l"].get<std::string>());
                if (k.contains("c")) msg["close"] = std::stod(k["c"].get<std::string>());
                if (k.contains("v")) msg["volume"] = std::stod(k["v"].get<std::string>());
                if (k.contains("t")) msg["timestamp"] = k["t"].get<int64_t>();
            }

            // 发布到 Binance 专用通道
            zmq_server.publish_binance_market(msg, MessageType::KLINE);
            // 同时发布到统一通道
            zmq_server.publish_kline(msg);

            // Redis 录制 K线 数据（仅当 K 线完结时保存，x=true 表示已完结）
            if (g_redis_recorder && g_redis_recorder->is_running()) {
                bool is_closed = false;
                if (raw.contains("k") && raw["k"].contains("x")) {
                    is_closed = raw["k"]["x"].get<bool>();
                }
                if (is_closed) {
                    std::string interval = msg.value("interval", "1m");
                    g_redis_recorder->record_kline(symbol, interval, "binance", msg);
                }
            }
        });

        // Binance 标记价格回调（原始JSON格式）- 注意：目前设在 g_binance_ws_market，但实际 markPrice 在 g_binance_ws_depth
        g_binance_ws_market->set_mark_price_callback([&zmq_server](const nlohmann::json& raw) {
            g_binance_markprice_count++;
            g_funding_rate_count++;

            // Binance markPrice 字段: s(symbol), p(markPrice), i(indexPrice), r(fundingRate), T(nextFundingTime), E(eventTime)
            std::string symbol = raw.value("s", "");

            nlohmann::json msg = {
                {"type", "mark_price"},
                {"exchange", "binance"},
                {"symbol", symbol},
                {"timestamp_ns", current_timestamp_ns()}
            };

            if (raw.contains("p")) msg["mark_price"] = std::stod(raw["p"].get<std::string>());
            if (raw.contains("i")) msg["index_price"] = std::stod(raw["i"].get<std::string>());
            if (raw.contains("r")) msg["funding_rate"] = std::stod(raw["r"].get<std::string>());
            if (raw.contains("T")) msg["next_funding_time"] = raw["T"].get<int64_t>();
            if (raw.contains("E")) msg["timestamp"] = raw["E"].get<int64_t>();

            // 发布到 Binance 专用通道
            zmq_server.publish_binance_market(msg, MessageType::TICKER);
            // 同时发布到统一通道
            zmq_server.publish_ticker(msg);

            // Redis 录制 Funding Rate 数据（Mark Price 包含资金费率）
            if (g_redis_recorder && g_redis_recorder->is_running() && msg.contains("funding_rate")) {
                g_redis_recorder->record_funding_rate(symbol, "binance", msg);
            }
        });
    }

    // Binance 用户数据流回调
    if (g_binance_ws_user) {
        // 账户更新回调
        g_binance_ws_user->set_account_update_callback([&zmq_server](const nlohmann::json& acc) {
            nlohmann::json msg = {
                {"type", "account_update"},
                {"exchange", "binance"},
                {"data", acc},
                {"timestamp", current_timestamp_ms()}
            };
            zmq_server.publish_report(msg);

            // 发送到前端 WebSocket（Binance 实盘账户更新）
            if (g_frontend_server) {
                g_frontend_server->send_event("account_update", msg);
            }
        });

        // 订单成交更新回调
        g_binance_ws_user->set_order_trade_update_callback([&zmq_server](const nlohmann::json& order) {
            nlohmann::json msg = {
                {"type", "order_update"},
                {"exchange", "binance"},
                {"data", order},
                {"timestamp", current_timestamp_ms()}
            };
            zmq_server.publish_report(msg);

            // 发送到前端 WebSocket（Binance 实盘订单更新）
            if (g_frontend_server) {
                g_frontend_server->send_event("order_update", msg);
            }
        });
    }

    // Binance markPrice 专用连接（g_binance_ws_depth 实际用于 !markPrice@arr）
    if (g_binance_ws_depth) {
        g_binance_ws_depth->set_mark_price_callback([&zmq_server](const nlohmann::json& raw) {
            g_binance_markprice_count++;
            g_funding_rate_count++;

            // Binance markPrice 字段: s(symbol), p(markPrice), i(indexPrice), r(fundingRate), T(nextFundingTime), E(eventTime)
            std::string symbol = raw.value("s", "");

            nlohmann::json msg = {
                {"type", "mark_price"},
                {"exchange", "binance"},
                {"symbol", symbol},
                {"timestamp_ns", current_timestamp_ns()}
            };

            if (raw.contains("p")) msg["mark_price"] = std::stod(raw["p"].get<std::string>());
            if (raw.contains("i")) msg["index_price"] = std::stod(raw["i"].get<std::string>());
            if (raw.contains("r")) msg["funding_rate"] = std::stod(raw["r"].get<std::string>());
            if (raw.contains("T")) msg["next_funding_time"] = raw["T"].get<int64_t>();
            if (raw.contains("E")) msg["timestamp"] = raw["E"].get<int64_t>();

            // 发布到 Binance 专用通道
            zmq_server.publish_binance_market(msg, MessageType::TICKER);
            // 同时发布到统一通道
            zmq_server.publish_ticker(msg);

            // Redis 录制 Funding Rate 数据（Mark Price 包含资金费率）
            if (g_redis_recorder && g_redis_recorder->is_running() && msg.contains("funding_rate")) {
                g_redis_recorder->record_funding_rate(symbol, "binance", msg);
            }
        });
    }
}

} // namespace server
} // namespace trading
