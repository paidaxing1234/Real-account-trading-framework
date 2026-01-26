#!/usr/bin/env python3
"""
钉钉告警组件 - 风控系统

支持的消息类型：
- text: 纯文本消息
- markdown: Markdown 格式消息
- actionCard: 卡片消息

使用方式：
1. Python 直接调用:
    from dingtalk_alert import DingTalkAlertService, AlertLevel
    ding = DingTalkAlertService(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx")
    ding.send_alert("策略异常", AlertLevel.WARNING)

2. 命令行调用 (供 C++ 使用):
    python dingtalk_alert.py --message "策略异常" --level warning
"""

import os
import sys
import json
import argparse
import threading
import requests
import hashlib
import hmac
import base64
import time
import urllib.parse
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class AlertLevel(Enum):
    """告警级别"""
    INFO = 1       # 信息通知
    WARNING = 2    # 警告
    CRITICAL = 3   # 严重告警


class DingTalkAlertService:
    """
    钉钉告警服务组件

    使用示例：
        ding_service = DingTalkAlertService(
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
            secret="SECxxx",  # 可选，加签密钥
            at_mobiles=["13800138000"],  # @指定人
            at_all=False  # 是否@所有人
        )
        ding_service.send_alert("策略异常：持仓超限", AlertLevel.WARNING)
    """

    def __init__(
        self,
        webhook_url: str = "",
        secret: str = "",  # 加签密钥（可选）
        at_mobiles: List[str] = None,  # @指定手机号
        at_user_ids: List[str] = None,  # @指定用户ID
        at_all: bool = False,  # @所有人
        # 通用配置
        enabled: bool = True,
        min_alert_interval: int = 10,  # 最小告警间隔（秒）
        alert_level_threshold: AlertLevel = AlertLevel.INFO,
        config_file: str = "",
    ):
        if config_file and os.path.exists(config_file):
            self._load_config(config_file)
        else:
            self.webhook_url = webhook_url
            self.secret = secret
            self.at_mobiles = at_mobiles or []
            self.at_user_ids = at_user_ids or []
            self.at_all = at_all

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

        self.webhook_url = config.get("webhook_url", "")
        self.secret = config.get("secret", "")
        self.at_mobiles = config.get("at_mobiles", [])
        self.at_user_ids = config.get("at_user_ids", [])
        self.at_all = config.get("at_all", False)

        self.enabled = config.get("enabled", True)
        self.min_alert_interval = config.get("min_alert_interval", 10)
        threshold = config.get("alert_level_threshold", "INFO")
        self.alert_level_threshold = AlertLevel[threshold]

    def _load_from_env(self):
        """从环境变量加载配置"""
        if os.getenv("DINGTALK_WEBHOOK_URL"):
            self.webhook_url = os.getenv("DINGTALK_WEBHOOK_URL")
        if os.getenv("DINGTALK_SECRET"):
            self.secret = os.getenv("DINGTALK_SECRET")
        if os.getenv("DINGTALK_AT_MOBILES"):
            self.at_mobiles = os.getenv("DINGTALK_AT_MOBILES").split(",")
        if os.getenv("DINGTALK_AT_ALL"):
            self.at_all = os.getenv("DINGTALK_AT_ALL").lower() == "true"

    def _get_signed_url(self) -> str:
        """获取签名后的 URL"""
        if not self.secret:
            return self.webhook_url

        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        return f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"

    def send_alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        alert_type: str = "default",
        title: str = "",
        force: bool = False
    ) -> bool:
        """
        发送钉钉告警（Markdown 格式）

        Args:
            message: 告警消息
            level: 告警级别
            alert_type: 告警类型
            title: 消息标题
            force: 强制发送
        """
        if not self.enabled:
            print(f"[DingTalk] 钉钉服务已禁用")
            return False

        if level.value < self.alert_level_threshold.value:
            print(f"[DingTalk] 告警级别 {level.name} 低于阈值 {self.alert_level_threshold.name}")
            return False

        if not force:
            with self._lock:
                last_time = self._last_alert_time.get(alert_type)
                if last_time:
                    elapsed = (datetime.now() - last_time).total_seconds()
                    if elapsed < self.min_alert_interval:
                        print(f"[DingTalk] 告警间隔不足，距上次 {elapsed:.0f}s")
                        return False

        # 构建 Markdown 内容
        level_icons = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨"
        }
        level_colors = {
            AlertLevel.INFO: "#17a2b8",
            AlertLevel.WARNING: "#ffc107",
            AlertLevel.CRITICAL: "#dc3545"
        }

        icon = level_icons[level]
        color = level_colors[level]
        title = title or f"{icon} 交易系统告警"

        markdown_text = f"""### {title}

**告警级别**: <font color="{color}">{level.name}</font>

**告警类型**: {alert_type}

**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

{message}

---
"""
        # 添加 @ 信息
        if self.at_mobiles:
            markdown_text += "\n" + " ".join([f"@{m}" for m in self.at_mobiles])

        alert_record = {
            "time": datetime.now().isoformat(),
            "message": message,
            "level": level.name,
            "type": alert_type,
            "sent": False
        }

        print(f"[DingTalk] 发送告警: {message[:50]}...")
        success = self._send_markdown(title, markdown_text)
        alert_record["sent"] = success

        with self._lock:
            self._alert_history.append(alert_record)
            if len(self._alert_history) > 1000:
                self._alert_history = self._alert_history[-500:]
            if success:
                self._last_alert_time[alert_type] = datetime.now()

        return success

    def send_text(self, content: str) -> bool:
        """发送纯文本消息"""
        if not self.webhook_url:
            print("[DingTalk] Webhook URL 未配置")
            return False

        data = {
            "msgtype": "text",
            "text": {"content": content},
            "at": {
                "atMobiles": self.at_mobiles,
                "atUserIds": self.at_user_ids,
                "isAtAll": self.at_all
            }
        }

        return self._send_request(data)

    def _send_markdown(self, title: str, text: str) -> bool:
        """发送 Markdown 消息"""
        if not self.webhook_url:
            print("[DingTalk] Webhook URL 未配置")
            return False

        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            },
            "at": {
                "atMobiles": self.at_mobiles,
                "atUserIds": self.at_user_ids,
                "isAtAll": self.at_all
            }
        }

        return self._send_request(data)

    def send_action_card(
        self,
        title: str,
        text: str,
        single_title: str = "查看详情",
        single_url: str = ""
    ) -> bool:
        """发送卡片消息"""
        if not self.webhook_url:
            print("[DingTalk] Webhook URL 未配置")
            return False

        data = {
            "msgtype": "actionCard",
            "actionCard": {
                "title": title,
                "text": text,
                "singleTitle": single_title,
                "singleURL": single_url,
                "btnOrientation": "0"
            }
        }

        return self._send_request(data)

    def send_link(
        self,
        title: str,
        text: str,
        message_url: str,
        pic_url: str = ""
    ) -> bool:
        """发送链接消息"""
        if not self.webhook_url:
            print("[DingTalk] Webhook URL 未配置")
            return False

        data = {
            "msgtype": "link",
            "link": {
                "title": title,
                "text": text,
                "messageUrl": message_url,
                "picUrl": pic_url
            }
        }

        return self._send_request(data)

    def _send_request(self, data: dict) -> bool:
        """发送请求到钉钉"""
        try:
            url = self._get_signed_url()
            headers = {"Content-Type": "application/json"}

            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30
            )

            result = response.json()
            if result.get("errcode") == 0:
                print(f"[DingTalk] 发送成功")
                return True
            else:
                print(f"[DingTalk] 发送失败: {result.get('errmsg', 'Unknown error')}")
                return False

        except Exception as e:
            print(f"[DingTalk] 发送异常: {e}")
            return False

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

    def test_dingtalk(self) -> bool:
        """测试钉钉功能"""
        print("[DingTalk] 开始测试钉钉功能...")
        return self.send_alert(
            "这是一条测试消息，请忽略。\n\nThis is a test message, please ignore.",
            AlertLevel.INFO,
            "test",
            "测试消息",
            force=True
        )

    def get_config_status(self) -> Dict:
        """获取配置状态"""
        return {
            "enabled": self.enabled,
            "webhook_configured": bool(self.webhook_url),
            "secret_configured": bool(self.secret),
            "at_mobiles": self.at_mobiles,
            "at_all": self.at_all,
            "min_alert_interval": self.min_alert_interval,
            "alert_level_threshold": self.alert_level_threshold.name,
        }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="钉钉告警服务")
    parser.add_argument("--message", "-m", required=True, help="告警消息")
    parser.add_argument("--title", default="", help="消息标题")
    parser.add_argument("--level", "-l", default="warning", choices=["info", "warning", "critical"])
    parser.add_argument("--type", "-t", default="default", help="告警类型")
    parser.add_argument("--force", "-f", action="store_true", help="强制发送")
    parser.add_argument("--config", "-c", default="", help="配置文件路径")
    parser.add_argument("--test", action="store_true", help="测试模式")
    parser.add_argument("--status", action="store_true", help="显示配置状态")
    parser.add_argument("--text", action="store_true", help="发送纯文本消息")

    args = parser.parse_args()

    service = DingTalkAlertService(config_file=args.config)

    if args.status:
        status = service.get_config_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0

    if args.test:
        success = service.test_dingtalk()
        return 0 if success else 1

    if args.text:
        success = service.send_text(args.message)
        return 0 if success else 1

    level_map = {"info": AlertLevel.INFO, "warning": AlertLevel.WARNING, "critical": AlertLevel.CRITICAL}
    success = service.send_alert(args.message, level_map[args.level], args.type, args.title, args.force)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
