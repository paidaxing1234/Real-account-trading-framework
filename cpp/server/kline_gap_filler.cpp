#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <fstream>
#include <cstdlib>
#include <algorithm>
#include <nlohmann/json.hpp>
#include "gap_detector.h"
#include "historical_data_fetcher.h"
#include "kline_utils.h"
#include <hiredis/hiredis.h>

using json = nlohmann::json;

// ==================== 配置 ====================

struct Config {
    // Redis配置
    static std::string redis_host;
    static int redis_port;
    static std::string redis_password;

    // 交易对列表
    static std::vector<std::string> symbols;

    // K线周期
    static std::vector<std::string> intervals;

    // 聚合配置: {目标周期, {基础周期, 聚合倍数}}
    static std::map<std::string, std::pair<std::string, int>> aggregated_intervals;

    // 过期时间（秒）
    static int expire_seconds_1m_to_30m;  // 1min、5min、15min、30min：2个月
    static int expire_seconds_1h;         // 1H：6个月

    // 测试网配置
    static bool is_testnet;
};

// 静态成员初始化
std::string Config::redis_host = "127.0.0.1";
int Config::redis_port = 6379;
std::string Config::redis_password = "";

// 从Redis动态获取，不再硬编码
std::vector<std::string> Config::symbols = {};

std::vector<std::string> Config::intervals = {"1m"};  // 只拉取1分钟K线

// ==================== 白名单配置 ====================
// 只补全这些币种的数据，避免拉取冗余的币种

// OKX 白名单
std::vector<std::string> okx_whitelist = {
    // 现货
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOGE-USDT",
    "ADA-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT", "MATIC-USDT",
    "UNI-USDT", "ATOM-USDT", "LTC-USDT", "ETC-USDT", "FIL-USDT",
    "APT-USDT", "ARB-USDT", "OP-USDT", "NEAR-USDT", "INJ-USDT",
    // 合约
    "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP",
    "DOGE-USDT-SWAP", "ADA-USDT-SWAP", "AVAX-USDT-SWAP", "DOT-USDT-SWAP",
    "LINK-USDT-SWAP", "MATIC-USDT-SWAP"
};

// Binance 白名单
std::vector<std::string> binance_whitelist = {
    // 现货
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT",
    "UNIUSDT", "ATOMUSDT", "LTCUSDT", "ETCUSDT", "FILUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "NEARUSDT", "INJUSDT",
    // 合约（永续）
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT"
};

std::map<std::string, std::pair<std::string, int>> Config::aggregated_intervals = {
    {"5m", {"1m", 5}},       // 5个1分钟 -> 5分钟
    {"15m", {"1m", 15}},     // 15个1分钟 -> 15分钟
    {"30m", {"1m", 30}},     // 30个1分钟 -> 30分钟
    {"1H", {"1m", 60}}       // 60个1分钟 -> 1小时
};

int Config::expire_seconds_1m_to_30m = 60 * 24 * 60 * 60;  // 2个月
int Config::expire_seconds_1h = 180 * 24 * 60 * 60;  // 6个月
bool Config::is_testnet = false;  // 默认使用主网获取历史K线数据

// ==================== Redis写入器 ====================

class RedisWriter {
public:
    RedisWriter(const std::string& host, int port) : host_(host), port_(port), context_(nullptr) {}

    ~RedisWriter() {
        if (context_) {
            redisFree(context_);
        }
    }

    bool connect() {
        context_ = redisConnect(host_.c_str(), port_);

        if (context_ == nullptr || context_->err) {
            if (context_) {
                std::cerr << "[RedisWriter] 连接错误: " << context_->errstr << std::endl;
                redisFree(context_);
                context_ = nullptr;
            }
            return false;
        }

        std::cout << "[RedisWriter] 已连接到Redis " << host_ << ":" << port_ << std::endl;
        return true;
    }

    bool write_kline(const std::string& symbol, const std::string& interval,
                     const trading::kline_utils::Kline& kline, bool is_aggregated = false) {
        if (!context_) return false;

        std::string key = "kline:" + symbol + ":" + interval;
        json kline_json = kline.to_json();
        std::string value = kline_json.dump();

        // ZADD添加到有序集合
        redisReply* reply = (redisReply*)redisCommand(
            context_, "ZADD %s %lld %s",
            key.c_str(), (long long)kline.timestamp, value.c_str()
        );

        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            if (reply) freeReplyObject(reply);
            return false;
        }
        freeReplyObject(reply);

