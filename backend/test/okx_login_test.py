"""
OKX WebSocket 登录功能测试
测试 OKX API 的 WebSocket 认证是否正常工作
"""

import asyncio
import websockets
import json
import hmac
import base64
import time
from datetime import datetime


class OKXWebSocketTest:
    """OKX WebSocket 登录测试类"""
    
    def __init__(self, api_key: str, secret_key: str, passphrase: str, is_demo: bool = False):
        """
        初始化OKX WebSocket测试客户端
        
        Args:
            api_key: API Key
            secret_key: Secret Key
            passphrase: API密码短语
            is_demo: 是否使用模拟盘 (True=模拟盘, False=实盘)
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        
        # WebSocket URL
        if is_demo:
            self.ws_url = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"  # 模拟盘私有频道
        else:
            self.ws_url = "wss://ws.okx.com:8443/ws/v5/private"  # 实盘私有频道
        
        self.ws = None
    
    def generate_signature(self, timestamp: str) -> str:
        """
        生成签名
        
        签名算法：
        1. 拼接: timestamp + method + requestPath
        2. HMAC SHA256 加密
        3. Base64 编码
        
        Args:
            timestamp: Unix时间戳（秒）
            
        Returns:
            Base64编码的签名字符串
        """
        method = 'GET'
        request_path = '/users/self/verify'
        
        # 拼接字符串
        message = timestamp + method + request_path
        
        # HMAC SHA256 加密
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf8'),
            digestmod='sha256'
        )
        
        # Base64 编码
        signature = base64.b64encode(mac.digest()).decode()
        
        return signature
    
    def create_login_message(self) -> dict:
        """
        创建登录消息
        
        Returns:
            登录消息的字典格式
        """
        # 生成时间戳（秒级）
        timestamp = str(int(time.time()))
        
        # 生成签名
        sign = self.generate_signature(timestamp)
        
        # 构造登录消息
        login_msg = {
            "op": "login",
            "args": [
                {
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": sign
                }
            ]
        }
        
        return login_msg
    
    async def test_login(self):
        """测试登录功能"""
        try:
            print(f"{'='*60}")
            print(f"OKX WebSocket 登录测试")
            print(f"{'='*60}")
            print(f"连接地址: {self.ws_url}")
            print(f"API Key: {self.api_key[:8]}...")
            print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}\n")
            
            # 连接WebSocket
            print("📡 正在连接 OKX WebSocket...")
            async with websockets.connect(self.ws_url) as websocket:
                self.ws = websocket
                print("✅ WebSocket 连接成功！\n")
                
                # 创建登录消息
                login_msg = self.create_login_message()
                print("📝 发送登录请求:")
                print(json.dumps(login_msg, indent=2))
                print()
                
                # 发送登录请求
                await websocket.send(json.dumps(login_msg))
                print("✉️  登录消息已发送，等待响应...\n")
                
                # 等待响应
                response = await websocket.recv()
                response_data = json.loads(response)
                
                print("📬 收到服务器响应:")
                print(json.dumps(response_data, indent=2, ensure_ascii=False))
                print()
                
                # 解析响应
                if response_data.get('event') == 'login':
                    code = response_data.get('code')
                    if code == '0':
                        print("✅ 登录成功！")
                        print(f"   连接ID: {response_data.get('connId')}")
                        print(f"   状态码: {code}")
                    else:
                        print("❌ 登录失败！")
                        print(f"   错误码: {code}")
                        print(f"   错误信息: {response_data.get('msg')}")
                elif response_data.get('event') == 'error':
                    print("❌ 登录出错！")
                    print(f"   错误码: {response_data.get('code')}")
                    print(f"   错误信息: {response_data.get('msg')}")
                    print(f"   连接ID: {response_data.get('connId')}")
                else:
                    print("⚠️  收到未知响应:")
                    print(json.dumps(response_data, indent=2, ensure_ascii=False))
                
                print(f"\n{'='*60}")
                print("测试完成")
                print(f"{'='*60}")
                
        except websockets.exceptions.WebSocketException as e:
            print(f"❌ WebSocket 错误: {e}")
        except Exception as e:
            print(f"❌ 发生错误: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数"""
    
    # OKX API 凭证
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    # 创建测试实例
    # is_demo=True 表示使用模拟盘API
    # 如果要测试实盘，改为 is_demo=False
    okx_test = OKXWebSocketTest(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        is_demo=True  # False=实盘, True=模拟盘
    )
    
    # 执行登录测试
    await okx_test.test_login()


if __name__ == "__main__":
    print("\n🚀 启动 OKX WebSocket 登录测试...\n")
    
    # 运行异步测试
    asyncio.run(main())

