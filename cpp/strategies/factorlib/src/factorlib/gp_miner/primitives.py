"""
DEAP Primitive Set Definition - Unified Panel Data Format

All operators work on DataFrame format:
- rows = timestamps
- columns = assets

Supports both:
1. Time-series (ts_*) operators: work on each asset column independently
2. Cross-sectional (cs_*) operators: work across assets at each timestamp

All operators are from: factorlib.utils.operators.ops
"""

import numpy as np
import pandas as pd
from deap import gp
from typing import List, Dict, Any
from functools import partial

from factorlib.utils.operators import ops


# ============================================================================
# Window Size Constants (for factor generation)
# ============================================================================

# Short-term windows (minutes)
SHORT_WINDOWS = [3, 5, 10, 15, 20, 30, 45]

# Medium-term windows (hours)
MEDIUM_WINDOWS = [60, 90, 120, 180, 240, 360, 480, 720]

# Long-term windows (1-2 days max)
LONG_WINDOWS = [1440, 2160, 2880]

# All windows
ALL_WINDOWS = SHORT_WINDOWS + MEDIUM_WINDOWS + LONG_WINDOWS

# EMA alpha values
EMA_ALPHAS = [2.0, 3.0, 5.0, 10.0, 20.0, 50.0]

# Delay/Return periods
PERIODS = [1, 2, 3, 5, 10, 20, 30, 60]

# CS operator parameters
CS_LONG_SHORT_N = [1, 2, 3, 5]
CS_SOFTMAX_TAU = [0.5, 1.0, 2.0, 5.0]


# ============================================================================
# Safe Wrappers (handle edge cases) - All work on both Series and DataFrame
# ============================================================================

def safe_divide(x, y):
    """Safe division with inf handling."""
    result = ops.divide(x, y)
    return ops.replace_inf(result)


def safe_log(x):
    """Safe log - handle non-positive."""
    if isinstance(x, pd.DataFrame):
        x_safe = x.clip(lower=1e-10)
    elif isinstance(x, pd.Series):
        x_safe = x.clip(lower=1e-10)
    else:
        x_safe = np.clip(x, 1e-10, None)
    return ops.log(x_safe)


def safe_sqrt(x):
    """Safe sqrt - handle negative."""
    if isinstance(x, (pd.DataFrame, pd.Series)):
        x_safe = x.clip(lower=0)
    else:
        x_safe = np.clip(x, 0, None)
    return ops.sqrt(x_safe)


def safe_returns(x, period=1):
    """Safe returns with fill_na."""
    result = ops.returns(x, period)
    return ops.fill_na(result, 0)


def safe_ts_zscore(x, window):
    """Safe ts_zscore with inf/nan handling."""
    result = ops.ts_zscore(x, window)
    result = ops.replace_inf(result)
    return ops.fill_na(result, 0)


def safe_ts_std(x, window):
    """Safe ts_std with minimum value."""
    result = ops.ts_std(x, window)
    if isinstance(result, (pd.Series, pd.DataFrame)):
        return result.clip(lower=1e-10)
    return np.clip(result, 1e-10, None)


# ============================================================================
# Safe CS Wrappers (cross-sectional operations)
# ============================================================================

def safe_cs_rank(x):
    """Safe cross-sectional rank."""
    result = ops.cs_rank(x)
    return ops.fill_na(result, 0.5)


def safe_cs_zscore(x):
    """Safe cross-sectional z-score."""
    result = ops.cs_zscore(x)
    result = ops.replace_inf(result)
    return ops.fill_na(result, 0)


def safe_cs_demean(x):
    """Safe cross-sectional demean."""
    result = ops.cs_demean(x)
    return ops.fill_na(result, 0)


def safe_cs_scale(x):
    """Safe cross-sectional scale."""
    result = ops.cs_scale(x)
    result = ops.replace_inf(result)
    return ops.fill_na(result, 0)


def safe_cs_normalize(x):
    """Safe cross-sectional normalize."""
    result = ops.cs_normalize(x)
    return ops.fill_na(result, 0.5)