        // 设置过期时间
        int expire_seconds;
        if (interval == "1H") {
            expire_seconds = Config::expire_seconds_1h;  // 1H：6个月
        } else {
            // 1min、5min、15min、30min：都是2个月
            expire_seconds = Config::expire_seconds_1m_to_30m;
        }

        reply = (redisReply*)redisCommand(
            context_, "EXPIRE %s %d", key.c_str(), expire_seconds
        );
        if (reply) freeReplyObject(reply);

        return true;
    }

    int write_klines_batch(const std::string& symbol, const std::string& interval,
                           const std::vector<trading::kline_utils::Kline>& klines,
                           bool is_aggregated = false) {
        int count = 0;
        for (const auto& kline : klines) {
            if (write_kline(symbol, interval, kline, is_aggregated)) {
                count++;
            }
        }
        return count;
    }

private:
    std::string host_;
    int port_;
    redisContext* context_;
};

// ==================== K线聚合器（简化版） ====================

class SimpleAggregator {
public:
    static trading::kline_utils::Kline aggregate(
        const std::vector<trading::kline_utils::Kline>& klines,
        int64_t aligned_timestamp
    ) {
        trading::kline_utils::Kline result;
        result.timestamp = aligned_timestamp;
        result.open = klines[0].open;
        result.close = klines.back().close;
        result.high = klines[0].high;
        result.low = klines[0].low;
        result.volume = 0.0;

        for (const auto& k : klines) {
            result.high = std::max(result.high, k.high);
            result.low = std::min(result.low, k.low);
            result.volume += k.volume;
        }

        return result;
    }
};

// ==================== 主程序 ====================

// 从Redis key中提取exchange信息
std::string extract_exchange_from_key(const std::string& key) {
    // key格式: kline:exchange:symbol:interval
    // 例如: kline:okx:BTC-USDT-SWAP:1m 或 kline:binance:BTCUSDT:1m
    size_t first_colon = key.find(':');
    if (first_colon == std::string::npos) return "";

    size_t second_colon = key.find(':', first_colon + 1);
    if (second_colon == std::string::npos) return "";

    return key.substr(first_colon + 1, second_colon - first_colon - 1);
}

// 从Redis key中提取symbol信息
std::string extract_symbol_from_key(const std::string& key) {
    // key格式: kline:exchange:symbol:interval
    size_t first_colon = key.find(':');
    if (first_colon == std::string::npos) return "";

    size_t second_colon = key.find(':', first_colon + 1);
    if (second_colon == std::string::npos) return "";

    size_t third_colon = key.find(':', second_colon + 1);
    if (third_colon == std::string::npos) return "";

    return key.substr(second_colon + 1, third_colon - second_colon - 1);
}

bool is_okx_symbol(const std::string& symbol) {
    // OKX符号格式：BTC-USDT-SWAP, BTC-USDT, ETH-USD-SWAP等
    return symbol.find("-SWAP") != std::string::npos ||
           symbol.find("-USDT") != std::string::npos ||
           symbol.find("-USD") != std::string::npos;
}

/**
 * @brief 检查币种是否在白名单中
 */
bool is_symbol_in_whitelist(const std::string& exchange, const std::string& symbol) {
    if (exchange == "okx") {
        return std::find(okx_whitelist.begin(), okx_whitelist.end(), symbol) != okx_whitelist.end();
    } else if (exchange == "binance") {
        return std::find(binance_whitelist.begin(), binance_whitelist.end(), symbol) != binance_whitelist.end();
    }
    return false;
}

