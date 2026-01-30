"""
Orderbook Operators - 盘口数据专用算子（极致性能优化版）

使用 Numba JIT + NumPy 向量化实现最高性能

Usage:
    from factorlib.utils.ops_orderbook import ops_ob

    spread = ops_ob.spread(panel, level=0)
    imbalance = ops_ob.imbalance(panel, levels=5)
"""

import numpy as np
import pandas as pd
from typing import Union, Optional
from numba import jit, prange


# ============================================================================
# Numba JIT 核心计算函数（最高性能）
# ============================================================================

@jit(nopython=True, cache=True, fastmath=True)
def _spread(ask_price: np.ndarray, bid_price: np.ndarray) -> np.ndarray:
    """价差"""
    return ask_price - bid_price


@jit(nopython=True, cache=True, fastmath=True)
def _mid_price(ask_price: np.ndarray, bid_price: np.ndarray) -> np.ndarray:
    """中间价"""
    return (ask_price + bid_price) * 0.5


@jit(nopython=True, cache=True, fastmath=True)
def _micro_price(
    ask_price: np.ndarray,
    bid_price: np.ndarray,
    ask_amount: np.ndarray,
    bid_amount: np.ndarray
) -> np.ndarray:
    """微观价格"""
    total = ask_amount + bid_amount
    return (bid_price * ask_amount + ask_price * bid_amount) / (total + 1e-12)


@jit(nopython=True, parallel=True, cache=True, fastmath=True)
def _imbalance_multi_level(
    bid_amounts: np.ndarray,  # shape: (n_rows, n_levels)
    ask_amounts: np.ndarray   # shape: (n_rows, n_levels)
) -> np.ndarray:
    """多档位买卖不平衡 - 并行计算"""
    n = bid_amounts.shape[0]
    out = np.empty(n, dtype=np.float64)

    for i in prange(n):
        bid_sum = 0.0
        ask_sum = 0.0
        for lvl in range(bid_amounts.shape[1]):
            bid_sum += bid_amounts[i, lvl]
            ask_sum += ask_amounts[i, lvl]
        total = bid_sum + ask_sum
        if total > 1e-12:
            out[i] = (bid_sum - ask_sum) / total
        else:
            out[i] = 0.0

    return out


@jit(nopython=True, parallel=True, cache=True, fastmath=True)
def _depth_multi_level(amounts: np.ndarray) -> np.ndarray:
    """多档位深度求和 - 并行计算"""
    n = amounts.shape[0]
    out = np.empty(n, dtype=np.float64)

    for i in prange(n):
        s = 0.0
        for lvl in range(amounts.shape[1]):
            s += amounts[i, lvl]
        out[i] = s

    return out


@jit(nopython=True, parallel=True, cache=True, fastmath=True)
def _depth_value_multi_level(
    prices: np.ndarray,   # shape: (n_rows, n_levels)
    amounts: np.ndarray   # shape: (n_rows, n_levels)
) -> np.ndarray:
    """多档位深度价值 = sum(price * amount)"""
    n = prices.shape[0]
    out = np.empty(n, dtype=np.float64)

    for i in prange(n):
        s = 0.0
        for lvl in range(prices.shape[1]):
            s += prices[i, lvl] * amounts[i, lvl]
        out[i] = s

    return out


@jit(nopython=True, parallel=True, cache=True, fastmath=True)
def _vwap_mid_multi_level(
    bid_prices: np.ndarray,
    bid_amounts: np.ndarray,
    ask_prices: np.ndarray,
    ask_amounts: np.ndarray
) -> np.ndarray:
    """VWAP中间价 - 并行计算"""
    n = bid_prices.shape[0]
    out = np.empty(n, dtype=np.float64)

    for i in prange(n):
        bid_value = 0.0
        bid_vol = 0.0
        ask_value = 0.0
        ask_vol = 0.0

        for lvl in range(bid_prices.shape[1]):
            bid_value += bid_prices[i, lvl] * bid_amounts[i, lvl]
            bid_vol += bid_amounts[i, lvl]
            ask_value += ask_prices[i, lvl] * ask_amounts[i, lvl]
            ask_vol += ask_amounts[i, lvl]

        if bid_vol > 1e-12 and ask_vol > 1e-12:
            vwap_bid = bid_value / bid_vol
            vwap_ask = ask_value / ask_vol
            out[i] = (vwap_bid + vwap_ask) * 0.5
        else:
            out[i] = np.nan

    return out


