#!/usr/bin/env python3
"""
告警服务模块 - 风控系统

提供统一的告警接口，支持多种告警渠道：
- 电话告警 (phone_alert)
- 短信告警 (sms_alert)
- 邮件告警 (email_alert)
- 钉钉告警 (dingtalk_alert)

使用示例：
    from alerts import AlertManager, AlertLevel

    # 创建告警管理器
    manager = AlertManager()

    # 发送告警到所有渠道
    manager.send_alert("策略异常", AlertLevel.CRITICAL)

    # 或者单独使用某个服务
    from alerts import PhoneAlertService, SMSAlertService, EmailAlertService, DingTalkAlertService
"""

from enum import Enum
from typing import Dict, List, Optional
import threading
from datetime import datetime

# 导入各个告警服务
from .phone_alert import PhoneAlertService, AlertLevel as PhoneAlertLevel
from .sms_alert import SMSAlertService, AlertLevel as SMSAlertLevel
from .email_alert import EmailAlertService, AlertLevel as EmailAlertLevel, create_service_with_preset, SMTP_PRESETS
from .dingtalk_alert import DingTalkAlertService, AlertLevel as DingTalkAlertLevel

# 统一的告警级别
class AlertLevel(Enum):
    """告警级别"""
    INFO = 1       # 信息通知
    WARNING = 2    # 警告
    CRITICAL = 3   # 严重告警


class AlertManager:
    """
    统一告警管理器

    管理多个告警渠道，支持：
    - 统一发送告警到所有渠道
    - 按级别路由到不同渠道
    - 告警聚合和去重

    使用示例：
        manager = AlertManager()

        # 添加告警渠道
        manager.add_phone_service(PhoneAlertService(...))
        manager.add_sms_service(SMSAlertService(...))
        manager.add_email_service(EmailAlertService(...))
        manager.add_dingtalk_service(DingTalkAlertService(...))

        # 发送告警
        manager.send_alert("策略异常", AlertLevel.CRITICAL)

        # 按级别路由
        manager.set_routing({
            AlertLevel.INFO: ["dingtalk", "email"],
            AlertLevel.WARNING: ["dingtalk", "email", "sms"],
            AlertLevel.CRITICAL: ["dingtalk", "email", "sms", "phone"]
        })
    """

    def __init__(self):
        self._phone_services: List[PhoneAlertService] = []
        self._sms_services: List[SMSAlertService] = []
        self._email_services: List[EmailAlertService] = []
        self._dingtalk_services: List[DingTalkAlertService] = []

        self._routing: Dict[AlertLevel, List[str]] = {
            AlertLevel.INFO: ["dingtalk", "email"],
            AlertLevel.WARNING: ["dingtalk", "email", "sms"],
            AlertLevel.CRITICAL: ["dingtalk", "email", "sms", "phone"]
        }

        self._alert_history: List[Dict] = []
        self._lock = threading.Lock()

    def add_phone_service(self, service: PhoneAlertService):
        """添加电话告警服务"""
        self._phone_services.append(service)

    def add_sms_service(self, service: SMSAlertService):
        """添加短信告警服务"""
        self._sms_services.append(service)

    def add_email_service(self, service: EmailAlertService):
        """添加邮件告警服务"""
        self._email_services.append(service)

    def add_dingtalk_service(self, service: DingTalkAlertService):
        """添加钉钉告警服务"""
        self._dingtalk_services.append(service)

    def set_routing(self, routing: Dict[AlertLevel, List[str]]):
        """设置告警路由规则"""
        self._routing = routing

    def send_alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        alert_type: str = "default",
        title: str = "",
        force: bool = False
    ) -> Dict[str, bool]:
        """
        发送告警到配置的渠道

        Args:
            message: 告警消息
            level: 告警级别
            alert_type: 告警类型
            title: 标题（用于邮件和钉钉）
            force: 强制发送

        Returns:
            各渠道发送结果
        """
        channels = self._routing.get(level, [])
        results = {}

        # 转换告警级别
        level_map = {
            AlertLevel.INFO: 1,
            AlertLevel.WARNING: 2,
            AlertLevel.CRITICAL: 3
        }
        level_value = level_map[level]

        # 发送到各渠道
        if "phone" in channels:
            for service in self._phone_services:
                phone_level = PhoneAlertLevel(level_value)
                success = service.send_alert(message, phone_level, alert_type, force)
                results["phone"] = results.get("phone", False) or success

        if "sms" in channels:
            for service in self._sms_services:
                sms_level = SMSAlertLevel(level_value)
                success = service.send_alert(message, sms_level, alert_type, force)
                results["sms"] = results.get("sms", False) or success

        if "email" in channels:
            for service in self._email_services:
                email_level = EmailAlertLevel(level_value)
                success = service.send_alert(message, email_level, alert_type, title, force)
                results["email"] = results.get("email", False) or success

        if "dingtalk" in channels:
            for service in self._dingtalk_services:
                ding_level = DingTalkAlertLevel(level_value)
                success = service.send_alert(message, ding_level, alert_type, title, force)
                results["dingtalk"] = results.get("dingtalk", False) or success

        # 记录历史
        with self._lock:
            self._alert_history.append({
                "time": datetime.now().isoformat(),
                "message": message,
                "level": level.name,
                "type": alert_type,
                "results": results
            })
            if len(self._alert_history) > 1000:
                self._alert_history = self._alert_history[-500:]

        return results

    def send_alert_async(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        alert_type: str = "default",
        title: str = ""
    ):
        """异步发送告警"""
        thread = threading.Thread(
            target=self.send_alert,
            args=(message, level, alert_type, title),
            daemon=True
        )
        thread.start()

    def get_alert_history(self, limit: int = 100) -> List[Dict]:
        """获取告警历史"""
        with self._lock:
            return self._alert_history[-limit:]

    def get_status(self) -> Dict:
        """获取各服务状态"""
        return {
            "phone_services": len(self._phone_services),
            "sms_services": len(self._sms_services),
            "email_services": len(self._email_services),
            "dingtalk_services": len(self._dingtalk_services),
            "routing": {k.name: v for k, v in self._routing.items()},
            "alert_history_count": len(self._alert_history)
        }