def safe_cs_rank_signed(x):
    """Safe cross-sectional rank signed [-1, 1]."""
    result = ops.cs_rank_signed(x)
    return ops.fill_na(result, 0)


def safe_cs_softmax(x, tau=1.0):
    """Safe cross-sectional softmax."""
    result = ops.cs_softmax(x, tau)
    result = ops.replace_inf(result)
    return ops.fill_na(result, 0)


def safe_cs_long_short(x, n=None, pct=None):
    """Safe cross-sectional long-short position."""
    result = ops.cs_long_short(x, n=n, pct=pct)
    return ops.fill_na(result, 0)


def safe_cs_winsor(x, lower=0.05, upper=0.95):
    """Safe cross-sectional winsorization."""
    result = ops.cs_winsor(x, lower, upper)
    return ops.fill_na(result, 0)


def safe_cs_clip(x, n_std=3.0):
    """Safe cross-sectional clipping."""
    result = ops.cs_clip(x, n_std)
    return ops.fill_na(result, 0)


# ============================================================================
# Unified Primitive Set - Supports both TS and CS operators on Panel Data
# ============================================================================

def create_primitive_set(
    available_columns: List[str] = None,
    include_ts_ops: bool = True,
    include_cs_ops: bool = True,
) -> gp.PrimitiveSet:
    """
    Create DEAP primitive set with TS and CS operators for Panel Data.

    All operators work on DataFrame format (rows=timestamps, columns=assets):
    - ts_* operators: Apply to each column independently
    - cs_* operators: Apply across columns at each row

    Args:
        available_columns: List of available column names in data
        include_ts_ops: Whether to include time-series operators (default True)
        include_cs_ops: Whether to include cross-sectional operators (default True)

    Returns:
        DEAP PrimitiveSet instance
    """
    if available_columns is None:
        available_columns = ['Close', 'Open', 'High', 'Low', 'Volume', 'return']

    pset = gp.PrimitiveSet("FACTOR", 0)

    # ========================================================================
    # Time Series Operators (ts_*) - work on each asset independently
    # ========================================================================
    if include_ts_ops:
        # ts_mean
        for w in [3, 5, 10, 15, 20, 30, 60, 120, 240, 480, 720]:
            pset.addPrimitive(
                partial(ops.ts_mean, window=w),
                1, name=f"ops.ts_mean_{w}"
            )

        # ts_sum
        for w in [3, 5, 10, 20, 60, 120, 240, 720]:
            pset.addPrimitive(
                partial(ops.ts_sum, window=w),
                1, name=f"ops.ts_sum_{w}"
            )

        # ts_std
        for w in [5, 10, 20, 30, 60, 120, 240, 480, 720]:
            pset.addPrimitive(
                partial(safe_ts_std, window=w),
                1, name=f"ops.ts_std_{w}"
            )

        # ts_var
        for w in [10, 20, 60, 120, 240, 720]:
            pset.addPrimitive(
                partial(ops.ts_var, window=w),
                1, name=f"ops.ts_var_{w}"
            )

        # ts_zscore - KEY OPERATOR for signal generation
        for w in [20, 30, 60, 120, 240, 360, 480, 720, 1440]:
            pset.addPrimitive(
                partial(safe_ts_zscore, window=w),
                1, name=f"ops.ts_zscore_{w}"
            )

        # ts_rank
        for w in [10, 20, 30, 60, 120, 240, 480, 720]:
            pset.addPrimitive(
                partial(ops.ts_rank, window=w),
                1, name=f"ops.ts_rank_{w}"
            )

        # ts_skew
        for w in [30, 60, 120, 240, 480, 720]:
            pset.addPrimitive(
                partial(ops.ts_skew, window=w),
                1, name=f"ops.ts_skew_{w}"
            )

        # ts_kurt
        for w in [30, 60, 120, 240, 480, 720]:
            pset.addPrimitive(
                partial(ops.ts_kurt, window=w),
                1, name=f"ops.ts_kurt_{w}"
            )

        # ts_min
        for w in [10, 20, 60, 120, 240, 720]:
            pset.addPrimitive(
                partial(ops.ts_min, window=w),
                1, name=f"ops.ts_min_{w}"
            )

        # ts_max
        for w in [10, 20, 60, 120, 240, 720]:
            pset.addPrimitive(
                partial(ops.ts_max, window=w),
                1, name=f"ops.ts_max_{w}"
            )

        # ts_slope - Trend detection
        for w in [10, 20, 30, 60, 120, 240]:
            pset.addPrimitive(
                partial(ops.ts_slope, window=w),
                1, name=f"ops.ts_slope_{w}"
            )

        # ts_median
        for w in [10, 20, 60, 120, 240]:
            pset.addPrimitive(
                partial(ops.ts_median, window=w),
                1, name=f"ops.ts_median_{w}"
            )

        # ts_minmax_norm - Output in [0,1]
        for w in [30, 60, 120, 240, 720]:
            pset.addPrimitive(
                partial(ops.ts_minmax_norm, window=w),
                1, name=f"ops.ts_minmax_norm_{w}"
            )

        # ts_rank_signed - Output in [-1,1]
        for w in [30, 60, 120, 240, 720]:
            pset.addPrimitive(
                partial(ops.ts_rank_signed, window=w),
                1, name=f"ops.ts_rank_signed_{w}"
            )

        # ====================================================================
        # Decay Weighted Operators
        # ====================================================================

        # decay_linear
        for w in [3, 5, 10, 15, 20, 30, 60, 120]:
            pset.addPrimitive(
                partial(ops.decay_linear, window=w),
                1, name=f"ops.decay_linear_{w}"
            )

        # ts_ema
        for alpha in [2, 3, 5, 10, 20, 50, 100]:
            pset.addPrimitive(
                partial(ops.ts_ema, alpha=float(alpha)),
                1, name=f"ops.ts_ema_{alpha}"
            )

        # ====================================================================
        # Time Position Operators
        # ====================================================================

        # highday
        for w in [10, 20, 60, 120, 240, 720]:
            pset.addPrimitive(
                partial(ops.highday, window=w),
                1, name=f"ops.highday_{w}"
            )

        # lowday
        for w in [10, 20, 60, 120, 240, 720]:
            pset.addPrimitive(
                partial(ops.lowday, window=w),
                1, name=f"ops.lowday_{w}"
            )

        # ====================================================================
        # Returns and Delay - Key operators for momentum
        # ====================================================================

        # returns
        for p in [1, 2, 3, 5, 10, 15, 20, 30, 60]:
            pset.addPrimitive(
                partial(safe_returns, period=p),
                1, name=f"ops.returns_{p}"
            )

        # delay
        for p in [1, 2, 3, 5, 10, 20, 30, 60]:
            pset.addPrimitive(
                partial(ops.delay, period=p),
                1, name=f"ops.delay_{p}"
            )

        # delta
        for p in [1, 2, 3, 5, 10, 20, 30, 60]:
            pset.addPrimitive(
                partial(ops.delta, period=p),
                1, name=f"ops.delta_{p}"
            )

    # ========================================================================
    # Cross-Sectional Operators (cs_*) - work across assets at each timestamp
    # ========================================================================
    if include_cs_ops:
        # Core CS Operators (unary)
        pset.addPrimitive(safe_cs_rank, 1, name="ops.cs_rank")
        pset.addPrimitive(safe_cs_zscore, 1, name="ops.cs_zscore")
        pset.addPrimitive(safe_cs_demean, 1, name="ops.cs_demean")
        pset.addPrimitive(safe_cs_scale, 1, name="ops.cs_scale")
        pset.addPrimitive(safe_cs_normalize, 1, name="ops.cs_normalize")
        pset.addPrimitive(safe_cs_rank_signed, 1, name="ops.cs_rank_signed")

        # CS with parameters
        for tau in [0.5, 1.0, 2.0]:
            pset.addPrimitive(
                partial(safe_cs_softmax, tau=tau),
                1, name=f"ops.cs_softmax_{tau}"
            )

        # CS long-short positions
        for n in [1, 2, 3]:
            pset.addPrimitive(
                partial(safe_cs_long_short, n=n),
                1, name=f"ops.cs_long_short_{n}"
            )

        # CS winsorization
        pset.addPrimitive(
            partial(safe_cs_winsor, lower=0.05, upper=0.95),
            1, name="ops.cs_winsor"
        )

        # CS clipping
        for n_std in [2.0, 3.0]:
            pset.addPrimitive(
                partial(safe_cs_clip, n_std=n_std),
                1, name=f"ops.cs_clip_{n_std}"
            )

    # ========================================================================
    # Binary Operators
    # ========================================================================

    pset.addPrimitive(ops.add, 2, name="ops.add")
    pset.addPrimitive(ops.subtract, 2, name="ops.subtract")
    pset.addPrimitive(ops.multiply, 2, name="ops.multiply")
    pset.addPrimitive(safe_divide, 2, name="ops.divide")

    # ========================================================================
    # Unary Operators
    # ========================================================================

    pset.addPrimitive(ops.abs, 1, name="ops.abs")
    pset.addPrimitive(ops.sign, 1, name="ops.sign")
    pset.addPrimitive(lambda x: -x, 1, name="neg")
    pset.addPrimitive(safe_log, 1, name="ops.log")
    pset.addPrimitive(safe_sqrt, 1, name="ops.sqrt")
    pset.addPrimitive(ops.square, 1, name="ops.square")

    # ========================================================================
    # Clip Operators
    # ========================================================================

    pset.addPrimitive(
        partial(ops.clip, min_val=-3, max_val=3),
        1, name="ops.clip_3"
    )
    pset.addPrimitive(
        partial(ops.clip, min_val=-2, max_val=2),
        1, name="ops.clip_2"
    )
    pset.addPrimitive(
        partial(ops.clip, min_val=-1, max_val=1),
        1, name="ops.clip_1"
    )

    # ========================================================================
    # Filter Range
    # ========================================================================

    pset.addPrimitive(
        partial(ops.filter_range, min_val=-2, max_val=2),
        1, name="ops.filter_range_2"
    )
    pset.addPrimitive(
        partial(ops.filter_range, min_val=-1.5, max_val=1.5),
        1, name="ops.filter_range_1.5"
    )

    # ========================================================================
    # Data Processing
    # ========================================================================

    pset.addPrimitive(
        partial(ops.fill_na, value_or_method=0),
        1, name="ops.fill_na"
    )
    pset.addPrimitive(ops.replace_inf, 1, name="ops.replace_inf")

    # ========================================================================
    # Terminals - Column References
    # ========================================================================

    for col in available_columns:
        pset.addTerminal(col, name=col)

    return pset