@jit(nopython=True, parallel=True, cache=True, fastmath=True)
def _ofi_multi_level(
    bid_prices: np.ndarray,
    bid_amounts: np.ndarray,
    ask_prices: np.ndarray,
    ask_amounts: np.ndarray
) -> np.ndarray:
    """
    Order Flow Imbalance - 并行计算

    OFI = sum(bid_change when bid_price >= prev) - sum(ask_change when ask_price <= prev)
    """
    n = bid_prices.shape[0]
    out = np.empty(n, dtype=np.float64)
    out[0] = 0.0

    for i in prange(1, n):
        ofi = 0.0
        for lvl in range(bid_prices.shape[1]):
            # Bid side
            if bid_prices[i, lvl] >= bid_prices[i-1, lvl]:
                ofi += bid_amounts[i, lvl] - bid_amounts[i-1, lvl]

            # Ask side
            if ask_prices[i, lvl] <= ask_prices[i-1, lvl]:
                ofi -= ask_amounts[i, lvl] - ask_amounts[i-1, lvl]

        out[i] = ofi

    return out


@jit(nopython=True, parallel=True, cache=True, fastmath=True)
def _book_skew(
    mid: np.ndarray,
    bid_prices: np.ndarray,
    bid_amounts: np.ndarray,
    ask_prices: np.ndarray,
    ask_amounts: np.ndarray
) -> np.ndarray:
    """订单簿偏度 - 距离加权"""
    n = bid_prices.shape[0]
    out = np.empty(n, dtype=np.float64)

    for i in prange(n):
        bid_w = 0.0
        ask_w = 0.0
        m = mid[i]

        for lvl in range(bid_prices.shape[1]):
            # Bid: 距离越近权重越大
            dist_bid = (m - bid_prices[i, lvl]) / (m + 1e-12)
            if dist_bid > 1e-12:
                bid_w += bid_amounts[i, lvl] / dist_bid

            # Ask
            dist_ask = (ask_prices[i, lvl] - m) / (m + 1e-12)
            if dist_ask > 1e-12:
                ask_w += ask_amounts[i, lvl] / dist_ask

        total = bid_w + ask_w
        if total > 1e-12:
            out[i] = (bid_w - ask_w) / total
        else:
            out[i] = 0.0

    return out


@jit(nopython=True, cache=True, fastmath=True)
def _pressure(bid_depth: np.ndarray, ask_depth: np.ndarray) -> np.ndarray:
    """买卖压力差 = log(bid) - log(ask)"""
    n = len(bid_depth)
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        out[i] = np.log(bid_depth[i] + 1.0) - np.log(ask_depth[i] + 1.0)
    return out


@jit(nopython=True, parallel=True, cache=True, fastmath=True)
def _imbalance_value_multi_level(
    bid_prices: np.ndarray,
    bid_amounts: np.ndarray,
    ask_prices: np.ndarray,
    ask_amounts: np.ndarray
) -> np.ndarray:
    """价值加权不平衡"""
    n = bid_prices.shape[0]
    out = np.empty(n, dtype=np.float64)

    for i in prange(n):
        bid_val = 0.0
        ask_val = 0.0

        for lvl in range(bid_prices.shape[1]):
            bid_val += bid_prices[i, lvl] * bid_amounts[i, lvl]
            ask_val += ask_prices[i, lvl] * ask_amounts[i, lvl]

        total = bid_val + ask_val
        if total > 1e-12:
            out[i] = (bid_val - ask_val) / total
        else:
            out[i] = 0.0

    return out


# ============================================================================
# 辅助函数
# ============================================================================

def _extract_levels(panel, side: str, levels: int, field: str) -> np.ndarray:
    """
    从 panel 提取多档位数据，返回 (n_rows, levels) 的数组

    Args:
        panel: PanelData
        side: 'bids' or 'asks'
        levels: 档位数
        field: 'price' or 'amount'
    """
    cols = [f'ob_{side}_{lvl}_{field}' for lvl in range(levels)]
    available = [c for c in cols if c in panel.columns]

    if not available:
        raise KeyError(f"Orderbook columns not found: {cols[0]}")

    # 取第一个资产的数据作为示例获取 shape
    sample_df = panel[available[0]]

    if isinstance(sample_df, pd.DataFrame):
        # Panel 格式: 每列是一个资产
        # 需要为每个资产分别处理
        # 这里返回 dict: asset -> (n_rows, levels) array
        result = {}
        for asset in sample_df.columns:
            data = np.column_stack([
                panel[c][asset].values if c in panel.columns
                else np.full(len(sample_df), np.nan)
                for c in cols
            ])
            result[asset] = data.astype(np.float64)
        return result
    else:
        # Series 格式
        data = np.column_stack([
            panel[c].values if c in panel.columns
            else np.full(len(sample_df), np.nan)
            for c in cols
        ])
        return data.astype(np.float64)