void fill_gaps_for_symbol(
    const std::string& exchange,
    const std::string& symbol,
    const std::string& interval,
    trading::gap_detector::GapDetector& detector,
    trading::historical_fetcher::HistoricalDataFetcher* fetcher,
    RedisWriter& writer
) {
    std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
    std::cout << "[GapFiller] 检查 " << exchange << ":" << symbol << ":" << interval << std::endl;

    // 使用完整的key格式检测缺失: kline:exchange:symbol:interval
    std::string full_key = exchange + ":" + symbol;
    auto gaps = detector.detect_gaps(full_key, interval);

    if (gaps.empty()) {
        std::cout << "[GapFiller] ✓ 无缺失" << std::endl;
        return;
    }

    int64_t interval_ms = trading::kline_utils::get_interval_milliseconds(interval);

    std::cout << "[GapFiller] 发现 " << gaps.size() << " 个缺失段" << std::endl;

    int total_filled = 0;

    for (size_t i = 0; i < gaps.size(); i++) {
        const auto& gap = gaps[i];
        int gap_count = gap.count(interval_ms);

        std::cout << "[GapFiller]   缺失" << (i + 1) << ": "
                  << trading::kline_utils::format_timestamp(gap.start_ts)
                  << " ~ " << trading::kline_utils::format_timestamp(gap.end_ts)
                  << " (" << gap_count << "根)" << std::endl;

        // 确定API符号格式
        std::string api_symbol = symbol;
        bool is_okx = (exchange == "okx");

        if (!is_okx) {
            // Binance符号已经是正确格式(BTCUSDT)，不需要转换
            std::cout << "[GapFiller]   Binance符号: " << api_symbol << std::endl;
        }

        // 拉取历史数据
        auto klines = fetcher->fetch_history(api_symbol, interval, gap.start_ts, gap.end_ts);

        if (klines.empty()) {
            std::cerr << "[GapFiller]   ✗ 拉取失败" << std::endl;
            continue;
        }

        // 写入Redis（使用完整的key格式）
        int written = writer.write_klines_batch(full_key, interval, klines, false);
        total_filled += written;

        std::cout << "[GapFiller]   ✓ 拉取并写入 " << written << " 根K线" << std::endl;
    }

    std::cout << "[GapFiller] " << exchange << ":" << symbol << ":" << interval << " 补全完成，共 " << total_filled << " 根" << std::endl;
}

void aggregate_filled_klines(
    const std::string& exchange,
    const std::string& symbol,
    const std::string& target_interval,
    const std::string& base_interval,
    int multiplier,
    trading::gap_detector::GapDetector& detector,
    RedisWriter& writer
) {
    std::cout << "\n[Aggregator] 聚合 " << exchange << ":" << symbol << " " << base_interval << " -> " << target_interval << std::endl;

    // 从Redis读取所有基础K线（使用完整的key格式）
    redisContext* context = redisConnect(Config::redis_host.c_str(), Config::redis_port);
    if (!context || context->err) {
        std::cerr << "[Aggregator] Redis连接失败" << std::endl;
        if (context) redisFree(context);
        return;
    }

    std::string full_key = exchange + ":" + symbol;
    std::string key = "kline:" + full_key + ":" + base_interval;
    redisReply* reply = (redisReply*)redisCommand(context, "ZRANGE %s 0 -1", key.c_str());

    if (!reply || reply->type != REDIS_REPLY_ARRAY) {
        if (reply) freeReplyObject(reply);
        redisFree(context);
        return;
    }

    // 解析所有K线
    std::vector<trading::kline_utils::Kline> base_klines;
    for (size_t i = 0; i < reply->elements; i++) {
        try {
            json kline_json = json::parse(reply->element[i]->str);
            trading::kline_utils::Kline kline;
            kline.timestamp = kline_json["timestamp"];
            kline.open = kline_json["open"];
            kline.high = kline_json["high"];
            kline.low = kline_json["low"];
            kline.close = kline_json["close"];
            kline.volume = kline_json["volume"];
            base_klines.push_back(kline);
        } catch (const std::exception& e) {
            std::cerr << "[Aggregator] 解析K线失败: " << e.what() << std::endl;
        }
    }

    freeReplyObject(reply);
    redisFree(context);

    if (base_klines.empty()) {
        std::cout << "[Aggregator] 没有基础K线数据" << std::endl;
        return;
    }

    // 按周期分组并聚合
    int64_t base_period_ms = trading::kline_utils::get_interval_milliseconds(base_interval);
    int64_t target_period_ms = base_period_ms * multiplier;

    std::map<int64_t, std::vector<trading::kline_utils::Kline>> groups;

    for (const auto& kline : base_klines) {
        int64_t aligned_ts = trading::kline_utils::align_timestamp(kline.timestamp, target_period_ms);
        groups[aligned_ts].push_back(kline);
    }

    // 聚合并写入
    int aggregated_count = 0;
    for (const auto& [aligned_ts, klines] : groups) {
        if (klines.size() == static_cast<size_t>(multiplier)) {
            auto aggregated = SimpleAggregator::aggregate(klines, aligned_ts);
            if (writer.write_kline(full_key, target_interval, aggregated, true)) {
                aggregated_count++;
            }
        }
    }

    std::cout << "[Aggregator] 生成 " << aggregated_count << " 根 " << target_interval << " K线" << std::endl;
}

