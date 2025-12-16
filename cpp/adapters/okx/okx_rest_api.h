#pragma once

#include <string>
#include <memory>
#include <vector>
#include <optional>
#include <nlohmann/json.hpp>

namespace trading {
namespace okx {

// ==================== 数据结构定义 ====================

/**
 * @brief 止盈止损订单参数
 * 
 * 用于下单时附带止盈止损信息
 */
struct AttachAlgoOrder {
    std::string attach_algo_id;         // 附带止盈止损的订单ID（改单时必填，由系统生成）
    std::string attach_algo_cl_ord_id;  // 客户自定义策略订单ID (可选)
    
    // 止盈参数
    std::string tp_trigger_px;           // 止盈触发价
    std::string tp_trigger_ratio;        // 止盈触发比例 (如 "0.3" 表示 30%)
    std::string tp_ord_px;               // 止盈委托价 ("-1" 表示市价)
    std::string tp_ord_kind;             // 止盈订单类型: "condition"(条件单) 或 "limit"(限价单)
    std::string tp_trigger_px_type;      // 触发价类型: "last"/"index"/"mark"
    
    // 止损参数
    std::string sl_trigger_px;           // 止损触发价
    std::string sl_trigger_ratio;        // 止损触发比例
    std::string sl_ord_px;               // 止损委托价 ("-1" 表示市价)
    std::string sl_trigger_px_type;      // 触发价类型: "last"/"index"/"mark"
    
    // 分批止盈参数
    std::string sz;                      // 数量 (分批止盈必填)
    std::string amend_px_on_trigger_type; // 是否启用开仓价止损: "0"/"1"
    
    // 转换为JSON
    nlohmann::json to_json() const;
};

/**
 * @brief 下单请求参数
 * 
 * 完整支持OKX下单API的所有参数
 * 参考: https://www.okx.com/docs-v5/zh/#order-book-trading-trade-post-place-order
 */
struct PlaceOrderRequest {
    // ========== 必填参数 ==========
    std::string inst_id;      // 产品ID，如 "BTC-USDT"
    std::string td_mode;      // 交易模式: "cash"/"isolated"/"cross"/"spot_isolated"
    std::string side;         // 订单方向: "buy"/"sell"
    std::string ord_type;     // 订单类型: "market"/"limit"/"post_only"/"fok"/"ioc"等
    std::string sz;           // 委托数量
    
    // ========== 可选参数 ==========
    std::string ccy;          // 保证金币种 (逐仓杠杆/合约全仓杠杆)
    std::string cl_ord_id;    // 客户自定义订单ID (1-32位)
    std::string tag;          // 订单标签 (1-16位)
    std::string pos_side;     // 持仓方向: "long"/"short" (开平仓模式必填)
    std::string px;           // 委托价格 (限价单必填)
    std::string px_usd;       // 以USD价格下单 (仅期权)
    std::string px_vol;       // 以隐含波动率下单 (仅期权)
    
    bool reduce_only = false;       // 是否只减仓
    std::string tgt_ccy;            // 市价单数量单位: "base_ccy"/"quote_ccy"
    bool ban_amend = false;         // 是否禁止币币市价改单
    std::string px_amend_type;      // 价格修正类型: "0"/"1"
    std::string trade_quote_ccy;    // 用于交易的计价币种
    std::string stp_mode;           // 自成交保护: "cancel_maker"/"cancel_taker"/"cancel_both"
    
    // 止盈止损
    std::vector<AttachAlgoOrder> attach_algo_ords;  // 附带止盈止损订单
    
    // 转换为JSON
    nlohmann::json to_json() const;
};

/**
 * @brief 下单响应
 */
struct PlaceOrderResponse {
    std::string code;         // 结果代码，"0"表示成功
    std::string msg;          // 错误信息
    std::string ord_id;       // 订单ID
    std::string cl_ord_id;    // 客户自定义订单ID
    std::string tag;          // 订单标签
    int64_t ts;               // 时间戳
    std::string s_code;       // 事件执行结果code
    std::string s_msg;        // 事件执行消息
    int64_t in_time;          // 网关接收时间 (微秒)
    int64_t out_time;         // 网关发送时间 (微秒)
    
    // 从JSON解析
    static PlaceOrderResponse from_json(const nlohmann::json& j);
    
    // 是否成功
    bool is_success() const { return code == "0" && s_code == "0"; }
};

// ==================== API类定义 ====================

/**
 * @brief OKX REST API封装
 * 
 * 提供以下功能：
 * - 下单（限价、市价、止盈止损）
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
    
    // ==================== 下单接口 ====================
    
    /**
     * @brief 简化版下单 (向后兼容)
     */
    nlohmann::json place_order(
        const std::string& inst_id,
        const std::string& td_mode,
        const std::string& side,
        const std::string& ord_type,
        double sz,
        double px = 0.0,
        const std::string& cl_ord_id = ""
    );
    
