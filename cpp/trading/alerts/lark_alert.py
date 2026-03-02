#!/usr/bin/env python3
"""
飞书(Lark)告警组件 - 风控系统

支持的消息类型：
- text: 纯文本消息
- interactive: 卡片消息（默认）

使用方式：
1. Python 直接调用:
    from lark_alert import LarkAlertService, AlertLevel
    lark = LarkAlertService(webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
    lark.send_alert("策略异常", AlertLevel.WARNING)

2. 命令行调用 (供 C++ 使用):
    python lark_alert.py --message "策略异常" --level warning
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
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class AlertLevel(Enum):
    """告警级别"""
    INFO = 1       # 信息通知
    WARNING = 2    # 警告
    CRITICAL = 3   # 严重告警


class LarkAlertService:
    """
    飞书告警服务组件

    使用示例：
        lark_service = LarkAlertService(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
            secret="xxx",  # 可选，加签密钥
        )
        lark_service.send_alert("策略异常：持仓超限", AlertLevel.WARNING)
    """

    def __init__(
        self,
        webhook_url: str = "",
        secret: str = "",
        enabled: bool = True,
        min_alert_interval: int = 10,
        alert_level_threshold: AlertLevel = AlertLevel.INFO,
        config_file: str = "",
    ):
        if config_file and os.path.exists(config_file):
            self._load_config(config_file)
        else:
            self.webhook_url = webhook_url
            self.secret = secret
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
        self.enabled = config.get("enabled", True)
        self.min_alert_interval = config.get("min_alert_interval", 10)
        threshold = config.get("alert_level_threshold", "INFO")
        self.alert_level_threshold = AlertLevel[threshold]

    def _load_from_env(self):
        """从环境变量加载配置"""
        if os.getenv("LARK_WEBHOOK_URL"):
            self.webhook_url = os.getenv("LARK_WEBHOOK_URL")
        if os.getenv("LARK_SECRET"):
            self.secret = os.getenv("LARK_SECRET")

    def _gen_sign(self, timestamp: str) -> str:
        """飞书签名: base64(hmac_sha256(timestamp + "\n" + secret))"""
        string_to_sign = f'{timestamp}\n{self.secret}'
        hmac_code = hmac.new(
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode('utf-8')

    def send_alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        alert_type: str = "default",
        title: str = "",
        force: bool = False
    ) -> bool:
        """发送飞书告警（卡片格式）"""
        if not self.enabled:
            print("[Lark] 飞书服务已禁用")
            return False

        if level.value < self.alert_level_threshold.value:
            return False

        if not force:
            with self._lock:
                last_time = self._last_alert_time.get(alert_type)
                if last_time:
                    elapsed = (datetime.now() - last_time).total_seconds()
                    if elapsed < self.min_alert_interval:
                        print(f"[Lark] 告警间隔不足，距上次 {elapsed:.0f}s")
                        return False

        level_colors = {
            AlertLevel.INFO: "blue",
            AlertLevel.WARNING: "orange",
            AlertLevel.CRITICAL: "red",
        }
        level_icons = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
        }

        color = level_colors[level]
        icon = level_icons[level]
        title = title or f"{icon} 交易系统告警"

        print(f"[Lark] 发送告警: {message[:50]}...")
        success = self._send_card(title, message, level, color)

        with self._lock:
            self._alert_history.append({
                "time": datetime.now().isoformat(),
                "message": message,
                "level": level.name,
                "type": alert_type,
                "sent": success,
            })
            if len(self._alert_history) > 1000:
                self._alert_history = self._alert_history[-500:]
            if success:
                self._last_alert_time[alert_type] = datetime.now()

        return success

    def _send_card(self, title: str, message: str, level: AlertLevel, color: str) -> bool:
        """发送飞书卡片消息"""
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color,
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**告警级别**\n{level.name}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**时间**\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}},
                        ],
                    },
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": message},
                    },
                ],
            },
        }
        return self._send_request(card)

    def send_text(self, content: str) -> bool:
        """发送纯文本消息"""
        data = {"msg_type": "text", "content": {"text": content}}
        return self._send_request(data)

    def _send_request(self, data: dict) -> bool:
        """发送请求到飞书"""
        if not self.webhook_url:
            print("[Lark] Webhook URL 未配置")
            return False

        try:
            # 加签
            if self.secret:
                timestamp = str(int(time.time()))
                sign = self._gen_sign(timestamp)
                data["timestamp"] = timestamp
                data["sign"] = sign

            response = requests.post(
                self.webhook_url,
                headers={"Content-Type": "application/json"},
                json=data,
                timeout=30,
            )

            result = response.json()
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                print("[Lark] 发送成功")
                return True
            else:
                print(f"[Lark] 发送失败: {result.get('msg', result.get('StatusMessage', 'Unknown'))}")
                return False

        except Exception as e:
            print(f"[Lark] 发送异常: {e}")
            return False

    def send_alert_async(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        alert_type: str = "default",
        title: str = "",
    ):
        """异步发送告警"""
        thread = threading.Thread(
            target=self.send_alert,
            args=(message, level, alert_type, title),
            daemon=True,
        )
        thread.start()

    def get_alert_history(self, limit: int = 100) -> List[Dict]:
        with self._lock:
            return self._alert_history[-limit:]

    def test_lark(self) -> bool:
        """测试飞书功能"""
        print("[Lark] 开始测试飞书功能...")
        return self.send_alert(
            "这是一条测试消息，请忽略。\n\nThis is a test message, please ignore.",
            AlertLevel.INFO, "test", "测试消息", force=True,
        )

    def get_config_status(self) -> Dict:
        return {
            "enabled": self.enabled,
            "webhook_configured": bool(self.webhook_url),
            "secret_configured": bool(self.secret),
            "min_alert_interval": self.min_alert_interval,
            "alert_level_threshold": self.alert_level_threshold.name,
        }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="飞书告警服务")
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
    service = LarkAlertService(config_file=args.config)

    if args.status:
        print(json.dumps(service.get_config_status(), indent=2, ensure_ascii=False))
        return 0
    if args.test:
        return 0 if service.test_lark() else 1
    if args.text:
        return 0 if service.send_text(args.message) else 1

    level_map = {"info": AlertLevel.INFO, "warning": AlertLevel.WARNING, "critical": AlertLevel.CRITICAL}
    success = service.send_alert(args.message, level_map[args.level], args.type, args.title, args.force)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