// ==================== 配置加载 ====================

/**
 * @brief 加载账户配置（可选，公开市场数据不需要API密钥）
 */
bool load_config(const std::string& config_file = "accounts.json") {
    std::cout << "[配置] 加载配置文件: " << config_file << std::endl;

    // 尝试从多个位置加载配置文件
    std::vector<std::string> config_paths = {
        config_file,
        "server/" + config_file,
        "../server/" + config_file,
        "../../server/" + config_file
    };

    json config;
    bool loaded = false;

    for (const auto& path : config_paths) {
        std::ifstream file(path);
        if (file.is_open()) {
            try {
                file >> config;
                loaded = true;
                std::cout << "[配置] 成功加载: " << path << std::endl;
                break;
            } catch (const std::exception& e) {
                std::cerr << "[配置] 解析失败: " << e.what() << std::endl;
            }
        }
    }

    if (!loaded) {
        std::cout << "[配置] 未找到配置文件，将使用公开市场数据端点（不需要API密钥）" << std::endl;
    }

    // 从配置文件或环境变量加载 testnet 配置
    // 注意：对于公开市场数据（K线历史），建议使用主网以获取完整数据
    if (loaded && config.contains("default") && config["default"].is_object()) {
        auto& def = config["default"];
        // 不从配置文件读取 is_testnet，保持默认值 false（主网）
        // Config::is_testnet = def.value("is_testnet", false);
    }

    const char* testnet_env = std::getenv("TESTNET");
    if (testnet_env) {
        Config::is_testnet = (std::string(testnet_env) == "1" || std::string(testnet_env) == "true");
        std::cout << "[配置] 环境变量覆盖: TESTNET=" << testnet_env << std::endl;
    }

    // 打印配置状态
    std::cout << "\n[配置] 运行模式: " << (Config::is_testnet ? "模拟盘/测试网" : "实盘/主网") << std::endl;
    std::cout << "[配置] 说明: K线历史数据通过公开市场数据端点获取，不需要API密钥" << std::endl;
    std::cout << "[配置] 建议: 使用主网端点以获取完整的历史K线数据" << std::endl;
    std::cout << std::endl;

    return true;
}

