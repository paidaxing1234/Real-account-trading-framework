"""
OKX持仓信息查询接口测试
测试：get_positions（查询持仓）, get_positions_history（查询历史持仓）
"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.okx import OKXRestAPI


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


def test_get_positions():
    """测试查询持仓信息"""
    print_section("测试1: 查询持仓信息 (get_positions)")
    
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    client = OKXRestAPI(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        is_demo=True
    )
    
    try:
        # 测试1.1: 查询所有持仓
        print("\n📝 测试1.1: 查询所有持仓...")
        positions = client.get_positions()
        
        print("\n【服务器响应】")
        print(json.dumps(positions, indent=2, ensure_ascii=False))
        
        if positions['code'] == '0':
            count = len(positions['data'])
            print(f"\n✅ 查询成功！共 {count} 个持仓")
            
            if positions['data']:
                print(f"\n【持仓信息示例】")
                for i, pos in enumerate(positions['data'][:3], 1):
                    print(f"\n   持仓{i}:")
                    print(f"      产品ID: {pos['instId']}")
                    print(f"      产品类型: {pos['instType']}")
                    print(f"      持仓方向: {pos['posSide']}")
                    print(f"      持仓数量: {pos['pos']}")
                    print(f"      可平仓数量: {pos.get('availPos', 'N/A')}")
                    print(f"      开仓均价: {pos['avgPx']}")
                    print(f"      标记价格: {pos['markPx']}")
                    print(f"      杠杆倍数: {pos.get('lever', 'N/A')}")
                    print(f"      保证金模式: {pos['mgnMode']}")
                    print(f"      未实现收益: {pos.get('upl', 'N/A')}")
                    print(f"      未实现收益率: {pos.get('uplRatio', 'N/A')}")
                    print(f"      持仓ID: {pos.get('posId', 'N/A')}")
            else:
                print(f"\n   ℹ️  当前没有持仓")
        
        # 测试1.2: 查询杠杆持仓
        print("\n\n📝 测试1.2: 查询杠杆持仓（MARGIN）...")
        margin_positions = client.get_positions(inst_type="MARGIN")
        
        if margin_positions['code'] == '0':
            count = len(margin_positions['data'])
            print(f"✅ 查询成功！共 {count} 个杠杆持仓")
            
            if margin_positions['data']:
                for pos in margin_positions['data']:
                    print(f"\n   {pos['instId']}:")
                    print(f"      持仓数量: {pos['pos']}")
                    print(f"      持仓币种: {pos.get('posCcy', 'N/A')}")
                    print(f"      负债额: {pos.get('liab', '0')}")
                    print(f"      负债币种: {pos.get('liabCcy', 'N/A')}")
                    print(f"      维持保证金率: {pos.get('mgnRatio', 'N/A')}")
        
        # 测试1.3: 查询特定产品持仓
        print("\n\n📝 测试1.3: 查询特定产品持仓（BTC-USDT）...")
        btc_position = client.get_positions(inst_id="BTC-USDT")
        
        if btc_position['code'] == '0':
            count = len(btc_position['data'])
            if count > 0:
                print(f"✅ 查询成功！找到 {count} 个BTC-USDT持仓")
                pos = btc_position['data'][0]
                print(f"\n【BTC-USDT持仓详情】")
                print(f"   产品类型: {pos['instType']}")
                print(f"   持仓方向: {pos['posSide']}")
                print(f"   持仓数量: {pos['pos']}")
                print(f"   开仓均价: {pos['avgPx']}")
                print(f"   当前标记价: {pos['markPx']}")
                print(f"   未实现收益: {pos.get('upl', 'N/A')}")
            else:
                print(f"ℹ️  没有BTC-USDT持仓")
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_positions_history():
    """测试查询历史持仓信息"""
    print_section("测试2: 查询历史持仓信息 (get_positions_history)")
    
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    client = OKXRestAPI(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        is_demo=True
    )
    
    try:
        # 测试2.1: 查询所有历史持仓
        print("\n📝 测试2.1: 查询所有历史持仓（限制10条）...")
        history = client.get_positions_history(limit="10")
        
        print("\n【服务器响应】")
        print(json.dumps(history, indent=2, ensure_ascii=False))
        
        if history['code'] == '0':
            count = len(history['data'])
            print(f"\n✅ 查询成功！共 {count} 条历史持仓记录")
            
            if history['data']:
                print(f"\n【历史持仓统计】")
                # 统计平仓类型
                type_count = {}
                type_names = {
                    "1": "部分平仓",
                    "2": "完全平仓",
                    "3": "强平",
                    "4": "强减",
                    "5": "ADL自动减仓-未完全平仓",
                    "6": "ADL自动减仓-完全平仓"
                }
                
                for pos in history['data']:
                    pos_type = pos.get('type', 'unknown')
                    type_count[pos_type] = type_count.get(pos_type, 0) + 1
                
                print(f"   平仓类型分布:")
                for pos_type, count in type_count.items():
                    type_name = type_names.get(pos_type, f"未知类型({pos_type})")
                    print(f"      {type_name}: {count}条")
                
                # 显示详细信息
                print(f"\n【历史持仓详情（前3条）】")
                for i, pos in enumerate(history['data'][:3], 1):
                    print(f"\n   记录{i}:")
                    print(f"      产品ID: {pos['instId']}")
                    print(f"      产品类型: {pos['instType']}")
                    print(f"      持仓方向: {pos['posSide']}")
                    print(f"      保证金模式: {pos['mgnMode']}")
                    print(f"      开仓均价: {pos['openAvgPx']}")
                    print(f"      平仓均价: {pos['closeAvgPx']}")
                    print(f"      最大持仓量: {pos['openMaxPos']}")
                    print(f"      累计平仓量: {pos['closeTotalPos']}")
                    print(f"      已实现收益: {pos['realizedPnl']}")
                    print(f"      收益率: {pos.get('pnlRatio', 'N/A')}")
                    print(f"      平仓类型: {type_names.get(pos.get('type', ''), pos.get('type', 'N/A'))}")
                    print(f"      杠杆倍数: {pos.get('lever', 'N/A')}")
            else:
                print(f"\n   ℹ️  没有历史持仓记录")
        
        # 测试2.2: 查询杠杆历史持仓
        print("\n\n📝 测试2.2: 查询杠杆历史持仓（MARGIN）...")
        margin_history = client.get_positions_history(
            inst_type="MARGIN",
            limit="5"
        )
        
        if margin_history['code'] == '0':
            count = len(margin_history['data'])
            print(f"✅ 查询成功！共 {count} 条杠杆历史持仓")
        
        # 测试2.3: 查询完全平仓记录
        print("\n\n📝 测试2.3: 查询完全平仓记录（type=2）...")
        close_history = client.get_positions_history(
            type="2",
            limit="5"
        )
        
        if close_history['code'] == '0':
            count = len(close_history['data'])
            print(f"✅ 查询成功！共 {count} 条完全平仓记录")
            
            if close_history['data']:
                total_pnl = sum(float(pos.get('realizedPnl', 0)) for pos in close_history['data'])
                print(f"   累计已实现收益: {total_pnl}")
        
        # 测试2.4: 查询全仓历史持仓
        print("\n\n📝 测试2.4: 查询全仓历史持仓（mgnMode=cross）...")
        cross_history = client.get_positions_history(
            mgn_mode="cross",
            limit="5"
        )
        
        if cross_history['code'] == '0':
            count = len(cross_history['data'])
            print(f"✅ 查询成功！共 {count} 条全仓历史持仓")
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX 持仓信息查询接口测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: 查询持仓信息
    results['get_positions'] = test_get_positions()
    
    # 测试2: 查询历史持仓信息
    results['get_positions_history'] = test_get_positions_history()
    
    # 汇总结果
    print_section("📊 测试结果汇总")
    
    print("\n接口测试结果:")
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name:25s} : {status}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
