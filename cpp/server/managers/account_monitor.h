#pragma once

/**
 * @file account_monitor.h
 * @brief 账户实时监控模块 - 定期查询账户状态并更新风控管理器
 *
 * 功能：
 * - 定期查询账户余额和持仓
 * - 计算实时盈亏
 * - 更新风控管理器状态
 * - 触发风控告警
 */

#include <string>
#include <thread>
#include <atomic>
#include <chrono>
#include <map>
#include "../../trading/risk_manager.h"
#include "../../adapters/okx/okx_rest_api.h"
#include "../../adapters/binance/binance_rest_api.h"

namespace trading {
namespace server {

/**
 * @brief 账户监控器 - 实时监控账户状态并更新风控
 */
class AccountMonitor {
public:
    AccountMonitor(RiskManager& risk_manager)
        : risk_manager_(risk_manager), running_(false) {}

    ~AccountMonitor() {
        stop();
    }

    /**
     * @brief 启动监控线程
     * @param interval_seconds 监控间隔（秒）
     */
    void start(int interval_seconds = 5) {
        if (running_) {
            return;
        }

        running_ = true;
        monitor_thread_ = std::thread([this, interval_seconds]() {
            std::cout << "[账户监控] 启动，间隔: " << interval_seconds << "秒\n";

            while (running_) {
                try {
                    update_all_accounts();
                } catch (const std::exception& e) {
                    std::cerr << "[账户监控] 错误: " << e.what() << "\n";
                }

                // 等待指定间隔
                for (int i = 0; i < interval_seconds && running_; i++) {
                    std::this_thread::sleep_for(std::chrono::seconds(1));
                }
            }

            std::cout << "[账户监控] 已停止\n";
        });
    }

    /**
     * @brief 停止监控线程
     */
    void stop() {
        if (!running_) {
            return;
        }

        running_ = false;
        if (monitor_thread_.joinable()) {
            monitor_thread_.join();
        }
    }

    /**
     * @brief 注册需要监控的 OKX 账户
     */
    void register_okx_account(const std::string& strategy_id, okx::OKXRestAPI* api) {
        okx_accounts_[strategy_id] = api;
        std::cout << "[账户监控] 注册 OKX 账户: " << strategy_id << "\n";
    }

    /**
     * @brief 注册需要监控的 Binance 账户
     */
    void register_binance_account(const std::string& strategy_id, binance::BinanceRestAPI* api) {
        binance_accounts_[strategy_id] = api;
        std::cout << "[账户监控] 注册 Binance 账户: " << strategy_id << "\n";
    }

    /**
     * @brief 注销 OKX 账户监控
     */
    void unregister_okx_account(const std::string& strategy_id) {
        auto it = okx_accounts_.find(strategy_id);
        if (it != okx_accounts_.end()) {
            okx_accounts_.erase(it);
            std::cout << "[账户监控] 注销 OKX 账户: " << strategy_id << "\n";
        }
    }

    /**
     * @brief 注销 Binance 账户监控
     */
    void unregister_binance_account(const std::string& strategy_id) {
        auto it = binance_accounts_.find(strategy_id);
        if (it != binance_accounts_.end()) {
            binance_accounts_.erase(it);
            std::cout << "[账户监控] 注销 Binance 账户: " << strategy_id << "\n";
        }
    }

