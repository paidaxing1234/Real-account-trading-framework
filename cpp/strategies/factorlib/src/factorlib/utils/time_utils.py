"""
Time-related utility functions for factorlib.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "ceil_59999_to_next_minute",
    "to_datetime_utc",
    "to_datetime_utc_batch",
]


def to_datetime_utc(series: pd.Series) -> pd.Series:
    """
    将任意表示时间的 series 转为 UTC 的 pandas datetime64[ns] Series（去时区）。

    支持:
    - datetime64 类型
    - 数值型: 根据量级自动判定单位（>=1e12 视为毫秒，否则视为秒）
    - 字符串/对象: 优先尝试数值再解析

    返回: 无时区的 UTC datetime Series
    """
    s = series

    # 已是 datetime
    if np.issubdtype(s.dtype, np.datetime64):
        dt = pd.to_datetime(s, errors='coerce', utc=True)
        try:
            return dt.dt.tz_convert(None)
        except AttributeError:
            return dt.tz_convert(None)

    # 数值型（整型/浮点）
    if np.issubdtype(s.dtype, np.number):
        arr = s.to_numpy()
        if arr.size == 0:
            return pd.to_datetime(s, errors='coerce', utc=True)
        maxabs = np.nanmax(np.abs(arr))
        unit = 'ms' if (np.isfinite(maxabs) and maxabs >= 1e12) else 's'
        dt = pd.to_datetime(arr, unit=unit, utc=True)
        out = pd.Series(dt).dt.tz_convert(None)
        out.index = s.index
        return out

    # 字符串/其他对象 - 尝试数值解析
    numeric_try = pd.to_numeric(s, errors='coerce')
    if numeric_try.notna().any():
        arr = numeric_try.to_numpy()
        maxabs = np.nanmax(np.abs(arr[~np.isnan(arr)]))
        unit = 'ms' if (np.isfinite(maxabs) and maxabs >= 1e12) else 's'
        dt = pd.to_datetime(arr, unit=unit, utc=True)
        out = pd.Series(dt).dt.tz_convert(None)
        out.index = s.index
        return out

    # 直接解析字符串日期
    dt = pd.to_datetime(s, errors='coerce', utc=True)
    try:
        return dt.dt.tz_convert(None)
    except AttributeError:
        return dt


def to_datetime_utc_batch(df: pd.DataFrame, col: str = 'tradeTime') -> pd.Series:
    """
    批量转换 DataFrame 中的时间列为 UTC datetime。
    避免在循环中重复调用 to_datetime_utc。

    返回: 无时区的 UTC datetime Series
    """
    if col not in df.columns:
        raise KeyError(f"Column '{col}' not found in DataFrame")
    return to_datetime_utc(df[col])


def ceil_59999_to_next_minute(obj, col: str | None = "CloseTime"):
    """
    将 mm:59.999 的时间进位为下一分钟的 00.000。

    参数:
    - obj: pandas Series[datetime64] 或 DataFrame
    - col: 当 obj 是 DataFrame 时的列名，默认 'CloseTime'

    返回:
    - 与输入同类型的对象（Series 或 DataFrame）

    说明:
    - 支持 tz-naive 与 tz-aware（例如 UTC）时间，保持原有时区信息
    - 仅对毫秒部分为 999 且秒为 59 的条目生效
    """
    def _to_datetime(s: pd.Series) -> pd.Series:
        if not pd.api.types.is_datetime64_any_dtype(s):
            return pd.to_datetime(s, errors="coerce")
        return s

    def _fix_series(s: pd.Series) -> pd.Series:
        s = _to_datetime(s)
        remainder = s - s.dt.floor("S")
        ms = remainder.dt.components.milliseconds
        sec = s.dt.second
        mask = (sec == 59) & (ms == 999)
        if mask.any():
            s = s.copy()
            s.loc[mask] = s.loc[mask] + pd.to_timedelta(1, unit="ms")
        return s

    if isinstance(obj, pd.Series):
        return _fix_series(obj)
    elif isinstance(obj, pd.DataFrame):
        if col is None:
            raise ValueError("When passing a DataFrame, `col` must be provided.")
        out = obj.copy()
        out[col] = _fix_series(out[col])
        return out
    else:
        raise TypeError("obj must be a pandas Series or DataFrame")
