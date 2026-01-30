import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable
from ..config.settings import BIG_DATA_CONFIG, MAX_MEMORY_PERCENT
from ..utils.memory_utils import MemoryManager, DataTypeOptimizer
from ..utils.file_utils import FileManager, CheckpointManager
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import importlib, inspect, sys, pathlib

# ================= 插件式因子函数注册机制 =================
FACTOR_FUNC_REGISTRY: Dict[str, Callable] = {}

def register_factor_func(name: str):
    """装饰器方式注册: @register_factor_func('my_factor').
    要求函数签名: fn(group: pd.DataFrame, **params) -> Optional[Dict]
    返回字典需至少含 key 'factor_value'.
    """
    def deco(fn: Callable):
        FACTOR_FUNC_REGISTRY[name] = fn
        return fn
    return deco

def register_factor_callable(name: str, fn: Callable, override: bool = True):
    """直接传入可调用对象注册 (便于外部脚本传入)。"""
    if (not override) and name in FACTOR_FUNC_REGISTRY:
        return FACTOR_FUNC_REGISTRY[name]
    FACTOR_FUNC_REGISTRY[name] = fn
    return fn

def _resolve_module_from_path(file_path: str) -> str:
    """将绝对路径加入 sys.path 并返回可导入模块名(临时)。
    如果文件不在包结构内, 生成临时模块名 _ext_factor_xxx.
    """
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)
    base_name = pathlib.Path(file_path).stem
    # 若所在目录已有 __init__.py 则尝试包内导入
    parent = pathlib.Path(file_path).parent
    if (parent / '__init__.py').exists():
        # 构造相对 sys.path 的层级
        sys.path.insert(0, str(parent.parent)) if str(parent.parent) not in sys.path else None
        return f"{parent.name}.{base_name}"
    # 否则临时加载
    sys.path.insert(0, str(parent)) if str(parent) not in sys.path else None
    return base_name

def load_and_register_factor(spec: str, name: Optional[str] = None, override: bool = True) -> str:
    """根据 spec 加载外部因子函数并注册.
    spec 形态:
      1) 包路径:   package.sub.module:func_name
      2) 文件路径: /abs/path/to/file.py:func_name
    name: 注册名(可与函数名不同); 默认=函数名.
    返回: 最终注册名.
    """
    if ':' not in spec:
        raise ValueError("factor spec 必须形如 'module_or_file:func'")
    mod_part, func_name = spec.split(':', 1)
    if mod_part.endswith('.py'):
        mod_name = _resolve_module_from_path(mod_part)
    else:
        mod_name = mod_part
    module = importlib.import_module(mod_name)
    if not hasattr(module, func_name):
        raise AttributeError(f"模块 {mod_name} 不存在函数 {func_name}")
    fn = getattr(module, func_name)
    if not callable(fn):
        raise TypeError(f"对象 {func_name} 不是可调用")
    reg_name = name or func_name
    register_factor_callable(reg_name, fn, override=override)
    return reg_name

# ================= 默认示例因子(可选) =================
# 避免强耦合: 如果 numba 版本存在则提供一个默认 top_volume_ratio
try:
    from ..numba_operators import calculate_top_volume_ratio_numba as _calc_top_vol_ratio
except Exception:  # pragma: no cover
    _calc_top_vol_ratio = None

@register_factor_func('top_volume_ratio')
def top_volume_ratio_factor(group: pd.DataFrame, threshold: float = 0.99) -> Optional[Dict]:
    """示例因子: 计算顶端累计成交量覆盖比例.
    可被外部同名注册覆盖(override).
    返回字典至少含 'factor_value'.
    """
    if len(group) == 0:
        return None
    if _calc_top_vol_ratio is None:
        # 退化: 使用简单占位逻辑 (最大单笔 / 总量)
        volumes = group['q'].values.astype(np.float32)
        total = volumes.sum()
        if total <= 0:
            return None
        val = float(volumes.max() / total)
    else:
        volumes = group['q'].values.astype(np.float32)
        val = float(_calc_top_vol_ratio(volumes, threshold))
    if np.isnan(val):
        return None
    return {
        'factor_value': val,
        'trade_count': int(len(group)),
        'total_volume': float(volumes.sum()),
        'avg_trade_size': float(volumes.mean()),
        'max_trade_size': float(volumes.max()),
        'min_trade_size': float(volumes.min())
    }

# =============== 通用单文件处理（供多进程调用） =================
# 新的签名允许动态传入因子名称与参数, 以及未注册时的 spec

