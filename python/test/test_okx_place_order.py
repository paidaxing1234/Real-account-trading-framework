"""
OKX下单接口测试
在模拟盘上测试现货限价单
"""

import json
from adapters.okx import OKXRestAPI


def test_place_order():
    """测试下单功能"""
    
    # API凭证（模拟盘）
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    # 创建客户端
    client = OKXRestAPI(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        is_demo=True  # 使用模拟盘
    )
    
    print("=" * 80)
    print("OKX 模拟盘下单测试")
    print("=" * 80)
    
    # ========== 第一步：获取当前行情 ==========
    print("\n📊 第一步：获取BTC-USDT当前行情...")
    try:
        ticker_response = client.get_ticker("BTC-USDT")
        
        if ticker_response['code'] == '0':
            ticker_data = ticker_response['data'][0]
            last_price = float(ticker_data['last'])
            bid_price = float(ticker_data['bidPx'])
            ask_price = float(ticker_data['askPx'])
            
            print("✅ 行情获取成功！")
            print(f"   最新价: {last_price:.2f} USDT")
            print(f"   买一价: {bid_price:.2f} USDT")
            print(f"   卖一价: {ask_price:.2f} USDT")
        else:
            print(f"❌ 行情获取失败: {ticker_response['msg']}")
            return
    except Exception as e:
        print(f"❌ 获取行情异常: {e}")
        return
    
    # ========== 第二步：查询账户余额 ==========
    print("\n💰 第二步：查询账户余额...")
    try:
        balance_response = client.get_balance()
        
        if balance_response['code'] == '0':
            print("✅ 余额查询成功！")
            
            # 查找USDT余额
            usdt_balance = None
            for detail in balance_response['data'][0]['details']:
                if detail['ccy'] == 'USDT':
                    usdt_balance = float(detail['availBal'])
                    print(f"   USDT 可用余额: {usdt_balance:.2f} USDT")
                    break
            
            if usdt_balance is None:
                print("   ⚠️  未找到USDT余额")
        else:
            print(f"❌ 余额查询失败: {balance_response['msg']}")
    except Exception as e:
        print(f"❌ 查询余额异常: {e}")
    
    # ========== 第三步：下限价单 ==========
    print("\n📝 第三步：下限价买单...")
    print("\n【订单参数】")
    print(f"   产品: BTC-USDT (现货)")
    print(f"   方向: 买入 (buy)")
    print(f"   类型: 限价单 (limit)")
    print(f"   价格: 93300 USDT")
    print(f"   数量: 0.01 BTC")
    print(f"   交易模式: cash (现货非保证金)")
    
    print("\n🚀 正在提交订单...")
    
    try:
        # 下单（不传clOrdId，让交易所自动生成）
        order_response = client.place_order(
            inst_id="BTC-USDT",        # 产品ID
            td_mode="cash",             # 现货模式
            side="buy",                 # 买入
            ord_type="limit",           # 限价单
            px="93300",                 # 价格
            sz="0.01"                   # 数量
        )
        
        print("\n【服务器响应】")
        print(json.dumps(order_response, indent=2, ensure_ascii=False))
        
        # 解析响应
        if order_response['code'] == '0':
            print("\n✅ 下单成功！")
            
            order_data = order_response['data'][0]
            
            print(f"\n【订单信息】")
            print(f"   订单ID: {order_data['ordId']}")
            print(f"   客户订单ID: {order_data['clOrdId']}")
            print(f"   订单标签: {order_data['tag']}")
            print(f"   提交时间: {order_data['ts']}")
            print(f"   状态码: {order_data['sCode']}")
            print(f"   状态信息: {order_data['sMsg'] or '成功'}")
            
            # ========== 第四步：查询订单状态 ==========
            print("\n🔍 第四步：查询订单状态...")
            
            import time
            time.sleep(1)  # 等待1秒
            
            query_response = client.get_order(
                inst_id="BTC-USDT",
                ord_id=order_data['ordId']
            )
            
            if query_response['code'] == '0':
                query_data = query_response['data'][0]
                print("✅ 查询成功！")
                print(f"\n【订单详情】")
                print(f"   订单ID: {query_data['ordId']}")
                print(f"   产品: {query_data['instId']}")
                print(f"   订单类型: {query_data['ordType']}")
                print(f"   方向: {query_data['side']}")
                print(f"   价格: {query_data['px']}")
                print(f"   数量: {query_data['sz']}")
                print(f"   状态: {query_data['state']}")
                print(f"   已成交数量: {query_data['accFillSz']}")
                print(f"   平均成交价: {query_data.get('avgPx', 'N/A')}")
            else:
                print(f"❌ 查询失败: {query_response['msg']}")
            
            # ========== 第五步：撤单 ==========
            print("\n🗑️  第五步：撤销订单...")
            
            time.sleep(1)  # 等待1秒
            
            cancel_response = client.cancel_order(
                inst_id="BTC-USDT",
                ord_id=order_data['ordId']
            )
            
            if cancel_response['code'] == '0':
                cancel_data = cancel_response['data'][0]
                print("✅ 撤单成功！")
                print(f"   订单ID: {cancel_data['ordId']}")
                print(f"   状态码: {cancel_data['sCode']}")
            else:
                print(f"❌ 撤单失败: {cancel_response['msg']}")
        
        else:
            print(f"\n❌ 下单失败！")
            print(f"   错误码: {order_response['code']}")
            print(f"   错误信息: {order_response['msg']}")
            
            # 如果有data字段，打印详细错误
            if 'data' in order_response and order_response['data']:
                for item in order_response['data']:
                    if 'sMsg' in item and item['sMsg']:
                        print(f"   详细信息: {item['sMsg']}")
    
    except Exception as e:
        print(f"\n❌ 下单异常: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    test_place_order()

