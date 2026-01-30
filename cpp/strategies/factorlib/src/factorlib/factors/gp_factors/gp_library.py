"""
GP Factor Library - Dynamic Factor Registry

Manages GP-mined factors with on-demand computation.
Factors are stored as expressions and evaluated dynamically.
"""

import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any, Union
import pandas as pd
import numpy as np


@dataclass
class GPFactorInfo:
    """GP Factor metadata and performance metrics."""
    factor_id: str
    expression: str
    inner_expression: str
    normalize_window: int
    clip_range: float
    sharpe: float
    returns: float
    turnover: float
    long_ratio: float
    short_ratio: float
    coverage: float
    added_at_gen: int
    source_run: str = ""  # Which GP run this came from

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'GPFactorInfo':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class GPFactorLibrary:
    """
    Dynamic GP Factor Library.

    Instead of generating thousands of Python classes, this library:
    1. Stores factor expressions in a JSON registry
    2. Evaluates expressions on-demand using ops
    3. Supports fast filtering and batch computation
    """

    def __init__(self, registry_path: Optional[str] = None):
        """
        Initialize the GP Factor Library.

        Args:
            registry_path: Path to the factor registry JSON file.
                          If None, uses default location.
        """
        self._factors: Dict[str, GPFactorInfo] = {}
        self._registry_path = registry_path or self._default_registry_path()
        self._load_registry()

    def _default_registry_path(self) -> str:
        """Get default registry path."""
        return str(Path(__file__).parent / "gp_registry.json")

    def _load_registry(self):
        """Load factor registry from JSON file."""
        if Path(self._registry_path).exists():
            with open(self._registry_path, 'r') as f:
                data = json.load(f)
                for factor_id, info in data.get('factors', {}).items():
                    self._factors[factor_id] = GPFactorInfo.from_dict(info)

    def save_registry(self):
        """Save current registry to JSON file."""
        data = {
            'factors': {fid: f.to_dict() for fid, f in self._factors.items()},
            'metadata': {
                'total_factors': len(self._factors),
                'sharpe_range': [
                    min(f.sharpe for f in self._factors.values()) if self._factors else 0,
                    max(f.sharpe for f in self._factors.values()) if self._factors else 0,
                ],
            }
        }
        with open(self._registry_path, 'w') as f:
            json.dump(data, f, indent=2)

    def import_from_gp_result(
        self,
        json_path: str,
        source_run: str = "",
        min_sharpe: float = 2.0,
        max_turnover: float = 200000,
        prefix: str = "gp"
    ) -> int:
        """
        Import factors from GP mining result JSON file.

        Args:
            json_path: Path to GP result JSON (e.g., sharpe_gt2_GOOD.json)
            source_run: Name of the GP run (for tracking)
            min_sharpe: Minimum sharpe ratio to import
            max_turnover: Maximum turnover to import
            prefix: Prefix for factor IDs

        Returns:
            Number of factors imported
        """
        with open(json_path, 'r') as f:
            gp_factors = json.load(f)

        imported = 0
        existing_exprs = {f.expression for f in self._factors.values()}

        for i, factor in enumerate(gp_factors):
            # Filter
            if factor['sharpe'] < min_sharpe:
                continue
            if factor['turnover'] > max_turnover:
                continue

            # Skip duplicates (same expression)
            if factor['expression'] in existing_exprs:
                continue

            # Generate unique ID from expression hash
            expr_hash = hashlib.md5(factor['expression'].encode()).hexdigest()[:8]
            factor_id = f"{prefix}_{expr_hash}"

            # Create factor info
            info = GPFactorInfo(
                factor_id=factor_id,
                expression=factor['expression'],
                inner_expression=factor.get('inner_expression', ''),
                normalize_window=factor.get('normalize_window', 1440),
                clip_range=factor.get('clip_range', 3.0),
                sharpe=factor['sharpe'],
                returns=factor['returns'],
                turnover=factor['turnover'],
                long_ratio=factor['long_ratio'],
                short_ratio=factor['short_ratio'],
                coverage=factor['coverage'],
                added_at_gen=factor.get('added_at_gen', 0),
                source_run=source_run,
            )

            self._factors[factor_id] = info
            existing_exprs.add(factor['expression'])
            imported += 1

        # Save updated registry
        self.save_registry()
        return imported

    def get_info(self, factor_id: str) -> GPFactorInfo:
        """Get factor info by ID."""
        if factor_id not in self._factors:
            raise KeyError(f"Factor '{factor_id}' not found")
        return self._factors[factor_id]

    def list_factors(
        self,
        min_sharpe: float = 0,
        max_turnover: float = float('inf'),
        sort_by: str = 'sharpe',
        ascending: bool = False,
        limit: int = None
    ) -> List[GPFactorInfo]:
        """
        List factors with filtering and sorting.

        Args:
            min_sharpe: Minimum sharpe filter
            max_turnover: Maximum turnover filter
            sort_by: Field to sort by ('sharpe', 'returns', 'turnover')
            ascending: Sort ascending (default False = descending)
            limit: Max number to return

        Returns:
            List of GPFactorInfo
        """
        factors = [
            f for f in self._factors.values()
            if f.sharpe >= min_sharpe and f.turnover <= max_turnover
        ]

        factors.sort(key=lambda x: getattr(x, sort_by), reverse=not ascending)

        if limit:
            factors = factors[:limit]

        return factors

    def compute(
        self,
        factor_id: str,
        panel_data: Dict[str, pd.DataFrame],
        normalize: bool = False,  # Expression already includes normalization
    ) -> pd.DataFrame:
        """
        Compute a GP factor on panel data.

        Args:
            factor_id: Factor ID
            panel_data: Dict of column -> DataFrame (rows=time, cols=assets)
            normalize: Whether to apply additional normalization

        Returns:
            DataFrame with factor values
        """
        from factorlib.utils.operators import ops

        info = self.get_info(factor_id)
        expr = info.expression

        # Build local namespace with panel data columns
        local_ns = {'ops': ops, 'np': np}
        for col_name in ['Close', 'Open', 'High', 'Low', 'Volume',
                         'QuoteAssetVolume', 'NumberOfTrades',
                         'TakerBuyQuoteAssetVolume', 'TakerSellQuoteAssetVolume']:
            if col_name in panel_data:
                local_ns[col_name] = panel_data[col_name]

        # Also add common aliases
        local_ns['neg'] = lambda x: -x

        # Evaluate expression
        try:
            result = eval(expr, {"__builtins__": {}}, local_ns)
        except Exception as e:
            raise ValueError(f"Failed to evaluate factor {factor_id}: {e}\nExpression: {expr}")

        # Optional additional normalization
        if normalize and isinstance(result, pd.DataFrame):
            result = ops.replace_inf(result)
            result = ops.fill_na(result, 0)
            result = ops.ts_zscore(result, 1440)
            result = ops.clip(result, -3, 3)
            result = ops.fill_na(result, 0)

        return result

    def compute_batch(
        self,
        factor_ids: List[str],
        panel_data: Dict[str, pd.DataFrame],
        verbose: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Compute multiple factors.

        Args:
            factor_ids: List of factor IDs to compute
            panel_data: Panel data dict
            verbose: Print progress

        Returns:
            Dict of factor_id -> result DataFrame
        """
        results = {}
        for i, fid in enumerate(factor_ids):
            if verbose:
                print(f"Computing {i+1}/{len(factor_ids)}: {fid}")
            try:
                results[fid] = self.compute(fid, panel_data)
            except Exception as e:
                print(f"  Failed: {e}")
        return results

    def to_dataframe(self) -> pd.DataFrame:
        """Convert registry to DataFrame for analysis."""
        if not self._factors:
            return pd.DataFrame()

        records = [f.to_dict() for f in self._factors.values()]
        df = pd.DataFrame(records)
        return df.sort_values('sharpe', ascending=False)

    def filter(
        self,
        min_sharpe: float = 0,
        max_sharpe: float = float('inf'),
        min_turnover: float = 0,
        max_turnover: float = float('inf'),
        min_returns: float = -float('inf'),
    ) -> 'GPFactorLibrary':
        """
        Create a filtered view of the library.

        Returns a new GPFactorLibrary with only matching factors.
        """
        new_lib = GPFactorLibrary.__new__(GPFactorLibrary)
        new_lib._factors = {}
        new_lib._registry_path = self._registry_path

        for fid, f in self._factors.items():
            if (min_sharpe <= f.sharpe <= max_sharpe and
                min_turnover <= f.turnover <= max_turnover and
                f.returns >= min_returns):
                new_lib._factors[fid] = f

        return new_lib

    def __len__(self):
        return len(self._factors)

    def __contains__(self, factor_id: str):
        return factor_id in self._factors

    def __iter__(self):
        return iter(self._factors.values())

    def __repr__(self):
        if not self._factors:
            return "GPFactorLibrary(empty)"
        sharpes = [f.sharpe for f in self._factors.values()]
        return (f"GPFactorLibrary({len(self._factors)} factors, "
                f"sharpe: {min(sharpes):.2f}-{max(sharpes):.2f})")


# Global instance
gp_library = GPFactorLibrary()
