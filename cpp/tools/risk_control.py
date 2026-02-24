#!/usr/bin/env python3
"""
风控管理工具 - 通过WebSocket与trading_server通信
用于查看风控状态和解除kill switch
"""

import websocket
import json
import sys
import argparse
from datetime import datetime

class RiskControlClient:
    def __init__(self, host="localhost", port=8002):
        self.url = f"ws://{host}:{port}"
        self.ws = None

    def connect(self):
        """连接到trading_server"""
        try:
            self.ws = websocket.create_connection(self.url, timeout=5)
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            print(f"请确保trading_server正在运行并监听端口{self.url}")
            return False

    def send_command(self, action, data=None):
        """发送命令并接收响应"""
        if not self.ws:
            if not self.connect():
                return None

        try:
            message = {
                "type": "command",
                "action": action,
                "data": data or {}
            }

            self.ws.send(json.dumps(message))

            # 增加超时时间
            self.ws.settimeout(10)

            # 可能会收到多条消息（日志+响应），需要找到正确的响应
            max_attempts = 5
            for _ in range(max_attempts):
                response_str = self.ws.recv()
                response = json.loads(response_str)

                # 跳过日志消息，找到命令响应
                if response.get("type") == "log":
                    continue

                # 找到响应消息（type=response）
                if response.get("type") == "response":
                    # 提取嵌套的data字段
                    return response.get("data", response)

                # 或者直接是命令响应
                if "success" in response:
                    return response

            print("❌ 未收到有效响应")
            return None

        except websocket.WebSocketTimeoutException:
            print(f"❌ 命令执行超时（10秒）")
            return None
        except Exception as e:
            print(f"❌ 命令执行失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_risk_status(self):
        """获取风控状态"""
        print("正在查询风控状态...")
        response = self.send_command("get_risk_status")

        if not response:
            print("❌ 查询失败：无响应")
            return

        if not response.get("success"):
            print(f"❌ 查询失败：{response.get('message', '未知错误')}")
            print(f"完整响应：{response}")
            return

        data = response.get("data", {})

        print("\n" + "="*60)
        print("风控状态报告")
        print("="*60)
        print(f"查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Kill Switch状态
        kill_switch = data.get("kill_switch", False)
        if kill_switch:
            print("🔴 Kill Switch: 已激活 (所有订单被拒绝)")
        else:
            print("🟢 Kill Switch: 未激活 (正常交易)")

        print()
        print(f"挂单数量: {data.get('open_orders', 0)}")
        print(f"每日盈亏: {data.get('daily_pnl', 0):.2f} USDT")
        print(f"总敞口: {data.get('total_exposure', 0):.2f} USDT")
        print(f"持仓品种数: {data.get('position_count', 0)}")

        # 策略统计
        strategy_stats = data.get("strategy_stats", {})
        if strategy_stats:
            print()
            print("策略统计:")
            for strategy_id, stats in strategy_stats.items():
                peak = stats.get("peak_pnl", 0)
                initial = stats.get("initial_equity", 0)
                print(f"  - {strategy_id}:")
                print(f"      当日峰值: {peak:.2f} USDT")
                print(f"      当日初值: {initial:.2f} USDT")

        print("="*60)
        print()

        return kill_switch

    def deactivate_kill_switch(self):
        """解除kill switch"""
        print("正在解除kill switch...")
        response = self.send_command("deactivate_kill_switch")

        if not response:
            print("❌ 解除失败")
            return False

        if response.get("success"):
            print(f"✅ {response.get('message', 'Kill switch已解除')}")
            return True
        else:
            print(f"❌ {response.get('message', '解除失败')}")
            return False

    def close(self):
        """关闭连接"""
        if self.ws:
            self.ws.close()

def main():
    parser = argparse.ArgumentParser(
        description="风控管理工具 - 查看状态和解除kill switch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 查看风控状态
  python3 risk_control.py status

  # 解除kill switch
  python3 risk_control.py deactivate

  # 查看状态并自动解除（如果已激活）
  python3 risk_control.py auto
        """
    )

    parser.add_argument(
        "command",
        choices=["status", "deactivate", "auto"],
        help="命令: status(查看状态) | deactivate(解除kill switch) | auto(自动解除)"
    )

    parser.add_argument(
        "--host",
        default="localhost",
        help="trading_server地址 (默认: localhost)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="WebSocket端口 (默认: 8002)"
    )

    args = parser.parse_args()

    client = RiskControlClient(args.host, args.port)

    try:
        if args.command == "status":
            client.get_risk_status()

        elif args.command == "deactivate":
            # 先查看状态
            kill_switch = client.get_risk_status()

            if kill_switch:
                print()
                confirm = input("确认要解除kill switch吗? (yes/no): ")
                if confirm.lower() in ["yes", "y"]:
                    client.deactivate_kill_switch()
                else:
                    print("已取消")
            else:
                print("ℹ️  Kill switch当前未激活，无需解除")

        elif args.command == "auto":
            # 自动模式：如果激活则解除
            kill_switch = client.get_risk_status()

            if kill_switch:
                print()
                client.deactivate_kill_switch()
            else:
                print("ℹ️  Kill switch当前未激活")

    finally:
        client.close()

if __name__ == "__main__":
    main()
