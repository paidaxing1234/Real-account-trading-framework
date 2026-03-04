/**
 * @file test_vpn_monitor.cpp
 * @brief VPN/代理网络监控功能测试
 *
 * 测试方式：不断开VPN，通过修改代理端口模拟代理中断
 *
 * 测试流程：
 *   1. 先用正确端口(7890)探测 → 应该成功
 *   2. 用错误端口(7899)探测 → 应该失败，触发告警邮件
 *   3. 切回正确端口(7890)探测 → 应该成功，触发恢复通知
 *
 * 编译: make test_vpn_monitor
 * 运行: ./test_vpn_monitor
 */

#include <iostream>
#include <chrono>
#include <thread>
#include <curl/curl.h>
#include "../network/vpn_network_monitor.h"
#include "../trading/risk_manager.h"

using namespace trading;

// ============================================================
// 测试1: 单次代理探测（不发邮件，只测连通性）
// ============================================================
bool test_probe_single(const std::string& proxy_host, int proxy_port,
                       const std::string& target_url) {
    std::string proxy_url = "http://" + proxy_host + ":" + std::to_string(proxy_port);

    CURL* curl = curl_easy_init();
    if (!curl) {
        std::cerr << "  curl_easy_init 失败\n";
        return false;
    }

    curl_easy_setopt(curl, CURLOPT_URL, target_url.c_str());
    curl_easy_setopt(curl, CURLOPT_NOBODY, 1L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);
    curl_easy_setopt(curl, CURLOPT_PROXY, proxy_url.c_str());
    curl_easy_setopt(curl, CURLOPT_PROXYTYPE, CURLPROXY_HTTP);
    curl_easy_setopt(curl, CURLOPT_HTTPPROXYTUNNEL, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);

    auto start = std::chrono::steady_clock::now();
    CURLcode res = curl_easy_perform(curl);
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - start).count();

    long http_code = 0;
    if (res == CURLE_OK) {
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    }

    curl_easy_cleanup(curl);

    std::cout << "  代理: " << proxy_url << "\n";
    std::cout << "  目标: " << target_url << "\n";
    std::cout << "  结果: " << (res == CURLE_OK ? "成功" : "失败")
              << " (curl code=" << res << ", http=" << http_code
              << ", 耗时=" << elapsed << "ms)\n";

    return (res == CURLE_OK);
}

// ============================================================
// 测试2: 完整监控流程（会发邮件告警）
// ============================================================
void test_full_monitor_flow() {
    std::cout << "\n========================================\n";
    std::cout << "  测试2: 完整监控流程（会发送告警邮件）\n";
    std::cout << "========================================\n\n";

    // 创建 RiskManager（使用默认配置，不需要真实风控参数）
    RiskLimits limits;
    AlertConfig alert_config;
    RiskManager risk_manager(limits, alert_config);

    // 创建临时配置：用错误端口模拟代理中断
    std::string test_config_path = "/tmp/test_vpn_monitor_config.json";
    {
        nlohmann::json config;
        config["network_monitor"] = {
            {"enabled", true},
            {"proxy_host", "127.0.0.1"},
            {"proxy_port", 7899},  // 错误端口！模拟代理不通
            {"check_targets", {"https://www.okx.com"}},
            {"check_interval_seconds", 3},  // 缩短间隔加快测试
            {"check_timeout_seconds", 3},
            {"fail_threshold", 2},  // 2次失败就告警
            {"alert_cooldown_seconds", 60},
            {"notify_on_recovery", true}
        };

        // 从真实配置读取邮件设置
        std::string real_config = "/home/xyc/Real-account-trading-framework-main/"
                                  "Real-account-trading-framework-main/cpp/"
                                  "totalconfig/network_monitor_config.json";
        try {
            std::ifstream f(real_config);
            nlohmann::json real_j;
            f >> real_j;
            if (real_j.contains("email_alert")) {
                config["email_alert"] = real_j["email_alert"];
            }
        } catch (...) {
            std::cerr << "  警告: 无法读取真实邮件配置，邮件告警可能不工作\n";
        }

        std::ofstream out(test_config_path);
        out << config.dump(2);
        out.close();
    }

    VpnNetworkMonitor monitor(risk_manager);
    if (!monitor.load_config(test_config_path)) {
        std::cerr << "  配置加载失败\n";
        return;
    }

    std::cout << "\n--- 阶段1: 使用错误端口(7899)，等待告警触发 ---\n";
    std::cout << "  预期: 2次失败后发送中断告警邮件\n\n";
    monitor.start();

    // 等待足够时间让告警触发 (2次失败 × 3秒间隔 + 5秒启动延迟 + 余量)
    std::cout << "  等待 20 秒...\n";
    std::this_thread::sleep_for(std::chrono::seconds(20));

    // 打印状态
    auto status = monitor.get_status();
    std::cout << "\n  当前状态: " << status.dump(2) << "\n";

    // 停止监控
    monitor.stop();

    std::cout << "\n--- 阶段1 完成 ---\n";
    std::cout << "  请检查邮箱是否收到 VPN 中断告警邮件\n";
}

