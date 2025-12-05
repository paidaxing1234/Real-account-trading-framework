"""
OKX REST API 封装
实现交易、查询等API接口
"""

import hmac
import base64
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import requests


class OKXRestAPI:
    """
    OKX REST API 客户端
    
    功能：
    - 下单（限价、市价）
    - 撤单
    - 查询订单
    - 查询账户余额
    - 查询持仓
    
    文档：https://www.okx.com/docs-v5/zh/
    """
    
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        is_demo: bool = False
    ):
        """
        初始化OKX REST API客户端
        
        Args:
            api_key: API Key
            secret_key: Secret Key
            passphrase: API密码短语
            is_demo: 是否使用模拟盘
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_demo = is_demo
        
        # REST API基础URL
        if is_demo:
            self.base_url = "https://www.okx.com"  # 模拟盘也用主站API
        else:
            self.base_url = "https://www.okx.com"
        
        # 请求头模板
        self.headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self.api_key,
        }
    
    def _generate_signature(
        self,
        timestamp: str,
        method: str,
        request_path: str,
        body: str = ""
    ) -> str:
        """
        生成签名
        
        REST API签名算法：
        1. 拼接: timestamp + method + requestPath + body
        2. HMAC SHA256 加密
        3. Base64 编码
        
        Args:
            timestamp: ISO格式时间戳
            method: HTTP方法（GET/POST）
            request_path: 请求路径（如 /api/v5/trade/order）
            body: 请求体（JSON字符串）
        
        Returns:
            Base64编码的签名
        """
        # 拼接待签名字符串
        message = timestamp + method + request_path + body
        
        # HMAC SHA256 加密
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf8'),
            digestmod='sha256'
        )
        
        # Base64 编码
        signature = base64.b64encode(mac.digest()).decode()
        
        return signature
    
    def _get_timestamp(self) -> str:
        """
        获取ISO格式的时间戳
        
        Returns:
            ISO格式时间戳，如 2024-12-04T10:30:00.123Z
        """
        return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    def _request(
        self,
        method: str,
        request_path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送HTTP请求
        
        Args:
            method: HTTP方法（GET/POST）
            request_path: 请求路径
            params: URL参数
            body: 请求体
        
        Returns:
            响应JSON
        """
        # 生成时间戳
        timestamp = self._get_timestamp()
        
        # 准备请求路径（GET请求需要包含query参数）
        sign_path = request_path
        if method == "GET" and params:
            # 构造query string (不需要排序，使用原始顺序)
            query_string = urlencode(params)
            sign_path = f"{request_path}?{query_string}"
        
        # 准备请求体
        body_str = ""
        if body:
            body_str = json.dumps(body)
        
        # 生成签名（GET请求需要包含完整路径+参数）
        signature = self._generate_signature(timestamp, method, sign_path, body_str)
        
        # 准备请求头
        headers = self.headers.copy()
        headers.update({
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
        })
        
        # 模拟盘需要额外的header
        if self.is_demo:
            headers["x-simulated-trading"] = "1"
        
        # 完整URL
        url = self.base_url + request_path
        
        # 发送请求
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=body, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # 解析响应
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
    
    # ==================== 交易接口 ====================
    
    def place_batch_orders(
        self,
        orders: list[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量下单
        
        每次最多可以批量提交20个新订单
        
        Args:
            orders: 订单列表，每个订单包含：
                - inst_id: 产品ID
                - td_mode: 交易模式
                - side: 订单方向
                - ord_type: 订单类型
                - sz: 委托数量
                - px: 委托价格（限价单必填）
                - 其他可选参数
        
        Returns:
            响应数据
            {
                "code": "0",
                "msg": "",
                "data": [{
                    "ordId": "12345689",
                    "clOrdId": "oktswap6",
                    "sCode": "0",
                    "sMsg": ""
                }, ...]
            }
        
        Example:
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
                    "px": "3000",
                    "sz": "0.1"
                }
            ]
            response = client.place_batch_orders(orders)
        """
        if not orders or len(orders) > 20:
            raise ValueError("Orders list must contain 1-20 orders")
        
        return self._request("POST", "/api/v5/trade/batch-orders", body=orders)
    
    def place_order(
        self,
        inst_id: str,
        td_mode: str,
        side: str,
        ord_type: str,
        sz: str,
        px: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
        tag: Optional[str] = None,
        pos_side: Optional[str] = None,
        reduce_only: Optional[bool] = None,
        tgt_ccy: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        下单
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            td_mode: 交易模式
                - cash: 现货（非保证金）
                - isolated: 逐仓保证金
                - cross: 全仓保证金
            side: 订单方向
                - buy: 买入
                - sell: 卖出
            ord_type: 订单类型
                - market: 市价单
                - limit: 限价单
                - post_only: 只做maker
                - fok: 全部成交或立即取消
                - ioc: 立即成交并取消剩余
            sz: 委托数量
            px: 委托价格（限价单必填）
            cl_ord_id: 客户自定义订单ID
            tag: 订单标签
            pos_side: 持仓方向（开平仓模式下必填：long/short）
            reduce_only: 是否只减仓
            tgt_ccy: 市价单数量单位（base_ccy/quote_ccy）
            **kwargs: 其他参数
        
        Returns:
            响应数据
            {
                "code": "0",
                "msg": "",
                "data": [{
                    "ordId": "12345689",
                    "clOrdId": "oktswap6",
                    "tag": "",
                    "ts": "1695190491421",
                    "sCode": "0",
                    "sMsg": ""
                }]
            }
        """
        # 构造请求体
        body = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz,
        }
        
        # 可选参数
        if px is not None:
            body["px"] = px
        if cl_ord_id is not None:
            body["clOrdId"] = cl_ord_id
        if tag is not None:
            body["tag"] = tag
        if pos_side is not None:
            body["posSide"] = pos_side
        if reduce_only is not None:
            body["reduceOnly"] = reduce_only
        if tgt_ccy is not None:
            body["tgtCcy"] = tgt_ccy
        
        # 添加其他参数
        body.update(kwargs)
        
        # 发送请求
        return self._request("POST", "/api/v5/trade/order", body=body)
    
    def cancel_order(
        self,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        撤单
        
        Args:
            inst_id: 产品ID
            ord_id: 订单ID（ordId和clOrdId必须填一个）
            cl_ord_id: 客户自定义订单ID
        
        Returns:
            响应数据
        """
        body = {"instId": inst_id}
        
        if ord_id:
            body["ordId"] = ord_id
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
        
        return self._request("POST", "/api/v5/trade/cancel-order", body=body)
    
    def cancel_batch_orders(
        self,
        orders: list[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        批量撤单
        
        每次最多可以撤销20个订单
        
        Args:
            orders: 订单列表，每个订单包含：
                - inst_id: 产品ID
                - ord_id: 订单ID（ordId和clOrdId必须填一个）
                - cl_ord_id: 客户自定义订单ID
        
        Returns:
            响应数据
        
        Example:
            orders = [
                {"instId": "BTC-USDT", "ordId": "123456"},
                {"instId": "ETH-USDT", "ordId": "789012"}
            ]
            response = client.cancel_batch_orders(orders)
        """
        if not orders or len(orders) > 20:
            raise ValueError("Orders list must contain 1-20 orders")
        
        return self._request("POST", "/api/v5/trade/cancel-batch-orders", body=orders)
    
    def amend_order(
        self,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
        new_sz: Optional[str] = None,
        new_px: Optional[str] = None,
        cxl_on_fail: Optional[bool] = None,
        req_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        修改订单
        
        修改当前未成交的挂单
        
        Args:
            inst_id: 产品ID
            ord_id: 订单ID（ordId和clOrdId必须填一个）
            cl_ord_id: 客户自定义订单ID
            new_sz: 修改的新数量（包含已成交数量）
            new_px: 修改后的新价格
            cxl_on_fail: 修改失败时是否自动撤单
            req_id: 用户自定义修改事件ID
            **kwargs: 其他参数
        
        Returns:
            响应数据
        
        Example:
            # 修改价格
            response = client.amend_order(
                inst_id="BTC-USDT",
                ord_id="123456",
                new_px="50100"
            )
            
            # 修改数量
            response = client.amend_order(
                inst_id="BTC-USDT",
                ord_id="123456",
                new_sz="0.02"
            )
        """
        body = {"instId": inst_id}
        
        if ord_id:
            body["ordId"] = ord_id
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
        if new_sz:
            body["newSz"] = new_sz
        if new_px:
            body["newPx"] = new_px
        if cxl_on_fail is not None:
            body["cxlOnFail"] = cxl_on_fail
        if req_id:
            body["reqId"] = req_id
        
        # 添加其他参数
        body.update(kwargs)
        
        return self._request("POST", "/api/v5/trade/amend-order", body=body)
    
    def amend_batch_orders(
        self,
        orders: list[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量修改订单
        
        一次最多可批量修改20个订单
        
        Args:
            orders: 订单列表，每个订单包含：
                - inst_id: 产品ID
                - ord_id: 订单ID（ordId和clOrdId必须填一个）
                - cl_ord_id: 客户自定义订单ID
                - new_sz: 修改的新数量
                - new_px: 修改后的新价格
                - 其他可选参数
        
        Returns:
            响应数据
        
        Example:
            orders = [
                {
                    "instId": "BTC-USDT",
                    "ordId": "123456",
                    "newPx": "50100"
                },
                {
                    "instId": "ETH-USDT",
                    "ordId": "789012",
                    "newSz": "0.2"
                }
            ]
            response = client.amend_batch_orders(orders)
        """
        if not orders or len(orders) > 20:
            raise ValueError("Orders list must contain 1-20 orders")
        
        return self._request("POST", "/api/v5/trade/amend-batch-orders", body=orders)
    
    def get_order(
        self,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询订单
        
        Args:
            inst_id: 产品ID
            ord_id: 订单ID
            cl_ord_id: 客户自定义订单ID
        
        Returns:
            订单详情
        """
        params = {"instId": inst_id}
        
        if ord_id:
            params["ordId"] = ord_id
        if cl_ord_id:
            params["clOrdId"] = cl_ord_id
        
        return self._request("GET", "/api/v5/trade/order", params=params)
    
    def get_orders_pending(
        self,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
        ord_type: Optional[str] = None,
        state: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        limit: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        查询未成交订单列表
        
        获取当前账户下所有未成交订单信息
        
        Args:
            inst_type: 产品类型（SPOT/SWAP/FUTURES/OPTION）
            inst_id: 产品ID
            ord_type: 订单类型（market/limit/post_only/fok/ioc等，多个用逗号分隔）
            state: 订单状态（live/partially_filled）
            after: 请求此ID之前（更旧的数据）的分页内容
            before: 请求此ID之后（更新的数据）的分页内容
            limit: 返回结果的数量，最大为100，默认100条
            **kwargs: 其他参数（inst_family等）
        
        Returns:
            未成交订单列表
            
        Example:
            # 查询所有未成交订单
            response = client.get_orders_pending()
            
            # 查询BTC-USDT的未成交限价单
            response = client.get_orders_pending(
                inst_id="BTC-USDT",
                ord_type="limit"
            )
        """
        params = {}
        if inst_type:
            params["instType"] = inst_type
        if inst_id:
            params["instId"] = inst_id
        if ord_type:
            params["ordType"] = ord_type
        if state:
            params["state"] = state
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = limit
        
        # 添加其他参数
        params.update(kwargs)
        
        return self._request("GET", "/api/v5/trade/orders-pending", params=params)
    
    def get_orders_history(
        self,
        inst_type: str,
        inst_id: Optional[str] = None,
        ord_type: Optional[str] = None,
        state: Optional[str] = None,
        category: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        begin: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        获取历史订单记录（近七天）
        
        获取最近7天挂单，且完成的订单数据，包括7天以前挂单，但近7天才成交的订单数据。
        按照订单创建时间倒序排序。已经撤销的未成交单只保留2小时。
        
        Args:
            inst_type: 产品类型（SPOT/SWAP/FUTURES/OPTION）- 必填
            inst_id: 产品ID
            ord_type: 订单类型（market/limit/post_only/fok/ioc等，多个用逗号分隔）
            state: 订单状态（canceled/filled/mmp_canceled）
            category: 订单种类（twap/adl/full_liquidation/partial_liquidation/delivery/ddh）
            after: 请求此ID之前（更旧的数据）的分页内容
            before: 请求此ID之后（更新的数据）的分页内容
            begin: 筛选的开始时间戳，Unix时间戳毫秒数
            end: 筛选的结束时间戳，Unix时间戳毫秒数
            limit: 返回结果的数量，最大为100，默认100条
            **kwargs: 其他参数（inst_family等）
        
        Returns:
            历史订单列表
            
        Example:
            # 查询币币历史订单（7天内）
            response = client.get_orders_history(inst_type="SPOT")
            
            # 查询BTC-USDT已完成的订单
            response = client.get_orders_history(
                inst_type="SPOT",
                inst_id="BTC-USDT",
                state="filled"
            )
            
            # 查询指定时间范围的订单
            response = client.get_orders_history(
                inst_type="SPOT",
                begin="1597026383085",
                end="1597027383085"
            )
        """
        params = {"instType": inst_type}
        
        if inst_id:
            params["instId"] = inst_id
        if ord_type:
            params["ordType"] = ord_type
        if state:
            params["state"] = state
        if category:
            params["category"] = category
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if begin:
            params["begin"] = begin
        if end:
            params["end"] = end
        if limit:
            params["limit"] = limit
        
        # 添加其他参数
        params.update(kwargs)
        
        return self._request("GET", "/api/v5/trade/orders-history", params=params)
    
    # ==================== 账户接口 ====================
    
    def get_balance(self, ccy: Optional[str] = None) -> Dict[str, Any]:
        """
        查询账户余额
        
        Args:
            ccy: 币种，如 BTC
        
        Returns:
            账户余额
        """
        params = {}
        if ccy:
            params["ccy"] = ccy
        
        return self._request("GET", "/api/v5/account/balance", params=params)
    
    def get_positions(
        self,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
        pos_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询持仓信息
        
        获取该账户下拥有实际持仓的信息。账户为买卖模式会显示净持仓(net)，
        账户为开平仓模式下会分别返回开多(long)或开空(short)的仓位。
        
        Args:
            inst_type: 产品类型（MARGIN/SWAP/FUTURES/OPTION）
            inst_id: 产品ID，支持多个（不超过10个），半角逗号分隔
            pos_id: 持仓ID，支持多个（不超过20个）
        
        Returns:
            持仓信息
        """
        params = {}
        if inst_type:
            params["instType"] = inst_type
        if inst_id:
            params["instId"] = inst_id
        if pos_id:
            params["posId"] = pos_id
        
        return self._request("GET", "/api/v5/account/positions", params=params)
    
    def get_positions_history(
        self,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
        mgn_mode: Optional[str] = None,
        type: Optional[str] = None,
        pos_id: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        limit: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询历史持仓信息
        
        获取最近3个月有更新的仓位信息，按照仓位更新时间倒序排列。
        
        Args:
            inst_type: 产品类型（MARGIN/SWAP/FUTURES/OPTION）
            inst_id: 产品ID
            mgn_mode: 保证金模式（cross:全仓, isolated:逐仓）
            type: 最近一次平仓的类型
                  1:部分平仓, 2:完全平仓, 3:强平, 4:强减, 
                  5:ADL自动减仓-未完全平仓, 6:ADL自动减仓-完全平仓
            pos_id: 持仓ID
            after: 查询仓位更新(uTime)之前的内容，时间戳(毫秒)
            before: 查询仓位更新(uTime)之后的内容，时间戳(毫秒)
            limit: 分页返回结果的数量，最大100，默认100
        
        Returns:
            历史持仓信息
        """
        params = {}
        if inst_type:
            params["instType"] = inst_type
        if inst_id:
            params["instId"] = inst_id
        if mgn_mode:
            params["mgnMode"] = mgn_mode
        if type:
            params["type"] = type
        if pos_id:
            params["posId"] = pos_id
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = limit
        
        return self._request("GET", "/api/v5/account/positions-history", params=params)
    
    def get_account_instruments(
        self,
        inst_type: str,
        inst_family: Optional[str] = None,
        inst_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取交易产品基础信息（账户维度）
        
        获取当前账户可交易产品的信息列表
        
        Args:
            inst_type: 产品类型（SPOT/MARGIN/SWAP/FUTURES/OPTION）- 必填
            inst_family: 交易品种（仅适用于交割/永续/期权，期权必填）
            inst_id: 产品ID
        
        Returns:
            账户可交易产品信息
            
        Example:
            # 查询现货产品
            response = client.get_account_instruments(inst_type="SPOT")
            
            # 查询特定产品
            response = client.get_account_instruments(
                inst_type="SPOT",
                inst_id="BTC-USDT"
            )
        """
        params = {"instType": inst_type}
        
        if inst_family:
            params["instFamily"] = inst_family
        if inst_id:
            params["instId"] = inst_id
        
        return self._request("GET", "/api/v5/account/instruments", params=params)
    
    def get_bills(
        self,
        inst_type: Optional[str] = None,
        ccy: Optional[str] = None,
        mgn_mode: Optional[str] = None,
        ct_type: Optional[str] = None,
        type: Optional[str] = None,
        sub_type: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        begin: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        账单流水查询（近七天）
        
        获取最近7天的账单数据
        
        Args:
            inst_type: 产品类型（SPOT/MARGIN/SWAP/FUTURES/OPTION）
            ccy: 账单币种
            mgn_mode: 仓位类型（isolated:逐仓, cross:全仓）
            ct_type: 合约类型（linear:正向合约, inverse:反向合约）
            type: 账单类型（1-34，如1:划转, 2:交易, 3:交割等）
            sub_type: 账单子类型（详见文档）
            after: 请求此id之前（更旧的数据）的分页内容
            before: 请求此id之后（更新的数据）的分页内容
            begin: 筛选的开始时间戳，Unix时间戳毫秒数
            end: 筛选的结束时间戳，Unix时间戳毫秒数
            limit: 分页返回数量，最大100，默认100
            **kwargs: 其他参数（inst_id等）
        
        Returns:
            账单流水数据
            
        Example:
            # 查询所有账单
            response = client.get_bills()
            
            # 查询USDT账单
            response = client.get_bills(ccy="USDT", limit="50")
            
            # 查询交易类账单
            response = client.get_bills(type="2", limit="20")
            
            # 查询指定时间范围
            response = client.get_bills(
                begin="1597026383085",
                end="1597027383085"
            )
        """
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if ccy:
            params["ccy"] = ccy
        if mgn_mode:
            params["mgnMode"] = mgn_mode
        if ct_type:
            params["ctType"] = ct_type
        if type:
            params["type"] = type
        if sub_type:
            params["subType"] = sub_type
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if begin:
            params["begin"] = begin
        if end:
            params["end"] = end
        if limit:
            params["limit"] = limit
        
        # 添加其他参数
        params.update(kwargs)
        
        return self._request("GET", "/api/v5/account/bills", params=params)
    
    def get_bills_archive(
        self,
        inst_type: Optional[str] = None,
        ccy: Optional[str] = None,
        mgn_mode: Optional[str] = None,
        ct_type: Optional[str] = None,
        type: Optional[str] = None,
        sub_type: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        begin: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        账单流水查询（近三个月）
        
        获取最近3个月的账单数据
        
        Args:
            inst_type: 产品类型（SPOT/MARGIN/SWAP/FUTURES/OPTION）
            ccy: 账单币种
            mgn_mode: 仓位类型（isolated:逐仓, cross:全仓）
            ct_type: 合约类型（linear:正向合约, inverse:反向合约）
            type: 账单类型（1-34）
            sub_type: 账单子类型
            after: 请求此id之前（更旧的数据）的分页内容
            before: 请求此id之后（更新的数据）的分页内容
            begin: 筛选的开始时间戳，Unix时间戳毫秒数
            end: 筛选的结束时间戳，Unix时间戳毫秒数
            limit: 分页返回数量，最大100，默认100
            **kwargs: 其他参数（inst_id等）
        
        Returns:
            历史账单流水数据
            
        Example:
            # 查询所有历史账单
            response = client.get_bills_archive()
            
            # 查询现货交易账单
            response = client.get_bills_archive(
                inst_type="SPOT",
                type="2",
                limit="50"
            )
        """
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if ccy:
            params["ccy"] = ccy
        if mgn_mode:
            params["mgnMode"] = mgn_mode
        if ct_type:
            params["ctType"] = ct_type
        if type:
            params["type"] = type
        if sub_type:
            params["subType"] = sub_type
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if begin:
            params["begin"] = begin
        if end:
            params["end"] = end
        if limit:
            params["limit"] = limit
        
        # 添加其他参数
        params.update(kwargs)
        
        return self._request("GET", "/api/v5/account/bills-archive", params=params)
    
    # ==================== 市场数据接口 ====================
    
    def get_ticker(self, inst_id: str) -> Dict[str, Any]:
        """
        获取行情数据
        
        Args:
            inst_id: 产品ID
        
        Returns:
            行情数据
        """
        params = {"instId": inst_id}
        return self._request("GET", "/api/v5/market/ticker", params=params)
    
    def get_instruments(
        self,
        inst_type: str,
        inst_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取交易产品基础信息
        
        Args:
            inst_type: 产品类型（SPOT/SWAP/FUTURES/OPTION）
            inst_id: 产品ID
        
        Returns:
            产品信息
        """
        params = {"instType": inst_type}
        if inst_id:
            params["instId"] = inst_id
        
        return self._request("GET", "/api/v5/public/instruments", params=params)


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    # 测试配置
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    # 创建客户端（模拟盘）
    client = OKXRestAPI(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        is_demo=True
    )
    
    print("=" * 60)
    print("OKX REST API 测试")
    print("=" * 60)
    
    # 测试1: 获取BTC-USDT行情
    print("\n1️⃣ 获取BTC-USDT行情...")
    try:
        ticker = client.get_ticker("BTC-USDT")
        if ticker['code'] == '0':
            print("✅ 成功！")
            data = ticker['data'][0]
            print(f"   最新价: {data['last']}")
            print(f"   买一价: {data['bidPx']}")
            print(f"   卖一价: {data['askPx']}")
        else:
            print(f"❌ 失败: {ticker['msg']}")
    except Exception as e:
        print(f"❌ 异常: {e}")
    
    # 测试2: 查询账户余额
    print("\n2️⃣ 查询账户余额...")
    try:
        balance = client.get_balance()
        if balance['code'] == '0':
            print("✅ 成功！")
            print(f"   响应: {json.dumps(balance, indent=2)}")
        else:
            print(f"❌ 失败: {balance['msg']}")
    except Exception as e:
        print(f"❌ 异常: {e}")
    
    print("\n" + "=" * 60)

