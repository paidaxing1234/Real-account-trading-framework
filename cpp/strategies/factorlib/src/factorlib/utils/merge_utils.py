"""
Merge-related utility functions for factorlib.
"""
from __future__ import annotations

import pathlib
import pandas as pd

from .time_utils import ceil_59999_to_next_minute

__all__ = ["prepare_tick_kline_merge"]


def set_time_index(df: pd.DataFrame, col: str = 'CloseTime') -> pd.DataFrame:
    """Set time column as index."""
    out = df.copy()
    if col in out.columns:
        out = out.set_index(col).sort_index()
    return out


def prepare_tick_kline_merge(
    tick_read_path: str,
    df_k: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Read aggregated 1-minute factors and align with K-line by time (inner join).

    Args:
    - tick_read_path: tick factor file path (parquet only)
    - df_k: loaded K-line DataFrame

    Returns:
    - merged DataFrame (inner joined by index), index is CloseTime (UTC)
    """
    # Read tick factors (parquet only)
    suffix = pathlib.Path(tick_read_path).suffix.lower()
    if suffix in (".parquet", ".pq"):
        df_tick = pd.read_parquet(tick_read_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix} (only parquet supported)")

    # Standardize tick CloseTime
    if "CloseTime" not in df_tick.columns:
        if "datetime" in df_tick.columns:
            dt_series = df_tick["datetime"]
            if pd.api.types.is_integer_dtype(dt_series) and dt_series.astype(str).str.len().median() >= 13:
                df_tick["CloseTime"] = pd.to_datetime(dt_series, unit="ms", utc=True)
            else:
                df_tick["CloseTime"] = pd.to_datetime(dt_series, utc=True, errors="coerce")
            df_tick = df_tick.drop(columns=["datetime"])
        else:
            raise ValueError("tick factor file missing CloseTime/datetime column")

    df_tick["CloseTime"] = pd.to_datetime(df_tick["CloseTime"], utc=True, errors="coerce")
    df_tick = df_tick.set_index("CloseTime").sort_index()

    # K-line must be provided
    if df_k is None:
        raise ValueError("df_k must be provided")
    k = df_k.copy()

    # Round up 59.999 seconds, then set index
    k = ceil_59999_to_next_minute(k, col="CloseTime")
    k = set_time_index(k, "CloseTime")

    # Merge by index (inner join)
    merged = pd.merge(df_tick, k, left_index=True, right_index=True, how='inner')

    return merged
