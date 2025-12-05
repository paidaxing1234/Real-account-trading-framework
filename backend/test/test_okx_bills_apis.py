"""
OKX账单流水查询接口测试
测试：get_bills (近7天), get_bills_archive (近3个月)
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


def test_get_bills():
    """测试查询账单流水（近7天）"""
    print_section("测试1: 查询账单流水（近7天）(get_bills)")
    
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
        # 测试1.1: 查询所有账单
        print("\n📝 测试1.1: 查询所有账单（限制10条）...")
        bills = client.get_bills(limit="10")
        
        print("\n【服务器响应】")
        print(json.dumps(bills, indent=2, ensure_ascii=False))
        
        if bills['code'] == '0':
            count = len(bills['data'])
            print(f"\n✅ 查询成功！共 {count} 条账单记录")
            
            if bills['data']:
                print(f"\n【最新账单信息】")
                bill = bills['data'][0]
                print(f"   账单ID: {bill['billId']}")
                print(f"   币种: {bill['ccy']}")
                print(f"   账单类型: {bill['type']}")
                print(f"   账单子类型: {bill['subType']}")
                print(f"   余额变动: {bill['balChg']}")
                print(f"   余额: {bill['bal']}")
                print(f"   产品ID: {bill.get('instId', 'N/A')}")
                print(f"   产品类型: {bill.get('instType', 'N/A')}")
                print(f"   手续费: {bill.get('fee', '0')}")
                print(f"   时间戳: {bill['ts']}")
        
        # 测试1.2: 查询USDT账单
        print("\n\n📝 测试1.2: 查询USDT账单...")
        usdt_bills = client.get_bills(ccy="USDT", limit="5")
        
        if usdt_bills['code'] == '0':
            count = len(usdt_bills['data'])
            print(f"✅ 查询成功！共 {count} 条USDT账单")
            
            if usdt_bills['data']:
                print(f"\n【USDT账单示例】")
                for i, bill in enumerate(usdt_bills['data'][:3], 1):
                    print(f"\n   账单{i}:")
                    print(f"      账单ID: {bill['billId']}")
                    print(f"      类型: {bill['type']} (子类型: {bill['subType']})")
                    print(f"      余额变动: {bill['balChg']}")
                    print(f"      当前余额: {bill['bal']}")
        
        # 测试1.3: 查询交易类账单
        print("\n\n📝 测试1.3: 查询交易类账单（type=2）...")
        trade_bills = client.get_bills(type="2", limit="5")
        
        if trade_bills['code'] == '0':
            count = len(trade_bills['data'])
            print(f"✅ 查询成功！共 {count} 条交易账单")
            
            if trade_bills['data']:
                bill = trade_bills['data'][0]
                print(f"\n【交易账单详情】")
                print(f"   产品: {bill.get('instId', 'N/A')}")
                print(f"   订单ID: {bill.get('ordId', 'N/A')}")
                print(f"   成交价格: {bill.get('px', 'N/A')}")
                print(f"   成交数量: {bill.get('sz', 'N/A')}")
                print(f"   手续费: {bill.get('fee', '0')}")
                print(f"   流动性: {bill.get('execType', 'N/A')}")
        
        # 测试1.4: 查询现货账单
        print("\n\n📝 测试1.4: 查询现货账单...")
        spot_bills = client.get_bills(inst_type="SPOT", limit="5")
        
        if spot_bills['code'] == '0':
            count = len(spot_bills['data'])
            print(f"✅ 查询成功！共 {count} 条现货账单")
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_bills_archive():
    """测试查询账单流水（近3个月）"""
    print_section("测试2: 查询账单流水（近3个月）(get_bills_archive)")
    
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
        # 测试2.1: 查询所有历史账单
        print("\n📝 测试2.1: 查询所有历史账单（限制10条）...")
        archive_bills = client.get_bills_archive(limit="10")
        
        print("\n【服务器响应】")
        print(json.dumps(archive_bills, indent=2, ensure_ascii=False))
        
        if archive_bills['code'] == '0':
            count = len(archive_bills['data'])
            print(f"\n✅ 查询成功！共 {count} 条历史账单")
            
            if archive_bills['data']:
                print(f"\n【历史账单统计】")
                # 统计账单类型
                type_count = {}
                for bill in archive_bills['data']:
                    bill_type = bill['type']
                    type_count[bill_type] = type_count.get(bill_type, 0) + 1
                
                print(f"   账单类型分布:")
                for bill_type, count in type_count.items():
                    print(f"      类型{bill_type}: {count}条")
        
        # 测试2.2: 查询现货历史账单
        print("\n\n📝 测试2.2: 查询现货历史账单...")
        spot_archive = client.get_bills_archive(
            inst_type="SPOT",
            limit="5"
        )
        
        if spot_archive['code'] == '0':
            count = len(spot_archive['data'])
            print(f"✅ 查询成功！共 {count} 条现货历史账单")
        
        # 测试2.3: 查询特定币种历史账单
        print("\n\n📝 测试2.3: 查询USDT历史账单...")
        usdt_archive = client.get_bills_archive(
            ccy="USDT",
            limit="5"
        )
        
        if usdt_archive['code'] == '0':
            count = len(usdt_archive['data'])
            print(f"✅ 查询成功！共 {count} 条USDT历史账单")
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX 账单流水查询接口测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: 查询账单流水（近7天）
    results['get_bills'] = test_get_bills()
    
    # 测试2: 查询账单流水（近3个月）
    results['get_bills_archive'] = test_get_bills_archive()
    
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