# ============================================================================
# Panel Data Utilities - 支持 PanelData 和 data_dict 两种输入格式
# ============================================================================

def build_panel_data(data, column: str) -> pd.DataFrame:
    """
    Build panel data (DataFrame) from PanelData or data_dict.

    Args:
        data: PanelData object OR Dict of instrument -> DataFrame
        column: Column name to extract (e.g., 'Close', 'return')

    Returns:
        DataFrame with:
        - rows = timestamps (aligned across all assets)
        - columns = asset names
    """
    # Check if it's a PanelData object
    if hasattr(data, '__getitem__') and hasattr(data, 'columns'):
        # It's a PanelData object
        try:
            return data[column]
        except (KeyError, AttributeError):
            raise ValueError(f"Column '{column}' not found in PanelData")

    # It's a data_dict
    panel_dict = {}
    for inst, df in data.items():
        if column in df.columns:
            panel_dict[inst] = df[column]

    if not panel_dict:
        raise ValueError(f"Column '{column}' not found in any instrument")

    # Combine into panel DataFrame (automatically aligns on index)
    panel_df = pd.DataFrame(panel_dict)
    return panel_df


def build_all_panels(data, columns: List[str] = None) -> Dict[str, pd.DataFrame]:
    """
    Build panel DataFrames for all specified columns.

    Args:
        data: PanelData object OR Dict of instrument -> DataFrame
        columns: List of columns to extract (default: auto-detect)

    Returns:
        Dict of column_name -> panel DataFrame
    """
    # Check if it's a PanelData object
    if hasattr(data, 'columns') and hasattr(data, '__getitem__'):
        # It's a PanelData object
        if columns is None:
            # 使用 PanelData 的 columns 属性
            columns = data.columns

        panels = {}
        for col in columns:
            try:
                panel_df = data[col]
                if panel_df is not None and not panel_df.empty:
                    panels[col] = panel_df
            except (KeyError, AttributeError):
                continue
        return panels

    # It's a data_dict
    if columns is None:
        # Auto-detect common columns
        sample_df = next(iter(data.values()))
        candidate_cols = ['Close', 'Open', 'High', 'Low', 'Volume', 'return',
                          'QuoteAssetVolume', 'TakerBuyBaseAssetVolume']
        columns = [c for c in candidate_cols if c in sample_df.columns]

    panels = {}
    for col in columns:
        try:
            panels[col] = build_panel_data(data, col)
        except ValueError:
            continue

    return panels