// ============================================================
// 测试3: 中断 → 恢复 完整流程
// ============================================================
void test_interrupt_and_recovery() {
    std::cout << "\n========================================\n";
    std::cout << "  测试3: 中断 → 恢复 完整流程\n";
    std::cout << "========================================\n\n";

    RiskLimits limits;
    AlertConfig alert_config;
    RiskManager risk_manager(limits, alert_config);

    // 阶段1: 错误端口配置
    std::string config_path = "/tmp/test_vpn_recovery_config.json";
    auto write_config = [&](int port) {
        nlohmann::json config;
        config["network_monitor"] = {
            {"enabled", true},
            {"proxy_host", "127.0.0.1"},
            {"proxy_port", port},
            {"check_targets", {"https://www.okx.com"}},
            {"check_interval_seconds", 3},
            {"check_timeout_seconds", 3},
            {"fail_threshold", 2},
            {"alert_cooldown_seconds", 60},
            {"notify_on_recovery", true}
        };

        std::string real_config = "/home/xyc/Real-account-trading-framework-main/"
                                  "Real-account-trading-framework-main/cpp/"
                                  "totalconfig/network_monitor_config.json";
        try {
            std::ifstream f(real_config);
            nlohmann::json real_j;
            f >> real_j;
            if (real_j.contains("email_alert")) {
                config["email_alert"] = real_j["email_alert"];
            }
        } catch (...) {}

        std::ofstream out(config_path);
        out << config.dump(2);
    };

    // 注意：VpnNetworkMonitor 的端口在 load_config 时就固定了
    // 要测试恢复，我们需要用两个 monitor 实例

    // 阶段1: 错误端口 → 触发告警
    std::cout << "--- 阶段1: 错误端口(7899) → 触发中断告警 ---\n";
    write_config(7899);
    {
        VpnNetworkMonitor monitor(risk_manager);
        monitor.load_config(config_path);
        monitor.start();
        std::cout << "  等待 18 秒让告警触发...\n";
        std::this_thread::sleep_for(std::chrono::seconds(18));
        auto status = monitor.get_status();
        std::cout << "  状态: proxy_down=" << status["proxy_down"]
                  << ", failures=" << status["consecutive_failures"]
                  << ", alerts=" << status["alerts_sent"] << "\n";
        monitor.stop();
    }

    std::cout << "\n--- 阶段2: 正确端口(7890) → 验证代理正常 ---\n";
    write_config(7890);
    {
        VpnNetworkMonitor monitor(risk_manager);
        monitor.load_config(config_path);
        monitor.start();
        std::cout << "  等待 12 秒验证代理正常...\n";
        std::this_thread::sleep_for(std::chrono::seconds(12));
        auto status = monitor.get_status();
        std::cout << "  状态: proxy_down=" << status["proxy_down"]
                  << ", failures=" << status["consecutive_failures"]
                  << ", checks=" << status["total_checks"] << "\n";
        monitor.stop();
    }

    std::cout << "\n--- 测试3 完成 ---\n";
    std::cout << "  请检查邮箱：应收到1封中断告警\n";
}

// ============================================================
// main
// ============================================================
int main(int argc, char* argv[]) {
    std::cout << "========================================\n";
    std::cout << "  VPN/代理 网络监控功能测试\n";
    std::cout << "========================================\n";

    curl_global_init(CURL_GLOBAL_ALL);

    // 测试1: 基础连通性测试（不发邮件）
    std::cout << "\n--- 测试1: 基础代理连通性 ---\n\n";

    std::cout << "[1a] 正确端口(7890) → 应该成功:\n";
    bool ok1 = test_probe_single("127.0.0.1", 7890, "https://www.okx.com");
    std::cout << "  判定: " << (ok1 ? "✓ 通过" : "✗ 失败") << "\n\n";

    std::cout << "[1b] 错误端口(7899) → 应该失败:\n";
    bool ok2 = test_probe_single("127.0.0.1", 7899, "https://www.okx.com");
    std::cout << "  判定: " << (!ok2 ? "✓ 通过（预期失败）" : "✗ 异常（不应该成功）") << "\n\n";

    std::cout << "[1c] 正确端口(7890) → Binance:\n";
    bool ok3 = test_probe_single("127.0.0.1", 7890, "https://fapi.binance.com");
    std::cout << "  判定: " << (ok3 ? "✓ 通过" : "✗ 失败") << "\n";

    // 根据参数决定是否继续
    if (argc > 1 && std::string(argv[1]) == "--full") {
        test_full_monitor_flow();
    } else if (argc > 1 && std::string(argv[1]) == "--recovery") {
        test_interrupt_and_recovery();
    } else {
        std::cout << "\n========================================\n";
        std::cout << "  基础连通性测试完成\n";
        std::cout << "========================================\n";
        std::cout << "\n  要测试完整告警流程（会发送邮件），请运行:\n";
        std::cout << "    ./test_vpn_monitor --full       # 测试中断告警\n";
        std::cout << "    ./test_vpn_monitor --recovery   # 测试中断+恢复\n";
    }

    curl_global_cleanup();
    return 0;
}
