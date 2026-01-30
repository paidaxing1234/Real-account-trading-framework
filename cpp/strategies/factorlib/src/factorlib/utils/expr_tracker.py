"""
Expression Tracker - 自动追踪并打印因子表达式

Usage:
    from factorlib.utils.expr_tracker import Expr, tracked_ops

    # 方法1: 使用 Expr 包装列
    close = Expr('Close', df['Close'])
    high = Expr('High', df['High'])

    rolling_mean_3 = tracked_ops.ts_mean(close, 3)
    rolling_mean_60 = tracked_ops.ts_mean(close, 60)
    momentum = tracked_ops.divide(rolling_mean_3, rolling_mean_60) - 1
    factor = tracked_ops.clip(tracked_ops.ts_zscore(momentum, 1440), -3, 3)
    factor = tracked_ops.ts_ema(factor, 2)

    print(factor.formula)  # 输出: ts_ema(clip(ts_zscore((ts_mean(Close, 3) / ts_mean(Close, 60)) - 1, 1440), -3, 3), 2)
    df['factor'] = factor.data  # 获取实际数据

    # 方法2: 使用 build_factor 函数
    def my_factor(df, ops):
        close = ops.col(df, 'Close')
        ma3 = ops.ts_mean(close, 3)
        ma60 = ops.ts_mean(close, 60)
        momentum = ops.divide(ma3, ma60) - 1
        return ops.ts_ema(ops.clip(ops.ts_zscore(momentum, 1440), -3, 3), 2)

    factor, formula = build_factor(df, my_factor)
    print(f"Formula: {formula}")
"""

import numpy as np
import pandas as pd
from typing import Union, Optional, Callable
from .operators import ops


class Expr:
    """
    表达式追踪类 - 包装数据并自动记录表达式

    Attributes:
        formula: 表达式字符串
        data: 实际的 Series/ndarray 数据
    """

    def __init__(self, formula: str, data: Union[pd.Series, np.ndarray, float, int, 'Expr']):
        if isinstance(data, Expr):
            self.formula = data.formula
            self.data = data.data
        else:
            self.formula = formula
            self.data = data

    def __repr__(self):
        return f"Expr('{self.formula}')"

    def __str__(self):
        return self.formula

    # ==================== 算术运算符 ====================

    def __neg__(self):
        return Expr(f"-{self._wrap(self.formula)}", -self.data)

    def __add__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} + {other.formula})", self.data + other.data)
        return Expr(f"({self.formula} + {other})", self.data + other)

    def __radd__(self, other):
        return Expr(f"({other} + {self.formula})", other + self.data)

    def __sub__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} - {other.formula})", self.data - other.data)
        return Expr(f"({self.formula} - {other})", self.data - other)

    def __rsub__(self, other):
        return Expr(f"({other} - {self.formula})", other - self.data)

    def __mul__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} * {other.formula})", self.data * other.data)
        return Expr(f"({self.formula} * {other})", self.data * other)

    def __rmul__(self, other):
        return Expr(f"({other} * {self.formula})", other * self.data)

    def __truediv__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} / {other.formula})", self.data / other.data)
        return Expr(f"({self.formula} / {other})", self.data / other)

    def __rtruediv__(self, other):
        return Expr(f"({other} / {self.formula})", other / self.data)

    def __pow__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} ** {other.formula})", self.data ** other.data)
        return Expr(f"({self.formula} ** {other})", self.data ** other)

    def __abs__(self):
        return Expr(f"abs({self.formula})", abs(self.data))

    # ==================== 比较运算符 ====================

    def __gt__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} > {other.formula})", self.data > other.data)
        return Expr(f"({self.formula} > {other})", self.data > other)

    def __lt__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} < {other.formula})", self.data < other.data)
        return Expr(f"({self.formula} < {other})", self.data < other)

    def __ge__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} >= {other.formula})", self.data >= other.data)
        return Expr(f"({self.formula} >= {other})", self.data >= other)

    def __le__(self, other):
        if isinstance(other, Expr):
            return Expr(f"({self.formula} <= {other.formula})", self.data <= other.data)
        return Expr(f"({self.formula} <= {other})", self.data <= other)

    # ==================== 辅助方法 ====================

    def _wrap(self, s: str) -> str:
        """为复杂表达式添加括号"""
        if ' ' in s and not s.startswith('('):
            return f"({s})"
        return s

    def fillna(self, value=0):
        """填充 NaN 值"""
        if isinstance(self.data, pd.Series):
            return Expr(f"fillna({self.formula}, {value})", self.data.fillna(value))
        return Expr(f"fillna({self.formula}, {value})", np.nan_to_num(self.data, nan=value))

    def shift(self, periods: int):
        """移位"""
        if isinstance(self.data, pd.Series):
            return Expr(f"shift({self.formula}, {periods})", self.data.shift(periods))
        return Expr(f"shift({self.formula}, {periods})", np.roll(self.data, periods))