def panel_to_dict(panel_df: pd.DataFrame) -> Dict[str, pd.Series]:
    """
    Convert panel DataFrame back to dict of Series.

    Args:
        panel_df: DataFrame (rows=timestamps, columns=assets)

    Returns:
        Dict of asset -> Series
    """
    return {col: panel_df[col] for col in panel_df.columns}


def get_available_columns(data) -> List[str]:
    """
    Get available columns from PanelData or data_dict.

    Args:
        data: PanelData object OR Dict of instrument -> DataFrame

    Returns:
        List of column names
    """
    # Check if it's a PanelData object
    if hasattr(data, 'columns'):
        return list(data.columns)

    # It's a data_dict
    sample_df = next(iter(data.values()))
    return list(sample_df.columns)


# ============================================================================
# Expression Evaluation - Unified for Panel Data
# ============================================================================

def evaluate_expression(
    individual,
    panel_data: Dict[str, pd.DataFrame],
    pset: gp.PrimitiveSet,
    normalize: bool = True,
    zscore_window: int = 1440,
    clip_range: float = 3.0,
) -> pd.DataFrame:
    """
    Evaluate a GP expression tree against panel data.

    Supports BOTH time-series and cross-sectional operators.

    Data flow:
    - Terminal (column name) -> Get DataFrame from panel_data[col]
    - TS operators (ts_*) -> Apply to each column independently, return DataFrame
    - CS operators (cs_*) -> Apply across columns at each row, return DataFrame
    - Binary operators -> Element-wise on DataFrames, return DataFrame

    Args:
        individual: DEAP individual (expression tree)
        panel_data: Dict of column_name -> panel DataFrame (rows=timestamps, cols=assets)
        pset: Primitive set
        normalize: Whether to normalize output (zscore + clip)
        zscore_window: Window for rolling zscore normalization
        clip_range: Clip range for final output

    Returns:
        pd.DataFrame with factor values (rows=timestamps, cols=assets)
    """
    try:
        # Get reference DataFrame for shape info
        ref_df = next(iter(panel_data.values()))
        index = ref_df.index
        columns = ref_df.columns

        # Use stack-based evaluation (DEAP trees are in prefix notation)
        stack = []

        # Iterate in reverse order (right to left for prefix notation)
        for node in reversed(individual):
            if isinstance(node, gp.Terminal):
                # Terminal: get panel DataFrame or constant
                value = node.value
                if isinstance(value, str) and value in panel_data:
                    stack.append(panel_data[value].copy())
                elif isinstance(value, str):
                    # Column not found - return zeros
                    stack.append(pd.DataFrame(0.0, index=index, columns=columns))
                else:
                    # Constant value - broadcast to DataFrame
                    stack.append(pd.DataFrame(value, index=index, columns=columns))

            elif isinstance(node, gp.Primitive):
                # Primitive: pop arguments, apply function, push result
                args = []
                for _ in range(node.arity):
                    if stack:
                        args.append(stack.pop())
                    else:
                        # Stack underflow - push zeros
                        args.append(pd.DataFrame(0.0, index=index, columns=columns))

                # Get the actual function from pset.context
                func = pset.context[node.name]

                try:
                    result = func(*args)

                    # Ensure result is DataFrame
                    if isinstance(result, pd.Series):
                        # CS aggregate operations return Series - broadcast to DataFrame
                        result = pd.DataFrame(
                            np.tile(result.values.reshape(-1, 1), (1, len(columns))),
                            index=index,
                            columns=columns
                        )
                    elif isinstance(result, (int, float)):
                        result = pd.DataFrame(result, index=index, columns=columns)
                    elif isinstance(result, np.ndarray):
                        if result.ndim == 1:
                            result = pd.DataFrame(
                                np.tile(result.reshape(-1, 1), (1, len(columns))),
                                index=index,
                                columns=columns
                            )
                        else:
                            result = pd.DataFrame(result, index=index, columns=columns)

                    stack.append(result)

                except Exception as e:
                    # On error, push zero DataFrame
                    stack.append(pd.DataFrame(0.0, index=index, columns=columns))

        # Final result should be on stack
        if not stack:
            return pd.DataFrame(0.0, index=index, columns=columns)

        result = stack[0]

        # Ensure result is DataFrame
        if isinstance(result, pd.Series):
            result = pd.DataFrame(
                np.tile(result.values.reshape(-1, 1), (1, len(columns))),
                index=index,
                columns=columns
            )
        elif not isinstance(result, pd.DataFrame):
            result = pd.DataFrame(result, index=index, columns=columns)

        # ============================================================
        # NORMALIZATION: Apply to each column (asset) independently
        # ============================================================
        if normalize:
            # Step 1: Replace inf/-inf with NaN, then fill with 0
            result = ops.replace_inf(result)
            result = ops.fill_na(result, 0)

            # Step 2: Rolling z-score normalization (per asset)
            result = ops.ts_zscore(result, zscore_window)

            # Step 3: Replace any inf from zscore, fill with 0
            result = ops.replace_inf(result)
            result = ops.fill_na(result, 0)

            # Step 4: Clip to [-clip_range, clip_range]
            result = ops.clip(result, -clip_range, clip_range)

            # Step 5: Final NaN fill
            result = ops.fill_na(result, 0)

        else:
            # Even without normalization, ensure no inf/nan
            result = ops.replace_inf(result)
            result = ops.fill_na(result, 0)

        return result

    except Exception as e:
        # On error, return all zeros
        ref_df = next(iter(panel_data.values()))
        return pd.DataFrame(0.0, index=ref_df.index, columns=ref_df.columns)