    /**
     * @brief 完整版下单 (支持所有参数包括止盈止损)
     */
    PlaceOrderResponse place_order_advanced(const PlaceOrderRequest& request);
    
    /**
     * @brief 带止盈止损的下单 (便捷方法)
     */
    PlaceOrderResponse place_order_with_tp_sl(
        const std::string& inst_id,
        const std::string& td_mode,
        const std::string& side,
        const std::string& ord_type,
        const std::string& sz,
        const std::string& px,
        const std::string& tp_trigger_px = "",
        const std::string& tp_ord_px = "-1",
        const std::string& sl_trigger_px = "",
        const std::string& sl_ord_px = "-1",
        const std::string& cl_ord_id = ""
    );
    
    /**
     * @brief 批量下单
     * 
     * 每次最多可以批量提交20个新订单
     * 
     * @param orders 订单请求数组，每个元素是一个PlaceOrderRequest
     * @return nlohmann::json 包含所有订单的响应结果
     */
    nlohmann::json place_batch_orders(const std::vector<PlaceOrderRequest>& orders);
    
    // ==================== 撤单接口 ====================
    
    nlohmann::json cancel_order(
        const std::string& inst_id,
        const std::string& ord_id = "",
        const std::string& cl_ord_id = ""
    );
    
    nlohmann::json cancel_batch_orders(
        const std::vector<std::string>& ord_ids,
        const std::string& inst_id
    );
    
    // ==================== 修改订单接口 ====================
    
    /**
     * @brief 修改订单
     * 
     * 修改当前未成交的挂单
     * 
     * @param inst_id 产品ID
     * @param ord_id 订单ID（与cl_ord_id二选一，优先使用ord_id）
     * @param cl_ord_id 客户自定义订单ID
     * @param new_sz 修改的新数量（可选）
     * @param new_px 修改后的新价格（可选）
     * @param new_px_usd 以USD价格进行期权改单（可选，仅期权）
     * @param new_px_vol 以隐含波动率进行期权改单（可选，仅期权）
     * @param cxl_on_fail 当订单修改失败时，该订单是否需要自动撤销（默认false）
     * @param req_id 用户自定义修改事件ID（可选）
     * @param px_amend_type 订单价格修正类型："0"不允许系统修改，"1"允许（默认"0"）
     * @param attach_algo_ords 修改附带止盈止损信息（可选）
     * @return nlohmann::json 修改结果
     */
    nlohmann::json amend_order(
        const std::string& inst_id,
        const std::string& ord_id = "",
        const std::string& cl_ord_id = "",
        const std::string& new_sz = "",
        const std::string& new_px = "",
        const std::string& new_px_usd = "",
        const std::string& new_px_vol = "",
        bool cxl_on_fail = false,
        const std::string& req_id = "",
        const std::string& px_amend_type = "0",
        const std::vector<AttachAlgoOrder>& attach_algo_ords = {}
    );
    
    /**
     * @brief 批量修改订单
     * 
     * 修改未完成的订单，一次最多可批量修改20个订单
     * 
     * @param orders 修改订单请求数组，每个元素包含instId、ordId/clOrdId、newSz/newPx等
     * @return nlohmann::json 包含所有修改结果的响应
     */
    nlohmann::json amend_batch_orders(const std::vector<nlohmann::json>& orders);
    
    // ==================== 查询接口 ====================
    
    nlohmann::json get_order(
        const std::string& inst_id,
        const std::string& ord_id = "",
        const std::string& cl_ord_id = ""
    );
    
    nlohmann::json get_pending_orders(
        const std::string& inst_type = "",
        const std::string& inst_id = ""
    );
    
    nlohmann::json get_account_balance(const std::string& ccy = "");
    
    nlohmann::json get_positions(
        const std::string& inst_type = "",
        const std::string& inst_id = ""
    );
    
    nlohmann::json get_account_instruments(
        const std::string& inst_type,
        const std::string& inst_family = "",
        const std::string& inst_id = ""
    );
    
    nlohmann::json get_candles(
        const std::string& inst_id,
        const std::string& bar,
        int64_t after = 0,
        int64_t before = 0,
        int limit = 100
    );
    
    // ==================== 代理设置 ====================
    
    /**
     * @brief 设置HTTP代理
     * 
     * @param proxy_host 代理主机地址（如 "127.0.0.1"）
     * @param proxy_port 代理端口（如 7890）
     */
    void set_proxy(const std::string& proxy_host, uint16_t proxy_port);

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
