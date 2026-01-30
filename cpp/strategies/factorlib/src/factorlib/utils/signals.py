import numpy as np
import pandas as pd

__all__ = ['get_strategy_signal']

def get_strategy_signal(df_result: pd.DataFrame, factor_col: str, threshold: float = 1):
    """
    基于因子值生成仓位信号（-1/0/1），并前向填充。

    返回包含新列 f"{factor_col}_str" 的 DataFrame。
    """
    if factor_col not in df_result.columns:
        raise ValueError(f"缺少列: {factor_col}")

    df = df_result.copy()
    sig = df[factor_col].apply(lambda x: 1.0 if x >= threshold else (-1.0 if x <= -threshold else np.nan))
    sig = sig.ffill().fillna(0.0)
    df[f'{factor_col}_str'] = sig
    return df
