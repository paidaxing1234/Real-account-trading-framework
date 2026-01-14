/**
 * @file order_processor.h
 * @brief 订单处理模块
 */

#pragma once

#include <nlohmann/json.hpp>
#include "../../network/zmq_server.h"

namespace trading {
namespace server {

/**
 * @brief 处理下单请求
 */
void process_place_order(ZmqServer& server, const nlohmann::json& order);

/**
 * @brief 处理批量下单请求
 */
void process_batch_orders(ZmqServer& server, const nlohmann::json& request);

/**
 * @brief 处理撤单请求
 */
void process_cancel_order(ZmqServer& server, const nlohmann::json& request);

/**
 * @brief 处理批量撤单请求
 */
void process_batch_cancel(ZmqServer& server, const nlohmann::json& request);

/**
 * @brief 处理修改订单请求
 */
void process_amend_order(ZmqServer& server, const nlohmann::json& request);

/**
 * @brief 处理账户注册请求
 */
void process_register_account(ZmqServer& server, const nlohmann::json& request);

/**
 * @brief 处理账户注销请求
 */
void process_unregister_account(ZmqServer& server, const nlohmann::json& request);

/**
 * @brief 处理账户查询请求（查询余额）
 */
void process_query_account(ZmqServer& server, const nlohmann::json& request);

/**
 * @brief 处理持仓查询请求
 */
void process_query_positions(ZmqServer& server, const nlohmann::json& request);

/**
 * @brief 订单请求路由
 */
void process_order_request(ZmqServer& server, const nlohmann::json& request);

} // namespace server
} // namespace trading
