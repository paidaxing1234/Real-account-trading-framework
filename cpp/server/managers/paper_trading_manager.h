/**
 * @file paper_trading_manager.h
 * @brief PaperTrading 管理模块
 */

#pragma once

#include <nlohmann/json.hpp>

namespace trading {
namespace server {

/**
 * @brief 启动模拟交易
 */
nlohmann::json process_start_paper_strategy(const nlohmann::json& request);

/**
 * @brief 停止模拟交易
 */
nlohmann::json process_stop_paper_strategy(const nlohmann::json& request);

/**
 * @brief 获取模拟交易状态
 */
nlohmann::json process_get_paper_strategy_status(const nlohmann::json& request);

} // namespace server
} // namespace trading
