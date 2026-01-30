import gc
import psutil
import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any

class MemoryManager:
    @staticmethod
    def get_memory_usage() -> float:
        return psutil.virtual_memory().percent

    @staticmethod
    def get_memory_info() -> Dict[str, float]:
        mem = psutil.virtual_memory()
        return {
            'total_gb': mem.total/(1024**3),
            'available_gb': mem.available/(1024**3),
            'used_gb': mem.used/(1024**3),
            'percent': mem.percent,
            'free_gb': mem.free/(1024**3),
        }

    @staticmethod
    def force_gc() -> int:
        return gc.collect()

    @staticmethod
    def check_memory_threshold(threshold: float = 0.8) -> bool:
        return MemoryManager.get_memory_usage() > threshold * 100

class DataTypeOptimizer:
    @staticmethod
    def optimize_dtypes(df: pd.DataFrame, aggressive: bool = True) -> pd.DataFrame:
        out = df.copy()
        for c in out.columns:
            dt = out[c].dtype
            if dt == 'float64':
                out[c] = out[c].astype('float32')
            elif dt == 'int64':
                mn, mx = out[c].min(), out[c].max()
                if mn >= 0 and mx < 2**32:
                    out[c] = out[c].astype('uint32')
                elif -2**31 <= mn <= 2**31-1 and -2**31 <= mx <= 2**31-1:
                    out[c] = out[c].astype('int32')
            elif dt == 'object' and aggressive:
                if out[c].nunique() / max(len(out),1) < 0.5:
                    out[c] = out[c].astype('category')
        return out
