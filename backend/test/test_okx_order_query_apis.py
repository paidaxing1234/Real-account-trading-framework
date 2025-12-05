"""
OKX订单查询接口测试
测试：get_order, get_orders_pending (完善版), get_orders_history
"""

import json
import time
from adapters.okx import OKXRestAPI


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


def test_get_order_detailed():
    """测试查询订单详情（完整信息）"""
    print_section("测试1: 查询订单详情 (get_order)")
    
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
        # 步骤1: 先创建一个测试订单
        print("\n📝 步骤1: 创建测试订单...")
        order_result = client.place_order(
            inst_id="BTC-USDT",
            td_mode="cash",
            side="buy",
            ord_type="limit",
            px="50000",  # 远低于市价
            sz="0.01"
        )
        
        if order_result['code'] != '0':
            print(f"❌ 下单失败: {order_result['msg']}")
            return False
        
        order_id = order_result['data'][0]['ordId']
        print(f"✅ 订单创建成功")
        print(f"   订单ID: {order_id}")
        
        time.sleep(1)
        
        # 步骤2: 查询订单详情
        print("\n📝 步骤2: 查询订单详情...")
        order_info = client.get_order(
            inst_id="BTC-USDT",
            ord_id=order_id
        )
        
        print("\n【服务器响应】")
        print(json.dumps(order_info, indent=2, ensure_ascii=False))
        
        if order_info['code'] == '0':
            order_data = order_info['data'][0]
            print("\n✅ 查询成功！")
            print(f"\n【订单详情】")
            print(f"   订单ID: {order_data['ordId']}")
            print(f"   产品: {order_data['instId']}")
            print(f"   订单类型: {order_data['ordType']}")
            print(f"   方向: {order_data['side']}")
            print(f"   状态: {order_data['state']}")
            print(f"   委托价格: {order_data['px']}")
            print(f"   委托数量: {order_data['sz']}")
            print(f"   已成交: {order_data['accFillSz']}")
            print(f"   均价: {order_data.get('avgPx', 'N/A')}")
            print(f"   手续费: {order_data.get('fee', '0')} {order_data.get('feeCcy', '')}")
            print(f"   创建时间: {order_data['cTime']}")
            print(f"   更新时间: {order_data['uTime']}")
            
            # 撤销测试订单
            time.sleep(1)
            print("\n📝 步骤3: 撤销测试订单...")
            cancel_result = client.cancel_order(
                inst_id="BTC-USDT",
                ord_id=order_id
            )
            if cancel_result['code'] == '0':
                print("✅ 订单已撤销")
            
            return True
        else:
            print(f"\n❌ 查询失败: {order_info['msg']}")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_orders_pending_advanced():
    """测试查询未成交订单（完善版，支持更多参数）"""
    print_section("测试2: 查询未成交订单（完善版）(get_orders_pending)")
    
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
        # 步骤1: 创建几个测试订单
        print("\n📝 步骤1: 创建测试订单...")
        order_ids = []
        
        # 创建限价单
        for i in range(2):
            result = client.place_order(
                inst_id="BTC-USDT",
                td_mode="cash",
                side="buy",
                ord_type="limit",
                px=str(50000 + i * 100),
                sz="0.01"
            )
            if result['code'] == '0':
                order_ids.append(result['data'][0]['ordId'])
                print(f"   ✅ 订单{i+1}创建成功: {result['data'][0]['ordId']}")
        
        time.sleep(1)
        
        # 步骤2: 查询所有未成交订单
        print("\n📝 步骤2: 查询所有未成交订单...")
        all_orders = client.get_orders_pending()
        
        if all_orders['code'] == '0':
            print(f"✅ 查询成功！共 {len(all_orders['data'])} 个未成交订单")
        
        # 步骤3: 按订单类型查询
        print("\n📝 步骤3: 查询限价单（ord_type=limit）...")
        limit_orders = client.get_orders_pending(
            inst_type="SPOT",
            ord_type="limit"
        )
        
        if limit_orders['code'] == '0':
            print(f"✅ 查询成功！共 {len(limit_orders['data'])} 个限价单")
            if limit_orders['data']:
                print(f"\n【第一个限价单信息】")
                order = limit_orders['data'][0]
                print(f"   订单ID: {order['ordId']}")
                print(f"   产品: {order['instId']}")
                print(f"   价格: {order['px']}")
                print(f"   数量: {order['sz']}")
                print(f"   状态: {order['state']}")
        
        # 步骤4: 查询BTC-USDT的未成交订单
        print("\n📝 步骤4: 查询BTC-USDT的未成交订单...")
        btc_orders = client.get_orders_pending(
            inst_id="BTC-USDT",
            limit="10"
        )
        
        if btc_orders['code'] == '0':
            print(f"✅ 查询成功！共 {len(btc_orders['data'])} 个BTC-USDT未成交订单")
        
        # 步骤5: 清理测试订单
        print("\n📝 步骤5: 清理测试订单...")
        for order_id in order_ids:
            client.cancel_order(inst_id="BTC-USDT", ord_id=order_id)
        print("✅ 测试订单已清理")
        
        return True
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_orders_history():
    """测试查询历史订单（近7天）"""
    print_section("测试3: 查询历史订单（近7天）(get_orders_history)")
    
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
        # 步骤1: 创建并立即撤销一个订单（生成历史记录）
        print("\n📝 步骤1: 创建并撤销测试订单（生成历史记录）...")
        order_result = client.place_order(
            inst_id="BTC-USDT",
            td_mode="cash",
            side="buy",
            ord_type="limit",
            px="50000",
            sz="0.01"
        )
        
        if order_result['code'] == '0':
            order_id = order_result['data'][0]['ordId']
            print(f"   ✅ 订单创建成功: {order_id}")
            
            time.sleep(1)
            
            # 撤销订单
            cancel_result = client.cancel_order(
                inst_id="BTC-USDT",
                ord_id=order_id
            )
            if cancel_result['code'] == '0':
                print(f"   ✅ 订单已撤销")
        
        time.sleep(2)  # 等待订单进入历史记录
        
        # 步骤2: 查询所有历史订单
        print("\n📝 步骤2: 查询所有现货历史订单...")
        all_history = client.get_orders_history(
            inst_type="SPOT",
            limit="10"
        )
        
        print("\n【服务器响应】")
        print(json.dumps(all_history, indent=2, ensure_ascii=False))
        
        if all_history['code'] == '0':
            print(f"\n✅ 查询成功！最近 {len(all_history['data'])} 条历史记录")
            
            if all_history['data']:
                print(f"\n【最新历史订单】")
                order = all_history['data'][0]
                print(f"   订单ID: {order['ordId']}")
                print(f"   产品: {order['instId']}")
                print(f"   类型: {order['ordType']}")
                print(f"   方向: {order['side']}")
                print(f"   状态: {order['state']}")
                print(f"   价格: {order.get('px', 'N/A')}")
                print(f"   数量: {order['sz']}")
                print(f"   已成交: {order['accFillSz']}")
                print(f"   创建时间: {order['cTime']}")
                print(f"   更新时间: {order['uTime']}")
        
        # 步骤3: 查询BTC-USDT的历史订单
        print("\n📝 步骤3: 查询BTC-USDT的历史订单...")
        btc_history = client.get_orders_history(
            inst_type="SPOT",
            inst_id="BTC-USDT",
            limit="5"
        )
        
        if btc_history['code'] == '0':
            print(f"✅ 查询成功！最近 {len(btc_history['data'])} 条BTC-USDT历史记录")
            if btc_history['data']:
                print(f"   最新订单ID: {btc_history['data'][0]['ordId']}")
                print(f"   订单状态: {btc_history['data'][0]['state']}")
        
        return True
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX 订单查询接口测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: 查询订单详情
    results['get_order'] = test_get_order_detailed()
    
    # 测试2: 查询未成交订单（完善版）
    results['get_orders_pending_advanced'] = test_get_orders_pending_advanced()
    
    # 测试3: 查询历史订单
    results['get_orders_history'] = test_get_orders_history()
    
    # 汇总结果
    print_section("📊 测试结果汇总")
    
    print("\n接口测试结果:")
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name:35s} : {status}")
    
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

