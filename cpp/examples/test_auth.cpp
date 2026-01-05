/**
 * @file test_auth.cpp
 * @brief 认证系统测试程序
 */

#include <iostream>
#include <cassert>
#include "../network/auth_manager.h"

using namespace trading::auth;

void test_login() {
    std::cout << "\n=== 测试登录 ===" << std::endl;

    AuthManager auth;

    // 测试正确登录
    std::string token = auth.login("admin", "admin123");
    assert(!token.empty());
    std::cout << "✓ admin登录成功" << std::endl;
    std::cout << "  Token: " << token.substr(0, 50) << "..." << std::endl;

    // 测试错误密码
    std::string bad_token = auth.login("admin", "wrongpassword");
    assert(bad_token.empty());
    std::cout << "✓ 错误密码被拒绝" << std::endl;

    // 测试不存在的用户
    std::string no_user = auth.login("nonexistent", "password");
    assert(no_user.empty());
    std::cout << "✓ 不存在的用户被拒绝" << std::endl;
}

void test_token_verification() {
    std::cout << "\n=== 测试Token验证 ===" << std::endl;

    AuthManager auth;

    std::string token = auth.login("admin", "admin123");

    TokenInfo info;
    bool valid = auth.verify_token(token, info);

    assert(valid);
    assert(info.username == "admin");
    assert(info.role == UserRole::SUPER_ADMIN);

    std::cout << "✓ Token验证成功" << std::endl;
    std::cout << "  用户: " << info.username << std::endl;
    std::cout << "  角色: " << AuthManager::role_to_string(info.role) << std::endl;

    // 测试无效Token
    TokenInfo bad_info;
    bool invalid = auth.verify_token("invalid.token.here", bad_info);
    assert(!invalid);
    std::cout << "✓ 无效Token被拒绝" << std::endl;
}

void test_logout() {
    std::cout << "\n=== 测试登出 ===" << std::endl;

    AuthManager auth;

    std::string token = auth.login("admin", "admin123");

    TokenInfo info;
    assert(auth.verify_token(token, info));
    std::cout << "✓ 登出前Token有效" << std::endl;

    auth.logout(token);

    assert(!auth.verify_token(token, info));
    std::cout << "✓ 登出后Token失效" << std::endl;
}

void test_add_user() {
    std::cout << "\n=== 测试添加用户 ===" << std::endl;

    AuthManager auth;

    // 添加新用户
    bool added = auth.add_user("trader1", "password123", UserRole::TRADER);
    assert(added);
    std::cout << "✓ 添加用户成功" << std::endl;

    // 测试新用户登录
    std::string token = auth.login("trader1", "password123");
    assert(!token.empty());
    std::cout << "✓ 新用户登录成功" << std::endl;

    TokenInfo info;
    auth.verify_token(token, info);
    assert(info.role == UserRole::TRADER);
    std::cout << "✓ 用户角色正确: " << AuthManager::role_to_string(info.role) << std::endl;

    // 测试重复添加
    bool duplicate = auth.add_user("trader1", "anotherpass", UserRole::VIEWER);
    assert(!duplicate);
    std::cout << "✓ 重复用户被拒绝" << std::endl;
}

void test_change_password() {
    std::cout << "\n=== 测试修改密码 ===" << std::endl;

    AuthManager auth;

    auth.add_user("testuser", "oldpass123", UserRole::VIEWER);

    // 修改密码
    bool changed = auth.change_password("testuser", "oldpass123", "newpass456");
    assert(changed);
    std::cout << "✓ 密码修改成功" << std::endl;

    // 旧密码无法登录
    std::string old_token = auth.login("testuser", "oldpass123");
    assert(old_token.empty());
    std::cout << "✓ 旧密码无法登录" << std::endl;

    // 新密码可以登录
    std::string new_token = auth.login("testuser", "newpass456");
    assert(!new_token.empty());
    std::cout << "✓ 新密码登录成功" << std::endl;
}

void test_permissions() {
    std::cout << "\n=== 测试权限 ===" << std::endl;

    AuthManager auth;

    // SUPER_ADMIN 拥有所有权限
    assert(auth.has_permission(UserRole::SUPER_ADMIN, "view"));
    assert(auth.has_permission(UserRole::SUPER_ADMIN, "trade"));
    assert(auth.has_permission(UserRole::SUPER_ADMIN, "manage_admin"));
    std::cout << "✓ SUPER_ADMIN 拥有所有权限" << std::endl;

    // ADMIN 不能管理其他管理员
    assert(auth.has_permission(UserRole::ADMIN, "view"));
    assert(auth.has_permission(UserRole::ADMIN, "trade"));
    assert(!auth.has_permission(UserRole::ADMIN, "manage_admin"));
    std::cout << "✓ ADMIN 权限正确" << std::endl;

    // TRADER 可以交易和查看
    assert(auth.has_permission(UserRole::TRADER, "view"));
    assert(auth.has_permission(UserRole::TRADER, "trade"));
    assert(!auth.has_permission(UserRole::TRADER, "manage_admin"));
    std::cout << "✓ TRADER 权限正确" << std::endl;

    // VIEWER 只能查看
    assert(auth.has_permission(UserRole::VIEWER, "view"));
    assert(!auth.has_permission(UserRole::VIEWER, "trade"));
    assert(!auth.has_permission(UserRole::VIEWER, "manage_admin"));
    std::cout << "✓ VIEWER 权限正确" << std::endl;
}

void test_get_users() {
    std::cout << "\n=== 测试获取用户列表 ===" << std::endl;

    AuthManager auth;

    auth.add_user("user1", "pass1", UserRole::TRADER);
    auth.add_user("user2", "pass2", UserRole::VIEWER);

    auto users = auth.get_users();

    std::cout << "用户列表:" << std::endl;
    for (const auto& user : users) {
        std::cout << "  - " << user["username"].get<std::string>()
                  << " (" << user["role"].get<std::string>() << ")" << std::endl;
    }

    assert(users.size() >= 4);  // admin, viewer, user1, user2
    std::cout << "✓ 获取用户列表成功，共 " << users.size() << " 个用户" << std::endl;
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "       认证系统测试" << std::endl;
    std::cout << "========================================" << std::endl;

    try {
        test_login();
        test_token_verification();
        test_logout();
        test_add_user();
        test_change_password();
        test_permissions();
        test_get_users();

        std::cout << "\n========================================" << std::endl;
        std::cout << "       所有测试通过！" << std::endl;
        std::cout << "========================================" << std::endl;

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n✗ 测试失败: " << e.what() << std::endl;
        return 1;
    }
}