def _apply_to_panel(panel, func, *args, **kwargs) -> pd.DataFrame:
    """将计算应用到 panel 的每个资产"""
    sample = panel[panel.columns[0]]
    if isinstance(sample, pd.DataFrame):
        # Panel 格式
        assets = sample.columns
        index = sample.index
        results = {}
        for asset in assets:
            # 提取该资产的数据
            asset_args = []
            for arg in args:
                if isinstance(arg, dict):
                    asset_args.append(arg[asset])
                elif isinstance(arg, pd.DataFrame):
                    asset_args.append(arg[asset].values.astype(np.float64))
                elif isinstance(arg, np.ndarray):
                    asset_args.append(arg)
                else:
                    asset_args.append(arg)
            results[asset] = func(*asset_args, **kwargs)
        return pd.DataFrame(results, index=index)
    else:
        # 单资产
        arr_args = [a.values.astype(np.float64) if isinstance(a, (pd.Series, pd.DataFrame)) else a for a in args]
        result = func(*arr_args, **kwargs)
        return pd.Series(result, index=sample.index)


# ============================================================================
# Orderbook Operators Class
# ============================================================================

class ops_ob:
    """
    Orderbook 专用算子类 - 极致性能优化版

    所有方法使用 Numba JIT 加速，支持并行计算
    """

    # ========================= 基础指标 =========================

    @staticmethod
    def spread(panel, level: int = 0) -> pd.DataFrame:
        """价差 = ask - bid"""
        ask = panel[f'ob_asks_{level}_price']
        bid = panel[f'ob_bids_{level}_price']

        if isinstance(ask, pd.DataFrame):
            return ask - bid
        return pd.Series(_spread(ask.values, bid.values), index=ask.index)

    @staticmethod
    def spread_bps(panel, level: int = 0) -> pd.DataFrame:
        """价差（基点）= spread / mid * 10000"""
        spread = ops_ob.spread(panel, level)
        mid = ops_ob.mid_price(panel, level)
        return spread / mid * 10000

    @staticmethod
    def mid_price(panel, level: int = 0) -> pd.DataFrame:
        """中间价 = (ask + bid) / 2"""
        ask = panel[f'ob_asks_{level}_price']
        bid = panel[f'ob_bids_{level}_price']

        if isinstance(ask, pd.DataFrame):
            return (ask + bid) * 0.5
        return pd.Series(_mid_price(ask.values, bid.values), index=ask.index)

    @staticmethod
    def micro_price(panel) -> pd.DataFrame:
        """微观价格（量加权中间价）"""
        ask_p = panel['ob_asks_0_price']
        bid_p = panel['ob_bids_0_price']
        ask_a = panel['ob_asks_0_amount']
        bid_a = panel['ob_bids_0_amount']

        if isinstance(ask_p, pd.DataFrame):
            total = ask_a + bid_a
            return (bid_p * ask_a + ask_p * bid_a) / (total + 1e-12)

        result = _micro_price(
            ask_p.values.astype(np.float64),
            bid_p.values.astype(np.float64),
            ask_a.values.astype(np.float64),
            bid_a.values.astype(np.float64)
        )
        return pd.Series(result, index=ask_p.index)

    # ========================= 深度指标 =========================

    @staticmethod
    def depth(panel, side: str = 'bid', levels: int = 5) -> pd.DataFrame:
        """深度 = sum(amounts)"""
        side_name = 'bids' if side == 'bid' else 'asks'
        level_data = _extract_levels(panel, side_name, levels, 'amount')

        if isinstance(level_data, dict):
            # Panel 格式
            sample_col = f'ob_{side_name}_0_amount'
            index = panel[sample_col].index
            results = {asset: _depth_multi_level(data) for asset, data in level_data.items()}
            return pd.DataFrame(results, index=index)
        else:
            sample_col = f'ob_{side_name}_0_amount'
            return pd.Series(_depth_multi_level(level_data), index=panel[sample_col].index)

    @staticmethod
    def depth_value(panel, side: str = 'bid', levels: int = 5) -> pd.DataFrame:
        """深度价值 = sum(price * amount)"""
        side_name = 'bids' if side == 'bid' else 'asks'
        prices = _extract_levels(panel, side_name, levels, 'price')
        amounts = _extract_levels(panel, side_name, levels, 'amount')

        sample_col = f'ob_{side_name}_0_price'
        index = panel[sample_col].index

        if isinstance(prices, dict):
            results = {}
            for asset in prices:
                results[asset] = _depth_value_multi_level(prices[asset], amounts[asset])
            return pd.DataFrame(results, index=index)
        else:
            return pd.Series(_depth_value_multi_level(prices, amounts), index=index)

    # ========================= 不平衡指标 =========================

    @staticmethod
    def imbalance(panel, levels: int = 1) -> pd.DataFrame:
        """买卖不平衡 = (bid - ask) / (bid + ask)"""
        bid_data = _extract_levels(panel, 'bids', levels, 'amount')
        ask_data = _extract_levels(panel, 'asks', levels, 'amount')

        sample_col = 'ob_bids_0_amount'
        index = panel[sample_col].index

        if isinstance(bid_data, dict):
            results = {}
            for asset in bid_data:
                results[asset] = _imbalance_multi_level(bid_data[asset], ask_data[asset])
            return pd.DataFrame(results, index=index)
        else:
            return pd.Series(_imbalance_multi_level(bid_data, ask_data), index=index)

    @staticmethod
    def imbalance_value(panel, levels: int = 5) -> pd.DataFrame:
        """价值加权不平衡"""
        bid_prices = _extract_levels(panel, 'bids', levels, 'price')
        bid_amounts = _extract_levels(panel, 'bids', levels, 'amount')
        ask_prices = _extract_levels(panel, 'asks', levels, 'price')
        ask_amounts = _extract_levels(panel, 'asks', levels, 'amount')

        sample_col = 'ob_bids_0_price'
        index = panel[sample_col].index

        if isinstance(bid_prices, dict):
            results = {}
            for asset in bid_prices:
                results[asset] = _imbalance_value_multi_level(
                    bid_prices[asset], bid_amounts[asset],
                    ask_prices[asset], ask_amounts[asset]
                )
            return pd.DataFrame(results, index=index)
        else:
            return pd.Series(
                _imbalance_value_multi_level(bid_prices, bid_amounts, ask_prices, ask_amounts),
                index=index
            )

    @staticmethod
    def book_skew(panel, levels: int = 5) -> pd.DataFrame:
        """订单簿偏度（距离加权）"""
        mid = ops_ob.mid_price(panel, 0)
        bid_prices = _extract_levels(panel, 'bids', levels, 'price')
        bid_amounts = _extract_levels(panel, 'bids', levels, 'amount')
        ask_prices = _extract_levels(panel, 'asks', levels, 'price')
        ask_amounts = _extract_levels(panel, 'asks', levels, 'amount')

        if isinstance(bid_prices, dict):
            results = {}
            for asset in bid_prices:
                results[asset] = _book_skew(
                    mid[asset].values.astype(np.float64),
                    bid_prices[asset], bid_amounts[asset],
                    ask_prices[asset], ask_amounts[asset]
                )
            return pd.DataFrame(results, index=mid.index)
        else:
            return pd.Series(
                _book_skew(mid.values, bid_prices, bid_amounts, ask_prices, ask_amounts),
                index=mid.index
            )

    # ========================= VWAP =========================

    @staticmethod
    def vwap_mid(panel, levels: int = 5) -> pd.DataFrame:
        """VWAP 中间价"""
        bid_prices = _extract_levels(panel, 'bids', levels, 'price')
        bid_amounts = _extract_levels(panel, 'bids', levels, 'amount')
        ask_prices = _extract_levels(panel, 'asks', levels, 'price')
        ask_amounts = _extract_levels(panel, 'asks', levels, 'amount')

        sample_col = 'ob_bids_0_price'
        index = panel[sample_col].index

        if isinstance(bid_prices, dict):
            results = {}
            for asset in bid_prices:
                results[asset] = _vwap_mid_multi_level(
                    bid_prices[asset], bid_amounts[asset],
                    ask_prices[asset], ask_amounts[asset]
                )
            return pd.DataFrame(results, index=index)
        else:
            return pd.Series(
                _vwap_mid_multi_level(bid_prices, bid_amounts, ask_prices, ask_amounts),
                index=index
            )

    @staticmethod
    def vwap_spread(panel, levels: int = 5) -> pd.DataFrame:
        """VWAP 价差"""
        bid_value = ops_ob.depth_value(panel, 'bid', levels)
        bid_depth = ops_ob.depth(panel, 'bid', levels)
        ask_value = ops_ob.depth_value(panel, 'ask', levels)
        ask_depth = ops_ob.depth(panel, 'ask', levels)

        vwap_bid = bid_value / (bid_depth + 1e-12)
        vwap_ask = ask_value / (ask_depth + 1e-12)

        return vwap_ask - vwap_bid

    # ========================= 高级因子 =========================

    @staticmethod
    def ofi(panel, levels: int = 1) -> pd.DataFrame:
        """Order Flow Imbalance"""
        bid_prices = _extract_levels(panel, 'bids', levels, 'price')
        bid_amounts = _extract_levels(panel, 'bids', levels, 'amount')
        ask_prices = _extract_levels(panel, 'asks', levels, 'price')
        ask_amounts = _extract_levels(panel, 'asks', levels, 'amount')

        sample_col = 'ob_bids_0_price'
        index = panel[sample_col].index

        if isinstance(bid_prices, dict):
            results = {}
            for asset in bid_prices:
                results[asset] = _ofi_multi_level(
                    bid_prices[asset], bid_amounts[asset],
                    ask_prices[asset], ask_amounts[asset]
                )
            return pd.DataFrame(results, index=index)
        else:
            return pd.Series(
                _ofi_multi_level(bid_prices, bid_amounts, ask_prices, ask_amounts),
                index=index
            )

    @staticmethod
    def depth_ratio(panel, levels: int = 5) -> pd.DataFrame:
        """深度比率 = bid_depth / ask_depth"""
        bid = ops_ob.depth(panel, 'bid', levels)
        ask = ops_ob.depth(panel, 'ask', levels)
        return bid / (ask + 1e-12)

    @staticmethod
    def pressure(panel, levels: int = 5) -> pd.DataFrame:
        """买卖压力 = log(bid) - log(ask)"""
        bid = ops_ob.depth(panel, 'bid', levels)
        ask = ops_ob.depth(panel, 'ask', levels)

        if isinstance(bid, pd.DataFrame):
            return np.log(bid + 1) - np.log(ask + 1)

        return pd.Series(_pressure(bid.values, ask.values), index=bid.index)

    @staticmethod
    def depth_change(panel, side: str = 'bid', levels: int = 5, period: int = 1) -> pd.DataFrame:
        """深度变化"""
        depth = ops_ob.depth(panel, side, levels)
        return depth.diff(period)

    @staticmethod
    def depth_change_pct(panel, side: str = 'bid', levels: int = 5, period: int = 1) -> pd.DataFrame:
        """深度变化率"""
        depth = ops_ob.depth(panel, side, levels)
        return depth.pct_change(period)

    # ========================= 价格相关 =========================

    @staticmethod
    def quoted_spread(panel) -> pd.DataFrame:
        """报价价差 = ask_0 - bid_0"""
        return panel['ob_asks_0_price'] - panel['ob_bids_0_price']

    @staticmethod
    def relative_spread(panel) -> pd.DataFrame:
        """相对价差 = spread / mid"""
        spread = ops_ob.quoted_spread(panel)
        mid = ops_ob.mid_price(panel, 0)
        return spread / mid

    @staticmethod
    def price_impact_est(panel, levels: int = 5) -> pd.DataFrame:
        """价格冲击估计 (bps) = (vwap - mid) / mid * 10000"""
        mid = ops_ob.mid_price(panel, 0)
        vwap = ops_ob.vwap_mid(panel, levels)
        return (vwap - mid).abs() / mid * 10000

    # ========================= 组合因子 =========================

    @staticmethod
    def liquidity_score(panel, levels: int = 5, window: int = 60) -> pd.DataFrame:
        """流动性得分 = depth_norm / spread_norm"""
        spread_bps = ops_ob.spread_bps(panel, 0)
        depth = ops_ob.depth(panel, 'bid', levels) + ops_ob.depth(panel, 'ask', levels)

        spread_norm = spread_bps / spread_bps.rolling(window, min_periods=1).mean()
        depth_norm = depth / depth.rolling(window, min_periods=1).mean()

        return depth_norm / (spread_norm + 1e-8)

    @staticmethod
    def ob_momentum(panel, levels: int = 5, window: int = 10) -> pd.DataFrame:
        """订单簿动量 = imbalance.diff(window)"""
        imb = ops_ob.imbalance(panel, levels)
        return imb.diff(window)


# ============================================================================
# Export
# ============================================================================

__all__ = ['ops_ob']