    /**
     * @brief 手动触发一次账户更新
     */
    void update_all_accounts() {
        std::cout << "\n========== [账户监控] 开始更新所有账户 ==========\n";

        // 收集需要移除的账户
        std::vector<std::string> okx_to_remove;
        std::vector<std::string> binance_to_remove;

        // 更新所有 OKX 账户
        for (const auto& [strategy_id, api] : okx_accounts_) {
            if (!api) {
                std::cout << "[账户监控] ⚠️  OKX 账户 " << strategy_id << " API 指针无效，将自动注销\n";
                okx_to_remove.push_back(strategy_id);
                continue;
            }

            bool success = update_okx_account(strategy_id, api);
            if (!success) {
                // 更新失败，可能账户已被注销
                okx_to_remove.push_back(strategy_id);
            }
        }

        // 更新所有 Binance 账户
        for (const auto& [strategy_id, api] : binance_accounts_) {
            if (!api) {
                std::cout << "[账户监控] ⚠️  Binance 账户 " << strategy_id << " API 指针无效，将自动注销\n";
                binance_to_remove.push_back(strategy_id);
                continue;
            }

            bool success = update_binance_account(strategy_id, api);
            if (!success) {
                // 更新失败，可能账户已被注销
                binance_to_remove.push_back(strategy_id);
            }
        }

        // 移除失效的账户
        for (const auto& strategy_id : okx_to_remove) {
            okx_accounts_.erase(strategy_id);
            std::cout << "[账户监控] ✓ 已自动注销 OKX 账户: " << strategy_id << "\n";
        }
        for (const auto& strategy_id : binance_to_remove) {
            binance_accounts_.erase(strategy_id);
            std::cout << "[账户监控] ✓ 已自动注销 Binance 账户: " << strategy_id << "\n";
        }

        std::cout << "========== [账户监控] 更新完成 ==========\n\n";
    }

private:
    /**
     * @brief 更新单个 OKX 账户状态
     * @return true 更新成功，false 更新失败（账户可能已注销）
     */
    bool update_okx_account(const std::string& strategy_id, okx::OKXRestAPI* api) {
        if (!api) return false;

        try {
            std::cout << "[账户监控] 正在查询 OKX 账户: " << strategy_id << "\n";

            // 1. 查询账户余额
            auto balance_result = api->get_account_balance("");
            if (balance_result["code"] == "0" && balance_result.contains("data")) {
                double total_equity = 0.0;
                double unrealized_pnl = 0.0;

                for (const auto& detail : balance_result["data"][0]["details"]) {
                    double eq = std::stod(detail.value("eq", "0"));
                    double upl = std::stod(detail.value("upl", "0"));
                    total_equity += eq;
                    unrealized_pnl += upl;
                }

                std::cout << "[账户监控] " << strategy_id << " - 总权益: " << total_equity
                          << " USDT, 未实现盈亏: " << unrealized_pnl << " USDT\n";

                // 检查账户余额
                auto balance_check = risk_manager_.check_account_balance(total_equity);
                if (!balance_check.passed) {
                    std::cout << "[账户监控] ⚠️  " << strategy_id << " - 余额告警: "
                              << balance_check.reason << "\n";
                    risk_manager_.send_alert(
                        "[" + strategy_id + "] " + balance_check.reason,
                        AlertLevel::WARNING,
                        "账户余额不足"
                    );
                } else {
                    std::cout << "[账户监控] ✓ " << strategy_id << " - 余额正常\n";
                }

                // 更新账户总权益（用于回撤检查）
                risk_manager_.update_account_equity(total_equity, strategy_id);

                // 更新每日盈亏（仅用于统计）
                risk_manager_.update_daily_pnl(unrealized_pnl);
            }

            // 2. 查询持仓
            auto positions_result = api->get_positions("SWAP", "");
            if (positions_result["code"] == "0" && positions_result.contains("data")) {
                int position_count = 0;
                for (const auto& pos : positions_result["data"]) {
                    std::string symbol = pos.value("instId", "");
                    double notional = std::stod(pos.value("notionalUsd", "0"));

                    if (std::abs(notional) > 0.01) {  // 只显示有效持仓
                        std::cout << "[账户监控] " << strategy_id << " - 持仓: "
                                  << symbol << " = " << notional << " USDT\n";
                        position_count++;
                    }

                    // 更新持仓到风控管理器
                    risk_manager_.update_position(symbol, std::abs(notional));
                }
                if (position_count == 0) {
                    std::cout << "[账户监控] " << strategy_id << " - 无持仓\n";
                }
            }

            // 3. 查询挂单数量
            auto orders_result = api->get_pending_orders("SWAP", "");
            if (orders_result["code"] == "0" && orders_result.contains("data")) {
                int open_orders = orders_result["data"].size();
                std::cout << "[账户监控] " << strategy_id << " - 挂单数量: " << open_orders << "\n";
                risk_manager_.set_open_order_count(open_orders);
            }

            std::cout << "[账户监控] ✓ " << strategy_id << " 更新完成\n";
            return true;

        } catch (const std::exception& e) {
            std::cerr << "[账户监控] ✗ OKX账户 " << strategy_id << " 更新失败: " << e.what() << "\n";
            return false;
        }
    }

