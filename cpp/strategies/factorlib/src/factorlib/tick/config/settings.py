import multiprocessing as mp
import os
from typing import Dict, Any

try:
    import psutil  # 用于检测内存
except Exception:
    psutil = None

N_CORES = mp.cpu_count() or 4

# 基于硬件的推荐参数（可被环境变量覆盖）
def _mem_gb() -> float:
    if psutil is not None:
        return psutil.virtual_memory().total / (1024**3)
    return float(os.getenv('FACTORLIB_MEM_GB', '8'))

def _recommended_workers(cores: int, mem_gb: float) -> int:
    # 预留1核给系统，且受内存与上限约束
    base = max(1, cores - 1)
    if mem_gb < 8:
        base = min(base, 4)
    elif mem_gb < 16:
        base = min(base, 8)
    else:
        base = int(base * 0.8)
    return max(2, base)

def _recommended_batch_size(mem_gb: float) -> int:
    # 粗略估计单文件占用，按内存分档设置 batch
    if mem_gb >= 64:
        return 24
    if mem_gb >= 32:
        return 16
    if mem_gb >= 16:
        return 12
    if mem_gb >= 8:
        return 8
    return 4

MEM_GB = _mem_gb()

# 环境变量优先
PARALLEL_WORKERS = int(os.getenv('FACTORLIB_WORKERS', str(_recommended_workers(N_CORES, MEM_GB))))
BATCH_SIZE = int(os.getenv('FACTORLIB_BATCH_SIZE', str(_recommended_batch_size(MEM_GB))))

MAX_MEMORY_PERCENT = float(os.getenv('FACTORLIB_MAX_MEM_PCT', '0.8'))
WINDOW_SIZE_MS = int(os.getenv('FACTORLIB_WINDOW_MS', '60000'))
VOLUME_THRESHOLD = float(os.getenv('FACTORLIB_TOPVOL_TH', '0.99'))

DEFAULT_DATA_DIR = os.getenv('FACTORLIB_DATA_DIR', '/home/ch/data/tick/')
# 默认输出目录
DEFAULT_OUTPUT_DIR = os.getenv('FACTORLIB_OUT_DIR', '/home/ch/data/result/')

OUTPUT_CONFIG = {
    'base_dir': DEFAULT_OUTPUT_DIR,
    # 修改默认输出文件为 parquet
    'factor_file': os.getenv('FACTORLIB_FACTOR_FILE', 'BTCUSDT_top99_volume_factor.parquet'),
    # 使子目录位于 base_dir 下（仍支持环境变量覆盖）
    'checkpoint_dir': os.getenv('FACTORLIB_CKPT_DIR', os.path.join(DEFAULT_OUTPUT_DIR, 'checkpoints/')),
    'temp_dir': os.getenv('FACTORLIB_TEMP_DIR', os.path.join(DEFAULT_OUTPUT_DIR, 'temp_factors/')),
    'log_dir': os.getenv('FACTORLIB_LOG_DIR', os.path.join(DEFAULT_OUTPUT_DIR, 'logs/')),
    'metadata_file': 'processing_metadata.json'
}

BIG_DATA_CONFIG = {
    'window_size_ms': WINDOW_SIZE_MS,
    'threshold': VOLUME_THRESHOLD,
    'batch_size': BATCH_SIZE,
    'n_cores': N_CORES,
    'batch_processing': True,
    'parallel_workers': PARALLEL_WORKERS,
    'memory_efficient': True,
    'streaming_mode': True,
    'intermediate_save': True,
    'checkpoint_interval': int(os.getenv('FACTORLIB_CKPT_INTERVAL', '100')),
    'auto_resume': True,
    'memory_limit_gb': int(os.getenv('FACTORLIB_MEM_LIMIT_GB', str(int(MEM_GB*0.8)))) if MEM_GB > 0 else 8,
    'gc_interval': 50,
    'memory_monitor': True
}

VISUALIZATION_CONFIG = {
    'max_plot_points': 10000,
    'sampling_strategy': 'uniform',
    'memory_efficient': True,
    'figure_size': (15, 10),
    'dpi': 100,
    'style': 'seaborn',
    'color_palette': 'viridis',
    'alpha': 0.7,
    'save_plots': True,
    'plot_format': 'png',
    'interactive': False
}


def create_directories() -> None:
    for k in ['base_dir', 'checkpoint_dir', 'temp_dir', 'log_dir']:
        try:
            os.makedirs(OUTPUT_CONFIG[k], exist_ok=True)
        except PermissionError:
            # Fallback to home directory if permission denied
            fallback_dir = os.path.expanduser(f'~/factorlib_output/{k}')
            os.makedirs(fallback_dir, exist_ok=True)
            OUTPUT_CONFIG[k] = fallback_dir

try:
    create_directories()
except Exception:
    pass  # Skip directory creation on import error