def _process_one_file(file_path: str,
                      window_size_ms: int,
                      factor_name: str,
                      factor_params: Dict,
                      max_mem_pct: float,
                      zero_to_nan: bool,
                      factor_spec: Optional[str] = None,
                      override_existing: bool = False) -> Tuple[List[Dict], str]:
    # 修改: 增加 override_existing 以便外部覆盖
    try:
        if factor_spec:
            # 若提供 spec 且需要覆盖或尚未注册
            need_load = override_existing or (factor_name not in FACTOR_FUNC_REGISTRY)
            if need_load:
                load_and_register_factor(factor_spec, name=factor_name, override=True)
        if factor_name not in FACTOR_FUNC_REGISTRY:
            raise ValueError(f'Factor function not registered: {factor_name}')
        factor_fn = FACTOR_FUNC_REGISTRY[factor_name]
        # 读取 (parquet only)
        df = pd.read_parquet(file_path)
        df = DataTypeOptimizer.optimize_dtypes(df, aggressive=False)
        if MemoryManager.get_memory_usage() > max_mem_pct * 100:
            MemoryManager.force_gc()
        results: List[Dict] = []
        df['minute_group'] = (df['T'] // window_size_ms) * window_size_ms
        for minute_ts, group in df.groupby('minute_group'):
            if len(group) == 0:
                continue
            out = factor_fn(group, **(factor_params or {}))
            if not out:
                continue
            fv = out.get('factor_value')
            if zero_to_nan and (fv == 0):
                out['factor_value'] = np.nan
            if np.isnan(out.get('factor_value', np.nan)):
                continue
            out['timestamp'] = int(minute_ts)
            results.append(out)
        return results, file_path
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        return [], file_path

class SingleFileProcessor:
    def __init__(self,
                 window_size_ms: int = 60000,
                 factor_name: str = 'top_volume_ratio',
                 factor_params: Optional[Dict] = None,
                 zero_to_nan: bool = True,
                 external_factor_spec: Optional[str] = None,
                 factor_callable: Optional[Callable] = None,
                 override_existing: bool = False):
        self.window_size_ms = window_size_ms
        self.factor_name = factor_name
        self.factor_params = factor_params or {}
        self.zero_to_nan = zero_to_nan
        self.external_factor_spec = external_factor_spec
        self.override_existing = override_existing
        # 注册外部 callable / spec
        if factor_callable is not None:
            register_factor_callable(self.factor_name, factor_callable, override=True)
        if self.external_factor_spec:
            need_load = self.override_existing or (self.factor_name not in FACTOR_FUNC_REGISTRY)
            if need_load:
                load_and_register_factor(self.external_factor_spec, name=self.factor_name, override=True)
        if self.factor_name not in FACTOR_FUNC_REGISTRY:
            raise ValueError(f'Factor function not registered: {self.factor_name}')

    def process_file_streaming(self, file_path: str) -> Tuple[List[Dict], str]:
        try:
            if self.external_factor_spec:
                need_load = self.override_existing or (self.factor_name not in FACTOR_FUNC_REGISTRY)
                if need_load:
                    load_and_register_factor(self.external_factor_spec, name=self.factor_name, override=True)
            factor_fn = FACTOR_FUNC_REGISTRY[self.factor_name]
            df = pd.read_parquet(file_path)
            df = DataTypeOptimizer.optimize_dtypes(df)
            if MemoryManager.check_memory_threshold(MAX_MEMORY_PERCENT):
                MemoryManager.force_gc()
            results: List[Dict] = []
            df['minute_group'] = (df['T'] // self.window_size_ms) * self.window_size_ms
            for minute_ts, group in df.groupby('minute_group'):
                if len(group) == 0:
                    continue
                out = factor_fn(group, **self.factor_params)
                if not out:
                    continue
                fv = out.get('factor_value')
                if self.zero_to_nan and (fv == 0):
                    out['factor_value'] = np.nan
                if np.isnan(out.get('factor_value', np.nan)):
                    continue
                out['timestamp'] = int(minute_ts)
                results.append(out)
            del df
            MemoryManager.force_gc()
            return results, file_path
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            return [], file_path

class BigDataProcessor:
    def __init__(self,
                 data_dir: str,
                 output_config: Dict,
                 factor_name: str = 'top_volume_ratio',
                 factor_params: Optional[Dict] = None,
                 zero_to_nan: bool = True,
                 external_factor_spec: Optional[str] = None,
                 factor_callable: Optional[Callable] = None,
                 override_existing: bool = False):
        self.data_dir = data_dir
        self.output_config = output_config
        self.checkpoint_manager = CheckpointManager(output_config['checkpoint_dir'])
        self.factor_name = factor_name
        self.factor_params = factor_params or {}
        self.zero_to_nan = zero_to_nan
        self.external_factor_spec = external_factor_spec
        self.override_existing = override_existing
        if factor_callable is not None:
            register_factor_callable(self.factor_name, factor_callable, override=True)
        if self.external_factor_spec:
            need_load = self.override_existing or (self.factor_name not in FACTOR_FUNC_REGISTRY)
            if need_load:
                load_and_register_factor(self.external_factor_spec, name=self.factor_name, override=True)
        if self.factor_name not in FACTOR_FUNC_REGISTRY:
            raise ValueError(f'Factor function not registered: {self.factor_name}')
        self.single = SingleFileProcessor(
            window_size_ms=BIG_DATA_CONFIG['window_size_ms'],
            factor_name=self.factor_name,
            factor_params=self.factor_params,
            zero_to_nan=self.zero_to_nan,
            external_factor_spec=self.external_factor_spec,
            override_existing=self.override_existing
        )
        self.stats = {
            'total_files': 0,
            'processed_files': 0,
            'total_factors': 0,
            'processing_time': 0,
            'memory_peak': 0,
            'checkpoints_created': 0
        }

    def get_all_files(self) -> List[str]:
        return FileManager.get_parquet_files(self.data_dir)

    def _print_progress(self, processed: int, total: int):
        pct = (processed / total) * 100 if total else 100
        bar_len = 24
        filled = int(bar_len * pct / 100)
        bar = '#' * filled + '-' * (bar_len - filled)
        print(f"Progress [{bar}] {pct:5.1f}%  ({processed}/{total})\r", end='', flush=True)

    def process_all_files(self) -> Dict:
        import time
        start = time.time()
        files = self.get_all_files()
        total = len(files)
        self.stats['total_files'] = total
        if total == 0:
            print('No files found to process')
            return self.stats

        batch_size = int(BIG_DATA_CONFIG.get('batch_size', 10))
        n_workers = int(BIG_DATA_CONFIG.get('parallel_workers', os.cpu_count() or 4))
        use_parallel = bool(BIG_DATA_CONFIG.get('batch_processing', True))
        ckpt_interval = int(BIG_DATA_CONFIG.get('checkpoint_interval', 100))

        all_results: List[Dict] = []
        ckpt_id = 0
        processed_files = 0

        if use_parallel:
            for i in range(0, total, batch_size):
                batch = files[i:i+batch_size]
                with ProcessPoolExecutor(max_workers=n_workers) as ex:
                    futures = [
                        ex.submit(
                            _process_one_file,
                            fp,
                            BIG_DATA_CONFIG['window_size_ms'],
                            self.factor_name,
                            self.factor_params,
                            MAX_MEMORY_PERCENT,
                            self.zero_to_nan,
                            self.external_factor_spec,
                            self.override_existing
                        ) for fp in batch
                    ]
                    for fut in as_completed(futures):
                        try:
                            results, _ = fut.result()
                            if results:
                                all_results.extend(results)
                        except Exception as e:
                            print(f"Worker error: {e}")
                        processed_files += 1
                        self.stats['processed_files'] = processed_files
                        self._print_progress(processed_files, total)

                if processed_files % ckpt_interval == 0 and all_results:
                    f = self.checkpoint_manager.save_checkpoint(all_results, ckpt_id)
                    if f:
                        ckpt_id += 1
                        self.stats['checkpoints_created'] = ckpt_id
                        all_results = []
                        MemoryManager.force_gc()
        else:
            for i, fp in enumerate(files, 1):
                res, _ = self.single.process_file_streaming(fp)
                if res:
                    all_results.extend(res)
                processed_files = i
                self.stats['processed_files'] = processed_files
                self._print_progress(processed_files, total)
                if processed_files % ckpt_interval == 0 and all_results:
                    f = self.checkpoint_manager.save_checkpoint(all_results, ckpt_id)
                    if f:
                        ckpt_id += 1
                        self.stats['checkpoints_created'] = ckpt_id
                        all_results = []
                        MemoryManager.force_gc()

        if all_results:
            f = self.checkpoint_manager.save_checkpoint(all_results, ckpt_id)
            if f:
                ckpt_id += 1
                self.stats['checkpoints_created'] = ckpt_id

        print()
        self.stats['processing_time'] = time.time() - start
        self.stats['memory_peak'] = MemoryManager.get_memory_usage()
        return self.stats

    def merge_results(self) -> Optional[pd.DataFrame]:
        return self.checkpoint_manager.merge_all_checkpoints()

    def save_final_results(self, output_file: str, factor_col: str = 'factor_value') -> bool:
        try:
            df = self.merge_results()
            if df is None:
                print('No results to save')
                return False
            # timestamp -> datetime(UTC)
            if 'datetime' not in df.columns and 'timestamp' in df.columns:
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            if 'factor_value' in df.columns and factor_col:
                df = df.rename(columns={'factor_value': factor_col})
            cols = ['datetime'] + [c for c in df.columns if c not in ('datetime',)]
            df[cols].to_parquet(output_file, index=False)
            self.stats['total_factors'] = len(df)
            print(f'Results saved to {output_file}')
            return True
        except Exception as e:
            print(f'Error saving results: {e}')
            return False
