#pragma once

/**
 * @file auth_manager.h
 * @brief 用户认证管理器
 *
 * 功能：
 * - 用户登录/登出
 * - JWT Token 生成和验证
 * - 密码哈希（bcrypt风格，使用SHA256+盐）
 * - 角色权限管理
 */

#include <string>
#include <unordered_map>
#include <unordered_set>
#include <mutex>
#include <chrono>
#include <random>
#include <sstream>
#include <iomanip>
#include <openssl/hmac.h>
#include <openssl/sha.h>
#include <openssl/evp.h>
#include <nlohmann/json.hpp>

namespace trading {
namespace auth {

/**
 * @brief 用户角色
 */
enum class UserRole {
    VIEWER,         // 只读用户
    TRADER,         // 交易员
    ADMIN,          // 管理员
    SUPER_ADMIN     // 超级管理员
};

/**
 * @brief 用户信息
 */
struct UserInfo {
    std::string username;
    std::string password_hash;  // SHA256(password + salt)
    std::string salt;
    UserRole role;
    bool active;
    int64_t created_at;
    int64_t last_login;
};

/**
 * @brief Token信息
 */
struct TokenInfo {
    std::string username;
    UserRole role;
    int64_t expires_at;
};

/**
 * @brief 认证管理器
 */
class AuthManager {
public:
    AuthManager(const std::string& jwt_secret = "trading_framework_secret_key_2025")
        : jwt_secret_(jwt_secret), token_expiry_hours_(24) {
        // 初始化默认管理员账户
        add_user("admin", "admin123", UserRole::SUPER_ADMIN);
        add_user("viewer", "viewer123", UserRole::VIEWER);
    }

    /**
     * @brief 用户登录
     * @return JWT Token，失败返回空字符串
     */
    std::string login(const std::string& username, const std::string& password) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto it = users_.find(username);
        if (it == users_.end()) {
            return "";  // 用户不存在
        }

        UserInfo& user = it->second;
        if (!user.active) {
            return "";  // 用户已禁用
        }

        // 验证密码
        std::string hash = hash_password(password, user.salt);
        if (hash != user.password_hash) {
            return "";  // 密码错误
        }

        // 更新最后登录时间
        user.last_login = current_timestamp();

        // 生成Token
        return generate_token(username, user.role);
    }

    /**
     * @brief 验证Token
     * @return 验证成功返回true，并填充TokenInfo
     */
    bool verify_token(const std::string& token, TokenInfo& info) {
        std::lock_guard<std::mutex> lock(mutex_);

        // 检查是否在黑名单中（已登出）
        if (revoked_tokens_.find(token) != revoked_tokens_.end()) {
            return false;
        }

        // 检查Token缓存
        auto it = active_tokens_.find(token);
        if (it != active_tokens_.end()) {
            if (it->second.expires_at > current_timestamp()) {
                info = it->second;
                return true;
            }
            // Token已过期，移除
            active_tokens_.erase(it);
            return false;
        }

        // 尝试解析Token
        if (!parse_token(token, info)) {
            return false;
        }

        // 检查是否过期
        if (info.expires_at <= current_timestamp()) {
            return false;
        }

        // 缓存有效Token
        active_tokens_[token] = info;
        return true;
    }

    /**
     * @brief 登出（使Token失效）
     */
    void logout(const std::string& token) {
        std::lock_guard<std::mutex> lock(mutex_);
        active_tokens_.erase(token);
        revoked_tokens_.insert(token);  // 加入黑名单
    }

    /**
     * @brief 添加用户
     */
    bool add_user(const std::string& username, const std::string& password, UserRole role) {
        std::lock_guard<std::mutex> lock(mutex_);

        if (users_.find(username) != users_.end()) {
            return false;  // 用户已存在
        }

        UserInfo user;
        user.username = username;
        user.salt = generate_salt();
        user.password_hash = hash_password(password, user.salt);
        user.role = role;
        user.active = true;
        user.created_at = current_timestamp();
        user.last_login = 0;

        users_[username] = user;
        return true;
    }

