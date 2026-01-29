#!/usr/bin/env python3
"""
测试日志记录是否完整
"""

import sys
import os
from pathlib import Path

# 添加路径
script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(script_dir))

from strategy_logger import setup_strategy_logging

def test_complete_logging():
    """测试完整的日志记录"""

    print("=" * 60)
    print("测试：完整日志记录")
    print("=" * 60)
    print()

    # 初始化日志
    logger = setup_strategy_logging(
        exchange='okx',
        strategy_id='test_complete',
        log_dir='./log'
    )

    # 测试各种格式的输出
    print("✓ 日志文件:", logger.log_file)
    print()

    print("╔" + "═" * 50 + "╗")
    print("║" + "  测试策略".center(44) + "║")
    print("╚" + "═" * 50 + "╝")
    print()

    print("策略配置:")
    print("  策略ID:     test_complete")
    print("  交易对:     BTC-USDT-SWAP")
    print("  网格数量:   20")
    print("  网格间距:   0.200%")
    print("  下单金额:   50 USDT")
    print("  交易环境:   测试网")
    print("  API Key:    1d7868a6-1...")
    print()

    print("模块化设计:")
    print("  - MarketDataModule: 行情数据（K线订阅、存储）")
    print("  - TradingModule: 交易操作（下单、撤单）")
    print("  - AccountModule: 账户管理（登录、余额、持仓）")
    print()

    print("[test_complete] 策略参数: BTC-USDT-SWAP | 网格:20x2 | 间距:0.200% | 金额:50U")
    print("[test_complete] 已连接到实盘服务器")
    print("[test_complete] 策略初始化...")
    print("[test_complete] 已发送 OKX 账户注册请求")
    print("[test_complete] " + "=" * 50)
    print("[test_complete] 开始测试下单功能...")
    print("[test_complete] 测试买入: BTC-USDT-SWAP buy 1张 (long)")
    print("[test_complete] [下单] buy 1张 BTC-USDT-SWAP | 订单ID: py5753847910")
    print("[test_complete] 买入订单已发送, 客户端订单ID: py5753847910")
    print("[test_complete] 下单测试完成")
    print("[test_complete] " + "=" * 50)
    print("[test_complete] 已订阅 BTC-USDT-SWAP 1s K线")
    print("[test_complete] 初始化完成，等待行情数据...")
    print("[test_complete] 策略运行中...")
    print("[test_complete] [账户注册] ✓ 注册成功")
    print("[test_complete] ✓ 账户注册成功")
    print("[test_complete] ✓ 余额数据已就绪")
    print("[test_complete]   USDT可用: 55253.12")
    print("[test_complete]   USDT冻结: 11005.40")
    print("[test_complete]   USDT总计: 66258.52")
    print("[test_complete] 网格初始化: 基准=89009.00 | 买入:85448.64~88830.98 | 卖出:89187.02~92569.36")
    print()

    logger.close()

    print()
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)
    print()
    print(f"请查看日志文件: {logger.log_file}")
    print()
    print("验证命令:")
    print(f"  cat {logger.log_file}")
    print()

if __name__ == "__main__":
    test_complete_logging()
