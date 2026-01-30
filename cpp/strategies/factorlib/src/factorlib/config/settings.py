"""
Centralized configuration management for FactorLib.

This module provides a unified configuration system with:
- Environment variable support
- Default values
- Runtime configuration updates
- Validation
"""

import os
import multiprocessing as mp
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _get_memory_gb() -> float:
    """Get total system memory in GB."""
    if HAS_PSUTIL:
        return psutil.virtual_memory().total / (1024 ** 3)
    return float(os.getenv('FACTORLIB_MEM_GB', '8'))


def _get_cpu_count() -> int:
    """Get CPU count with fallback."""
    return mp.cpu_count() or 4


@dataclass
class DatabaseConfig:
    """ClickHouse database configuration (TCP connection)."""
    host: str = '192.168.193.1'
    port: int = 9000  # TCP port (changed from HTTP 8123)
    username: str = 'default'
    password: str = 'SQ2025'
    database: str = 'OKX'
    kline_table: str = '1m_candles_data'
    trades_table: str = 'trades_data'

    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """Create config from environment variables."""
        return cls(
            host=os.getenv('FACTORLIB_DB_HOST', cls.host),
            port=int(os.getenv('FACTORLIB_DB_PORT', str(cls.port))),
            username=os.getenv('FACTORLIB_DB_USER', cls.username),
            password=os.getenv('FACTORLIB_DB_PASS', cls.password),
            database=os.getenv('FACTORLIB_DB_NAME', cls.database),
            kline_table=os.getenv('FACTORLIB_KLINE_TABLE', cls.kline_table),
            trades_table=os.getenv('FACTORLIB_TRADES_TABLE', cls.trades_table),
        )


@dataclass
class PathConfig:
    """File path configuration."""
    data_dir: Path = field(default_factory=lambda: Path('/home/ch/data'))
    output_dir: Path = field(default_factory=lambda: Path('/home/ch/data/result'))
    tick_dir: Path = field(default_factory=lambda: Path('/home/ch/data/tick'))
    kline_dir: Path = field(default_factory=lambda: Path('/home/ch/data/kline'))
    plot_dir: Path = field(default_factory=lambda: Path('/home/ch/data/result/plots'))
    checkpoint_dir: Path = field(default_factory=lambda: Path('/home/ch/data/result/checkpoints'))
    log_dir: Path = field(default_factory=lambda: Path('/home/ch/data/result/logs'))

    @classmethod
    def from_env(cls) -> 'PathConfig':
        """Create config from environment variables."""
        return cls(
            data_dir=Path(os.getenv('FACTORLIB_DATA_DIR', '/home/ch/data')),
            output_dir=Path(os.getenv('FACTORLIB_OUTPUT_DIR', '/home/ch/data/result')),
            tick_dir=Path(os.getenv('FACTORLIB_TICK_DIR', '/home/ch/data/tick')),
            kline_dir=Path(os.getenv('FACTORLIB_KLINE_DIR', '/home/ch/data/kline')),
            plot_dir=Path(os.getenv('FACTORLIB_PLOT_DIR', '/home/ch/data/result/plots')),
            checkpoint_dir=Path(os.getenv('FACTORLIB_CKPT_DIR', '/home/ch/data/result/checkpoints')),
            log_dir=Path(os.getenv('FACTORLIB_LOG_DIR', '/home/ch/data/result/logs')),
        )

    def ensure_dirs(self) -> None:
        """Create all directories if they don't exist."""
        for path in [self.output_dir, self.plot_dir, self.checkpoint_dir, self.log_dir]:
            path.mkdir(parents=True, exist_ok=True)


