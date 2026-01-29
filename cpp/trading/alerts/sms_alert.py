#!/usr/bin/env python3
"""
短信告警组件 - 风控系统

支持的服务商：
- twilio: 国际通用
- aliyun: 阿里云短信
- tencent: 腾讯云短信

使用方式：
1. Python 直接调用:
    from sms_alert import SMSAlertService, AlertLevel
    sms = SMSAlertService(provider="aliyun", ...)
    sms.send_alert("策略异常", AlertLevel.WARNING)

2. 命令行调用 (供 C++ 使用):
    python sms_alert.py --provider aliyun --message "策略异常" --level warning
"""

import os
import sys
import json
import argparse
import threading
import requests
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class AlertLevel(Enum):
    """告警级别"""
    INFO = 1       # 信息通知
    WARNING = 2    # 警告
    CRITICAL = 3   # 严重告警


class SMSAlertService:
    """
    短信告警服务组件

    使用示例：
        sms_service = SMSAlertService(
            provider="aliyun",
            aliyun_access_key="your_key",
            aliyun_access_secret="your_secret",
            aliyun_sign_name="你的签名",
            aliyun_template_code="SMS_123456",
            to_phones=["13800138000"]
        )
        sms_service.send_alert("策略异常：持仓超限", AlertLevel.WARNING)
    """

    def __init__(
        self,
        provider: str = "aliyun",
        # Twilio 配置
        account_sid: str = "",
        auth_token: str = "",
        from_phone: str = "",
        to_phones: List[str] = None,
        # 阿里云专用参数
        aliyun_access_key: str = "",
        aliyun_access_secret: str = "",
        aliyun_sign_name: str = "",
        aliyun_template_code: str = "",
        # 腾讯云专用参数
        tencent_secret_id: str = "",
        tencent_secret_key: str = "",
        tencent_app_id: str = "",
        tencent_sign_name: str = "",
        tencent_template_id: str = "",
        # 通用配置
        enabled: bool = True,
        min_alert_interval: int = 60,  # 最小告警间隔（秒）
        alert_level_threshold: AlertLevel = AlertLevel.WARNING,
        config_file: str = "",
    ):
        if config_file and os.path.exists(config_file):
            self._load_config(config_file)
        else:
            self.provider = provider
            self.account_sid = account_sid
            self.auth_token = auth_token
            self.from_phone = from_phone
            self.to_phones = to_phones or []

            self.aliyun_access_key = aliyun_access_key
            self.aliyun_access_secret = aliyun_access_secret
            self.aliyun_sign_name = aliyun_sign_name
            self.aliyun_template_code = aliyun_template_code

            self.tencent_secret_id = tencent_secret_id
            self.tencent_secret_key = tencent_secret_key
            self.tencent_app_id = tencent_app_id
            self.tencent_sign_name = tencent_sign_name
            self.tencent_template_id = tencent_template_id

            self.enabled = enabled
            self.min_alert_interval = min_alert_interval
            self.alert_level_threshold = alert_level_threshold

        self._load_from_env()

        self._last_alert_time: Dict[str, datetime] = {}
        self._alert_history: List[Dict] = []
        self._lock = threading.Lock()

    def _load_config(self, config_file: str):
        """从配置文件加载"""
        with open(config_file, 'r') as f:
            config = json.load(f)

        self.provider = config.get("provider", "aliyun")
        self.account_sid = config.get("account_sid", "")
        self.auth_token = config.get("auth_token", "")
        self.from_phone = config.get("from_phone", "")
        self.to_phones = config.get("to_phones", [])

        self.aliyun_access_key = config.get("aliyun_access_key", "")
        self.aliyun_access_secret = config.get("aliyun_access_secret", "")
        self.aliyun_sign_name = config.get("aliyun_sign_name", "")
        self.aliyun_template_code = config.get("aliyun_template_code", "")

        self.tencent_secret_id = config.get("tencent_secret_id", "")
        self.tencent_secret_key = config.get("tencent_secret_key", "")
        self.tencent_app_id = config.get("tencent_app_id", "")
        self.tencent_sign_name = config.get("tencent_sign_name", "")
        self.tencent_template_id = config.get("tencent_template_id", "")

        self.enabled = config.get("enabled", True)
        self.min_alert_interval = config.get("min_alert_interval", 60)
        threshold = config.get("alert_level_threshold", "WARNING")
        self.alert_level_threshold = AlertLevel[threshold]

    def _load_from_env(self):
        """从环境变量加载配置"""
        # Twilio
        if os.getenv("TWILIO_ACCOUNT_SID"):
            self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        if os.getenv("TWILIO_AUTH_TOKEN"):
            self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        if os.getenv("TWILIO_FROM_PHONE"):
            self.from_phone = os.getenv("TWILIO_FROM_PHONE")
        if os.getenv("ALERT_TO_PHONES"):
            self.to_phones = os.getenv("ALERT_TO_PHONES").split(",")

        # 阿里云
        if os.getenv("ALIYUN_ACCESS_KEY"):
            self.aliyun_access_key = os.getenv("ALIYUN_ACCESS_KEY")
        if os.getenv("ALIYUN_ACCESS_SECRET"):
            self.aliyun_access_secret = os.getenv("ALIYUN_ACCESS_SECRET")
        if os.getenv("ALIYUN_SMS_SIGN_NAME"):
            self.aliyun_sign_name = os.getenv("ALIYUN_SMS_SIGN_NAME")
        if os.getenv("ALIYUN_SMS_TEMPLATE_CODE"):
            self.aliyun_template_code = os.getenv("ALIYUN_SMS_TEMPLATE_CODE")

        # 腾讯云
        if os.getenv("TENCENT_SECRET_ID"):
            self.tencent_secret_id = os.getenv("TENCENT_SECRET_ID")
        if os.getenv("TENCENT_SECRET_KEY"):
            self.tencent_secret_key = os.getenv("TENCENT_SECRET_KEY")
        if os.getenv("TENCENT_SMS_APP_ID"):
            self.tencent_app_id = os.getenv("TENCENT_SMS_APP_ID")
        if os.getenv("TENCENT_SMS_SIGN_NAME"):
            self.tencent_sign_name = os.getenv("TENCENT_SMS_SIGN_NAME")
        if os.getenv("TENCENT_SMS_TEMPLATE_ID"):
            self.tencent_template_id = os.getenv("TENCENT_SMS_TEMPLATE_ID")

        # 通用
        if os.getenv("SMS_ALERT_PROVIDER"):
            self.provider = os.getenv("SMS_ALERT_PROVIDER")

    def send_alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        alert_type: str = "default",
        force: bool = False
    ) -> bool:
        """发送短信告警"""
        if not self.enabled:
            print(f"[SMSAlert] 短信服务已禁用")
            return False

        if level.value < self.alert_level_threshold.value:
            print(f"[SMSAlert] 告警级别 {level.name} 低于阈值 {self.alert_level_threshold.name}")
            return False

        if not force:
            with self._lock:
                last_time = self._last_alert_time.get(alert_type)
                if last_time:
                    elapsed = (datetime.now() - last_time).total_seconds()
                    if elapsed < self.min_alert_interval:
                        print(f"[SMSAlert] 告警间隔不足，距上次 {elapsed:.0f}s")
                        return False

        alert_record = {
            "time": datetime.now().isoformat(),
            "message": message,
            "level": level.name,
            "type": alert_type,
            "sent": False
        }

        print(f"[SMSAlert] 发送短信: {message}")
        success = self._send_sms(message)
        alert_record["sent"] = success

        with self._lock:
            self._alert_history.append(alert_record)
            if len(self._alert_history) > 1000:
                self._alert_history = self._alert_history[-500:]
            if success:
                self._last_alert_time[alert_type] = datetime.now()

        return success

    def _send_sms(self, message: str) -> bool:
        """发送短信"""
        try:
            if self.provider == "twilio":
                return self._send_twilio(message)
            elif self.provider == "aliyun":
                return self._send_aliyun(message)
            elif self.provider == "tencent":
                return self._send_tencent(message)
            else:
                print(f"[SMSAlert] 不支持的服务商: {self.provider}")
                return False
        except Exception as e:
            print(f"[SMSAlert] 发送失败: {e}")
            return False

    def _send_twilio(self, message: str) -> bool:
        """通过 Twilio 发送短信"""
        if not all([self.account_sid, self.auth_token, self.from_phone, self.to_phones]):
            print("[SMSAlert] Twilio 配置不完整")
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

        success_count = 0
        for phone in self.to_phones:
            try:
                response = requests.post(
                    url,
                    auth=(self.account_sid, self.auth_token),
                    data={
                        "To": phone,
                        "From": self.from_phone,
                        "Body": message
                    },
                    timeout=30
                )
                if response.status_code in [200, 201]:
                    print(f"[SMSAlert] Twilio 发送成功: {phone}")
                    success_count += 1
                else:
                    print(f"[SMSAlert] Twilio 发送失败: {phone}, {response.text[:100]}")
            except Exception as e:
                print(f"[SMSAlert] Twilio 发送异常: {phone}, {e}")

        return success_count > 0

    def _send_aliyun(self, message: str) -> bool:
        """通过阿里云发送短信"""
        if not all([self.aliyun_access_key, self.aliyun_access_secret,
                    self.aliyun_sign_name, self.aliyun_template_code, self.to_phones]):
            print("[SMSAlert] 阿里云配置不完整")
            return False

        try:
            from alibabacloud_dysmsapi20170525.client import Client
            from alibabacloud_dysmsapi20170525 import models as sms_models
            from alibabacloud_tea_openapi import models as open_api_models

            config = open_api_models.Config(
                access_key_id=self.aliyun_access_key,
                access_key_secret=self.aliyun_access_secret
            )
            config.endpoint = 'dysmsapi.aliyuncs.com'
            client = Client(config)

            success_count = 0
            for phone in self.to_phones:
                phone_number = phone.lstrip('+').lstrip('86')

                request = sms_models.SendSmsRequest(
                    phone_numbers=phone_number,
                    sign_name=self.aliyun_sign_name,
                    template_code=self.aliyun_template_code,
                    template_param=json.dumps({"message": message[:20]})  # 模板参数
                )
                response = client.send_sms(request)
                if response.body.code == "OK":
                    print(f"[SMSAlert] 阿里云发送成功: {phone}")
                    success_count += 1
                else:
                    print(f"[SMSAlert] 阿里云发送失败: {phone}, {response.body.message}")

            return success_count > 0

        except ImportError:
            print("[SMSAlert] 请安装阿里云SDK: pip install alibabacloud_dysmsapi20170525")
            return False
        except Exception as e:
            print(f"[SMSAlert] 阿里云发送异常: {e}")
            return False

    def _send_tencent(self, message: str) -> bool:
        """通过腾讯云发送短信"""
        if not all([self.tencent_secret_id, self.tencent_secret_key,
                    self.tencent_app_id, self.tencent_template_id, self.to_phones]):
            print("[SMSAlert] 腾讯云配置不完整")
            return False

        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.sms.v20210111 import sms_client, models

            cred = credential.Credential(self.tencent_secret_id, self.tencent_secret_key)
            http_profile = HttpProfile()
            http_profile.endpoint = "sms.tencentcloudapi.com"
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            client = sms_client.SmsClient(cred, "ap-guangzhou", client_profile)

            # 格式化电话号码
            phone_numbers = []
            for phone in self.to_phones:
                if phone.startswith('+'):
                    phone_numbers.append(phone)
                else:
                    phone_numbers.append(f"+86{phone}")

            req = models.SendSmsRequest()
            req.SmsSdkAppId = self.tencent_app_id
            req.SignName = self.tencent_sign_name
            req.TemplateId = self.tencent_template_id
            req.TemplateParamSet = [message[:20]]  # 模板参数
            req.PhoneNumberSet = phone_numbers

            resp = client.SendSms(req)
            success_count = 0
            for status in resp.SendStatusSet:
                if status.Code == "Ok":
                    print(f"[SMSAlert] 腾讯云发送成功: {status.PhoneNumber}")
                    success_count += 1
                else:
                    print(f"[SMSAlert] 腾讯云发送失败: {status.PhoneNumber}, {status.Message}")

            return success_count > 0

        except ImportError:
            print("[SMSAlert] 请安装腾讯云SDK: pip install tencentcloud-sdk-python")
            return False
        except Exception as e:
            print(f"[SMSAlert] 腾讯云发送异常: {e}")
            return False

    def send_alert_async(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        alert_type: str = "default"
    ):
        """异步发送短信"""
        thread = threading.Thread(
            target=self.send_alert,
            args=(message, level, alert_type),
            daemon=True
        )
        thread.start()

    def get_alert_history(self, limit: int = 100) -> List[Dict]:
        """获取告警历史"""
        with self._lock:
            return self._alert_history[-limit:]

    def test_sms(self) -> bool:
        """测试短信功能"""
        print("[SMSAlert] 开始测试短信功能...")
        return self.send_alert(
            "测试短信，请忽略",
            AlertLevel.WARNING,
            "test",
            force=True
        )

    def get_config_status(self) -> Dict:
        """获取配置状态"""
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "to_phones": self.to_phones,
            "min_alert_interval": self.min_alert_interval,
            "alert_level_threshold": self.alert_level_threshold.name,
            "twilio_configured": bool(self.account_sid and self.auth_token),
            "aliyun_configured": bool(self.aliyun_access_key and self.aliyun_access_secret and self.aliyun_template_code),
            "tencent_configured": bool(self.tencent_secret_id and self.tencent_secret_key and self.tencent_app_id),
        }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="短信告警服务")
    parser.add_argument("--provider", default="aliyun", choices=["twilio", "aliyun", "tencent"])
    parser.add_argument("--message", "-m", required=True, help="告警消息")
    parser.add_argument("--level", "-l", default="warning", choices=["info", "warning", "critical"])
    parser.add_argument("--type", "-t", default="default", help="告警类型")
    parser.add_argument("--force", "-f", action="store_true", help="强制发送")
    parser.add_argument("--config", "-c", default="", help="配置文件路径")
    parser.add_argument("--test", action="store_true", help="测试模式")
    parser.add_argument("--status", action="store_true", help="显示配置状态")

    args = parser.parse_args()

    service = SMSAlertService(provider=args.provider, config_file=args.config)

    if args.status:
        status = service.get_config_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0

    if args.test:
        success = service.test_sms()
        return 0 if success else 1

    level_map = {"info": AlertLevel.INFO, "warning": AlertLevel.WARNING, "critical": AlertLevel.CRITICAL}
    success = service.send_alert(args.message, level_map[args.level], args.type, args.force)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