def tree_to_expression_string(individual, pset: gp.PrimitiveSet = None) -> str:
    """
    Convert expression tree to readable string.

    Args:
        individual: DEAP individual
        pset: Primitive set (optional)

    Returns:
        String representation of the expression
    """
    return str(individual)


def expression_to_code(expression_str: str) -> str:
    """
    Convert GP expression string to Python code using ops.

    Args:
        expression_str: Expression like "ops.ts_mean_20(Close)"

    Returns:
        Python code string
    """
    code = expression_str

    # Standard columns
    columns = [
        'Close', 'Open', 'High', 'Low', 'Volume',
        'return', 'QuoteAssetVolume',
        'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume',
        'NumberOfTrades',
    ]

    for col in columns:
        # Replace standalone column names with panel_data['col']
        code = code.replace(f"({col})", f"(panel_data['{col}'])")
        code = code.replace(f", {col})", f", panel_data['{col}'])")
        if code.startswith(col):
            code = f"panel_data['{col}']" + code[len(col):]

    return code


__all__ = [
    # Primitive set creation
    'create_primitive_set',
    # Expression evaluation
    'evaluate_expression',
    # Panel data utilities
    'build_panel_data',
    'build_all_panels',
    'panel_to_dict',
    'get_available_columns',
    # Expression utilities
    'tree_to_expression_string',
    'expression_to_code',
    # Window constants
    'SHORT_WINDOWS',
    'MEDIUM_WINDOWS',
    'LONG_WINDOWS',
    'ALL_WINDOWS',
    'EMA_ALPHAS',
    'CS_LONG_SHORT_N',
    'CS_SOFTMAX_TAU',
]