    /**
     * @brief 修改密码
     */
    bool change_password(const std::string& username, const std::string& old_password,
                         const std::string& new_password) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto it = users_.find(username);
        if (it == users_.end()) {
            return false;
        }

        UserInfo& user = it->second;

        // 验证旧密码
        if (hash_password(old_password, user.salt) != user.password_hash) {
            return false;
        }

        // 更新密码
        user.salt = generate_salt();
        user.password_hash = hash_password(new_password, user.salt);

        // 使该用户所有Token失效
        invalidate_user_tokens(username);

        return true;
    }

    /**
     * @brief 检查权限
     */
    bool has_permission(UserRole user_role, const std::string& action) {
        // 权限矩阵
        if (user_role == UserRole::SUPER_ADMIN) {
            return true;  // 超级管理员拥有所有权限
        }

        if (user_role == UserRole::ADMIN) {
            // 管理员不能管理其他管理员
            return action != "manage_admin";
        }

        if (user_role == UserRole::TRADER) {
            // 交易员可以交易和查看
            return action == "view" || action == "trade";
        }

        if (user_role == UserRole::VIEWER) {
            // 只读用户只能查看
            return action == "view";
        }

        return false;
    }

    /**
     * @brief 获取用户列表（管理员功能）
     */
    nlohmann::json get_users() {
        std::lock_guard<std::mutex> lock(mutex_);

        nlohmann::json result = nlohmann::json::array();
        for (const auto& [username, user] : users_) {
            result.push_back({
                {"username", username},
                {"role", role_to_string(user.role)},
                {"active", user.active},
                {"created_at", user.created_at},
                {"last_login", user.last_login}
            });
        }
        return result;
    }

    /**
     * @brief 设置Token过期时间（小时）
     */
    void set_token_expiry(int hours) {
        token_expiry_hours_ = hours;
    }

    // 角色转换
    static std::string role_to_string(UserRole role) {
        switch (role) {
            case UserRole::SUPER_ADMIN: return "SUPER_ADMIN";
            case UserRole::ADMIN: return "ADMIN";
            case UserRole::TRADER: return "TRADER";
            case UserRole::VIEWER: return "VIEWER";
            default: return "UNKNOWN";
        }
    }

    static UserRole string_to_role(const std::string& str) {
        if (str == "SUPER_ADMIN") return UserRole::SUPER_ADMIN;
        if (str == "ADMIN") return UserRole::ADMIN;
        if (str == "TRADER") return UserRole::TRADER;
        return UserRole::VIEWER;
    }

private:
    // 生成随机盐
    std::string generate_salt() {
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_int_distribution<> dis(0, 255);

        std::stringstream ss;
        for (int i = 0; i < 16; ++i) {
            ss << std::hex << std::setw(2) << std::setfill('0') << dis(gen);
        }
        return ss.str();
    }

    // 密码哈希
    std::string hash_password(const std::string& password, const std::string& salt) {
        std::string data = password + salt;
        unsigned char hash[SHA256_DIGEST_LENGTH];

        SHA256((unsigned char*)data.c_str(), data.length(), hash);

        std::stringstream ss;
        for (int i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
            ss << std::hex << std::setw(2) << std::setfill('0') << (int)hash[i];
        }
        return ss.str();
    }

    // HMAC SHA256
    std::string hmac_sha256(const std::string& key, const std::string& data) {
        unsigned char hash[SHA256_DIGEST_LENGTH];

        HMAC(EVP_sha256(), key.c_str(), key.length(),
             (unsigned char*)data.c_str(), data.length(),
             hash, nullptr);

        std::stringstream ss;
        for (int i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
            ss << std::hex << std::setw(2) << std::setfill('0') << (int)hash[i];
        }
        return ss.str();
    }