    /**
     * @brief 更新单个 Binance 账户状态
     * @return true 更新成功，false 更新失败（账户可能已注销）
     */
    bool update_binance_account(const std::string& strategy_id, binance::BinanceRestAPI* api) {
        if (!api) return false;

        try {
            std::cout << "[账户监控] 正在查询 Binance 账户: " << strategy_id << "\n";

            // 1. 查询账户余额
            auto balance_result = api->get_account_balance();

            // 调试：打印返回结果的类型和内容
            std::cout << "[账户监控] DEBUG: balance_result 类型: "
                      << (balance_result.is_array() ? "array" :
                          balance_result.is_object() ? "object" : "other") << "\n";

            double total_balance = 0.0;
            double unrealized_pnl = 0.0;

            // 检查返回结果是否是数组（直接返回数组）
            if (balance_result.is_array()) {
                std::cout << "[账户监控] DEBUG: 直接处理数组格式\n";
                for (const auto& asset : balance_result) {
                    if (asset.contains("balance")) {
                        double balance = std::stod(asset.value("balance", "0"));
                        total_balance += balance;
                    }
                    if (asset.contains("crossUnPnl")) {
                        double pnl = std::stod(asset.value("crossUnPnl", "0"));
                        unrealized_pnl += pnl;
                    }
                }
            }
            // 检查返回结果是否是对象（包含 code 和 data）
            else if (balance_result.is_object() &&
                     balance_result.contains("code") &&
                     balance_result["code"] == 200 &&
                     balance_result.contains("data") &&
                     balance_result["data"].is_array()) {
                std::cout << "[账户监控] DEBUG: 处理对象格式 {code, data}\n";
                for (const auto& asset : balance_result["data"]) {
                    if (asset.contains("balance")) {
                        double balance = std::stod(asset.value("balance", "0"));
                        total_balance += balance;
                    }
                    if (asset.contains("crossUnPnl")) {
                        double pnl = std::stod(asset.value("crossUnPnl", "0"));
                        unrealized_pnl += pnl;
                    }
                }
            } else {
                std::cout << "[账户监控] " << strategy_id << " - 余额查询返回格式未知，跳过\n";
            }

            if (total_balance > 0 || unrealized_pnl != 0) {
                std::cout << "[账户监控] " << strategy_id << " - 总余额: " << total_balance
                          << " USDT, 未实现盈亏: " << unrealized_pnl << " USDT\n";

                // 检查账户余额
                auto balance_check = risk_manager_.check_account_balance(total_balance);
                if (!balance_check.passed) {
                    std::cout << "[账户监控] ⚠️  " << strategy_id << " - 余额告警: "
                              << balance_check.reason << "\n";
                    risk_manager_.send_alert(
                        "[" + strategy_id + "] " + balance_check.reason,
                        AlertLevel::WARNING,
                        "账户余额不足"
                    );
                } else {
                    std::cout << "[账户监控] ✓ " << strategy_id << " - 余额正常\n";
                }

                // 更新账户总权益（用于回撤检查）
                risk_manager_.update_account_equity(total_balance, strategy_id);

                // 更新每日盈亏（仅用于统计）
                risk_manager_.update_daily_pnl(unrealized_pnl);
            }

            // 2. 查询持仓
            auto positions_result = api->get_positions();

            int position_count = 0;
            // 检查是否是数组（直接返回）
            if (positions_result.is_array()) {
                for (const auto& pos : positions_result) {
                    std::string symbol = pos.value("symbol", "");
                    double notional = std::stod(pos.value("notional", "0"));

                    if (std::abs(notional) > 0.01) {  // 只显示有效持仓
                        std::cout << "[账户监控] " << strategy_id << " - 持仓: "
                                  << symbol << " = " << notional << " USDT\n";
                        position_count++;
                    }

                    // 更新持仓到风控管理器
                    risk_manager_.update_position(symbol, std::abs(notional));
                }
            }
            // 检查是否是对象（包含 code 和 data）
            else if (positions_result.is_object() &&
                     positions_result.contains("code") &&
                     positions_result["code"] == 200 &&
                     positions_result.contains("data") &&
                     positions_result["data"].is_array()) {
                for (const auto& pos : positions_result["data"]) {
                    std::string symbol = pos.value("symbol", "");
                    double notional = std::stod(pos.value("notional", "0"));

                    if (std::abs(notional) > 0.01) {  // 只显示有效持仓
                        std::cout << "[账户监控] " << strategy_id << " - 持仓: "
                                  << symbol << " = " << notional << " USDT\n";
                        position_count++;
                    }

                    // 更新持仓到风控管理器
                    risk_manager_.update_position(symbol, std::abs(notional));
                }
            }

            if (position_count == 0) {
                std::cout << "[账户监控] " << strategy_id << " - 无持仓\n";
            }

            std::cout << "[账户监控] ✓ " << strategy_id << " 更新完成\n";
            return true;

        } catch (const std::exception& e) {
            std::cerr << "[账户监控] ✗ Binance账户 " << strategy_id << " 更新失败: " << e.what() << "\n";
            return false;
        }
    }

    RiskManager& risk_manager_;
    std::atomic<bool> running_;
    std::thread monitor_thread_;

    std::map<std::string, okx::OKXRestAPI*> okx_accounts_;
    std::map<std::string, binance::BinanceRestAPI*> binance_accounts_;
};

} // namespace server
} // namespace trading
