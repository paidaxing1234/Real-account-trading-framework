#!/usr/bin/env python3
"""
OKX 账户余额测试工具

测试指定账户的资金账户和交易账户余额

用法:
    python test_balance.py
"""

import hmac
import base64
import hashlib
import json
import time
from datetime import datetime, timezone
import requests

# ============================================================
# 账户配置（第二个账户 - 模拟盘）
# ============================================================

# API_KEY = "5c9c1eb1-3f0d-4d97-bda5-665828ebc194"
# SECRET_KEY = "B31368FDD1F52C4691A69E5C1C191E8F"
# PASSPHRASE = "Sequence2025.."
API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
PASSPHRASE = "Sequence2025."
IS_TESTNET = True  # 模拟盘

# ============================================================
# OKX API 签名
# ============================================================

def get_timestamp():
    """获取 ISO 格式时间戳"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def sign(timestamp: str, method: str, request_path: str, body: str = '') -> str:
    """生成 OKX API 签名"""
    message = timestamp + method + request_path + body
    mac = hmac.new(
        bytes(SECRET_KEY, encoding='utf-8'),
        bytes(message, encoding='utf-8'),
        digestmod=hashlib.sha256
    )
    return base64.b64encode(mac.digest()).decode()

def get_headers(method: str, request_path: str, body: str = '') -> dict:
    """生成请求头"""
    timestamp = get_timestamp()
    signature = sign(timestamp, method, request_path, body)
    
    headers = {
        'OK-ACCESS-KEY': API_KEY,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': PASSPHRASE,
        'Content-Type': 'application/json'
    }
    
    # 模拟盘需要添加此头
    if IS_TESTNET:
        headers['x-simulated-trading'] = '1'
    
    return headers

# ============================================================
# API 请求
# ============================================================

def get_base_url():
    """获取 API 基础 URL"""
    # OKX 模拟盘和实盘使用同一个 REST API 地址
    # 区别在于请求头中的 x-simulated-trading
    return "https://www.okx.com"

def get_funding_balance(ccy: str = ''):
    """
    获取资金账户余额
    GET /api/v5/asset/balances
    """
    request_path = '/api/v5/asset/balances'
    if ccy:
        request_path += f'?ccy={ccy}'
    
    url = get_base_url() + request_path
    headers = get_headers('GET', request_path)
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {'code': '-1', 'msg': str(e), 'data': []}

def get_trading_balance(ccy: str = ''):
    """
    获取交易账户余额
    GET /api/v5/account/balance
    """
    request_path = '/api/v5/account/balance'
    if ccy:
        request_path += f'?ccy={ccy}'
    
    url = get_base_url() + request_path
    headers = get_headers('GET', request_path)
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {'code': '-1', 'msg': str(e), 'data': []}

def get_account_config():
    """
    获取账户配置信息
    GET /api/v5/account/config
    """
    request_path = '/api/v5/account/config'
    
    url = get_base_url() + request_path
    headers = get_headers('GET', request_path)
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {'code': '-1', 'msg': str(e), 'data': []}

# ============================================================
# 主程序
# ============================================================

def main():
    print()
    print("=" * 60)
    print("  OKX 账户余额测试工具")
    print("=" * 60)
    print()
    print(f"API Key: {API_KEY[:12]}...{API_KEY[-4:]}")
    print(f"环境: {'模拟盘' if IS_TESTNET else '实盘'}")
    print()
    
    # 1. 获取账户配置
    print("-" * 60)
    print("1. 账户配置")
    print("-" * 60)
    config = get_account_config()
    if config.get('code') == '0' and config.get('data'):
        data = config['data'][0]
        print(f"  账户等级: {data.get('acctLv', 'N/A')}")
        print(f"  账户模式: {data.get('posMode', 'N/A')}")
        print(f"  UID: {data.get('uid', 'N/A')}")
        print(f"  账户类型: {data.get('ctIsoMode', 'N/A')}")
    else:
        print(f"  ❌ 获取失败: {config.get('msg', '未知错误')}")
    print()
    
    # 2. 获取资金账户余额
    print("-" * 60)
    print("2. 资金账户余额 (/api/v5/asset/balances)")
    print("-" * 60)
    funding = get_funding_balance()
    if funding.get('code') == '0':
        data = funding.get('data', [])
        if data:
            for item in data:
                ccy = item.get('ccy', '')
                bal = float(item.get('bal', '0'))
                avail = float(item.get('availBal', '0'))
                frozen = float(item.get('frozenBal', '0'))
                print(f"  {ccy}:")
                print(f"    总余额:   {bal:.8f}")
                print(f"    可用余额: {avail:.8f}")
                print(f"    冻结余额: {frozen:.8f}")
        else:
            print("  (无余额或余额为0)")
    else:
        print(f"  ❌ 获取失败: {funding.get('msg', '未知错误')}")
    print()
    
    # 3. 获取交易账户余额
    print("-" * 60)
    print("3. 交易账户余额 (/api/v5/account/balance)")
    print("-" * 60)
    trading = get_trading_balance()
    if trading.get('code') == '0':
        data = trading.get('data', [])
        if data:
            account_data = data[0]
            total_eq = float(account_data.get('totalEq', '0'))
            print(f"  总权益 (USD): {total_eq:.2f}")
            print()
            
            details = account_data.get('details', [])
            if details:
                print("  币种明细:")
                for item in details:
                    ccy = item.get('ccy', '')
                    eq = float(item.get('eq', '0'))
                    avail = float(item.get('availBal', '0'))
                    frozen = float(item.get('frozenBal', '0'))
                    if eq > 0 or avail > 0:
                        print(f"    {ccy}:")
                        print(f"      权益:   {eq:.8f}")
                        print(f"      可用:   {avail:.8f}")
                        print(f"      冻结:   {frozen:.8f}")
            else:
                print("  (无币种明细)")
        else:
            print("  (无数据)")
    else:
        print(f"  ❌ 获取失败: {trading.get('msg', '未知错误')}")
    print()
    
    print("=" * 60)
    print("  测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()

