"""
Core module for FactorLib.

Provides base classes and fundamental abstractions.
"""

from .base import (
    BaseFactor,
    KlineFactorBase,
    TradeFactorBase,
    FactorPipeline,
    FactorFrequency,
    FactorCategory,
)

__all__ = [
    'BaseFactor',
    'KlineFactorBase',
    'TradeFactorBase',
    'FactorPipeline',
    'FactorFrequency',
    'FactorCategory',
]
