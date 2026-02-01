#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis历史数据接口测试套件 - 主入口

运行所有测试脚本的统一入口：
1. test_redis_historical_basic.py - 基础接口测试
2. test_redis_strategy_scenarios.py - 策略场景测试
3. test_redis_edge_cases.py - 边界条件和异常测试
4. test_redis_performance.py - 性能和压力测试

使用方法:
    python3 run_all_redis_tests.py           # 运行所有测试
    python3 run_all_redis_tests.py basic     # 只运行基础测试
    python3 run_all_redis_tests.py scenario  # 只运行场景测试
    python3 run_all_redis_tests.py edge      # 只运行边界测试
    python3 run_all_redis_tests.py perf      # 只运行性能测试

@author Test Suite
@date 2025-01
"""

import sys
import os
import time
import subprocess
from datetime import datetime

# 测试脚本目录
TEST_DIR = os.path.dirname(os.path.abspath(__file__))

# 测试脚本列表
TESTS = {
    "basic": {
        "name": "基础接口测试",
        "script": "test_redis_historical_basic.py",
        "description": "测试所有基础的历史数据查询接口"
    },
    "scenario": {
        "name": "策略场景测试",
        "script": "test_redis_strategy_scenarios.py",
        "description": "模拟真实策略的使用场景进行测试"
    },
    "edge": {
        "name": "边界条件测试",
        "script": "test_redis_edge_cases.py",
        "description": "测试各种边界条件和异常情况"
    },
    "perf": {
        "name": "性能压力测试",
        "script": "test_redis_performance.py",
        "description": "测试接口的性能表现"
    }
}


def print_header():
    """打印测试套件头部"""
    print("\n" + "=" * 80)
    print("  Redis历史数据接口测试套件")
    print("=" * 80)
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  测试目录: {TEST_DIR}")
    print("=" * 80 + "\n")


def print_test_list():
    """打印可用的测试列表"""
    print("可用的测试:")
    print("-" * 60)
    for key, info in TESTS.items():
        print(f"  {key:<10} - {info['name']}")
        print(f"             {info['description']}")
    print("-" * 60)
    print()


def run_test(test_key: str) -> bool:
    """运行单个测试"""
    if test_key not in TESTS:
        print(f"✗ 未知的测试: {test_key}")
        return False

    test_info = TESTS[test_key]
    script_path = os.path.join(TEST_DIR, test_info["script"])

    if not os.path.exists(script_path):
        print(f"✗ 测试脚本不存在: {script_path}")
        return False

    print(f"\n{'='*80}")
    print(f"  开始运行: {test_info['name']}")
    print(f"  脚本: {test_info['script']}")
    print(f"{'='*80}\n")

    start_time = time.time()

    try:
        # 运行测试脚本
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=TEST_DIR,
            timeout=600  # 10分钟超时
        )
        success = result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"✗ 测试超时")
        success = False
    except Exception as e:
        print(f"✗ 运行异常: {e}")
        success = False

    elapsed = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"  {test_info['name']} 完成")
    print(f"  耗时: {elapsed:.2f}秒")
    print(f"  状态: {'✓ 成功' if success else '✗ 失败'}")
    print(f"{'='*80}\n")

    return success


def run_all_tests() -> dict:
    """运行所有测试"""
    results = {}

    for test_key in TESTS:
        results[test_key] = run_test(test_key)

    return results


def print_summary(results: dict):
    """打印测试摘要"""
    print("\n" + "=" * 80)
    print("  测试套件执行摘要")
    print("=" * 80 + "\n")

    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)

    for test_key, success in results.items():
        status = "✓ 通过" if success else "✗ 失败"
        print(f"  {TESTS[test_key]['name']:<20} {status}")

    print()
    print(f"  总计: {total_count} 个测试套件")
    print(f"  通过: {success_count}")
    print(f"  失败: {total_count - success_count}")
    print(f"  通过率: {success_count / total_count * 100:.1f}%")
    print()


def main():
    print_header()

    # 解析命令行参数
    if len(sys.argv) > 1:
        test_key = sys.argv[1].lower()

        if test_key == "help" or test_key == "-h" or test_key == "--help":
            print_test_list()
            print("使用方法:")
            print("  python3 run_all_redis_tests.py           # 运行所有测试")
            print("  python3 run_all_redis_tests.py <test>    # 运行指定测试")
            print()
            return

        if test_key == "all":
            results = run_all_tests()
            print_summary(results)
        elif test_key in TESTS:
            success = run_test(test_key)
            print(f"\n测试{'通过' if success else '失败'}！")
        else:
            print(f"✗ 未知的测试: {test_key}")
            print()
            print_test_list()
    else:
        # 默认运行所有测试
        print("将运行所有测试...\n")
        print_test_list()

        results = run_all_tests()
        print_summary(results)


if __name__ == "__main__":
    main()
