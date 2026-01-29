#!/usr/bin/env python3
"""
电话告警组件 - 风控系统

支持的服务商：
- twilio: 国际通用
- aliyun: 阿里云语音通知
- tencent: 腾讯云语音通知

使用方式：
1. Python 直接调用:
    from phone_alert import PhoneAlertService, AlertLevel
    alert = PhoneAlertService(provider="twilio", ...)
    alert.send_alert("策略异常", AlertLevel.CRITICAL)

2. 命令行调用 (供 C++ 使用):
    python phone_alert.py --provider twilio --message "策略异常" --level critical
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
    CRITICAL = 3   # 严重告警（触发电话）


class PhoneAlertService:
    """
    电话告警服务组件

    使用示例：
        alert_service = PhoneAlertService(
            provider="twilio",
            account_sid="your_account_sid",
            auth_token="your_auth_token",
            from_phone="+1234567890",
            to_phones=["+8613800138000"]
        )
        alert_service.send_alert("策略异常：持仓超限", AlertLevel.CRITICAL)
    """

    def __init__(
        self,
        provider: str = "twilio",
        # Twilio 配置
        account_sid: str = "",
        auth_token: str = "",
        from_phone: str = "",
        to_phones: List[str] = None,
        # 阿里云专用参数
        aliyun_access_key: str = "",
        aliyun_access_secret: str = "",
        aliyun_tts_code: str = "",
        aliyun_called_show_number: str = "",
        # 腾讯云专用参数
        tencent_secret_id: str = "",
        tencent_secret_key: str = "",
        tencent_app_id: str = "",
        tencent_template_id: str = "",
        # 通用配置
        enabled: bool = True,
        min_alert_interval: int = 300,  # 最小告警间隔（秒），防止频繁打电话
        alert_level_threshold: AlertLevel = AlertLevel.CRITICAL,
        config_file: str = "",  # 配置文件路径
    ):
        # 如果提供了配置文件，从文件加载配置
        if config_file and os.path.exists(config_file):
            self._load_config(config_file)
        else:
            self.provider = provider
            self.account_sid = account_sid
            self.auth_token = auth_token
            self.from_phone = from_phone
            self.to_phones = to_phones or []

            # 阿里云配置
            self.aliyun_access_key = aliyun_access_key
            self.aliyun_access_secret = aliyun_access_secret
            self.aliyun_tts_code = aliyun_tts_code
            self.aliyun_called_show_number = aliyun_called_show_number

            # 腾讯云配置
            self.tencent_secret_id = tencent_secret_id
            self.tencent_secret_key = tencent_secret_key
            self.tencent_app_id = tencent_app_id
            self.tencent_template_id = tencent_template_id

            # 通用配置
            self.enabled = enabled
            self.min_alert_interval = min_alert_interval
            self.alert_level_threshold = alert_level_threshold

        # 从环境变量覆盖配置
        self._load_from_env()

        # 状态
        self._last_alert_time: Dict[str, datetime] = {}
        self._alert_history: List[Dict] = []
        self._lock = threading.Lock()

    def _load_config(self, config_file: str):
        """从配置文件加载"""
        with open(config_file, 'r') as f:
            config = json.load(f)

        self.provider = config.get("provider", "twilio")
        self.account_sid = config.get("account_sid", "")
        self.auth_token = config.get("auth_token", "")
        self.from_phone = config.get("from_phone", "")
        self.to_phones = config.get("to_phones", [])

        self.aliyun_access_key = config.get("aliyun_access_key", "")
        self.aliyun_access_secret = config.get("aliyun_access_secret", "")
        self.aliyun_tts_code = config.get("aliyun_tts_code", "")
        self.aliyun_called_show_number = config.get("aliyun_called_show_number", "")

        self.tencent_secret_id = config.get("tencent_secret_id", "")
        self.tencent_secret_key = config.get("tencent_secret_key", "")
        self.tencent_app_id = config.get("tencent_app_id", "")
        self.tencent_template_id = config.get("tencent_template_id", "")

        self.enabled = config.get("enabled", True)
        self.min_alert_interval = config.get("min_alert_interval", 300)
        threshold = config.get("alert_level_threshold", "CRITICAL")
        self.alert_level_threshold = AlertLevel[threshold]

    def _load_from_env(self):
        """从环境变量加载配置（优先级最高）"""
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
        if os.getenv("ALIYUN_TTS_CODE"):
            self.aliyun_tts_code = os.getenv("ALIYUN_TTS_CODE")

        # 腾讯云
        if os.getenv("TENCENT_SECRET_ID"):
            self.tencent_secret_id = os.getenv("TENCENT_SECRET_ID")
        if os.getenv("TENCENT_SECRET_KEY"):
            self.tencent_secret_key = os.getenv("TENCENT_SECRET_KEY")
        if os.getenv("TENCENT_APP_ID"):
            self.tencent_app_id = os.getenv("TENCENT_APP_ID")

        # 通用
        if os.getenv("PHONE_ALERT_PROVIDER"):
            self.provider = os.getenv("PHONE_ALERT_PROVIDER")

    def send_alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.CRITICAL,
        alert_type: str = "default",
        force: bool = False
    ) -> bool:
        """
        发送告警

        Args:
            message: 告警消息
            level: 告警级别
            alert_type: 告警类型（用于控制同类告警频率）
            force: 是否强制发送（忽略间隔限制）

        Returns:
            是否发送成功
        """
        if not self.enabled:
            print(f"[PhoneAlert] 告警服务已禁用")
            return False

        # 检查告警级别
        if level.value < self.alert_level_threshold.value:
            print(f"[PhoneAlert] 告警级别 {level.name} 低于阈值 {self.alert_level_threshold.name}")
            return False

        # 检查告警间隔
        if not force:
            with self._lock:
                last_time = self._last_alert_time.get(alert_type)
                if last_time:
                    elapsed = (datetime.now() - last_time).total_seconds()
                    if elapsed < self.min_alert_interval:
                        print(f"[PhoneAlert] 告警间隔不足，距上次 {elapsed:.0f}s，需要 {self.min_alert_interval}s")
                        return False

        # 记录告警
        alert_record = {
            "time": datetime.now().isoformat(),
            "message": message,
            "level": level.name,
            "type": alert_type,
            "sent": False
        }

        # 发送电话
        print(f"[PhoneAlert] 发送告警: {message}")
        success = self._make_call(message)
        alert_record["sent"] = success

        with self._lock:
            self._alert_history.append(alert_record)
            if len(self._alert_history) > 1000:
                self._alert_history = self._alert_history[-500:]
            if success:
                self._last_alert_time[alert_type] = datetime.now()

        return success

    def _make_call(self, message: str) -> bool:
        """执行电话呼叫"""
        try:
            if self.provider == "twilio":
                return self._call_twilio(message)
            elif self.provider == "aliyun":
                return self._call_aliyun(message)
            elif self.provider == "tencent":
                return self._call_tencent(message)
            else:
                print(f"[PhoneAlert] 不支持的服务商: {self.provider}")
                return False
        except Exception as e:
            print(f"[PhoneAlert] 发送失败: {e}")
            return False

    def _call_twilio(self, message: str) -> bool:
        """通过 Twilio 发送语音电话"""
        if not all([self.account_sid, self.auth_token, self.from_phone, self.to_phones]):
            print("[PhoneAlert] Twilio 配置不完整")
            print(f"  account_sid: {'已设置' if self.account_sid else '未设置'}")
            print(f"  auth_token: {'已设置' if self.auth_token else '未设置'}")
            print(f"  from_phone: {'已设置' if self.from_phone else '未设置'}")
            print(f"  to_phones: {self.to_phones}")
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls.json"

        # TwiML 语音内容（重复两遍确保听清）
        twiml = f'''<Response>
            <Say language="zh-CN" voice="alice">{message}</Say>
            <Pause length="1"/>
            <Say language="zh-CN" voice="alice">重复一遍：{message}</Say>
        </Response>'''

        success_count = 0
        for phone in self.to_phones:
            try:
                response = requests.post(
                    url,
                    auth=(self.account_sid, self.auth_token),
                    data={
                        "To": phone,
                        "From": self.from_phone,
                        "Twiml": twiml
                    },
                    timeout=30
                )
                if response.status_code in [200, 201]:
                    print(f"[PhoneAlert] Twilio 呼叫成功: {phone}")
                    success_count += 1
                else:
                    print(f"[PhoneAlert] Twilio 呼叫失败: {phone}")
                    print(f"  状态码: {response.status_code}")
                    print(f"  响应: {response.text[:200]}")
            except Exception as e:
                print(f"[PhoneAlert] Twilio 呼叫异常: {phone}, {e}")

        return success_count > 0

    def _call_aliyun(self, message: str) -> bool:
        """通过阿里云发送语音通知"""
        if not all([self.aliyun_access_key, self.aliyun_access_secret, self.to_phones]):
            print("[PhoneAlert] 阿里云配置不完整")
            return False

        try:
            from alibabacloud_dyvmsapi20170525.client import Client
            from alibabacloud_dyvmsapi20170525 import models as dyvms_models
            from alibabacloud_tea_openapi import models as open_api_models

            config = open_api_models.Config(
                access_key_id=self.aliyun_access_key,
                access_key_secret=self.aliyun_access_secret
            )
            config.endpoint = 'dyvmsapi.aliyuncs.com'
            client = Client(config)

            success_count = 0
            for phone in self.to_phones:
                # 去掉国际区号前缀
                phone_number = phone.lstrip('+').lstrip('86')

                request = dyvms_models.SingleCallByTtsRequest(
                    called_number=phone_number,
                    called_show_number=self.aliyun_called_show_number,
                    tts_code=self.aliyun_tts_code,
                    tts_param=json.dumps({"message": message})
                )
                response = client.single_call_by_tts(request)
                if response.body.code == "OK":
                    print(f"[PhoneAlert] 阿里云呼叫成功: {phone}")
                    success_count += 1
                else:
                    print(f"[PhoneAlert] 阿里云呼叫失败: {phone}, {response.body.message}")

            return success_count > 0

        except ImportError:
            print("[PhoneAlert] 请安装阿里云SDK: pip install alibabacloud_dyvmsapi20170525")
            return False
        except Exception as e:
            print(f"[PhoneAlert] 阿里云呼叫异常: {e}")
            return False

    def _call_tencent(self, message: str) -> bool:
        """通过腾讯云发送语音通知"""
        if not all([self.tencent_secret_id, self.tencent_secret_key, self.tencent_app_id, self.to_phones]):
            print("[PhoneAlert] 腾讯云配置不完整")
            return False

        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.vms.v20200902 import vms_client, models

            cred = credential.Credential(self.tencent_secret_id, self.tencent_secret_key)
            http_profile = HttpProfile()
            http_profile.endpoint = "vms.tencentcloudapi.com"
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            client = vms_client.VmsClient(cred, "ap-guangzhou", client_profile)

            success_count = 0
            for phone in self.to_phones:
                # 腾讯云需要带国际区号
                phone_number = phone if phone.startswith('+') else f"+86{phone}"

                req = models.SendTtsVoiceRequest()
                req.TemplateId = self.tencent_template_id
                req.CalledNumber = phone_number
                req.VoiceSdkAppid = self.tencent_app_id
                req.TemplateParamSet = [message]

                resp = client.SendTtsVoice(req)
                if resp.SendStatus and resp.SendStatus.Code == "Ok":
                    print(f"[PhoneAlert] 腾讯云呼叫成功: {phone}")
                    success_count += 1
                else:
                    print(f"[PhoneAlert] 腾讯云呼叫失败: {phone}")

            return success_count > 0

        except ImportError:
            print("[PhoneAlert] 请安装腾讯云SDK: pip install tencentcloud-sdk-python")
            return False
        except Exception as e:
            print(f"[PhoneAlert] 腾讯云呼叫异常: {e}")
            return False

    def send_alert_async(
        self,
        message: str,
        level: AlertLevel = AlertLevel.CRITICAL,
        alert_type: str = "default"
    ):
        """异步发送告警（不阻塞主线程）"""
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

    def test_call(self) -> bool:
        """测试电话功能"""
        print("[PhoneAlert] 开始测试电话功能...")
        return self.send_alert(
            "这是一条测试告警，请忽略。This is a test alert.",
            AlertLevel.CRITICAL,
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
            "aliyun_configured": bool(self.aliyun_access_key and self.aliyun_access_secret),
            "tencent_configured": bool(self.tencent_secret_id and self.tencent_secret_key),
        }


def main():
    """命令行入口 - 供 C++ 调用"""
    parser = argparse.ArgumentParser(description="电话告警服务")
    parser.add_argument("--provider", default="twilio", choices=["twilio", "aliyun", "tencent"],
                        help="服务商")
    parser.add_argument("--message", "-m", required=True, help="告警消息")
    parser.add_argument("--level", "-l", default="critical",
                        choices=["info", "warning", "critical"], help="告警级别")
    parser.add_argument("--type", "-t", default="default", help="告警类型")
    parser.add_argument("--force", "-f", action="store_true", help="强制发送（忽略间隔限制）")
    parser.add_argument("--config", "-c", default="", help="配置文件路径")
    parser.add_argument("--test", action="store_true", help="测试模式")
    parser.add_argument("--status", action="store_true", help="显示配置状态")

    args = parser.parse_args()

    # 创建服务实例
    service = PhoneAlertService(
        provider=args.provider,
        config_file=args.config
    )

    # 显示配置状态
    if args.status:
        status = service.get_config_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0

    # 测试模式
    if args.test:
        success = service.test_call()
        return 0 if success else 1

    # 发送告警
    level_map = {
        "info": AlertLevel.INFO,
        "warning": AlertLevel.WARNING,
        "critical": AlertLevel.CRITICAL
    }
    level = level_map[args.level]

    success = service.send_alert(
        message=args.message,
        level=level,
        alert_type=args.type,
        force=args.force
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
