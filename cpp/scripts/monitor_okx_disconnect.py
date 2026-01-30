#!/usr/bin/env python3
"""
OKX WebSocket 断连监测脚本

功能：
1. 实时监测 trading_server 日志中的 OKX WebSocket 断连事件
2. 统计断连次数、重连成功率、断连时长
3. 发送告警通知（可选）
4. 生成断连报告

使用方法：
    python3 monitor_okx_disconnect.py [--log-dir /path/to/logs] [--alert]
"""

import os
import sys
import re
import argparse
from datetime import datetime, timedelta
import subprocess

class OKXDisconnectMonitor:
    def __init__(self, log_dir="/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/build/logs",
                 enable_alert=False):
        self.log_dir = log_dir
        self.enable_alert = enable_alert

        # 统计数据
        self.disconnect_count = 0
        self.reconnect_success_count = 0
        self.reconnect_fail_count = 0
        self.disconnect_events = []  # [(时间, 类型, 详情)]

        # 当前断连状态
        self.is_disconnected = False
        self.disconnect_start_time = None

        # 日志模式匹配
        self.patterns = {
            'disconnect': re.compile(r'\[OKXWebSocket\].*连接断开|disconnect', re.IGNORECASE),
            'reconnect_start': re.compile(r'\[OKXWebSocket\].*开始重连|监控线程检测到断开', re.IGNORECASE),
            'reconnect_success': re.compile(r'\[OKXWebSocket\].*✅.*重连成功|重连流程全部完成', re.IGNORECASE),
            'reconnect_fail': re.compile(r'\[OKXWebSocket\].*❌.*重连失败', re.IGNORECASE),
            'kline_count': re.compile(r'K线\[OKX:(\d+)\s+Binance:(\d+)\]'),
        }

        # 上次K线计数
        self.last_okx_kline_count = 0
        self.last_kline_check_time = None
        self.kline_stall_threshold = 60  # 60秒内K线不增长视为异常

    def get_latest_log_file(self):
        """获取最新的日志文件"""
        if not os.path.exists(self.log_dir):
            print(f"❌ 日志目录不存在: {self.log_dir}")
            return None

        log_files = [f for f in os.listdir(self.log_dir) if f.startswith('trading_server_') and f.endswith('.log')]
        if not log_files:
            print(f"❌ 未找到日志文件: {self.log_dir}")
            return None

        # 获取最新的日志文件
        log_files.sort(reverse=True)
        latest_log = os.path.join(self.log_dir, log_files[0])
        return latest_log

    def parse_timestamp(self, line):
        """从日志行中提取时间戳"""
        match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]', line)
        if match:
            try:
                return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S.%f')
            except:
                pass
        return None

    def check_kline_stall(self, line, timestamp):
        """检查K线是否停止增长（可能表示断连）"""
        match = self.patterns['kline_count'].search(line)
        if match:
            okx_count = int(match.group(1))

            if self.last_kline_check_time:
                time_diff = (timestamp - self.last_kline_check_time).total_seconds()

                # 如果K线计数没有增长且超过阈值
                if okx_count == self.last_okx_kline_count and time_diff > self.kline_stall_threshold:
                    if not self.is_disconnected:
                        self.log_event(timestamp, "K线停滞",
                                     f"OKX K线计数停滞在 {okx_count}，已持续 {time_diff:.0f} 秒")
                        return True

            self.last_okx_kline_count = okx_count
            self.last_kline_check_time = timestamp

        return False

    def process_line(self, line):
        """处理单行日志"""
        timestamp = self.parse_timestamp(line)
        if not timestamp:
            return

        # 检查K线停滞
        self.check_kline_stall(line, timestamp)

        # 检查断连
        if self.patterns['disconnect'].search(line):
            if not self.is_disconnected:
                self.is_disconnected = True
                self.disconnect_start_time = timestamp
                self.disconnect_count += 1
                self.log_event(timestamp, "断连", line.strip())
                self.send_alert(f"⚠️ OKX WebSocket 断连 (第{self.disconnect_count}次)", line)

        # 检查重连开始
        elif self.patterns['reconnect_start'].search(line):
            self.log_event(timestamp, "重连开始", line.strip())

        # 检查重连成功
        elif self.patterns['reconnect_success'].search(line):
            if self.is_disconnected:
                duration = (timestamp - self.disconnect_start_time).total_seconds()
                self.is_disconnected = False
                self.reconnect_success_count += 1
                self.log_event(timestamp, "重连成功", f"断连时长: {duration:.1f}秒")
                self.send_alert(f"✅ OKX WebSocket 重连成功", f"断连时长: {duration:.1f}秒")

        # 检查重连失败
        elif self.patterns['reconnect_fail'].search(line):
            self.reconnect_fail_count += 1
            self.log_event(timestamp, "重连失败", line.strip())
            self.send_alert(f"❌ OKX WebSocket 重连失败 (第{self.reconnect_fail_count}次)", line)

    def log_event(self, timestamp, event_type, details):
        """记录事件"""
        self.disconnect_events.append((timestamp, event_type, details))
        print(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] [{event_type}] {details}")

    def send_alert(self, title, message):
        """发送告警通知（可扩展为邮件、钉钉、企业微信等）"""
        if not self.enable_alert:
            return

        # 这里可以添加告警逻辑，例如：
        # - 发送邮件
        # - 发送钉钉/企业微信通知
        # - 写入告警日志
        print(f"\n{'='*60}")
        print(f"🔔 告警: {title}")
        print(f"详情: {message}")
        print(f"{'='*60}\n")

    def print_statistics(self):
        """打印统计信息"""
        print(f"\n{'='*60}")
        print(f"OKX WebSocket 断连统计")
        print(f"{'='*60}")
        print(f"总断连次数: {self.disconnect_count}")
        print(f"重连成功次数: {self.reconnect_success_count}")
        print(f"重连失败次数: {self.reconnect_fail_count}")

        if self.disconnect_count > 0:
            success_rate = (self.reconnect_success_count / self.disconnect_count) * 100
            print(f"重连成功率: {success_rate:.1f}%")

        if self.is_disconnected and self.disconnect_start_time:
            duration = (datetime.now() - self.disconnect_start_time).total_seconds()
            print(f"\n⚠️ 当前状态: 断连中 (已持续 {duration:.1f} 秒)")
        else:
            print(f"\n✅ 当前状态: 连接正常")

        # 打印最近的事件
        if self.disconnect_events:
            print(f"\n最近的断连事件:")
            for ts, event_type, details in self.disconnect_events[-10:]:
                print(f"  [{ts.strftime('%H:%M:%S')}] {event_type}: {details[:80]}")

        print(f"{'='*60}\n")

    def tail_log(self, log_file):
        """实时监控日志文件（类似 tail -f）"""
        print(f"📊 开始监控日志文件: {log_file}")
        print(f"按 Ctrl+C 停止监控\n")

        try:
            # 先处理现有日志
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        self.process_line(line)

            # 实时监控新增日志
            process = subprocess.Popen(
                ['tail', '-f', log_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            for line in process.stdout:
                self.process_line(line)

        except KeyboardInterrupt:
            print("\n\n⏹️  监控已停止")
            self.print_statistics()
        except Exception as e:
            print(f"❌ 错误: {e}")

    def analyze_history(self, log_file, hours=24):
        """分析历史日志"""
        print(f"📊 分析最近 {hours} 小时的日志: {log_file}\n")

        cutoff_time = datetime.now() - timedelta(hours=hours)

        if not os.path.exists(log_file):
            print(f"❌ 日志文件不存在: {log_file}")
            return

        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                timestamp = self.parse_timestamp(line)
                if timestamp and timestamp >= cutoff_time:
                    self.process_line(line)

        self.print_statistics()

def main():
    parser = argparse.ArgumentParser(description='OKX WebSocket 断连监测工具')
    parser.add_argument('--log-dir',
                       default='/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/build/logs',
                       help='日志文件目录')
    parser.add_argument('--alert', action='store_true', help='启用告警通知')
    parser.add_argument('--mode', choices=['realtime', 'history'], default='realtime',
                       help='监控模式: realtime(实时) 或 history(历史分析)')
    parser.add_argument('--hours', type=int, default=24, help='历史分析的时间范围（小时）')

    args = parser.parse_args()

    monitor = OKXDisconnectMonitor(log_dir=args.log_dir, enable_alert=args.alert)
    log_file = monitor.get_latest_log_file()

    if not log_file:
        sys.exit(1)

    if args.mode == 'realtime':
        monitor.tail_log(log_file)
    else:
        monitor.analyze_history(log_file, hours=args.hours)

if __name__ == '__main__':
    main()
