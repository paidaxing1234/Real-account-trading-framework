"""
OKX批量操作和修改订单接口测试
测试：place_batch_orders, cancel_batch_orders, amend_order, amend_batch_orders
"""

import json
import time
from adapters.okx import OKXRestAPI


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


def test_batch_place_orders():
    """测试批量下单"""
    print_section("测试1: 批量下单 (place_batch_orders)")
    
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
        print("\n📝 测试1.1: 批量下单（2个订单）...")
        print("   订单1: BTC-USDT, 买入, 限价 50000, 数量 0.01")
        print("   订单2: ETH-USDT, 买入, 限价 2000, 数量 0.1")
        
        orders = [
            {
                "instId": "BTC-USDT",
                "tdMode": "cash",
                "side": "buy",
                "ordType": "limit",
                "px": "50000",
                "sz": "0.01"
            },
            {
                "instId": "ETH-USDT",
                "tdMode": "cash",
                "side": "buy",
                "ordType": "limit",
                "px": "2000",
                "sz": "0.1"
            }
        ]
        
        response = client.place_batch_orders(orders)
        
        print("\n【服务器响应】")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        if response['code'] == '0':
            print("\n✅ 批量下单成功！")
            order_info = []  # 返回[(ordId, instId), ...]
            for i, (order_req, order_data) in enumerate(zip(orders, response['data']), 1):
                print(f"\n订单{i}:")
                print(f"   订单ID: {order_data['ordId']}")
                print(f"   状态码: {order_data['sCode']}")
                print(f"   状态信息: {order_data['sMsg']}")
                if order_data['sCode'] == '0':
                    order_info.append((order_data['ordId'], order_req['instId']))
            
            return order_info  # 返回订单ID和产品ID用于后续测试
        else:
            print(f"\n❌ 批量下单失败: {response['msg']}")
            return []
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_amend_order(order_info: tuple):
    """测试修改单个订单"""
    print_section("测试2: 修改订单 (amend_order)")
    
    order_id, inst_id = order_info
    
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
        print(f"\n📝 测试2.1: 修改订单价格...")
        print(f"   产品: {inst_id}")
        print(f"   订单ID: {order_id}")
        print(f"   新价格: 50100")
        
        time.sleep(1)  # 等待订单生效
        
        response = client.amend_order(
            inst_id=inst_id,
            ord_id=order_id,
            new_px="50100"
        )
        
        print("\n【服务器响应】")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        if response['code'] == '0':
            data = response['data'][0]
            if data['sCode'] == '0':
                print("\n✅ 订单修改成功！")
                print(f"   订单ID: {data['ordId']}")
                print(f"   修改时间: {data['ts']}")
                return True
            else:
                print(f"\n⚠️ 修改失败: {data['sMsg']}")
                return False
        else:
            print(f"\n❌ 修改请求失败: {response['msg']}")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_amend_orders(order_info_list: list):
    """测试批量修改订单"""
    print_section("测试3: 批量修改订单 (amend_batch_orders)")
    
    if len(order_info_list) < 2:
        print("⚠️  需要至少2个订单进行批量修改测试")
        return False
    
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
        print(f"\n📝 测试3.1: 批量修改订单（2个订单）...")
        print(f"   订单1: {order_info_list[0][1]} {order_info_list[0][0]}, 新价格: 50200")
        print(f"   订单2: {order_info_list[1][1]} {order_info_list[1][0]}, 新价格: 2100")
        
        time.sleep(1)
        
        orders = [
            {
                "instId": order_info_list[0][1],
                "ordId": order_info_list[0][0],
                "newPx": "50200"
            },
            {
                "instId": order_info_list[1][1],
                "ordId": order_info_list[1][0],
                "newPx": "2100"
            }
        ]
        
        response = client.amend_batch_orders(orders)
        
        print("\n【服务器响应】")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        if response['code'] == '0':
            print("\n✅ 批量修改成功！")
            for i, data in enumerate(response['data'], 1):
                print(f"\n订单{i}:")
                print(f"   订单ID: {data['ordId']}")
                print(f"   状态码: {data['sCode']}")
                print(f"   状态信息: {data['sMsg']}")
            return True
        else:
            print(f"\n❌ 批量修改失败: {response['msg']}")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_cancel_orders(order_info_list: list):
    """测试批量撤单"""
    print_section("测试4: 批量撤单 (cancel_batch_orders)")
    
    if not order_info_list:
        print("⚠️  没有可撤销的订单")
        return False
    
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
        print(f"\n📝 测试4.1: 批量撤单（{len(order_info_list)}个订单）...")
        for i, (order_id, inst_id) in enumerate(order_info_list, 1):
            print(f"   订单{i}: {inst_id} {order_id}")
        
        time.sleep(1)
        
        orders = [
            {"instId": inst_id, "ordId": order_id}
            for order_id, inst_id in order_info_list
        ]
        
        response = client.cancel_batch_orders(orders)
        
        print("\n【服务器响应】")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        # 批量操作可能部分成功
        if response['code'] in ['0', '2']:  # 0=全部成功, 2=部分成功
            success_count = sum(1 for data in response['data'] if data['sCode'] == '0')
            total_count = len(response['data'])
            
            if response['code'] == '0':
                print(f"\n✅ 批量撤单成功！（{success_count}/{total_count}）")
            else:
                print(f"\n⚠️  批量撤单部分成功！（{success_count}/{total_count}）")
            
            for i, data in enumerate(response['data'], 1):
                status = "✅" if data['sCode'] == '0' else "❌"
                print(f"\n订单{i}: {status}")
                print(f"   订单ID: {data['ordId']}")
                print(f"   状态码: {data['sCode']}")
                print(f"   状态信息: {data.get('sMsg', '成功')}")
            
            return success_count == total_count
        else:
            print(f"\n❌ 批量撤单失败: {response['msg']}")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX 批量操作和修改订单接口测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: 批量下单
    order_info_list = test_batch_place_orders()
    results['place_batch_orders'] = len(order_info_list) > 0
    
    if order_info_list:
        # 测试2: 修改单个订单
        results['amend_order'] = test_amend_order(order_info_list[0])
        
        # 测试3: 批量修改订单
        if len(order_info_list) >= 2:
            results['amend_batch_orders'] = test_batch_amend_orders(order_info_list)
        else:
            results['amend_batch_orders'] = False
            print("⚠️  跳过批量修改测试（订单数不足）")
        
        # 测试4: 批量撤单
        results['cancel_batch_orders'] = test_batch_cancel_orders(order_info_list)
    else:
        results['amend_order'] = False
        results['amend_batch_orders'] = False
        results['cancel_batch_orders'] = False
        print("⚠️  由于批量下单失败，跳过后续测试")
    
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

