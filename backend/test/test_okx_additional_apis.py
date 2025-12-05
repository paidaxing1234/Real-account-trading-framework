"""
OKX REST API 补充接口测试
测试未测试的接口：get_orders_pending, get_positions, get_instruments
以及市价单功能
"""

import json
import time
from adapters.okx import OKXRestAPI


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


def test_get_instruments():
    """测试获取产品信息"""
    print_section("测试1: 获取产品基础信息 (get_instruments)")
    
    # API凭证
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
        # 测试1.1: 获取BTC-USDT产品信息
        print("\n🔍 测试1.1: 获取BTC-USDT产品信息...")
        response = client.get_instruments(
            inst_type="SPOT",
            inst_id="BTC-USDT"
        )
        
        if response['code'] == '0':
            print("✅ 成功！")
            data = response['data'][0]
            print(f"   产品ID: {data['instId']}")
            print(f"   交易货币: {data['baseCcy']}")
            print(f"   计价货币: {data['quoteCcy']}")
            print(f"   最小下单量: {data['minSz']}")
            print(f"   价格精度: {data['tickSz']}")
            print(f"   数量精度: {data['lotSz']}")
            print(f"   状态: {data['state']}")
        else:
            print(f"❌ 失败: {response['msg']}")
            return False
        
        # 测试1.2: 获取所有现货产品列表（只显示前5个）
        print("\n🔍 测试1.2: 获取现货产品列表（前5个）...")
        response = client.get_instruments(inst_type="SPOT")
        
        if response['code'] == '0':
            print(f"✅ 成功！共有 {len(response['data'])} 个现货产品")
            print("   前5个产品:")
            for i, item in enumerate(response['data'][:5], 1):
                print(f"   {i}. {item['instId']} - {item['state']}")
        else:
            print(f"❌ 失败: {response['msg']}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_orders_pending():
    """测试查询未成交订单"""
    print_section("测试2: 查询未成交订单 (get_orders_pending)")
    
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
        # 先下一个限价单（不会立即成交）
        print("\n📝 步骤1: 先下一个限价买单...")
        order_response = client.place_order(
            inst_id="BTC-USDT",
            td_mode="cash",
            side="buy",
            ord_type="limit",
            px="50000",  # 远低于市价，不会成交
            sz="0.01"
        )
        
        if order_response['code'] == '0':
            order_id = order_response['data'][0]['ordId']
            print(f"✅ 订单创建成功！订单ID: {order_id}")
        else:
            print(f"❌ 下单失败: {order_response['msg']}")
            return False
        
        time.sleep(1)  # 等待1秒
        
        # 测试2.1: 查询所有未成交订单
        print("\n🔍 测试2.1: 查询所有未成交订单...")
        response = client.get_orders_pending()
        
        if response['code'] == '0':
            print(f"✅ 成功！共有 {len(response['data'])} 个未成交订单")
            if response['data']:
                for order in response['data'][:3]:  # 只显示前3个
                    print(f"   - {order['instId']}: {order['side']} {order['sz']} @ {order['px']} ({order['state']})")
        else:
            print(f"❌ 失败: {response['msg']}")
            return False
        
        # 测试2.2: 查询BTC-USDT的未成交订单
        print("\n🔍 测试2.2: 查询BTC-USDT的未成交订单...")
        response = client.get_orders_pending(inst_id="BTC-USDT")
        
        if response['code'] == '0':
            print(f"✅ 成功！BTC-USDT有 {len(response['data'])} 个未成交订单")
            if response['data']:
                order = response['data'][0]
                print(f"   订单ID: {order['ordId']}")
                print(f"   方向: {order['side']}")
                print(f"   价格: {order['px']}")
                print(f"   数量: {order['sz']}")
                print(f"   状态: {order['state']}")
        else:
            print(f"❌ 失败: {response['msg']}")
            return False
        
        # 清理：撤销测试订单
        print("\n🗑️  清理: 撤销测试订单...")
        cancel_response = client.cancel_order(
            inst_id="BTC-USDT",
            ord_id=order_id
        )
        
        if cancel_response['code'] == '0':
            print("✅ 订单已撤销")
        else:
            print(f"⚠️  撤单失败: {cancel_response['msg']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_positions():
    """测试查询持仓"""
    print_section("测试3: 查询持仓 (get_positions)")
    
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
        # 测试3.1: 查询所有持仓
        print("\n🔍 测试3.1: 查询所有持仓...")
        response = client.get_positions()
        
        if response['code'] == '0':
            print(f"✅ 成功！共有 {len(response['data'])} 个持仓")
            if response['data']:
                print("   持仓列表:")
                for pos in response['data']:
                    print(f"   - {pos['instId']}: {pos['pos']} (未实现盈亏: {pos.get('upl', 'N/A')})")
            else:
                print("   ℹ️  当前无持仓")
        else:
            print(f"❌ 失败: {response['msg']}")
            return False
        
        # 测试3.2: 查询特定产品持仓（永续合约）
        print("\n🔍 测试3.2: 查询BTC-USDT-SWAP持仓...")
        response = client.get_positions(inst_id="BTC-USDT-SWAP")
        
        if response['code'] == '0':
            print(f"✅ 成功！")
            if response['data']:
                pos = response['data'][0]
                print(f"   产品: {pos['instId']}")
                print(f"   持仓量: {pos['pos']}")
                print(f"   持仓方向: {pos.get('posSide', 'N/A')}")
                print(f"   未实现盈亏: {pos.get('upl', 'N/A')}")
            else:
                print("   ℹ️  该产品无持仓")
        else:
            print(f"❌ 失败: {response['msg']}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_market_order():
    """测试市价单"""
    print_section("测试4: 市价单功能 (place_order - market)")
    
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
        # 查询当前余额
        print("\n💰 步骤1: 查询账户余额...")
        balance_response = client.get_balance()
        
        if balance_response['code'] == '0':
            for detail in balance_response['data'][0]['details']:
                if detail['ccy'] == 'USDT':
                    usdt_balance = float(detail['availBal'])
                    print(f"✅ USDT可用余额: {usdt_balance:.2f} USDT")
                    break
        
        # 测试4.1: 市价买单（小额测试）
        print("\n📝 测试4.1: 市价买单...")
        print("   产品: BTC-USDT")
        print("   方向: 买入")
        print("   类型: 市价单")
        print("   数量单位: 计价货币（USDT）")
        print("   数量: 50 USDT")
        
        order_response = client.place_order(
            inst_id="BTC-USDT",
            td_mode="cash",
            side="buy",
            ord_type="market",
            sz="50",  # 50 USDT
            tgt_ccy="quote_ccy"  # 使用计价货币（USDT）
        )
        
        if order_response['code'] == '0':
            order_data = order_response['data'][0]
            print("✅ 市价买单提交成功！")
            print(f"   订单ID: {order_data['ordId']}")
            print(f"   状态: {order_data['sMsg']}")
            
            # 等待成交
            time.sleep(2)
            
            # 查询订单状态
            print("\n🔍 查询订单成交情况...")
            query_response = client.get_order(
                inst_id="BTC-USDT",
                ord_id=order_data['ordId']
            )
            
            if query_response['code'] == '0':
                query_data = query_response['data'][0]
                print(f"✅ 订单状态: {query_data['state']}")
                print(f"   已成交数量: {query_data['accFillSz']}")
                print(f"   平均成交价: {query_data.get('avgPx', 'N/A')}")
                print(f"   手续费: {query_data.get('fee', 'N/A')} {query_data.get('feeCcy', '')}")
                
                # 如果成交了，立即卖出（平仓）
                if query_data['state'] == 'filled':
                    print("\n📝 平仓: 市价卖单...")
                    sell_response = client.place_order(
                        inst_id="BTC-USDT",
                        td_mode="cash",
                        side="sell",
                        ord_type="market",
                        sz=query_data['accFillSz']
                    )
                    
                    if sell_response['code'] == '0':
                        print("✅ 市价卖单提交成功！已平仓")
                    else:
                        print(f"⚠️  卖单失败: {sell_response['msg']}")
            else:
                print(f"⚠️  查询失败: {query_response['msg']}")
        else:
            print(f"❌ 市价买单失败: {order_response['msg']}")
            if 'data' in order_response and order_response['data']:
                for item in order_response['data']:
                    if 'sMsg' in item:
                        print(f"   详细: {item['sMsg']}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX REST API 补充接口测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: get_instruments
    results['get_instruments'] = test_get_instruments()
    
    # 测试2: get_orders_pending
    results['get_orders_pending'] = test_get_orders_pending()
    
    # 测试3: get_positions
    results['get_positions'] = test_get_positions()
    
    # 测试4: market order
    results['market_order'] = test_market_order()
    
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

