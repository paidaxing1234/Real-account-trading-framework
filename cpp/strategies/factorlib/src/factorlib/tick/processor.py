import os
from typing import Dict, Optional
import pandas as pd
from .config.settings import BIG_DATA_CONFIG, OUTPUT_CONFIG, DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR
from .data.processor import BigDataProcessor
from .visualizer import FactorVisualizer
from .utils.memory_utils import MemoryManager

class TickFactorProcessor:
    def __init__(self, data_dir: str = DEFAULT_DATA_DIR, output_dir: str = DEFAULT_OUTPUT_DIR, config: Dict = None):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.config = config or BIG_DATA_CONFIG
        self.output_config = OUTPUT_CONFIG.copy(); self.output_config['base_dir'] = output_dir
        self.dp = BigDataProcessor(data_dir, self.output_config)
        self.viz = FactorVisualizer()
        self.results_available = False

    def _read_factor_file(self, path: str) -> pd.DataFrame:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        return pd.read_parquet(path)

    def run_factor_calculation(self, show_progress: bool = True, factor_col: str = 'trade_vol_perc') -> Dict:
        stats = self.dp.process_all_files()
        out_file = os.path.join(self.output_config['base_dir'], self.output_config['factor_file'])
        success = self.dp.save_final_results(out_file, factor_col=factor_col)
        self.results_available = success
        return {
            'processing_stats': stats,
            'save_success': success,
            'output_file': out_file if success else None,
            'system_status': MemoryManager.get_memory_info(),
            'factor_col': factor_col,
        }

    def analyze_results(self, factor_col: Optional[str] = None) -> Optional[Dict]:
        if not self.results_available:
            return None
        out_file = os.path.join(self.output_config['base_dir'], self.output_config['factor_file'])
        if not os.path.exists(out_file):
            return None
        df = self._read_factor_file(out_file)
        # 自动识别可用的数值型因子列
        candidates = [c for c in df.columns if c not in ('datetime', 'CloseTime')]
        numeric_cols = [c for c in candidates if pd.api.types.is_numeric_dtype(df[c])]
        col = factor_col if (factor_col and factor_col in df.columns) else (numeric_cols[0] if numeric_cols else None)
        stats = df[col].describe().to_dict() if col else {}
        return {
            'data_points': len(df),
            'time_span': (df['datetime'].min(), df['datetime'].max()) if 'datetime' in df.columns else None,
            'factor_statistics': stats,
            'factor_col': col,
            'memory_usage_mb': df.memory_usage(deep=True).sum() / 1024**2
        }

    def create_visualizations(self):
        if not self.results_available:
            return None
        out_file = os.path.join(self.output_config['base_dir'], self.output_config['factor_file'])
        df = self._read_factor_file(out_file)
        stats = self.viz.plot_factor_analysis(df)
        self.viz.plot_rolling_statistics(df)
        return stats