int main(int argc, char* argv[]) {
    std::cout << "╔════════════════════════════════════════════════════════════╗" << std::endl;
    std::cout << "║        K线缺失数据自动补全工具                              ║" << std::endl;
    std::cout << "╚════════════════════════════════════════════════════════════╝" << std::endl;
    std::cout << std::endl;

    // 加载配置（从文件或环境变量）
    if (!load_config()) {
        return 1;
    }

    // 打印配置信息
    std::cout << "[配置]" << std::endl;
    std::cout << "  Redis: " << Config::redis_host << ":" << Config::redis_port << std::endl;
    std::cout << "  1min~30min K线过期: " << Config::expire_seconds_1m_to_30m / (24 * 3600) << " 天" << std::endl;
    std::cout << "  1H K线过期: " << Config::expire_seconds_1h / (24 * 3600) << " 天" << std::endl;
    std::cout << std::endl;

    // 连接Redis
    trading::gap_detector::GapDetector detector(Config::redis_host, Config::redis_port);
    if (!detector.connect()) {
        std::cerr << "[GapFiller] Redis连接失败" << std::endl;
        return 1;
    }

    RedisWriter writer(Config::redis_host, Config::redis_port);
    if (!writer.connect()) {
        std::cerr << "[GapFiller] Redis写入器连接失败" << std::endl;
        return 1;
    }

    // 从Redis动态获取所有的kline keys
    std::cout << "[初始化] 从Redis获取所有K线数据..." << std::endl;
    redisContext* context = redisConnect(Config::redis_host.c_str(), Config::redis_port);
    if (!context || context->err) {
        std::cerr << "[GapFiller] Redis连接失败" << std::endl;
        return 1;
    }

    // 使用SCAN命令获取所有kline:*:1m的keys
    std::vector<std::string> kline_keys;
    redisReply* reply = (redisReply*)redisCommand(context, "KEYS kline:*:1m");
    if (reply && reply->type == REDIS_REPLY_ARRAY) {
        for (size_t i = 0; i < reply->elements; i++) {
            kline_keys.push_back(reply->element[i]->str);
        }
        freeReplyObject(reply);
    }
    redisFree(context);

    if (kline_keys.empty()) {
        std::cout << "[GapFiller] Redis中没有找到任何1min K线数据" << std::endl;
        std::cout << "[GapFiller] 请先运行trading_server_full和data_recorder收集数据" << std::endl;
        return 0;
    }

    std::cout << "[初始化] 找到 " << kline_keys.size() << " 个币种的1min K线数据" << std::endl;

    // 解析keys，提取exchange和symbol信息
    struct SymbolInfo {
        std::string exchange;
        std::string symbol;
    };
    std::vector<SymbolInfo> symbols;
    int filtered_count = 0;

    for (const auto& key : kline_keys) {
        // key格式: kline:exchange:symbol:1m
        std::string exchange = extract_exchange_from_key(key);
        std::string symbol = extract_symbol_from_key(key);

        if (!exchange.empty() && !symbol.empty()) {
            // 检查是否在白名单中
            if (is_symbol_in_whitelist(exchange, symbol)) {
                symbols.push_back({exchange, symbol});
                std::cout << "  ✓ " << exchange << ":" << symbol << std::endl;
            } else {
                filtered_count++;
                std::cout << "  ✗ " << exchange << ":" << symbol << " (不在白名单中，跳过)" << std::endl;
            }
        }
    }

    std::cout << "\n[过滤结果] 白名单内: " << symbols.size() << " 个币种" << std::endl;
    std::cout << "[过滤结果] 已过滤: " << filtered_count << " 个币种" << std::endl;

    if (symbols.empty()) {
        std::cerr << "[GapFiller] 无法解析任何有效的symbol信息" << std::endl;
        return 1;
    }

    // 创建历史数据拉取器（公开市场数据不需要API密钥）
    std::unique_ptr<trading::historical_fetcher::OKXHistoricalFetcher> okx_fetcher;
    std::unique_ptr<trading::historical_fetcher::BinanceHistoricalFetcher> binance_fetcher;

    // OKX: 使用空凭证创建（公开市场数据端点不需要认证）
    okx_fetcher = std::make_unique<trading::historical_fetcher::OKXHistoricalFetcher>(
        "", "", "", Config::is_testnet
    );

    // Binance: 使用空凭证创建（公开市场数据端点不需要认证）
    binance_fetcher = std::make_unique<trading::historical_fetcher::BinanceHistoricalFetcher>(
        "", "", Config::is_testnet
    );

    std::cout << "\n[开始补全] 开始检测并补全缺失的K线数据..." << std::endl;

    // 对每个symbol检测并补全1min K线
    for (const auto& info : symbols) {
        // 选择对应的拉取器
        trading::historical_fetcher::HistoricalDataFetcher* fetcher = nullptr;
        if (info.exchange == "okx") {
            fetcher = okx_fetcher.get();
        } else if (info.exchange == "binance") {
            fetcher = binance_fetcher.get();
        } else {
            std::cerr << "[GapFiller] 未知的交易所: " << info.exchange << std::endl;
            continue;
        }

        // 补全1min K线
        for (const auto& interval : Config::intervals) {
            fill_gaps_for_symbol(info.exchange, info.symbol, interval, detector, fetcher, writer);
        }

        // 聚合K线
        for (const auto& [target_interval, config] : Config::aggregated_intervals) {
            const auto& [base_interval, multiplier] = config;
            aggregate_filled_klines(info.exchange, info.symbol, target_interval, base_interval, multiplier, detector, writer);
        }
    }

    std::cout << "\n╔════════════════════════════════════════════════════════════╗" << std::endl;
    std::cout << "║        K线补全完成！                                        ║" << std::endl;
    std::cout << "╚════════════════════════════════════════════════════════════╝" << std::endl;

    return 0;
}
