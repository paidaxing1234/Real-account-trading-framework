#!/usr/bin/env python3
"""
测试 API Key 是模拟盘还是实盘
只通过 WebSocket 登录验证，不会下单
"""

import asyncio
import websockets
import json
import hmac
import hashlib
import base64
import time

# API 配置 (来自 api-key.txt)
API_KEY = "35984fef-11f1-4be4-8a18-c41a1e5b17dd"
SECRET_KEY = "D1D61A9AD1FD7E1822FB4879FF867E51"
PASSPHRASE = "Wbl20041209.."

# WebSocket 端点
WS_TESTNET = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"  # 模拟盘
WS_LIVE = "wss://ws.okx.com:8443/ws/v5/private"  # 实盘


def generate_sign(timestamp: str, secret_key: str) -> str:
    """
    生成签名
    sign = Base64(HMAC_SHA256(timestamp + 'GET' + '/users/self/verify', secret_key))
    """
    message = timestamp + 'GET' + '/users/self/verify'
    mac = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    )
    return base64.b64encode(mac.digest()).decode('utf-8')


def build_login_msg(api_key: str, secret_key: str, passphrase: str) -> str:
    """构建登录消息"""
    timestamp = str(int(time.time()))
    sign = generate_sign(timestamp, secret_key)
    
    login_msg = {
        "op": "login",
        "args": [
            {
                "apiKey": api_key,
                "passphrase": passphrase,
                "timestamp": timestamp,
                "sign": sign
            }
        ]
    }
    return json.dumps(login_msg)


async def test_login(ws_url: str, env_name: str) -> bool:
    """
    测试在指定环境登录
    
    Returns:
        bool: 登录成功返回 True
    """
    print(f"\n{'='*50}")
    print(f"测试 {env_name} 环境...")
    print(f"端点: {ws_url}")
    print(f"{'='*50}")
    
    try:
        async with websockets.connect(ws_url, ping_interval=20) as ws:
            # 发送登录消息
            login_msg = build_login_msg(API_KEY, SECRET_KEY, PASSPHRASE)
            print(f"发送登录请求...")
            await ws.send(login_msg)
            
            # 等待响应
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(response)
            
            print(f"响应: {json.dumps(data, indent=2)}")
            
            if data.get("event") == "login" and data.get("code") == "0":
                print(f"\n✅ {env_name} 登录成功！")
                return True
            else:
                print(f"\n❌ {env_name} 登录失败")
                print(f"   错误码: {data.get('code')}")
                print(f"   错误信息: {data.get('msg')}")
                return False
                
    except asyncio.TimeoutError:
        print(f"\n❌ {env_name} 连接超时")
        return False
    except Exception as e:
        print(f"\n❌ {env_name} 连接错误: {e}")
        return False


async def main():
    print("\n" + "="*60)
    print("  OKX API Key 环境检测工具")
    print("  (仅登录验证，不会下单)")
    print("="*60)
    print(f"\nAPI Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print(f"Secret Key: {SECRET_KEY[:8]}...{SECRET_KEY[-4:]}")
    
    # 测试模拟盘
    testnet_ok = await test_login(WS_TESTNET, "模拟盘(Testnet)")
    
    # 测试实盘
    live_ok = await test_login(WS_LIVE, "实盘(Live)")
    
    # 输出结论
    print("\n" + "="*60)
    print("  检测结论")
    print("="*60)
    
    if testnet_ok and not live_ok:
        print("\n🎯 此 API Key 是 【模拟盘】 的！")
        print("   请使用 --testnet 参数运行策略")
        print("   服务器启动时使用默认配置（模拟盘）")
    elif live_ok and not testnet_ok:
        print("\n🎯 此 API Key 是 【实盘】 的！")
        print("   请使用 --live 参数运行策略")
        print("   服务器启动时使用 OKX_TESTNET=0")
    elif testnet_ok and live_ok:
        print("\n⚠️ 两个环境都登录成功？这很奇怪...")
    else:
        print("\n❌ 两个环境都登录失败！")
        print("   请检查 API Key、Secret Key 和 Passphrase 是否正确")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())

