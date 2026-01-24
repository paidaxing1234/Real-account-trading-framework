#!/usr/bin/env python3
"""
真实策略运行测试 - 测试网版本

测试目标：
1. 启动交易服务器
2. 启动真实的策略程序（按照策略自己的逻辑运行）
3. 监控策略发送的订单
4. 验证订单回报中的策略ID是否正确
5. 验证账户一致性

@author Sequence Team
@date 2026-01-23
"""

import os
import json
import subprocess
import time
import zmq
import signal
import sys
from pathlib import Path
from typing import Dict, List, Optional
import threading

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

class RealStrategyTester:
    def __init__(self):
        self.base_dir = Path("/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp")
        self.config_dir = self.base_dir / "strategies/configs"
        self.server_process: Optional[subprocess.Popen] = None
        self.strategy_process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitor = False
        self.received_reports: List[Dict] = []
        self.test_passed = 0
        self.test_failed = 0

    def print_header(self, text: str):
        """打印测试标题"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}")
        print(f"  {text}")
        print(f"{'=' * 70}{Colors.ENDC}")

    def print_success(self, text: str):
        """打印成功信息"""
        print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")
        self.test_passed += 1

    def print_error(self, text: str):
        """打印错误信息"""
        print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")
        self.test_failed += 1

    def print_info(self, text: str):
        """打印信息"""
        print(f"{Colors.OKCYAN}  {text}{Colors.ENDC}")

    def print_warning(self, text: str):
        """打印警告"""
        print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

    def load_strategy_config(self) -> Optional[Dict]:
        """加载第一个启用的测试网策略配置"""
        self.print_header("加载策略配置")

        config_files = list(self.config_dir.glob("*.json"))

        for config_file in config_files:
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                if config.get('enabled', False) and config.get('is_testnet', False):
                    self.print_info(f"找到启用的测试网策略: {config['strategy_id']}")
                    self.print_info(f"  配置文件: {config_file.name}")
                    self.print_info(f"  交易所: {config['exchange']}")
                    self.print_info(f"  策略类型: {config.get('strategy_type', 'unknown')}")
                    return config
            except Exception as e:
                self.print_warning(f"跳过配置文件 {config_file.name}: {e}")

        self.print_error("没有找到启用的测试网策略")
        return None

    def start_server(self):
        """启动交易服务器"""
        self.print_header("启动交易服务器")

        server_bin = self.base_dir / "build/trading_server_full"
        if not server_bin.exists():
            self.print_error(f"服务器程序不存在: {server_bin}")
            self.print_info("请先编译服务器: cd cpp/build && cmake .. && make")
            sys.exit(1)

        # 清理旧的IPC文件
        self.print_info("清理旧的IPC文件...")
        subprocess.run("rm -f /tmp/seq_*.ipc", shell=True, check=False)

        # 启动服务器
        log_file = self.base_dir / "build/real_strategy_test.log"
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
        max_wait = 30
        wait_interval = 2

        for i in range(max_wait // wait_interval):
            time.sleep(wait_interval)
            if self.check_server_ready():
                self.print_success(f"服务器已就绪 (等待 {(i+1)*wait_interval} 秒)")
                return
            self.print_info(f"等待中... ({(i+1)*wait_interval}/{max_wait}秒)")

        self.print_error("服务器启动超时")
        self.print_info(f"查看日志: tail -100 {log_file}")
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

    def start_report_monitor(self, strategy_id: str):
        """启动订单回报监控线程"""
        self.print_header("启动订单回报监控")
        self.print_info(f"监控策略: {strategy_id}")

        def monitor_reports():
            context = zmq.Context()
            socket = context.socket(zmq.SUB)
            socket.connect("ipc:///tmp/seq_report.ipc")
            socket.setsockopt_string(zmq.SUBSCRIBE, "")
            socket.setsockopt(zmq.RCVTIMEO, 1000)

            self.print_info("订单回报监控已启动")

            while not self.stop_monitor:
                try:
                    msg = socket.recv()

                    # 解析回报
                    try:
                        report = json.loads(msg.decode('utf-8'))
                    except:
                        msg_str = msg.decode('utf-8')
                        if '|' in msg_str:
                            report = json.loads(msg_str.split('|', 1)[1])
                        else:
                            continue

                    # 记录回报
                    self.received_reports.append(report)

                    # 显示回报信息
                    report_strategy_id = report.get('strategy_id', 'unknown')
                    client_order_id = report.get('client_order_id', 'unknown')
                    status = report.get('status', 'unknown')

                    # 尝试多种可能的字段名
                    symbol = report.get('symbol') or report.get('inst_id') or report.get('instId') or 'unknown'
                    side = report.get('side') or report.get('posSide') or 'unknown'

                    print(f"\n{Colors.OKCYAN}[订单回报]{Colors.ENDC}")
                    print(f"  策略ID: {report_strategy_id}")
                    print(f"  客户端订单ID: {client_order_id}")
                    print(f"  交易对: {symbol}")
                    print(f"  方向: {side}")
                    print(f"  状态: {status}")

                    # 调试：显示完整的回报JSON（仅前3个回报）
                    if len(self.received_reports) <= 3:
                        print(f"  [调试] 完整回报: {json.dumps(report, ensure_ascii=False, indent=2)}")

                    # 验证策略ID
                    if report_strategy_id == strategy_id:
                        print(f"{Colors.OKGREEN}  ✓ 策略ID匹配{Colors.ENDC}")
                    else:
                        print(f"{Colors.FAIL}  ✗ 策略ID不匹配! 期望: {strategy_id}, 实际: {report_strategy_id}{Colors.ENDC}")

                    if status == 'rejected':
                        error_msg = report.get('error_msg', '')
                        print(f"  拒绝原因: {error_msg}")

                except zmq.error.Again:
                    continue
                except Exception as e:
                    if not self.stop_monitor:
                        print(f"{Colors.WARNING}解析回报失败: {e}{Colors.ENDC}")

            socket.close()
            context.term()
            self.print_info("订单回报监控已停止")

        self.monitor_thread = threading.Thread(target=monitor_reports, daemon=True)
        self.monitor_thread.start()
        time.sleep(1)  # 等待监控线程启动

    def start_strategy(self, config: Dict):
        """启动策略程序"""
        self.print_header("启动策略程序")

        strategy_id = config['strategy_id']
        strategy_type = config.get('strategy_type', 'unknown')

        # 根据策略类型选择策略文件
        if strategy_type == 'grid':
            strategy_file = self.base_dir / "strategies/grid_strategy_cpp.py"
        elif strategy_type == 'gnn':
            strategy_file = self.base_dir / "strategies/GNN_model/trading/GNNstr/gnn_strategy.py"
        else:
            self.print_error(f"未知的策略类型: {strategy_type}")
            return

        if not strategy_file.exists():
            self.print_error(f"策略文件不存在: {strategy_file}")
            return

        self.print_info(f"策略文件: {strategy_file}")
        self.print_info(f"策略ID: {strategy_id}")

        # 构造策略启动命令
        params = config.get('params', {})

        if strategy_type == 'grid':
            symbol = params.get('symbol', 'BTC-USDT-SWAP')
            grid_num = params.get('grid_num', 10)
            grid_spread = params.get('grid_spread', 0.002)
            order_amount = params.get('order_amount', 100)

            cmd = [
                'python3',
                str(strategy_file),
                '--strategy-id', strategy_id,
                '--symbol', symbol,
                '--grid-num', str(grid_num),
                '--grid-spread', str(grid_spread),
                '--order-amount', str(order_amount),
                '--api-key', config['api_key'],
                '--secret-key', config['secret_key'],
                '--passphrase', config['passphrase'],
                '--testnet'
            ]
        else:
            self.print_error(f"暂不支持启动 {strategy_type} 类型的策略")
            return

        self.print_info(f"启动命令: {' '.join(cmd[:10])}...")

        # 启动策略
        log_file = self.base_dir / f"build/strategy_{strategy_id}.log"

        # 设置PYTHONPATH，让策略能找到strategy_base模块
        env = os.environ.copy()
        strategies_dir = str(self.base_dir / "strategies")
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{strategies_dir}:{env['PYTHONPATH']}"
        else:
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
        self.print_info(f"策略日志: {log_file}")

    def wait_for_orders(self, duration: int = 30):
        """等待策略发送订单"""
        self.print_header(f"等待策略运行 ({duration}秒)")

        for i in range(duration):
            time.sleep(1)
            if (i + 1) % 5 == 0:
                self.print_info(f"已运行 {i+1}/{duration} 秒, 收到 {len(self.received_reports)} 个订单回报")

        self.print_success(f"等待完成，共收到 {len(self.received_reports)} 个订单回报")

    def analyze_results(self, strategy_id: str):
        """分析测试结果"""
        self.print_header("分析测试结果")

        if not self.received_reports:
            self.print_warning("未收到任何订单回报")
            self.print_info("可能原因:")
            self.print_info("  1. 策略启动失败")
            self.print_info("  2. 策略未发送订单")
            self.print_info("  3. 订单被立即拒绝")
            return

        self.print_info(f"共收到 {len(self.received_reports)} 个订单回报")

        # 统计策略ID匹配情况
        matched = 0
        mismatched = 0

        for report in self.received_reports:
            report_strategy_id = report.get('strategy_id', '')
            if report_strategy_id == strategy_id:
                matched += 1
            else:
                mismatched += 1
                self.print_error(f"策略ID不匹配: 期望 {strategy_id}, 实际 {report_strategy_id}")

        if matched > 0:
            self.print_success(f"策略ID匹配: {matched}/{len(self.received_reports)}")

        if mismatched > 0:
            self.print_error(f"策略ID不匹配: {mismatched}/{len(self.received_reports)}")

        # 统计订单状态
        status_count = {}
        for report in self.received_reports:
            status = report.get('status', 'unknown')
            status_count[status] = status_count.get(status, 0) + 1

        self.print_info("\n订单状态统计:")
        for status, count in status_count.items():
            self.print_info(f"  {status}: {count}")

        # 显示部分订单详情
        self.print_info("\n订单详情（最多显示5个）:")
        for i, report in enumerate(self.received_reports[:5]):
            self.print_info(f"\n  订单 {i+1}:")
            self.print_info(f"    客户端订单ID: {report.get('client_order_id', 'unknown')}")
            self.print_info(f"    交易对: {report.get('symbol', 'unknown')}")
            self.print_info(f"    方向: {report.get('side', 'unknown')}")
            self.print_info(f"    状态: {report.get('status', 'unknown')}")
            if report.get('status') == 'rejected':
                self.print_info(f"    拒绝原因: {report.get('error_msg', 'unknown')}")

    def stop_strategy(self):
        """停止策略程序"""
        if self.strategy_process:
            self.print_info("停止策略程序...")
            self.strategy_process.send_signal(signal.SIGINT)
            try:
                self.strategy_process.wait(timeout=5)
                self.print_success("策略程序已停止")
            except subprocess.TimeoutExpired:
                self.print_warning("策略停止超时，强制终止")
                self.strategy_process.kill()

    def stop_server(self):
        """停止服务器"""
        self.print_header("停止服务器")

        # 停止监控线程
        if self.monitor_thread:
            self.stop_monitor = True
            self.monitor_thread.join(timeout=3)

        if self.server_process:
            self.print_info("发送停止信号...")
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
            # 警告信息
            self.print_header("⚠️  真实策略运行测试（测试网）")
            print(f"{Colors.WARNING}")
            print("  本测试将启动真实的策略程序")
            print("  - 策略将按照自己的逻辑在测试网上运行")
            print("  - 使用虚拟资金，无真实资金风险")
            print("  - 会发送真实的订单（根据策略逻辑）")
            print("  - 需要有效的测试网API密钥")
            print(f"{Colors.ENDC}")

            # 加载策略配置
            config = self.load_strategy_config()
            if not config:
                return 1

            strategy_id = config['strategy_id']

            # 启动服务器
            self.start_server()

            # 启动订单回报监控
            self.start_report_monitor(strategy_id)

            # 启动策略
            self.start_strategy(config)

            # 等待策略运行
            self.wait_for_orders(duration=30)

            # 停止策略
            self.stop_strategy()

            # 分析结果
            self.analyze_results(strategy_id)

            # 显示结果
            self.print_header("测试结果")

            if len(self.received_reports) > 0:
                matched = sum(1 for r in self.received_reports if r.get('strategy_id') == strategy_id)
                if matched == len(self.received_reports):
                    print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ 所有订单的策略ID都正确{Colors.ENDC}")
                    print(f"\n{Colors.OKGREEN}账户一致性验证成功！{Colors.ENDC}")
                    print(f"策略 {strategy_id} 的所有订单都路由到了正确的账户")
                    return 0
                else:
                    print(f"\n{Colors.FAIL}{Colors.BOLD}✗ 部分订单的策略ID不正确{Colors.ENDC}")
                    return 1
            else:
                print(f"\n{Colors.WARNING}未收到订单回报，无法验证{Colors.ENDC}")
                return 1

        except KeyboardInterrupt:
            print(f"\n{Colors.WARNING}测试被用户中断{Colors.ENDC}")
            return 1
        except Exception as e:
            print(f"\n{Colors.FAIL}测试失败: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            self.stop_strategy()
            self.stop_server()

if __name__ == "__main__":
    tester = RealStrategyTester()
    exit_code = tester.run_test()
    sys.exit(exit_code)
