"""
Tick file I/O and normalization helpers.
- discover_tick_files: recursively find supported files
- load_tick: read a file and standardize to columns [price, size, tradeTime, is_buyer_maker, side, notional, CloseTime]
- extract_symbol: best-effort symbol extraction from file name
"""
from __future__ import annotations

import os
import re
from typing import List, Dict
import pandas as pd

__all__ = [
    "discover_tick_files",
    "load_tick",
    "extract_symbol",
]

_ALLOWED_EXT = {".csv", ".parquet"}
_SYMBOL_PATTERN = re.compile(r"([A-Za-z0-9_]+)")

# Column mapping (Binance aggTrades / OKX / generic)
COLUMN_ALIASES: Dict[str, str] = {
    # Generic
    'p':'price','v':'size',
    'qty':'size','quantity':'size','amount':'size','ts':'tradeTime','timestamp':'tradeTime',
    # Binance aggTrades
    'q':'size',
    'T':'tradeTime',
    'm':'is_buyer_maker',
    'a':'tradeId',
    'f':'firstTradeId',
    'l':'lastTradeId',
    # OKX tick
    'time':'tradeTime',
    'isBuyerMaker':'is_buyer_maker',
    'quoteQty':'quoteSize',
    'id':'tradeId',
    'isRPITrade':'is_rpi_trade'
}
REQUIRED = {"price", "size", "tradeTime"}

def discover_tick_files(root: str) -> List[str]:
    files: List[str] = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in _ALLOWED_EXT:
                files.append(os.path.join(dirpath, fn))
    return sorted(files)


def load_tick(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path)
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError("Unsupported ext " + ext)

    # Standardize column names
    rename_map: Dict[str, str] = {}
    for c in df.columns:
        if c in COLUMN_ALIASES:
            rename_map[c] = COLUMN_ALIASES[c]
    df = df.rename(columns=rename_map)

    # Normalize is_buyer_maker to 0/1
    if "is_buyer_maker" in df.columns:
        if pd.api.types.is_numeric_dtype(df["is_buyer_maker"]):
            df["is_buyer_maker"] = (df["is_buyer_maker"] != 0).astype("int8")
        else:
            mapped = (
                df["is_buyer_maker"].astype(str).str.strip().str.lower()
                .map({"true": 1, "t": 1, "1": 1, "false": 0, "f": 0, "0": 0})
            )
            df["is_buyer_maker"] = mapped.fillna(0).astype("int8")

    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns {missing} in {path}")

    # Convert time column to datetime
    if not pd.api.types.is_datetime64_any_dtype(df["tradeTime"]):
        if str(df["tradeTime"].dtype).startswith(("int", "uint", "float")):
            df["tradeTime"] = pd.to_datetime(df["tradeTime"], unit="ms", errors="coerce")
        else:
            df["tradeTime"] = pd.to_datetime(df["tradeTime"], errors="coerce")

    # Remove timezone if present
    if hasattr(df["tradeTime"].dtype, 'tz') and df["tradeTime"].dtype.tz is not None:
        df["tradeTime"] = df["tradeTime"].dt.tz_convert('UTC').dt.tz_localize(None)

    # Drop invalid rows
    df = df.dropna(subset=["tradeTime", "price", "size"]).copy()

    # Numeric types
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["size"] = pd.to_numeric(df["size"], errors="coerce")
    df = df[(df["price"] > 0) & (df["size"] > 0)]

    # Trade direction: is_buyer_maker=True => seller aggressive => -1
    if "is_buyer_maker" in df.columns and "side" not in df.columns:
        df["side"] = df["is_buyer_maker"].apply(lambda x: -1 if bool(x) else 1)
    elif "side" not in df.columns:
        df["side"] = 0

    # Minute bucket
    df["CloseTime"] = df["tradeTime"].dt.floor("T")

    # Notional
    if "notional" not in df.columns:
        df["notional"] = df["price"] * df["size"]

    return df


def extract_symbol(path: str) -> str:
    base = os.path.basename(path)
    m = _SYMBOL_PATTERN.search(base)
    sym = m.group(1).upper() if m else base.upper()
    return sym.replace("__", "_")
