"""
Configuration utilities for FactorLib.
"""
from __future__ import annotations

import os

__all__ = ["get_max_workers"]


def get_max_workers(frac: float = 0.8, env_key: str = "FACTORLIB_MAX_WORKERS") -> int:
    """
    Get recommended max workers for parallel processing.

    Priority:
    1. Environment variable FACTORLIB_MAX_WORKERS (if set)
    2. frac * cpu_count (default 0.8)

    Args:
        frac: Fraction of CPU cores to use (default 0.8)
        env_key: Environment variable name to check

    Returns:
        Number of workers to use

    Usage:
        from factorlib.utils.config import get_max_workers

        # Use default (0.8 * cpu_count)
        workers = get_max_workers()

        # Use custom fraction
        workers = get_max_workers(frac=0.5)

        # Override via environment
        # export FACTORLIB_MAX_WORKERS=4
    """
    # Check environment variable first
    env_val = os.getenv(env_key)
    if env_val:
        try:
            val = int(env_val)
            if val > 0:
                return val
        except ValueError:
            pass

    # Fall back to frac * cpu_count
    cpu = os.cpu_count() or 4
    return max(1, int(cpu * frac))
