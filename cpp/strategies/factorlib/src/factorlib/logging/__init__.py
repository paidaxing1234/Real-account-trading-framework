"""
Logging infrastructure for FactorLib.

Provides structured logging with:
- Console and file handlers
- JSON format for production
- Performance timing decorators
- Context managers for operation logging
"""

import logging
import sys
import time
import functools
from pathlib import Path
from typing import Optional, Callable, Any
from datetime import datetime
from contextlib import contextmanager

# Default format
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class FactorLibLogger:
    """
    Centralized logger for FactorLib.

    Usage:
        from factorlib.logger import get_logger

        logger = get_logger(__name__)
        logger.info("Processing started")
        logger.error("Error occurred", exc_info=True)
    """

    _loggers = {}
    _initialized = False
    _log_dir: Optional[Path] = None
    _level = logging.INFO

    @classmethod
    def setup(
        cls,
        level: int = logging.INFO,
        log_dir: Optional[Path] = None,
        log_to_file: bool = True,
        log_to_console: bool = True
    ) -> None:
        """
        Setup logging configuration.

        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_dir: Directory for log files
            log_to_file: Whether to log to file
            log_to_console: Whether to log to console
        """
        cls._level = level
        cls._log_dir = log_dir

        # Setup root logger
        root_logger = logging.getLogger('factorlib')
        root_logger.setLevel(level)

        # Remove existing handlers
        root_logger.handlers.clear()

        # Console handler
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(
                logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)
            )
            root_logger.addHandler(console_handler)

        # File handler
        if log_to_file and log_dir:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d")
            log_file = log_dir / f"factorlib_{timestamp}.log"

            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(level)
            file_handler.setFormatter(
                logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)
            )
            root_logger.addHandler(file_handler)

        cls._initialized = True

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Get a logger instance.

        Args:
            name: Logger name (usually __name__)

        Returns:
            Configured logger instance
        """
        if name not in cls._loggers:
            # Ensure it's under factorlib namespace
            if not name.startswith('factorlib'):
                name = f'factorlib.{name}'

            logger = logging.getLogger(name)
            logger.setLevel(cls._level)
            cls._loggers[name] = logger

        return cls._loggers[name]


def get_logger(name: str) -> logging.Logger:
    """
    Convenience function to get a logger.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return FactorLibLogger.get_logger(name)


def setup_logging(
    level: int = logging.INFO,
    log_dir: Optional[Path] = None,
    log_to_file: bool = True,
    log_to_console: bool = True
) -> None:
    """
    Setup logging configuration.

    Args:
        level: Logging level
        log_dir: Directory for log files
        log_to_file: Whether to log to file
        log_to_console: Whether to log to console
    """
    FactorLibLogger.setup(level, log_dir, log_to_file, log_to_console)


def log_execution_time(func: Callable) -> Callable:
    """
    Decorator to log function execution time.

    Usage:
        @log_execution_time
        def my_function():
            ...
    """
    logger = get_logger(func.__module__)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.debug(f"{func.__name__} executed in {elapsed:.3f}s")
        return result

    return wrapper


@contextmanager
def log_operation(name: str, logger: Optional[logging.Logger] = None):
    """
    Context manager to log operation start/end with timing.

    Usage:
        with log_operation("data loading"):
            df = load_data()
    """
    if logger is None:
        logger = get_logger('factorlib')

    logger.info(f"Starting: {name}")
    start = time.perf_counter()

    try:
        yield
        elapsed = time.perf_counter() - start
        logger.info(f"Completed: {name} ({elapsed:.3f}s)")
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.error(f"Failed: {name} ({elapsed:.3f}s) - {e}")
        raise


class ProgressLogger:
    """
    Simple progress logger for long-running operations.

    Usage:
        progress = ProgressLogger(total=100, name="Processing files")
        for i in range(100):
            process(i)
            progress.update()
        progress.finish()
    """

    def __init__(
        self,
        total: int,
        name: str = "Progress",
        log_interval: int = 10,
        logger: Optional[logging.Logger] = None
    ):
        self.total = total
        self.name = name
        self.log_interval = log_interval
        self.logger = logger or get_logger('factorlib')
        self.current = 0
        self.start_time = time.perf_counter()
        self._last_log = 0

    def update(self, n: int = 1) -> None:
        """Update progress by n steps."""
        self.current += n
        progress_pct = (self.current / self.total) * 100

        # Log at intervals
        if progress_pct - self._last_log >= self.log_interval:
            elapsed = time.perf_counter() - self.start_time
            rate = self.current / elapsed if elapsed > 0 else 0
            eta = (self.total - self.current) / rate if rate > 0 else 0

            self.logger.info(
                f"{self.name}: {self.current}/{self.total} "
                f"({progress_pct:.1f}%) | "
                f"Rate: {rate:.1f}/s | ETA: {eta:.1f}s"
            )
            self._last_log = progress_pct

    def finish(self) -> None:
        """Log completion."""
        elapsed = time.perf_counter() - self.start_time
        rate = self.total / elapsed if elapsed > 0 else 0
        self.logger.info(
            f"{self.name}: Completed {self.total} items in {elapsed:.2f}s "
            f"({rate:.1f}/s)"
        )
