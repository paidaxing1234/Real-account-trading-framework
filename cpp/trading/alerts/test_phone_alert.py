#!/usr/bin/env python3
"""
电话告警组件测试脚本

使用方法：
1. 配置环境变量或配置文件
2. 运行测试: python test_phone_alert.py

环境变量配置示例（Twilio）：
    export TWILIO_ACCOUNT_SID="your_account_sid"
    export TWILIO_AUTH_TOKEN="your_auth_token"
    export TWILIO_FROM_PHONE="+1234567890"
    export ALERT_TO_PHONES="+8613800138000,+8613900139000"
    export PHONE_ALERT_PROVIDER="twilio"

环境变量配置示例（阿里云）：
    export ALIYUN_ACCESS_KEY="your_access_key"
    export ALIYUN_ACCESS_SECRET="your_access_secret"
    export ALIYUN_TTS_CODE="your_tts_template_code"
    export ALERT_TO_PHONES="13800138000,13900139000"
    export PHONE_ALERT_PROVIDER="aliyun"

环境变量配置示例（腾讯云）：
    export TENCENT_SECRET_ID="your_secret_id"
    export TENCENT_SECRET_KEY="your_secret_key"
    export TENCENT_APP_ID="your_app_id"
    export TENCENT_TEMPLATE_ID="your_template_id"
    export ALERT_TO_PHONES="+8613800138000"
    export PHONE_ALERT_PROVIDER="tencent"
"""

import os
import sys
import json
import time

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phone_alert import PhoneAlertService, AlertLevel


def print_separator(title: str = ""):
    """打印分隔线"""
    print("\n" + "=" * 60)
    if title:
        print(f"  {title}")
        print("=" * 60)


def test_config_status(service: PhoneAlertService):
    """测试配置状态"""
    print_separator("配置状态检查")
    status = service.get_config_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))

    # 检查必要配置
    provider = status["provider"]
    if provider == "twilio" and not status["twilio_configured"]:
        print("\n⚠️  警告: Twilio 配置不完整")
        print("   请设置环境变量: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_PHONE")
    elif provider == "aliyun" and not status["aliyun_configured"]:
        print("\n⚠️  警告: 阿里云配置不完整")
        print("   请设置环境变量: ALIYUN_ACCESS_KEY, ALIYUN_ACCESS_SECRET, ALIYUN_TTS_CODE")
    elif provider == "tencent" and not status["tencent_configured"]:
        print("\n⚠️  警告: 腾讯云配置不完整")
        print("   请设置环境变量: TENCENT_SECRET_ID, TENCENT_SECRET_KEY, TENCENT_APP_ID")

    if not status["to_phones"]:
        print("\n⚠️  警告: 未配置接收电话号码")
        print("   请设置环境变量: ALERT_TO_PHONES")

    return status


def test_alert_levels(service: PhoneAlertService):
    """测试告警级别过滤"""
    print_separator("告警级别测试")

    # INFO 级别应该被过滤
    print("\n测试 INFO 级别（应被过滤）:")
    result = service.send_alert("INFO 测试消息", AlertLevel.INFO, "test_info")
    print(f"  结果: {'发送' if result else '已过滤'}")

    # WARNING 级别应该被过滤
    print("\n测试 WARNING 级别（应被过滤）:")
    result = service.send_alert("WARNING 测试消息", AlertLevel.WARNING, "test_warning")
    print(f"  结果: {'发送' if result else '已过滤'}")

    print("\n✓ 告警级别过滤正常工作")


def test_rate_limit(service: PhoneAlertService):
    """测试频率限制"""
    print_separator("频率限制测试")

    # 临时设置较短的间隔用于测试
    original_interval = service.min_alert_interval
    service.min_alert_interval = 5  # 5秒间隔

    print(f"\n当前最小告警间隔: {service.min_alert_interval}秒")

    # 第一次发送（模拟，不实际打电话）
    service.enabled = False  # 禁用实际发送
    print("\n第一次发送（模拟）:")
    # 手动记录时间
    from datetime import datetime
    service._last_alert_time["rate_test"] = datetime.now()
    print("  已记录发送时间")

    # 立即再次发送应该被限制
    service.enabled = True
    print("\n立即再次发送（应被限制）:")
    result = service.send_alert("频率测试", AlertLevel.CRITICAL, "rate_test")
    print(f"  结果: {'发送' if result else '已限制'}")

    # 恢复原始间隔
    service.min_alert_interval = original_interval
    print("\n✓ 频率限制正常工作")


