/**
 * @file websocket_callbacks.cpp
 * @brief WebSocket 回调设置模块实现
 */

#include "websocket_callbacks.h"
#include "../config/server_config.h"
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
        // OKX Ticker 回调
        g_ws_public->set_ticker_callback([&zmq_server](const TickerData::Ptr& ticker) {
            // 发送给前端时去掉 -SWAP 后缀
            std::string display_symbol = strip_swap_suffix(ticker->symbol());

            nlohmann::json msg = {
                {"type", "ticker"},
                {"exchange", "okx"},
                {"symbol", display_symbol},
                {"price", ticker->last_price()},
                {"timestamp", ticker->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            if (ticker->high_24h()) msg["high_24h"] = *ticker->high_24h();
            if (ticker->low_24h()) msg["low_24h"] = *ticker->low_24h();
            if (ticker->open_24h()) msg["open_24h"] = *ticker->open_24h();
            if (ticker->volume_24h()) msg["volume_24h"] = *ticker->volume_24h();

            zmq_server.publish_ticker(msg);

            if (g_frontend_server) {
                g_frontend_server->send_event("ticker", msg);
            }
        });

        g_ws_public->set_trade_callback([&zmq_server](const TradeData::Ptr& trade) {
            g_trade_count++;

            nlohmann::json msg = {
                {"type", "trade"},
                {"exchange", "okx"},
                {"symbol", trade->symbol()},
                {"trade_id", trade->trade_id()},
                {"price", trade->price()},
                {"quantity", trade->quantity()},
                {"side", trade->side().value_or("")},
                {"timestamp", trade->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            zmq_server.publish_ticker(msg);

            // 转发给前端 WebSocket（每10条发送一次，避免过多数据）
            static int trade_counter = 0;
            if (++trade_counter % 10 == 0 && g_frontend_server) {
                g_frontend_server->send_event("trade", msg);
            }
        });

        // 深度数据回调（公共频道）
        g_ws_public->set_orderbook_callback([&zmq_server](const OrderBookData::Ptr& orderbook) {
            g_orderbook_count++;

            nlohmann::json bids = nlohmann::json::array();
            nlohmann::json asks = nlohmann::json::array();

            for (const auto& bid : orderbook->bids()) {
                bids.push_back({bid.first, bid.second});
            }

            for (const auto& ask : orderbook->asks()) {
                asks.push_back({ask.first, ask.second});
            }

            std::string channel = "books5";
            {
                std::lock_guard<std::mutex> lock(g_sub_mutex);
                auto it = g_subscribed_orderbooks.find(orderbook->symbol());
                if (it != g_subscribed_orderbooks.end() && !it->second.empty()) {
                    channel = *it->second.begin();
                }
            }

            nlohmann::json msg = {
                {"type", "orderbook"},
                {"exchange", "okx"},
                {"symbol", orderbook->symbol()},
                {"channel", channel},
                {"bids", bids},
                {"asks", asks},
                {"timestamp", orderbook->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            auto best_bid = orderbook->best_bid();
            auto best_ask = orderbook->best_ask();
            if (best_bid) {
                msg["best_bid_price"] = best_bid->first;
                msg["best_bid_size"] = best_bid->second;
            }
            if (best_ask) {
                msg["best_ask_price"] = best_ask->first;
                msg["best_ask_size"] = best_ask->second;
            }

            auto mid_price = orderbook->mid_price();
            if (mid_price) {
                msg["mid_price"] = *mid_price;
            }
            auto spread = orderbook->spread();
            if (spread) {
                msg["spread"] = *spread;
            }

            zmq_server.publish_depth(msg);
        });

        // 资金费率回调（公共频道）
        g_ws_public->set_funding_rate_callback([&zmq_server](const FundingRateData::Ptr& fr) {
            g_funding_rate_count++;

            nlohmann::json msg = {
                {"type", "funding_rate"},
                {"exchange", "okx"},
                {"symbol", fr->inst_id},
                {"inst_type", fr->inst_type},
                {"funding_rate", fr->funding_rate},
                {"next_funding_rate", fr->next_funding_rate},
                {"funding_time", fr->funding_time},
                {"next_funding_time", fr->next_funding_time},
                {"min_funding_rate", fr->min_funding_rate},
                {"max_funding_rate", fr->max_funding_rate},
                {"interest_rate", fr->interest_rate},
                {"impact_value", fr->impact_value},
                {"premium", fr->premium},
                {"sett_state", fr->sett_state},
                {"sett_funding_rate", fr->sett_funding_rate},
                {"method", fr->method},
                {"formula_type", fr->formula_type},
                {"timestamp", fr->timestamp},
                {"timestamp_ns", current_timestamp_ns()}
            };

            zmq_server.publish_ticker(msg);
        });
    }

    // K线回调（业务频道）
    if (g_ws_business) {
        g_ws_business->set_kline_callback([&zmq_server](const KlineData::Ptr& kline) {
            if (!kline->is_confirmed()) {
                return;
            }

            g_kline_count++;

            nlohmann::json msg = {
                {"type", "kline"},
                {"exchange", "okx"},
                {"symbol", kline->symbol()},
                {"interval", kline->interval()},
                {"open", kline->open()},
                {"high", kline->high()},
                {"low", kline->low()},
                {"close", kline->close()},
                {"volume", kline->volume()},
                {"timestamp", kline->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            zmq_server.publish_kline(msg);
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
    // Binance Trades 回调
    if (g_binance_ws_market) {
        // Ticker 回调（全市场精简Ticker）
        g_binance_ws_market->set_ticker_callback([&zmq_server](const TickerData::Ptr& ticker) {
            nlohmann::json msg = {
                {"type", "ticker"},
                {"exchange", "binance"},
                {"symbol", ticker->symbol()},
                {"price", ticker->last_price()},
                {"timestamp", ticker->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            // 添加可选字段
            if (ticker->high_24h()) msg["high_24h"] = *ticker->high_24h();
            if (ticker->low_24h()) msg["low_24h"] = *ticker->low_24h();
            if (ticker->open_24h()) msg["open_24h"] = *ticker->open_24h();
            if (ticker->volume_24h()) msg["volume_24h"] = *ticker->volume_24h();

            zmq_server.publish_ticker(msg);

            // 转发给前端 WebSocket
            if (g_frontend_server) {
                g_frontend_server->send_event("ticker", msg);
            }
        });

        g_binance_ws_market->set_trade_callback([&zmq_server](const TradeData::Ptr& trade) {
            g_trade_count++;

            nlohmann::json msg = {
                {"type", "trade"},
                {"exchange", "binance"},
                {"symbol", trade->symbol()},
                {"trade_id", trade->trade_id()},
                {"price", trade->price()},
                {"quantity", trade->quantity()},
                {"side", trade->side().value_or("")},
                {"timestamp", trade->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            zmq_server.publish_ticker(msg);

            // 转发给前端 WebSocket（每10条发送一次，避免过多数据）
            static int binance_trade_counter = 0;
            if (++binance_trade_counter % 10 == 0 && g_frontend_server) {
                g_frontend_server->send_event("trade", msg);
            }
        });

        // Binance K线回调
        g_binance_ws_market->set_kline_callback([&zmq_server](const KlineData::Ptr& kline) {
            g_kline_count++;

            nlohmann::json msg = {
                {"type", "kline"},
                {"exchange", "binance"},
                {"symbol", kline->symbol()},
                {"interval", kline->interval()},
                {"open", kline->open()},
                {"high", kline->high()},
                {"low", kline->low()},
                {"close", kline->close()},
                {"volume", kline->volume()},
                {"timestamp", kline->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            zmq_server.publish_kline(msg);
        });

        // Binance 深度回调
        g_binance_ws_market->set_orderbook_callback([&zmq_server](const OrderBookData::Ptr& orderbook) {
            g_orderbook_count++;

            nlohmann::json bids = nlohmann::json::array();
            nlohmann::json asks = nlohmann::json::array();

            for (const auto& bid : orderbook->bids()) {
                bids.push_back({bid.first, bid.second});
            }
            for (const auto& ask : orderbook->asks()) {
                asks.push_back({ask.first, ask.second});
            }

            nlohmann::json msg = {
                {"type", "orderbook"},
                {"exchange", "binance"},
                {"symbol", orderbook->symbol()},
                {"bids", bids},
                {"asks", asks},
                {"timestamp", orderbook->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            // 添加最优价格信息（与OKX格式统一）
            auto best_bid = orderbook->best_bid();
            auto best_ask = orderbook->best_ask();
            if (best_bid) {
                msg["best_bid_price"] = best_bid->first;
                msg["best_bid_size"] = best_bid->second;
            }
            if (best_ask) {
                msg["best_ask_price"] = best_ask->first;
                msg["best_ask_size"] = best_ask->second;
            }

            auto mid_price = orderbook->mid_price();
            if (mid_price) {
                msg["mid_price"] = *mid_price;
            }
            auto spread = orderbook->spread();
            if (spread) {
                msg["spread"] = *spread;
            }

            zmq_server.publish_depth(msg);
        });

        // Binance 标记价格回调（包含资金费率）
        g_binance_ws_market->set_mark_price_callback([&zmq_server](const binance::MarkPriceData::Ptr& mp) {
            g_funding_rate_count++;

            nlohmann::json msg = {
                {"type", "mark_price"},
                {"exchange", "binance"},
                {"symbol", mp->symbol},
                {"mark_price", mp->mark_price},
                {"index_price", mp->index_price},
                {"funding_rate", mp->funding_rate},
                {"next_funding_time", mp->next_funding_time},
                {"timestamp", mp->timestamp},
                {"timestamp_ns", current_timestamp_ns()}
            };

            zmq_server.publish_ticker(msg);
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
}

} // namespace server
} // namespace trading
