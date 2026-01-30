import pandas as pd
from typing import Dict, Optional
import matplotlib.pyplot as plt
import numpy as np
from .numba_operators import smart_sampling, fast_big_data_stats, fast_rolling_stats
from .config.settings import VISUALIZATION_CONFIG

class FactorVisualizer:
    def __init__(self, config: Dict = None):
        self.config = config or VISUALIZATION_CONFIG
        plt.rcParams['figure.figsize'] = self.config.get('figure_size', (15,10))
        plt.rcParams['figure.dpi'] = self.config.get('dpi', 100)

    def plot_factor_analysis(self, df: pd.DataFrame, factor_col: str = 'factor_value') -> Dict:
        vals = df[factor_col].values.astype(np.float32)
        sampled, idx = smart_sampling(vals, self.config.get('max_plot_points', 10000))
        fig, axes = plt.subplots(2,2, figsize=self.config.get('figure_size', (15,10)))
        if 'datetime' in df.columns:
            axes[0,0].plot(df['datetime'].iloc[idx], sampled, lw=1)
        else:
            axes[0,0].plot(idx, sampled, lw=1)
        axes[0,1].hist(vals, bins=100)
        box_data = sampled if len(vals) > 50000 else vals
        axes[1,0].boxplot(box_data)
        qs = np.percentile(vals, [1,5,10,25,50,75,90,95,99])
        axes[1,1].bar(['1%','5%','10%','25%','50%','75%','90%','95%','99%'], qs)
        plt.tight_layout()
        mean, std, mn, mx, med = fast_big_data_stats(vals)
        return {
            'total_data_points': int(len(vals)),
            'visualization_points': int(len(sampled)),
            'mean': float(mean), 'std': float(std), 'min': float(mn), 'max': float(mx), 'median': float(med)
        }

    def plot_rolling_statistics(self, df: pd.DataFrame, factor_col: str = 'factor_value', window: int = 60):
        vals = df[factor_col].values.astype(np.float32)
        m, s = fast_rolling_stats(vals, window)
        if 'datetime' in df.columns:
            x = df['datetime']
        else:
            x = np.arange(len(vals))
        plt.figure(figsize=self.config.get('figure_size', (15,6)))
        plt.plot(x, m, label=f'mean({window})')
        plt.fill_between(x, m-s, m+s, alpha=0.3)
        plt.legend(); plt.tight_layout()