class TrackedOps:
    """
    追踪版本的 ops - 自动记录所有操作的表达式

    所有方法返回 Expr 对象，包含表达式字符串和实际数据
    """

    @staticmethod
    def _get_data(x):
        """提取实际数据"""
        return x.data if isinstance(x, Expr) else x

    @staticmethod
    def _get_formula(x):
        """提取表达式字符串"""
        if isinstance(x, Expr):
            return x.formula
        elif isinstance(x, pd.Series):
            return x.name if x.name else 'series'
        elif isinstance(x, (int, float)):
            return str(x)
        return 'data'

    # ==================== 列引用 ====================

    @staticmethod
    def col(df: pd.DataFrame, col_name: str) -> Expr:
        """创建一个追踪的列引用"""
        return Expr(col_name, df[col_name])

    # ==================== 基础数学 ====================

    @staticmethod
    def add(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} + {fy})", dx + dy)

    @staticmethod
    def subtract(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} - {fy})", dx - dy)

    @staticmethod
    def multiply(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} * {fy})", dx * dy)

    @staticmethod
    def divide(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} / {fy})", dx / dy)

    @staticmethod
    def power(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"power({fx}, {fy})", np.power(dx, dy))

    @staticmethod
    def abs_val(x) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"abs({f})", np.abs(d))

    @staticmethod
    def log(x) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"log({f})", np.log(d))

    @staticmethod
    def exp(x) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"exp({f})", np.exp(d))

    @staticmethod
    def sqrt(x) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"sqrt({f})", np.sqrt(d))

    @staticmethod
    def sign(x) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"sign({f})", np.sign(d))

    @staticmethod
    def abs(x) -> Expr:
        """绝对值（abs_val 的别名）"""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"abs({f})", np.abs(d))

    # ==================== 时间序列操作 ====================

    @staticmethod
    def delay(x, period: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"delay({f}, {period})", ops.delay(d, period))

    @staticmethod
    def delta(x, period: int = 1) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"delta({f}, {period})", ops.delta(d, period))

    @staticmethod
    def returns(x, period: int = 1) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"returns({f}, {period})", ops.returns(d, period))

    @staticmethod
    def ts_mean(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_mean({f}, {window})", ops.ts_mean(d, window))

    @staticmethod
    def ts_sum(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_sum({f}, {window})", ops.ts_sum(d, window))

    @staticmethod
    def ts_std(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_std({f}, {window})", ops.ts_std(d, window))

    @staticmethod
    def ts_var(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_var({f}, {window})", ops.ts_var(d, window))

    @staticmethod
    def ts_zscore(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_zscore({f}, {window})", ops.ts_zscore(d, window))

    @staticmethod
    def ts_rank(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_rank({f}, {window})", ops.ts_rank(d, window))

    @staticmethod
    def ts_skew(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_skew({f}, {window})", ops.ts_skew(d, window))

    @staticmethod
    def ts_kurt(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_kurt({f}, {window})", ops.ts_kurt(d, window))

    @staticmethod
    def ts_min(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_min({f}, {window})", ops.ts_min(d, window))

    @staticmethod
    def ts_max(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_max({f}, {window})", ops.ts_max(d, window))

    @staticmethod
    def ts_argmin(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_argmin({f}, {window})", ops.ts_argmin(d, window))

    @staticmethod
    def ts_argmax(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_argmax({f}, {window})", ops.ts_argmax(d, window))

    @staticmethod
    def ts_quantile(x, window: int, quantile: float) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_quantile({f}, {window}, {quantile})", ops.ts_quantile(d, window, quantile))

    @staticmethod
    def ts_median(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_median({f}, {window})", ops.ts_median(d, window))

    @staticmethod
    def ts_slope(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_slope({f}, {window})", ops.ts_slope(d, window))

    @staticmethod
    def decay_linear(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"decay_linear({f}, {window})", ops.decay_linear(d, window))

    @staticmethod
    def ts_ema(x, alpha: float) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_ema({f}, {alpha})", ops.ts_ema(d, alpha))

    @staticmethod
    def highday(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"highday({f}, {window})", ops.highday(d, window))

    @staticmethod
    def lowday(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"lowday({f}, {window})", ops.lowday(d, window))

    # ==================== 相关性和回归 ====================

    @staticmethod
    def correlation(x, y, window: int) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"correlation({fx}, {fy}, {window})", ops.correlation(dx, dy, window))

    @staticmethod
    def covariance(x, y, window: int) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"covariance({fx}, {fy}, {window})", ops.covariance(dx, dy, window))

    @staticmethod
    def beta(x, y, window: int) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"beta({fx}, {fy}, {window})", ops.beta(dx, dy, window))

    # ==================== 数据处理 ====================

    @staticmethod
    def clip(x, min_val: float, max_val: float) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"clip({f}, {min_val}, {max_val})", ops.clip(d, min_val, max_val))

    @staticmethod
    def filter_range(x, min_val: float, max_val: float) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"filter_range({f}, {min_val}, {max_val})", ops.filter_range(d, min_val, max_val))

    @staticmethod
    def winsorize(x, lower: float = 0.05, upper: float = 0.95) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"winsorize({f}, {lower}, {upper})", ops.winsorize(d, lower, upper))

    @staticmethod
    def fill_na(x, value_or_method: Union[float, int, str] = 0) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        if isinstance(value_or_method, (int, float)):
            return Expr(f"fill_na({f}, {value_or_method})", ops.fill_na(d, value_or_method))
        return Expr(f"fill_na({f}, '{value_or_method}')", ops.fill_na(d, value_or_method))

    @staticmethod
    def replace_inf(x) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"replace_inf({f})", ops.replace_inf(d))

    @staticmethod
    def forward_fill_signal(x, fill_length: int = 10) -> Expr:
        """前向填充非零信号"""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"forward_fill_signal({f}, {fill_length})", ops.forward_fill_signal(d, fill_length))

    @staticmethod
    def strategy_signal(x, threshold: float = 1.0) -> Expr:
        """生成策略信号 (-1/0/1)，并前向填充"""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"strategy_signal({f}, {threshold})", ops.strategy_signal(d, threshold))

    # ==================== 截面操作 (Cross-Sectional) ====================

    @staticmethod
    def cs_rank(x) -> Expr:
        """Cross-sectional rank [0, 1]."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_rank({f})", ops.cs_rank(d))

    @staticmethod
    def cs_zscore(x) -> Expr:
        """Cross-sectional z-score."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_zscore({f})", ops.cs_zscore(d))

    @staticmethod
    def cs_demean(x) -> Expr:
        """Cross-sectional demean."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_demean({f})", ops.cs_demean(d))

    @staticmethod
    def cs_scale(x) -> Expr:
        """Cross-sectional scale to sum(abs) = 1."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_scale({f})", ops.cs_scale(d))

    @staticmethod
    def cs_normalize(x) -> Expr:
        """Cross-sectional min-max normalization to [0, 1]."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_normalize({f})", ops.cs_normalize(d))

    @staticmethod
    def cs_rank_signed(x) -> Expr:
        """Cross-sectional rank mapped to [-1, 1]."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_rank_signed({f})", ops.cs_rank_signed(d))

    @staticmethod
    def cs_softmax(x, tau: float = 1.0) -> Expr:
        """Cross-sectional softmax weights."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_softmax({f}, {tau})", ops.cs_softmax(d, tau))

    @staticmethod
    def cs_long_short(x, n: int = None, pct: float = None) -> Expr:
        """Cross-sectional long-short position."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        if pct is not None:
            return Expr(f"cs_long_short({f}, pct={pct})", ops.cs_long_short(d, pct=pct))
        elif n is not None:
            return Expr(f"cs_long_short({f}, n={n})", ops.cs_long_short(d, n=n))
        return Expr(f"cs_long_short({f})", ops.cs_long_short(d))

    @staticmethod
    def cs_winsor(x, lower: float = 0.05, upper: float = 0.95) -> Expr:
        """Cross-sectional winsorization."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_winsor({f}, {lower}, {upper})", ops.cs_winsor(d, lower, upper))

    @staticmethod
    def cs_clip(x, n_std: float = 3.0) -> Expr:
        """Cross-sectional clipping based on std."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_clip({f}, {n_std})", ops.cs_clip(d, n_std))

    @staticmethod
    def cs_mean(x) -> Expr:
        """Cross-sectional mean."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_mean({f})", ops.cs_mean(d))

    @staticmethod
    def cs_std(x) -> Expr:
        """Cross-sectional std."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_std({f})", ops.cs_std(d))

    @staticmethod
    def cs_median(x) -> Expr:
        """Cross-sectional median."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_median({f})", ops.cs_median(d))

    @staticmethod
    def cs_max(x) -> Expr:
        """Cross-sectional max."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_max({f})", ops.cs_max(d))

    @staticmethod
    def cs_min(x) -> Expr:
        """Cross-sectional min."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_min({f})", ops.cs_min(d))

    @staticmethod
    def cs_quantile(x, q: float) -> Expr:
        """Cross-sectional quantile."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_quantile({f}, {q})", ops.cs_quantile(d, q))

    @staticmethod
    def cs_top_n_mask(x, n: int) -> Expr:
        """Cross-sectional top-N mask."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_top_n_mask({f}, {n})", ops.cs_top_n_mask(d, n))

    @staticmethod
    def cs_bottom_n_mask(x, n: int) -> Expr:
        """Cross-sectional bottom-N mask."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_bottom_n_mask({f}, {n})", ops.cs_bottom_n_mask(d, n))

    @staticmethod
    def cs_neutralize_mean(x) -> Expr:
        """Cross-sectional neutralization (same as cs_demean)."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"cs_neutralize_mean({f})", ops.cs_neutralize_mean(d))

    # ==================== 条件操作 ====================

    @staticmethod
    def condition(cond, x, y) -> Expr:
        fc = TrackedOps._get_formula(cond)
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dc = TrackedOps._get_data(cond)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"condition({fc}, {fx}, {fy})", ops.condition(dc, dx, dy))

    @staticmethod
    def greater(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} > {fy})", dx > dy)

    @staticmethod
    def less(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} < {fy})", dx < dy)

    @staticmethod
    def greater_equal(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} >= {fy})", dx >= dy)

    @staticmethod
    def less_equal(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} <= {fy})", dx <= dy)

    @staticmethod
    def equal(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} == {fy})", dx == dy)

    @staticmethod
    def and_(x, y) -> Expr:
        """逻辑与"""
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} & {fy})", dx & dy)

    @staticmethod
    def or_(x, y) -> Expr:
        """逻辑或"""
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"({fx} | {fy})", dx | dy)

    @staticmethod
    def not_(x) -> Expr:
        """逻辑非"""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"~{f}", ~d)

    @staticmethod
    def is_nan(x) -> Expr:
        """判断是否为 NaN"""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"is_nan({f})", np.isnan(d))

    @staticmethod
    def where(cond, x, y) -> Expr:
        """条件选择 (np.where 风格)"""
        fc = TrackedOps._get_formula(cond)
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dc = TrackedOps._get_data(cond)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"where({fc}, {fx}, {fy})", np.where(dc, dx, dy))

    @staticmethod
    def astype(x, dtype) -> Expr:
        """类型转换"""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        dtype_name = dtype.__name__ if hasattr(dtype, '__name__') else str(dtype)
        if isinstance(d, pd.Series):
            result = d.astype(dtype)
        else:
            result = np.asarray(d).astype(dtype)
        return Expr(f"astype({f}, {dtype_name})", result)

    # ==================== 高级时间序列 ====================

    @staticmethod
    def ts_realized_vol(ret, window: int) -> Expr:
        f, d = TrackedOps._get_formula(ret), TrackedOps._get_data(ret)
        return Expr(f"ts_realized_vol({f}, {window})", ops.ts_realized_vol(d, window))

    @staticmethod
    def ts_atr(high, low, close, window: int) -> Expr:
        fh, fl, fc = TrackedOps._get_formula(high), TrackedOps._get_formula(low), TrackedOps._get_formula(close)
        dh, dl, dc = TrackedOps._get_data(high), TrackedOps._get_data(low), TrackedOps._get_data(close)
        return Expr(f"ts_atr({fh}, {fl}, {fc}, {window})", ops.ts_atr(dh, dl, dc, window))

    @staticmethod
    def ts_crossover(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"ts_crossover({fx}, {fy})", ops.ts_crossover(dx, dy))

    @staticmethod
    def ts_crossunder(x, y) -> Expr:
        fx, fy = TrackedOps._get_formula(x), TrackedOps._get_formula(y)
        dx, dy = TrackedOps._get_data(x), TrackedOps._get_data(y)
        return Expr(f"ts_crossunder({fx}, {fy})", ops.ts_crossunder(dx, dy))

    @staticmethod
    def ts_minmax_norm(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_minmax_norm({f}, {window})", ops.ts_minmax_norm(d, window))

    @staticmethod
    def ts_rank_signed(x, window: int) -> Expr:
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"ts_rank_signed({f}, {window})", ops.ts_rank_signed(d, window))

    @staticmethod
    def rsi(x, window: int) -> Expr:
        """Relative Strength Index (RSI). Output range: [0, 100]."""
        f, d = TrackedOps._get_formula(x), TrackedOps._get_data(x)
        return Expr(f"rsi({f}, {window})", ops.rsi(d, window))


# 全局实例
tracked_ops = TrackedOps()


def build_factor(df: pd.DataFrame, factor_func: Callable[[pd.DataFrame, TrackedOps], Expr],
                 name: Optional[str] = None) -> tuple:
    """
    构建因子并自动获取表达式

    Args:
        df: 输入 DataFrame
        factor_func: 因子计算函数，签名为 (df, ops) -> Expr
        name: 可选的因子名称

    Returns:
        (data, formula): 因子数据和表达式字符串

    Example:
        def my_factor(df, ops):
            close = ops.col(df, 'Close')
            ma3 = ops.ts_mean(close, 3)
            ma60 = ops.ts_mean(close, 60)
            momentum = ops.divide(ma3, ma60) - 1
            return -ops.ts_ema(ops.clip(ops.ts_zscore(momentum, 1440), -3, 3), 2)

        data, formula = build_factor(df, my_factor)
        print(f"Formula: {formula}")
        # Output: Formula: -ts_ema(clip(ts_zscore(((ts_mean(Close, 3) / ts_mean(Close, 60)) - 1), 1440), -3, 3), 2)
    """
    result = factor_func(df, tracked_ops)

    if isinstance(result, Expr):
        return result.data, result.formula
    return result, str(result)


def print_factor_formula(expr: Expr, name: str = 'factor'):
    """
    打印因子表达式

    Args:
        expr: Expr 对象
        name: 因子名称
    """
    print(f"[{name}] Formula: {expr.formula}")


def compute_factor(
    data_dict: dict,
    factor_func: Callable[[pd.DataFrame, TrackedOps], Expr],
    name: str,
    verbose: bool = True
) -> str:
    """
    对多个 instrument 计算因子，并自动打印表达式

    Args:
        data_dict: Dict[str, DataFrame] - 多个 instrument 的数据
        factor_func: 因子计算函数，签名为 (df, ops) -> Expr
        name: 因子名称，会作为列名添加到 DataFrame
        verbose: 是否打印表达式

    Returns:
        formula: 因子表达式字符串

    Example:
        # 定义因子函数
        def my_factor(df, ops):
            close = ops.col(df, 'Close')
            ma3 = ops.ts_mean(close, 3)
            ma60 = ops.ts_mean(close, 60)
            momentum = ops.divide(ma3, ma60) - 1
            momentum = momentum.fillna(0)
            return -ops.ts_ema(ops.clip(ops.ts_zscore(momentum, 1440), -3, 3), 2)

        # 一行搞定：计算 + 打印表达式
        formula = compute_factor(data_dict, my_factor, 'momentum_factor')
    """
    formula = None

    for i, (inst, df) in enumerate(data_dict.items()):
        result = factor_func(df, tracked_ops)

        if isinstance(result, Expr):
            data_dict[inst][name] = result.data
            if i == 0:
                formula = result.formula
        else:
            data_dict[inst][name] = result
            if i == 0:
                formula = str(result)

    if verbose and formula:
        print(f"[{name}] Formula: {formula}")

    return formula


def compute_factor_single(
    df: pd.DataFrame,
    factor_func: Callable[[pd.DataFrame, TrackedOps], Expr],
    name: str,
    verbose: bool = True
) -> tuple:
    """
    对单个 DataFrame 计算因子，并自动打印表达式

    Args:
        df: 输入 DataFrame
        factor_func: 因子计算函数
        name: 因子名称
        verbose: 是否打印表达式

    Returns:
        (df, formula): 添加了因子列的 DataFrame 和表达式

    Example:
        def my_factor(df, ops):
            close = ops.col(df, 'Close')
            return ops.ts_zscore(close, 60)

        df, formula = compute_factor_single(df, my_factor, 'zscore_60')
    """
    result = factor_func(df, tracked_ops)

    if isinstance(result, Expr):
        df[name] = result.data
        formula = result.formula
    else:
        df[name] = result
        formula = str(result)

    if verbose:
        print(f"[{name}] Formula: {formula}")

    return df, formula


def compute_factor_panel(
    panel,
    factor_func: Callable,
    name: str,
    verbose: bool = True
) -> pd.DataFrame:
    """
    对 Panel Data（多资产）计算因子，支持 TS 和 CS 算子混合使用。

    Args:
        panel: PanelData 对象，或 Dict[str, DataFrame]（兼容旧格式）
        factor_func: 因子计算函数，签名为 (panel, ops) -> Expr
        name: 因子名称
        verbose: 是否打印表达式

    Returns:
        Panel DataFrame (rows=timestamps, cols=assets)

    Example:
        from factorlib.cli import load_panel_data

        # 加载数据
        panel = load_panel_data(['BTC-USDT-SWAP', 'ETH-USDT-SWAP'])

        # 定义因子（支持 TS + CS 算子混合）
        def my_factor(panel, ops):
            close = panel['Close']        # DataFrame (rows=time, cols=assets)
            ret = panel['return']         # DataFrame

            # TS 算子：对每列独立计算
            ts_zscore = ops.ts_zscore(ret, 60)

            # CS 算子：跨列计算（截面操作）
            cs_rank = ops.cs_rank(ts_zscore)

            return ops.ts_ema(cs_rank, 2)

        # 计算因子
        factor_panel = compute_factor_panel(panel, my_factor, 'cs_momentum')
        # factor_panel 是 DataFrame (rows=time, cols=assets)
    """
    # 兼容不同的输入格式
    # 1. PanelData 对象 -> 直接使用
    # 2. Dict[instrument -> DataFrame] -> 转换
    # 3. Dict[column -> DataFrame] -> 直接使用

    # 检查是否是 PanelData 对象
    if hasattr(panel, 'Close') and hasattr(panel, '__getitem__'):
        # PanelData 对象，直接使用
        panel_data = panel
    elif isinstance(panel, dict):
        sample_val = next(iter(panel.values()))
        if isinstance(sample_val, pd.DataFrame) and 'Close' in sample_val.columns:
            # data_dict 是 {instrument -> DataFrame}，需要转换
            all_columns = sample_val.columns.tolist()
            panel_data = {}
            for col in all_columns:
                col_dict = {}
                for inst, df in panel.items():
                    if col in df.columns:
                        col_dict[inst] = df[col]
                if col_dict:
                    panel_data[col] = pd.DataFrame(col_dict)
        else:
            # 已经是 {column -> panel DataFrame} 格式
            panel_data = panel
    else:
        raise ValueError("panel must be PanelData or Dict")

    # 计算因子
    result = factor_func(panel_data, tracked_ops)

    if isinstance(result, Expr):
        formula = result.formula
        factor_panel = result.data
    else:
        formula = str(result)
        factor_panel = result

    if verbose and formula:
        print(f"[{name}] Formula: {formula}")

    return factor_panel


def build_panel_data(data_dict: dict, columns: list = None) -> dict:
    """
    将 {instrument -> DataFrame} 转换为 {column -> Panel DataFrame}。

    Args:
        data_dict: Dict[instrument_name -> DataFrame]
        columns: 要提取的列（默认自动检测）

    Returns:
        Dict[column_name -> Panel DataFrame(rows=time, cols=assets)]

    Example:
        panel_data = build_panel_data(data_dict, ['Close', 'return', 'Volume'])
        # panel_data['Close'] 是一个 DataFrame，rows=时间, cols=资产
    """
    if not data_dict:
        return {}

    sample_df = next(iter(data_dict.values()))

    if columns is None:
        # 自动检测常用列
        candidate_cols = [
            'Close', 'Open', 'High', 'Low', 'Volume', 'return',
            'QuoteAssetVolume', 'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume',
        ]
        columns = [c for c in candidate_cols if c in sample_df.columns]

    panel_data = {}
    for col in columns:
        col_dict = {}
        for inst, df in data_dict.items():
            if col in df.columns:
                col_dict[inst] = df[col]
        if col_dict:
            panel_data[col] = pd.DataFrame(col_dict)

    return panel_data


__all__ = [
    'Expr',
    'TrackedOps',
    'tracked_ops',
    'build_factor',
    'print_factor_formula',
    'compute_factor',
    'compute_factor_single',
    # Panel Data support
    'compute_factor_panel',
    'build_panel_data',
]
