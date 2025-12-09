#pragma once

#include <string>
#include <memory>
#include <nlohmann/json.hpp>

namespace trading {
namespace okx {

/**
 * @brief OKX REST API封装
 * 
 * 提供以下功能：
 * - 下单（限价、市价）
 * - 撤单
 * - 查询订单
 * - 查询账户余额
 * - 查询持仓
 */
class OKXRestAPI {
public:
    OKXRestAPI(
        const std::string& api_key,
        const std::string& secret_key,
        const std::string& passphrase,
        bool is_testnet = false
    );
    
    ~OKXRestAPI() = default;
    
    // 下单
    nlohmann::json place_order(
        const std::string& inst_id,
        const std::string& td_mode,
        const std::string& side,
        const std::string& ord_type,
        double sz,
        double px = 0.0,
        const std::string& cl_ord_id = ""
    );
    
    // 撤单
    nlohmann::json cancel_order(
        const std::string& inst_id,
        const std::string& ord_id = "",
        const std::string& cl_ord_id = ""
    );
    
    // 批量撤单
    nlohmann::json cancel_batch_orders(
        const std::vector<std::string>& ord_ids,
        const std::string& inst_id
    );
    
    // 查询订单
    nlohmann::json get_order(
        const std::string& inst_id,
        const std::string& ord_id = "",
        const std::string& cl_ord_id = ""
    );
    
    // 查询未完成订单
    nlohmann::json get_pending_orders(
        const std::string& inst_type = "",
        const std::string& inst_id = ""
    );
    
    // 查询账户余额
    nlohmann::json get_account_balance(const std::string& ccy = "");
    
    // 查询持仓
    nlohmann::json get_positions(
        const std::string& inst_type = "",
        const std::string& inst_id = ""
    );
    
    // 查询历史K线
    nlohmann::json get_candles(
        const std::string& inst_id,
        const std::string& bar,
        int64_t after = 0,
        int64_t before = 0,
        int limit = 100
    );
    
    /**
     * @brief 获取交易产品基础信息（账户维度）
     * 
     * 获取当前账户可交易产品的信息列表
     * 
     * @param inst_type 产品类型（SPOT/MARGIN/SWAP/FUTURES/OPTION）- 必填
     * @param inst_family 交易品种（仅适用于交割/永续/期权，期权必填）
     * @param inst_id 产品ID
     * @return JSON响应
     * 
     * 限速：20次/2s
     * 权限：读取
     * 
     * Example:
     *   // 查询现货产品
     *   auto result = api.get_account_instruments("SPOT");
     *   
     *   // 查询特定产品
     *   auto result = api.get_account_instruments("SPOT", "", "BTC-USDT");
     */
    nlohmann::json get_account_instruments(
        const std::string& inst_type,
        const std::string& inst_family = "",
        const std::string& inst_id = ""
    );

private:
    std::string create_signature(
        const std::string& timestamp,
        const std::string& method,
        const std::string& request_path,
        const std::string& body
    );
    
    nlohmann::json send_request(
        const std::string& method,
        const std::string& endpoint,
        const nlohmann::json& params = nlohmann::json::object()
    );
    
    std::string get_iso8601_timestamp();
    
    std::string api_key_;
    std::string secret_key_;
    std::string passphrase_;
    std::string base_url_;
    bool is_testnet_;
};

} // namespace okx
} // namespace trading

