import os, glob, pickle
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Any
import pandas as pd
from .memory_utils import DataTypeOptimizer

class FileManager:
    @staticmethod
    def get_parquet_files(data_dir: str, pattern: str = '*.parquet', recursive: bool = False) -> List[str]:
        if recursive:
            files = glob.glob(os.path.join(data_dir, '**', pattern), recursive=True)
        else:
            files = glob.glob(os.path.join(data_dir, pattern))
        return sorted(files)

    @staticmethod
    def get_csv_files(data_dir: str, pattern: str = '*.csv', recursive: bool = False) -> List[str]:
        if recursive:
            files = glob.glob(os.path.join(data_dir, '**', pattern), recursive=True)
        else:
            files = glob.glob(os.path.join(data_dir, pattern))
        return sorted(files)

class CheckpointManager:
    def __init__(self, checkpoint_dir: str):
        self.dir = Path(checkpoint_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, data: Any, idx: int) -> Optional[str]:
        if not data:
            return None
        fn = self.dir / f'ckpt_{idx:05d}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pkl'
        with open(fn, 'wb') as f:
            pickle.dump(data, f)
        print(f'Saved checkpoint: {fn}')
        return str(fn)

    def list_checkpoints(self) -> List[str]:
        return sorted([str(p) for p in self.dir.glob('*.pkl')])

    def merge_all_checkpoints(self) -> Optional[pd.DataFrame]:
        files = self.list_checkpoints()
        if not files:
            return None
        rows = []
        for fp in files:
            try:
                with open(fp, 'rb') as f:
                    ck = pickle.load(f)
                rows.extend(ck)
            except Exception as e:
                print(f'Err reading {fp}: {e}')
        if not rows:
            return None
        df = pd.DataFrame(rows)
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp')
        df = df.rename(columns={'timestamp': 'datetime'})
        return df

    def cleanup_checkpoints(self):
        for p in self.dir.glob('*.pkl'):
            try: p.unlink()
            except: pass
