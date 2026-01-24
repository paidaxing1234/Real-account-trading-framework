#!/usr/bin/env python3
"""
简化测试脚本 - 用于诊断问题
"""

import os
import json
import subprocess
import time
import zmq
import signal
import sys
from pathlib import Path

def main():
    print("=" * 60)
    print("  简化测试开始")
    print("=" * 60)

    base_dir = Path("/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp")
    config_dir = base_dir / "strategies/configs"

    # 1. 清理IPC文件
    print("\n[1/5] 清理IPC文件...")
    subprocess.run("rm -f /tmp/seq_*.ipc /tmp/trading_*.ipc", shell=True, check=False)
    print("✓ IPC文件已清理")

    # 2. 启动服务器
    print("\n[2/5] 启动服务器...")
    server_bin = base_dir / "build/trading_server_full"
    if not server_bin.exists():
        print(f"✗ 服务器不存在: {server_bin}")
        return 1

    log_file = base_dir / "build/test_simple.log"
    with open(log_file, 'w') as f:
        server_process = subprocess.Popen(
            [str(server_bin)],
            cwd=str(base_dir / "build"),
            stdout=f,
            stderr=subprocess.STDOUT
        )
    print(f"✓ 服务器已启动 (PID: {server_process.pid})")
    print(f"  日志文件: {log_file}")

    # 3. 等待服务器就绪
    print("\n[3/5] 等待服务器就绪...")
    max_wait = 60  # 增加到60秒
    wait_interval = 3  # 增加到3秒

    for i in range(max_wait // wait_interval):
        time.sleep(wait_interval)

        # 尝试连接
        try:
            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            socket.connect("ipc:///tmp/seq_query.ipc")
            socket.setsockopt(zmq.RCVTIMEO, 3000)  # 增加到3秒

            # 使用一个已注册的策略ID进行查询
            query = {"strategy_id": "test_strategy_1", "query_type": "registered_accounts"}
            socket.send_json(query)
            response = socket.recv_json()

            socket.close()
            context.term()

            # 只要能收到响应（即使是错误响应），说明服务器已就绪
            if isinstance(response, dict):
                if 'count' in response:
                    print(f"✓ 服务器就绪 (等待 {(i+1)*wait_interval} 秒)")
                    print(f"  已注册策略数: {response.get('count', 0)}")
                    break
                elif response.get('code') == -1:
                    # 收到错误响应也说明服务器在运行
                    print(f"✓ 服务器就绪 (等待 {(i+1)*wait_interval} 秒)")
                    print(f"  服务器响应正常")
                    break
            else:
                print(f"  收到无效响应: {response}")
        except zmq.error.Again:
            print(f"  等待中... ({(i+1)*wait_interval}/{max_wait}秒) - 查询超时")
        except Exception as e:
            print(f"  等待中... ({(i+1)*wait_interval}/{max_wait}秒) - {type(e).__name__}: {str(e)[:50]}")
    else:
        print("✗ 服务器启动超时")
        print("  查看日志文件获取更多信息:")
        print(f"  tail -100 {log_file}")
        server_process.terminate()
        return 1

    # 4. 测试查询
    print("\n[4/5] 测试查询接口...")
    try:
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("ipc:///tmp/seq_query.ipc")
        socket.setsockopt(zmq.RCVTIMEO, 5000)

        # 查询所有策略配置
        query = {"strategy_id": "test", "query_type": "get_all_strategy_configs"}
        socket.send_json(query)
        response = socket.recv_json()

        if response.get('code') == 0:
            configs = response.get('data', [])
            print(f"✓ 查询成功，共 {len(configs)} 个策略配置")
            for cfg in configs[:3]:  # 只显示前3个
                print(f"  - {cfg.get('strategy_id')}: {cfg.get('strategy_name')}")
        else:
            print(f"✗ 查询失败: {response.get('error')}")

        socket.close()
        context.term()
    except Exception as e:
        print(f"✗ 查询失败: {e}")

    # 5. 清理
    print("\n[5/5] 清理...")
    server_process.send_signal(signal.SIGINT)
    try:
        server_process.wait(timeout=10)
        print("✓ 服务器已停止")
    except subprocess.TimeoutExpired:
        print("✗ 服务器停止超时，强制终���")
        server_process.kill()

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
