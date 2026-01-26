#!/usr/bin/env python3
"""
测试策略K线订阅功能
验证 grid_strategy_cpp.py 是否能成功订阅并接收服务器发布的1s K线数据

测试流程:
1. 启动服务器
2. 监控服务器发布的K线数据
3. 启动策略
4. 监控策略的订阅请求
5. 验证策略是否收到K线数据

@author Sequence Team
@date 2026-01-23
"""

import os
import sys
import zmq
import json
import time
import signal
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, List

class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class KlineSubscriptionTester:
    def __init__(self):
        self.base_dir = Path("/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp")
        self.server_process: Optional[subprocess.Popen] = None
        self.strategy_process: Optional[subprocess.Popen] = None

        # 监控线程
        self.market_monitor_thread: Optional[threading.Thread] = None
        self.subscribe_monitor_thread: Optional[threading.Thread] = None
        self.stop_monitor = False

        # 统计数据
        self.server_kline_count = 0
        self.server_okx_1s_count = 0
        self.server_okx_1m_count = 0
        self.strategy_subscriptions: List[Dict] = []
        self.strategy_kline_received = False

        self.running = True

    def print_header(self, text: str):
        """打印标题"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}")
        print(f"  {text}")
        print(f"{'=' * 70}{Colors.ENDC}")

    def print_success(self, text: str):
        """打印成功信息"""
        print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

    def print_error(self, text: str):
        """打印错误信息"""
        print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

    def print_info(self, text: str):
        """打印信息"""
        print(f"{Colors.OKCYAN}  {text}{Colors.ENDC}")

    def print_warning(self, text: str):
        """打印警告"""
        print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

    def start_server(self):
        """启动服务器"""
        self.print_header("步骤1: 启动服务器")

        server_bin = self.base_dir / "build/trading_server_full"
        if not server_bin.exists():
            self.print_error(f"服务器程序不存在: {server_bin}")
            self.print_info("请先编译: cd cpp/build && cmake .. && make trading_server_full")
            sys.exit(1)

        # 清理旧的IPC文件
        self.print_info("清理旧的IPC文件...")
        subprocess.run("rm -f /tmp/seq_*.ipc", shell=True, check=False)

        # 启动服务器
        log_file = self.base_dir / "build/kline_test_server.log"
        self.print_info(f"启动服务器: {server_bin}")
        self.print_info(f"日志文件: {log_file}")

        with open(log_file, 'w') as f:
            self.server_process = subprocess.Popen(
                [str(server_bin)],
                cwd=str(self.base_dir / "build"),
                stdout=f,
                stderr=subprocess.STDOUT
            )

        # 等待服务器就绪
        self.print_info("等待服务器启动...")
        for i in range(15):
            time.sleep(2)
            if self.check_server_ready():
                self.print_success(f"服务器已就绪 (等待 {(i+1)*2} 秒)")
                return
            self.print_info(f"等待中... ({(i+1)*2}/30秒)")

        self.print_error("服务器启动超时")
        sys.exit(1)

    def check_server_ready(self) -> bool:
        """检查服务器是否就绪"""
        try:
            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            socket.connect("ipc:///tmp/seq_query.ipc")
            socket.setsockopt(zmq.RCVTIMEO, 2000)

            query = {"query_type": "registered_accounts"}
            socket.send_json(query)
            response = socket.recv_json()

            socket.close()
            context.term()
            return isinstance(response, dict)
        except:
            return False

    def start_market_monitor(self):
        """启动行情数据监控"""
        self.print_header("步骤2: 监控服务器发布的K线数据")

        def monitor_market():
            context = zmq.Context()
            socket = context.socket(zmq.SUB)
            socket.connect("ipc:///tmp/seq_md.ipc")
            socket.setsockopt_string(zmq.SUBSCRIBE, "")
            socket.setsockopt(zmq.RCVTIMEO, 1000)

            self.print_info("行情监控已启动 (ipc:///tmp/seq_md.ipc)")

            while not self.stop_monitor:
                try:
                    msg = socket.recv()
                    msg_str = msg.decode('utf-8')

                    # 解析消息
                    if '|' in msg_str:
                        topic, json_str = msg_str.split('|', 1)
                        data = json.loads(json_str)
                    else:
                        data = json.loads(msg_str)

                    msg_type = data.get('type', '')
                    if msg_type == 'kline':
                        self.server_kline_count += 1
                        exchange = data.get('exchange', '')
                        symbol = data.get('symbol', '')
                        interval = data.get('interval', '')

                        if exchange == 'okx' and symbol == 'BTC-USDT-SWAP':
                            if interval == '1s':
                                self.server_okx_1s_count += 1
                                if self.server_okx_1s_count <= 3:
                                    print(f"\n{Colors.OKGREEN}[服务器K线] OKX BTC-USDT-SWAP 1s #{self.server_okx_1s_count}{Colors.ENDC}")
                                    print(f"  收盘价: {data.get('close', 0)}")
                            elif interval == '1m':
                                self.server_okx_1m_count += 1

                except zmq.error.Again:
                    continue
                except Exception as e:
                    if not self.stop_monitor:
                        print(f"{Colors.WARNING}行情监控错误: {e}{Colors.ENDC}")

            socket.close()
            context.term()

        self.market_monitor_thread = threading.Thread(target=monitor_market, daemon=True)
        self.market_monitor_thread.start()
        time.sleep(2)

    def start_subscribe_monitor(self):
        """监控订阅请求"""
        self.print_info("启动订阅请求监控...")

        def monitor_subscribe():
            context = zmq.Context()
            socket = context.socket(zmq.SUB)
            socket.connect("ipc:///tmp/seq_subscribe.ipc")
            socket.setsockopt_string(zmq.SUBSCRIBE, "")
            socket.setsockopt(zmq.RCVTIMEO, 1000)

            while not self.stop_monitor:
                try:
                    msg = socket.recv()
                    msg_str = msg.decode('utf-8')
                    data = json.loads(msg_str)

                    self.strategy_subscriptions.append(data)

                    action = data.get('action', '')
                    channel = data.get('channel', '')
                    symbol = data.get('symbol', '')
                    interval = data.get('interval', '')
                    strategy_id = data.get('strategy_id', '')

                    if channel == 'kline':
                        print(f"\n{Colors.OKCYAN}[订阅请求]{Colors.ENDC}")
                        print(f"  策略ID: {strategy_id}")
                        print(f"  动作: {action}")
                        print(f"  交易对: {symbol}")
                        print(f"  周期: {interval}")

                except zmq.error.Again:
                    continue
                except Exception as e:
                    if not self.stop_monitor:
                        print(f"{Colors.WARNING}订阅监控错误: {e}{Colors.ENDC}")

            socket.close()
            context.term()

        self.subscribe_monitor_thread = threading.Thread(target=monitor_subscribe, daemon=True)
        self.subscribe_monitor_thread.start()

    def start_strategy(self):
        """启动策略"""
        self.print_header("步骤3: 启动策略")

        config_file = self.base_dir / "strategies/configs/grid_btc_main.json"
        if not config_file.exists():
            self.print_error(f"配置文件不存在: {config_file}")
            sys.exit(1)

        # 检查配置
        with open(config_file, 'r') as f:
            config = json.load(f)

        strategy_id = config.get('strategy_id', 'unknown')
        self.print_info(f"策略ID: {strategy_id}")
        self.print_info(f"配置文件: {config_file}")

        # 启动策略
        strategy_file = self.base_dir / "strategies/grid_strategy_cpp.py"
        log_file = self.base_dir / f"build/kline_test_strategy.log"

        cmd = [
            'python3.13',
            str(strategy_file),
            '--config', str(config_file)
        ]

        self.print_info(f"启动命令: {' '.join(cmd)}")
        self.print_info(f"策略日志: {log_file}")

        # 设置PYTHONPATH
        env = os.environ.copy()
        strategies_dir = str(self.base_dir / "strategies")
        env['PYTHONPATH'] = strategies_dir

        with open(log_file, 'w') as f:
            self.strategy_process = subprocess.Popen(
                cmd,
                cwd=strategies_dir,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=env
            )

        self.print_success(f"策略已启动 (PID: {self.strategy_process.pid})")

    def wait_and_analyze(self, duration: int = 30):
        """等待并分析结果"""
        self.print_header(f"步骤4: 等待并分析 ({duration}秒)")

        start_time = time.time()
        last_report_time = start_time

        while time.time() - start_time < duration:
            time.sleep(1)
            elapsed = time.time() - start_time

            # 每5秒报告一次
            if elapsed - (last_report_time - start_time) >= 5:
                last_report_time = time.time()
                print(f"\n{Colors.OKBLUE}[进度] {elapsed:.0f}/{duration}秒{Colors.ENDC}")
                print(f"  服务器K线总数: {self.server_kline_count}")
                print(f"  OKX BTC 1s: {self.server_okx_1s_count}")
                print(f"  OKX BTC 1m: {self.server_okx_1m_count}")
                print(f"  策略订阅请求: {len(self.strategy_subscriptions)}")

        self.print_success(f"等待完成")

    def analyze_results(self):
        """分析测试结果"""
        self.print_header("测试结果分析")

        # 检查服务器是否发布了K线
        print(f"\n{Colors.BOLD}1. 服务器K线发布情况:{Colors.ENDC}")
        if self.server_kline_count > 0:
            self.print_success(f"服务器共发布 {self.server_kline_count} 条K线")
            print(f"  - OKX BTC-USDT-SWAP 1s: {self.server_okx_1s_count} 条")
            print(f"  - OKX BTC-USDT-SWAP 1m: {self.server_okx_1m_count} 条")
        else:
            self.print_error("服务器未发布任何K线数据")
            self.print_info("可能原因:")
            self.print_info("  1. 服务器未成功连接到交易所")
            self.print_info("  2. 交易所未推送K线数据")
            self.print_info("  3. K线被confirm过滤掉了")

        # 检查策略订阅请求
        print(f"\n{Colors.BOLD}2. 策略订阅请求情况:{Colors.ENDC}")
        if self.strategy_subscriptions:
            self.print_success(f"策略发送了 {len(self.strategy_subscriptions)} 个订阅请求")

            # 查找1s K线订阅
            found_1s_subscribe = False
            for sub in self.strategy_subscriptions:
                if (sub.get('channel') == 'kline' and
                    sub.get('symbol') == 'BTC-USDT-SWAP' and
                    sub.get('interval') == '1s' and
                    sub.get('action') == 'subscribe'):
                    found_1s_subscribe = True
                    self.print_success("找到 BTC-USDT-SWAP 1s K线订阅请求")
                    print(f"  策略ID: {sub.get('strategy_id')}")
                    break

            if not found_1s_subscribe:
                self.print_error("未找到 BTC-USDT-SWAP 1s K线订阅请求")
                self.print_info("策略订阅的内容:")
                for sub in self.strategy_subscriptions:
                    print(f"  - {sub.get('channel')} {sub.get('symbol')} {sub.get('interval')}")
        else:
            self.print_error("策略未发送任何订阅请求")
            self.print_info("可能原因:")
            self.print_info("  1. 策略启动失败")
            self.print_info("  2. 策略未调用 subscribe_kline()")

        # 检查策略日志
        print(f"\n{Colors.BOLD}3. 策略运行情况:{Colors.ENDC}")
        log_file = self.base_dir / "build/kline_test_strategy.log"
        if log_file.exists():
            with open(log_file, 'r') as f:
                log_content = f.read()

            # 检查关键信息
            if "已订阅 BTC-USDT-SWAP 1s K线" in log_content:
                self.print_success("策略日志显示已订阅1s K线")
            else:
                self.print_warning("策略日志中未找到订阅确认")

            # 检查K线接收
            if "基准价格:" in log_content:
                # 提取基准价格
                for line in log_content.split('\n'):
                    if "基准价格:" in line:
                        print(f"  {line.strip()}")
                    if "K线数量:" in line:
                        print(f"  {line.strip()}")
                        if "0 根" not in line:
                            self.print_success("策略收到了K线数据")
                            self.strategy_kline_received = True
                        else:
                            self.print_error("策略未收到K线数据")
        else:
            self.print_warning("策略日志文件不存在")

        # 最终结论
        print(f"\n{Colors.BOLD}{'=' * 70}{Colors.ENDC}")
        print(f"{Colors.BOLD}最终结论:{Colors.ENDC}")
        print(f"{Colors.BOLD}{'=' * 70}{Colors.ENDC}")

        if self.server_okx_1s_count > 0 and self.strategy_subscriptions and self.strategy_kline_received:
            print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ 测试通过！{Colors.ENDC}")
            print(f"{Colors.OKGREEN}策略成功订阅并接收到服务器发布的1s K线数据{Colors.ENDC}")
        else:
            print(f"\n{Colors.FAIL}{Colors.BOLD}✗ 测试失败！{Colors.ENDC}")
            if self.server_okx_1s_count == 0:
                self.print_error("服务器未发布1s K线数据")
            if not self.strategy_subscriptions:
                self.print_error("策略未发送订阅请求")
            if not self.strategy_kline_received:
                self.print_error("策略未收到K线数据")

        print(f"\n{Colors.BOLD}查看详细日志:{Colors.ENDC}")
        print(f"  服务器: tail -100 {self.base_dir}/build/kline_test_server.log")
        print(f"  策略:   tail -100 {self.base_dir}/build/kline_test_strategy.log")

    def cleanup(self):
        """清理资源"""
        self.print_header("清理资源")

        # 停止监控线程
        self.stop_monitor = True
        if self.market_monitor_thread:
            self.market_monitor_thread.join(timeout=2)
        if self.subscribe_monitor_thread:
            self.subscribe_monitor_thread.join(timeout=2)

        # 停止策略
        if self.strategy_process:
            self.print_info("停止策略...")
            self.strategy_process.send_signal(signal.SIGINT)
            try:
                self.strategy_process.wait(timeout=5)
                self.print_success("策略已停止")
            except subprocess.TimeoutExpired:
                self.print_warning("策略停止超时，强制终止")
                self.strategy_process.kill()

        # 停止服务器
        if self.server_process:
            self.print_info("停止服务器...")
            self.server_process.send_signal(signal.SIGINT)
            try:
                self.server_process.wait(timeout=10)
                self.print_success("服务器已停止")
            except subprocess.TimeoutExpired:
                self.print_warning("服务器停止超时，强制终止")
                self.server_process.kill()

    def run_test(self):
        """运行测试"""
        try:
            print(f"\n{Colors.HEADER}{Colors.BOLD}")
            print("=" * 70)
            print("  策略K线订阅测试")
            print("  测试 grid_strategy_cpp.py 是否能订阅并接收1s K线")
            print("=" * 70)
            print(f"{Colors.ENDC}")

            # 步骤1: 启动服务器
            self.start_server()

            # 步骤2: 监控服务器K线
            self.start_market_monitor()

            # 等待服务器开始发布K线
            self.print_info("等待服务器开始发布K线...")
            time.sleep(5)

            # 步骤3: 监控订阅请求
            self.start_subscribe_monitor()

            # 步骤4: 启动策略
            self.start_strategy()

            # 步骤5: 等待并分析
            self.wait_and_analyze(duration=30)

            # 步骤6: 分析结果
            self.analyze_results()

        except KeyboardInterrupt:
            print(f"\n{Colors.WARNING}测试被用户中断{Colors.ENDC}")
        except Exception as e:
            print(f"\n{Colors.FAIL}测试失败: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup()

def main():
    tester = KlineSubscriptionTester()
    tester.run_test()

if __name__ == "__main__":
    main()
