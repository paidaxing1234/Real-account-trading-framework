/**
 * @file websocket_callbacks.h
 * @brief WebSocket 回调设置模块
 */

#pragma once

#include "../../network/zmq_server.h"

namespace trading {
namespace server {

/**
 * @brief 设置 OKX WebSocket 回调
 */
void setup_websocket_callbacks(ZmqServer& zmq_server);

/**
 * @brief 设置 Binance WebSocket 回调
 */
void setup_binance_websocket_callbacks(ZmqServer& zmq_server);

} // namespace server
} // namespace trading