@dataclass
class ComputeConfig:
    """Computation configuration."""
    n_cores: int = field(default_factory=_get_cpu_count)
    memory_gb: float = field(default_factory=_get_memory_gb)
    max_workers: Optional[int] = None
    batch_size: int = 16
    max_memory_percent: float = 0.8
    gc_interval: int = 50
    checkpoint_interval: int = 100

    def __post_init__(self):
        if self.max_workers is None:
            self.max_workers = self._recommended_workers()
        self.batch_size = self._recommended_batch_size()

    def _recommended_workers(self) -> int:
        """Calculate recommended worker count based on hardware."""
        base = max(1, self.n_cores - 1)
        if self.memory_gb < 8:
            base = min(base, 4)
        elif self.memory_gb < 16:
            base = min(base, 8)
        else:
            base = min(base, 16)
        return max(2, base)

    def _recommended_batch_size(self) -> int:
        """Calculate recommended batch size based on memory."""
        if self.memory_gb >= 64:
            return 24
        elif self.memory_gb >= 32:
            return 16
        elif self.memory_gb >= 16:
            return 12
        elif self.memory_gb >= 8:
            return 8
        return 4

    @classmethod
    def from_env(cls) -> 'ComputeConfig':
        """Create config from environment variables."""
        config = cls()
        if os.getenv('FACTORLIB_WORKERS'):
            config.max_workers = int(os.getenv('FACTORLIB_WORKERS'))
        if os.getenv('FACTORLIB_BATCH_SIZE'):
            config.batch_size = int(os.getenv('FACTORLIB_BATCH_SIZE'))
        if os.getenv('FACTORLIB_MAX_MEM_PCT'):
            config.max_memory_percent = float(os.getenv('FACTORLIB_MAX_MEM_PCT'))
        return config


@dataclass
class FactorConfig:
    """Factor computation defaults."""
    default_window: int = 60
    zscore_window: int = 14400  # 10 days at 1-min frequency
    clip_range: tuple = (-3, 3)
    decay_alpha: float = 2.0
    volume_threshold: float = 0.99
    signal_threshold: float = 2.0

    @classmethod
    def from_env(cls) -> 'FactorConfig':
        """Create config from environment variables."""
        return cls(
            default_window=int(os.getenv('FACTORLIB_DEFAULT_WINDOW', '60')),
            zscore_window=int(os.getenv('FACTORLIB_ZSCORE_WINDOW', '14400')),
            volume_threshold=float(os.getenv('FACTORLIB_VOL_THRESHOLD', '0.99')),
        )


@dataclass
class BacktestConfig:
    """Backtest configuration."""
    cost_bps: float = 1.0  # Transaction cost in basis points
    slippage_bps: float = 0.5
    compound: bool = True
    shift_periods: int = 1  # T+1 execution
    price_col: str = 'Close'
    return_col: str = 'return'

    @classmethod
    def from_env(cls) -> 'BacktestConfig':
        """Create config from environment variables."""
        return cls(
            cost_bps=float(os.getenv('FACTORLIB_COST_BPS', '1.0')),
            slippage_bps=float(os.getenv('FACTORLIB_SLIPPAGE_BPS', '0.5')),
            compound=os.getenv('FACTORLIB_COMPOUND', 'true').lower() == 'true',
        )


class Settings:
    """
    Global settings singleton.

    Usage:
        from factorlib.config import settings

        # Access settings
        settings.database.host
        settings.paths.output_dir
        settings.compute.max_workers

        # Update settings
        settings.update(database={'host': 'localhost'})
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_settings()
        return cls._instance

    def _init_settings(self):
        """Initialize all settings from environment."""
        self.database = DatabaseConfig.from_env()
        self.paths = PathConfig.from_env()
        self.compute = ComputeConfig.from_env()
        self.factor = FactorConfig.from_env()
        self.backtest = BacktestConfig.from_env()

    def update(self, **kwargs) -> None:
        """
        Update settings.

        Args:
            **kwargs: Setting groups to update (database, paths, compute, etc.)
        """
        for key, values in kwargs.items():
            if hasattr(self, key) and isinstance(values, dict):
                config = getattr(self, key)
                for k, v in values.items():
                    if hasattr(config, k):
                        setattr(config, k, v)

    def ensure_directories(self) -> None:
        """Create all required directories."""
        self.paths.ensure_dirs()

    def to_dict(self) -> Dict[str, Any]:
        """Export settings as dictionary."""
        return {
            'database': {k: v for k, v in self.database.__dict__.items() if k != 'password'},
            'paths': {k: str(v) for k, v in self.paths.__dict__.items()},
            'compute': self.compute.__dict__,
            'factor': self.factor.__dict__,
            'backtest': self.backtest.__dict__,
        }


# Global settings instance
settings = Settings()
