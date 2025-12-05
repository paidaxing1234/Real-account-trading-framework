"""
OKX账户接口测试
测试：get_balance, get_account_instruments
"""

import json
from adapters.okx import OKXRestAPI


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


def test_get_balance():
    """测试查询账户余额"""
    print_section("测试1: 查询账户余额 (get_balance)")
    
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
        # 测试1.1: 查询所有币种余额
        print("\n📝 测试1.1: 查询所有币种余额...")
        balance = client.get_balance()
        
        print("\n【服务器响应】")
        print(json.dumps(balance, indent=2, ensure_ascii=False))
        
        if balance['code'] == '0':
            print("\n✅ 查询成功！")
            
            data = balance['data'][0]
            print(f"\n【账户信息】")
            print(f"   总权益(USD): {data.get('totalEq', 'N/A')}")
            print(f"   有效保证金(USD): {data.get('adjEq', 'N/A')}")
            print(f"   账户更新时间: {data.get('uTime', 'N/A')}")
            
            print(f"\n【各币种余额详情】")
            for detail in data.get('details', [])[:5]:  # 只显示前5个
                ccy = detail['ccy']
                eq = detail['eq']
                avail_bal = detail['availBal']
                frozen_bal = detail['frozenBal']
                eq_usd = detail.get('eqUsd', '0')
                
                print(f"\n   {ccy}:")
                print(f"      总权益: {eq}")
                print(f"      可用余额: {avail_bal}")
                print(f"      冻结金额: {frozen_bal}")
                print(f"      USD价值: {eq_usd}")
            
            if len(data.get('details', [])) > 5:
                print(f"\n   ... 还有 {len(data['details']) - 5} 个币种")
        
        # 测试1.2: 查询特定币种余额
        print("\n\n📝 测试1.2: 查询USDT余额...")
        usdt_balance = client.get_balance(ccy="USDT")
        
        if usdt_balance['code'] == '0':
            print("✅ 查询成功！")
            
            data = usdt_balance['data'][0]
            for detail in data.get('details', []):
                if detail['ccy'] == 'USDT':
                    print(f"\n【USDT详情】")
                    print(f"   总权益: {detail['eq']}")
                    print(f"   可用余额: {detail['availBal']}")
                    print(f"   冻结金额: {detail['frozenBal']}")
                    print(f"   挂单冻结: {detail.get('ordFrozen', '0')}")
                    print(f"   USD价值: {detail.get('eqUsd', '0')}")
                    break
        
        # 测试1.3: 查询多个币种余额
        print("\n\n📝 测试1.3: 查询多个币种余额(USDT,BTC)...")
        multi_balance = client.get_balance(ccy="USDT,BTC")
        
        if multi_balance['code'] == '0':
            print("✅ 查询成功！")
            
            data = multi_balance['data'][0]
            for detail in data.get('details', []):
                ccy = detail['ccy']
                if ccy in ['USDT', 'BTC']:
                    print(f"\n   {ccy}: {detail['eq']} (可用: {detail['availBal']})")
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_account_instruments():
    """测试获取账户可交易产品信息"""
    print_section("测试2: 获取账户可交易产品信息 (get_account_instruments)")
    
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
        # 测试2.1: 查询所有现货产品
        print("\n📝 测试2.1: 查询所有现货产品...")
        instruments = client.get_account_instruments(inst_type="SPOT")
        
        if instruments['code'] == '0':
            count = len(instruments['data'])
            print(f"✅ 查询成功！共 {count} 个现货产品")
            
            # 显示前3个产品信息
            print(f"\n【前3个产品信息】")
            for inst in instruments['data'][:3]:
                print(f"\n   {inst['instId']}:")
                print(f"      基础币种: {inst.get('baseCcy', 'N/A')}")
                print(f"      计价币种: {inst.get('quoteCcy', 'N/A')}")
                print(f"      状态: {inst.get('state', 'N/A')}")
                print(f"      最小下单量: {inst.get('minSz', 'N/A')}")
                print(f"      下单价格精度: {inst.get('tickSz', 'N/A')}")
                print(f"      下单数量精度: {inst.get('lotSz', 'N/A')}")
                print(f"      手续费组ID: {inst.get('groupId', 'N/A')}")
        
        # 测试2.2: 查询特定产品
        print("\n\n📝 测试2.2: 查询BTC-USDT产品信息...")
        btc_inst = client.get_account_instruments(
            inst_type="SPOT",
            inst_id="BTC-USDT"
        )
        
        print("\n【服务器响应】")
        print(json.dumps(btc_inst, indent=2, ensure_ascii=False))
        
        if btc_inst['code'] == '0' and btc_inst['data']:
            print("\n✅ 查询成功！")
            
            inst = btc_inst['data'][0]
            print(f"\n【BTC-USDT详细信息】")
            print(f"   产品ID: {inst['instId']}")
            print(f"   产品类型: {inst['instType']}")
            print(f"   基础币种: {inst['baseCcy']}")
            print(f"   计价币种: {inst['quoteCcy']}")
            print(f"   状态: {inst['state']}")
            print(f"   最小下单量: {inst['minSz']}")
            print(f"   最大限价单数量: {inst.get('maxLmtSz', 'N/A')}")
            print(f"   最大市价单数量: {inst.get('maxMktSz', 'N/A')}")
            print(f"   限价单最大金额(USD): {inst.get('maxLmtAmt', 'N/A')}")
            print(f"   市价单最大金额(USD): {inst.get('maxMktAmt', 'N/A')}")
            print(f"   价格精度: {inst['tickSz']}")
            print(f"   数量精度: {inst['lotSz']}")
            print(f"   手续费组ID: {inst['groupId']}")
            print(f"   上线时间: {inst.get('listTime', 'N/A')}")
            print(f"   交易规则类型: {inst.get('ruleType', 'N/A')}")
            
            # 计价币种列表
            if 'tradeQuoteCcyList' in inst:
                print(f"   可用计价币种: {', '.join(inst['tradeQuoteCcyList'])}")
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX 账户接口测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: 查询账户余额
    results['get_balance'] = test_get_balance()
    
    # 测试2: 获取账户可交易产品信息
    results['get_account_instruments'] = test_get_account_instruments()
    
    # 汇总结果
    print_section("📊 测试结果汇总")
    
    print("\n接口测试结果:")
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name:30s} : {status}")
    
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