    // Base64编码
    std::string base64_encode(const std::string& input) {
        static const char* chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        std::string result;
        int val = 0, valb = -6;

        for (unsigned char c : input) {
            val = (val << 8) + c;
            valb += 8;
            while (valb >= 0) {
                result.push_back(chars[(val >> valb) & 0x3F]);
                valb -= 6;
            }
        }
        if (valb > -6) result.push_back(chars[((val << 8) >> (valb + 8)) & 0x3F]);
        while (result.size() % 4) result.push_back('=');
        return result;
    }

    // Base64解码
    std::string base64_decode(const std::string& input) {
        static const int T[256] = {
            -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
            -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
            -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,
            52,53,54,55,56,57,58,59,60,61,-1,-1,-1,-1,-1,-1,
            -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,
            15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
            -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,
            41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,-1
        };

        std::string result;
        int val = 0, valb = -8;

        for (unsigned char c : input) {
            if (T[c] == -1) break;
            val = (val << 6) + T[c];
            valb += 6;
            if (valb >= 0) {
                result.push_back(char((val >> valb) & 0xFF));
                valb -= 8;
            }
        }
        return result;
    }

    // 生成JWT Token
    std::string generate_token(const std::string& username, UserRole role) {
        int64_t expires = current_timestamp() + token_expiry_hours_ * 3600 * 1000;

        // Header
        nlohmann::json header = {{"alg", "HS256"}, {"typ", "JWT"}};

        // Payload
        nlohmann::json payload = {
            {"username", username},
            {"role", role_to_string(role)},
            {"exp", expires},
            {"iat", current_timestamp()}
        };

        std::string header_b64 = base64_encode(header.dump());
        std::string payload_b64 = base64_encode(payload.dump());

        // Signature
        std::string signature_input = header_b64 + "." + payload_b64;
        std::string signature = hmac_sha256(jwt_secret_, signature_input);
        std::string signature_b64 = base64_encode(signature);

        std::string token = header_b64 + "." + payload_b64 + "." + signature_b64;

        // 缓存Token
        TokenInfo info;
        info.username = username;
        info.role = role;
        info.expires_at = expires;
        active_tokens_[token] = info;

        return token;
    }

    // 解析JWT Token
    bool parse_token(const std::string& token, TokenInfo& info) {
        // 分割Token
        size_t pos1 = token.find('.');
        size_t pos2 = token.rfind('.');

        if (pos1 == std::string::npos || pos2 == std::string::npos || pos1 == pos2) {
            return false;
        }

        std::string header_b64 = token.substr(0, pos1);
        std::string payload_b64 = token.substr(pos1 + 1, pos2 - pos1 - 1);
        std::string signature_b64 = token.substr(pos2 + 1);

        // 验证签名
        std::string signature_input = header_b64 + "." + payload_b64;
        std::string expected_sig = base64_encode(hmac_sha256(jwt_secret_, signature_input));

        if (signature_b64 != expected_sig) {
            return false;
        }

        // 解析Payload
        try {
            std::string payload_str = base64_decode(payload_b64);
            auto payload = nlohmann::json::parse(payload_str);

            info.username = payload.value("username", "");
            info.role = string_to_role(payload.value("role", "VIEWER"));
            info.expires_at = payload.value("exp", (int64_t)0);

            return true;
        } catch (...) {
            return false;
        }
    }

    // 使用户所有Token失效
    void invalidate_user_tokens(const std::string& username) {
        for (auto it = active_tokens_.begin(); it != active_tokens_.end();) {
            if (it->second.username == username) {
                it = active_tokens_.erase(it);
            } else {
                ++it;
            }
        }
    }

    // 获取当前时间戳（毫秒）
    int64_t current_timestamp() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }

    std::string jwt_secret_;
    int token_expiry_hours_;
    std::unordered_map<std::string, UserInfo> users_;
    std::unordered_map<std::string, TokenInfo> active_tokens_;
    std::unordered_set<std::string> revoked_tokens_;  // 已登出Token黑名单
    std::mutex mutex_;
};

} // namespace auth
} // namespace trading
