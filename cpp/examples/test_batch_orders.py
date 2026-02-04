#!/usr/bin/env python3
"""
测试 Binance 批量下单接口
"""

import sys
import os

# 添加 strategies 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'strategies'))

# 导入 strategy_base 模块
import strategy_base

# 检查 send_batch_orders 方法签名
print("=" * 60)
print("检查 send_batch_orders 方法签名")
print("=" * 60)

# 查看方法
if hasattr(strategy_base.StrategyBase, 'send_batch_orders'):
    method = getattr(strategy_base.StrategyBase, 'send_batch_orders')
    print(f"方法存在: {method}")
    print(f"文档: {method.__doc__}")
else:
    print("方法不存在!")

print()
print("=" * 60)
print("检查模块中的所有方法")
print("=" * 60)

# 列出所有方法
for name in dir(strategy_base.StrategyBase):
    if not name.startswith('_'):
        attr = getattr(strategy_base.StrategyBase, name)
        if callable(attr):
            doc = attr.__doc__ or ""
            if "batch" in name.lower() or "batch" in doc.lower():
                print(f"  {name}: {doc[:50]}...")