# 便捷函数：从环境变量创建告警管理器
def create_alert_manager_from_env() -> AlertManager:
    """
    从环境变量创建告警管理器

    会自动检测配置的服务并添加
    """
    import os

    manager = AlertManager()

    # 检测并添加电话服务
    if os.getenv("TWILIO_ACCOUNT_SID") or os.getenv("ALIYUN_ACCESS_KEY"):
        phone_service = PhoneAlertService()
        manager.add_phone_service(phone_service)

    # 检测并添加短信服务
    if os.getenv("ALIYUN_SMS_TEMPLATE_CODE") or os.getenv("TENCENT_SMS_TEMPLATE_ID"):
        sms_service = SMSAlertService()
        manager.add_sms_service(sms_service)

    # 检测并添加邮件服务
    if os.getenv("SMTP_HOST") or os.getenv("SENDGRID_API_KEY"):
        email_service = EmailAlertService()
        manager.add_email_service(email_service)

    # 检测并添加钉钉服务
    if os.getenv("DINGTALK_WEBHOOK_URL"):
        dingtalk_service = DingTalkAlertService()
        manager.add_dingtalk_service(dingtalk_service)

    return manager


# 导出
__all__ = [
    # 告警级别
    "AlertLevel",

    # 告警管理器
    "AlertManager",
    "create_alert_manager_from_env",

    # 各服务类
    "PhoneAlertService",
    "SMSAlertService",
    "EmailAlertService",
    "DingTalkAlertService",

    # 邮件预设
    "create_service_with_preset",
    "SMTP_PRESETS",
]