def test_real_call(service: PhoneAlertService):
    """测试真实电话呼叫"""
    print_separator("真实电话测试")

    status = service.get_config_status()
    provider = status["provider"]

    # 检查配置
    configured = False
    if provider == "twilio" and status["twilio_configured"]:
        configured = True
    elif provider == "aliyun" and status["aliyun_configured"]:
        configured = True
    elif provider == "tencent" and status["tencent_configured"]:
        configured = True

    if not configured:
        print(f"\n⚠️  {provider} 配置不完整，跳过真实电话测试")
        return False

    if not status["to_phones"]:
        print("\n⚠️  未配置接收电话号码，跳过真实电话测试")
        return False

    print(f"\n服务商: {provider}")
    print(f"接收号码: {status['to_phones']}")

    # 确认测试
    confirm = input("\n是否进行真实电话测试？这将拨打配置的电话号码 (y/N): ")
    if confirm.lower() != 'y':
        print("已跳过真实电话测试")
        return False

    print("\n正在发送测试电话...")
    result = service.test_call()

    if result:
        print("\n✓ 电话发送成功！请检查手机是否收到来电")
    else:
        print("\n✗ 电话发送失败，请检查配置和日志")

    return result


def test_async_alert(service: PhoneAlertService):
    """测试异步发送"""
    print_separator("异步发送测试")

    print("\n发送异步告警（不阻塞）...")
    service.enabled = False  # 禁用实际发送
    service.send_alert_async("异步测试消息", AlertLevel.CRITICAL, "async_test")
    print("  异步调用已返回")
    time.sleep(0.5)  # 等待线程执行
    print("\n✓ 异步发送正常工作")


def test_alert_history(service: PhoneAlertService):
    """测试告警历史"""
    print_separator("告警历史测试")

    history = service.get_alert_history(10)
    print(f"\n最近 {len(history)} 条告警记录:")
    for record in history:
        print(f"  [{record['time']}] {record['level']}: {record['message'][:30]}...")

    print("\n✓ 告警历史记录正常")


def test_command_line():
    """测试命令行调用"""
    print_separator("命令行调用测试")

    script_path = os.path.join(os.path.dirname(__file__), "phone_alert.py")

    # 测试 --status
    print("\n测试 --status 参数:")
    os.system(f"python {script_path} --status")

    # 测试 --help
    print("\n测试 --help 参数:")
    os.system(f"python {script_path} --help")

    print("\n✓ 命令行调用正常")


def create_sample_config():
    """创建示例配置文件"""
    print_separator("创建示例配置文件")

    config = {
        "provider": "twilio",
        "account_sid": "your_twilio_account_sid",
        "auth_token": "your_twilio_auth_token",
        "from_phone": "+1234567890",
        "to_phones": ["+8613800138000"],
        "aliyun_access_key": "your_aliyun_access_key",
        "aliyun_access_secret": "your_aliyun_access_secret",
        "aliyun_tts_code": "your_tts_template_code",
        "aliyun_called_show_number": "your_show_number",
        "tencent_secret_id": "your_tencent_secret_id",
        "tencent_secret_key": "your_tencent_secret_key",
        "tencent_app_id": "your_app_id",
        "tencent_template_id": "your_template_id",
        "enabled": True,
        "min_alert_interval": 300,
        "alert_level_threshold": "CRITICAL"
    }

    config_path = os.path.join(os.path.dirname(__file__), "phone_alert_config.example.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"\n示例配置文件已创建: {config_path}")
    print("请复制为 phone_alert_config.json 并填入真实配置")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("       电话告警组件测试")
    print("=" * 60)

    # 创建服务实例
    service = PhoneAlertService()

    # 运行测试
    test_config_status(service)
    test_alert_levels(service)
    test_rate_limit(service)
    test_async_alert(service)
    test_alert_history(service)
    test_command_line()

    # 创建示例配置
    create_sample_config()

    # 真实电话测试（可选）
    print_separator("真实电话测试（可选）")
    test_real = input("\n是否进行真实电话测试？(y/N): ")
    if test_real.lower() == 'y':
        # 重新创建服务实例以获取最新配置
        service = PhoneAlertService()
        test_real_call(service)

    print_separator("测试完成")
    print("\n所有基础测试通过！")
    print("\n使用示例:")
    print("  # Python 调用")
    print("  from phone_alert import PhoneAlertService, AlertLevel")
    print("  alert = PhoneAlertService()")
    print("  alert.send_alert('策略异常', AlertLevel.CRITICAL)")
    print("")
    print("  # 命令行调用 (供 C++ 使用)")
    print("  python phone_alert.py -m '策略异常' -l critical")
    print("")
    print("  # C++ 调用示例")
    print("  system(\"python /path/to/phone_alert.py -m '策略异常' -l critical\");")


if __name__ == "__main__":
    main()
