"""
Factor Exporter - Using ops.xxx format for Panel Data

Export discovered factors to factorlib format for production use.
All generated code uses ops.xxx calling convention and works on Panel Data
(DataFrame: rows=timestamps, columns=assets).

Generates:
1. FactorBase class definition for library.py
2. Standalone factor function
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class ExportedFactor:
    """Exported factor information."""
    name: str
    expression: str
    class_code: str
    function_code: str
    description: str = ""
    category: str = "gp_mined"
    sharpe: float = 0.0
    ic: float = 0.0
    rank_ic: float = 0.0
    returns: float = 0.0
    turnover: float = 0.0


def detect_required_columns(expression: str) -> list:
    """Detect required columns from expression."""
    all_columns = [
        'Close', 'Open', 'High', 'Low', 'Volume',
        'QuoteAssetVolume', 'return',
        'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume',
        'TakerBuyQuoteAssetVolume', 'TakerSellQuoteAssetVolume',
        'NumberOfTrades',
    ]

    found = []
    for col in all_columns:
        if col in expression:
            found.append(col)

    return found if found else ['Close']


def detect_operator_types(expression: str) -> dict:
    """Detect which operator types are used in the expression."""
    has_ts = bool(re.search(r'ops\.ts_|ops\.decay_|ops\.delay|ops\.delta|ops\.returns|ops\.highday|ops\.lowday', expression))
    has_cs = bool(re.search(r'ops\.cs_', expression))

    return {
        'has_ts': has_ts,
        'has_cs': has_cs,
        'is_hybrid': has_ts and has_cs,
    }


def convert_expression_to_factor_func(expression: str) -> str:
    """
    Convert GP expression to factor_func code using ops.

    Args:
        expression: GP expression like "ops.ts_mean_20(Close)"

    Returns:
        factor_func method code
    """
    columns = detect_required_columns(expression)
    op_types = detect_operator_types(expression)

    # Build column variable assignments
    col_lines = []
    col_map = {}
    for col in columns:
        if col == 'return':
            var_name = 'ret'
        elif col == 'Open':
            var_name = 'open_'
        else:
            var_name = col.lower()
        col_map[col] = var_name
        col_lines.append(f"        {var_name} = panel_data['{col}']")

    col_code = '\n'.join(col_lines)

    # Convert expression
    result_expr = expression
    for col, var in col_map.items():
        result_expr = re.sub(rf'\b{col}\b', var, result_expr)

    # Convert ops.xxx_N format to ops.xxx(x, N)
    patterns = [
        # Time series with window
        (r'ops\.ts_mean_(\d+)\(([^)]+)\)', r'ops.ts_mean(\2, \1)'),
        (r'ops\.ts_sum_(\d+)\(([^)]+)\)', r'ops.ts_sum(\2, \1)'),
        (r'ops\.ts_std_(\d+)\(([^)]+)\)', r'ops.ts_std(\2, \1)'),
        (r'ops\.ts_var_(\d+)\(([^)]+)\)', r'ops.ts_var(\2, \1)'),
        (r'ops\.ts_zscore_(\d+)\(([^)]+)\)', r'ops.ts_zscore(\2, \1)'),
        (r'ops\.ts_rank_(\d+)\(([^)]+)\)', r'ops.ts_rank(\2, \1)'),
        (r'ops\.ts_skew_(\d+)\(([^)]+)\)', r'ops.ts_skew(\2, \1)'),
        (r'ops\.ts_kurt_(\d+)\(([^)]+)\)', r'ops.ts_kurt(\2, \1)'),
        (r'ops\.ts_min_(\d+)\(([^)]+)\)', r'ops.ts_min(\2, \1)'),
        (r'ops\.ts_max_(\d+)\(([^)]+)\)', r'ops.ts_max(\2, \1)'),
        (r'ops\.ts_slope_(\d+)\(([^)]+)\)', r'ops.ts_slope(\2, \1)'),
        (r'ops\.ts_median_(\d+)\(([^)]+)\)', r'ops.ts_median(\2, \1)'),
        (r'ops\.ts_minmax_norm_(\d+)\(([^)]+)\)', r'ops.ts_minmax_norm(\2, \1)'),
        (r'ops\.ts_rank_signed_(\d+)\(([^)]+)\)', r'ops.ts_rank_signed(\2, \1)'),
        # Decay weighted
        (r'ops\.decay_linear_(\d+)\(([^)]+)\)', r'ops.decay_linear(\2, \1)'),
        (r'ops\.ts_ema_(\d+)\(([^)]+)\)', r'ops.ts_ema(\2, \1)'),
        # Time position
        (r'ops\.highday_(\d+)\(([^)]+)\)', r'ops.highday(\2, \1)'),
        (r'ops\.lowday_(\d+)\(([^)]+)\)', r'ops.lowday(\2, \1)'),
        # Returns/Delay
        (r'ops\.returns_(\d+)\(([^)]+)\)', r'ops.returns(\2, \1)'),
        (r'ops\.delay_(\d+)\(([^)]+)\)', r'ops.delay(\2, \1)'),
        (r'ops\.delta_(\d+)\(([^)]+)\)', r'ops.delta(\2, \1)'),
        # Clip
        (r'ops\.clip_3\(([^)]+)\)', r'ops.clip(\1, -3, 3)'),
        (r'ops\.clip_2\(([^)]+)\)', r'ops.clip(\1, -2, 2)'),
        (r'ops\.clip_1\(([^)]+)\)', r'ops.clip(\1, -1, 1)'),
        # Filter range
        (r'ops\.filter_range_2\(([^)]+)\)', r'ops.filter_range(\1, -2, 2)'),
        (r'ops\.filter_range_1\.5\(([^)]+)\)', r'ops.filter_range(\1, -1.5, 1.5)'),
        # CS with parameters
        (r'ops\.cs_softmax_([0-9.]+)\(([^)]+)\)', r'ops.cs_softmax(\2, tau=\1)'),
        (r'ops\.cs_long_short_(\d+)\(([^)]+)\)', r'ops.cs_long_short(\2, n=\1)'),
        (r'ops\.cs_clip_([0-9.]+)\(([^)]+)\)', r'ops.cs_clip(\2, n_std=\1)'),
    ]

    for pattern, replacement in patterns:
        result_expr = re.sub(pattern, replacement, result_expr)

    # Determine operator type description
    if op_types['is_hybrid']:
        op_desc = "Hybrid (TS + CS)"
    elif op_types['has_cs']:
        op_desc = "Cross-sectional (CS)"
    else:
        op_desc = "Time-series (TS)"

    # Build factor_func with normalization
    code = f'''    def factor_func(self, panel_data, ops, normalize=True, zscore_window=1440, clip_range=3.0):
        """
        Compute factor values on Panel Data (DataFrame: rows=timestamps, cols=assets).

        Operator type: {op_desc}

        Output is normalized to [-clip_range, clip_range]:
        1. Replace inf/-inf with 0
        2. Fill NaN with 0
        3. Rolling z-score normalization
        4. Clip to bounded range
        5. Final NaN fill with 0

        GUARANTEED: No NaN, No inf in output. All values in [-clip_range, clip_range].

        Args:
            panel_data: Dict of column_name -> DataFrame (rows=timestamps, cols=assets)
            ops: Operators module
            normalize: Whether to normalize output
            zscore_window: Window for rolling zscore
            clip_range: Clip range for final output

        Returns:
            DataFrame with factor values (rows=timestamps, cols=assets)
        """
        import numpy as np
{col_code}
        result = {result_expr}

        # Normalize to [-clip_range, clip_range], no NaN/inf allowed
        if normalize:
            result = ops.replace_inf(result)
            result = ops.fill_na(result, 0)
            result = ops.ts_zscore(result, zscore_window)
            result = ops.replace_inf(result)
            result = ops.fill_na(result, 0)
            result = ops.clip(result, -clip_range, clip_range)
            result = ops.fill_na(result, 0)
        else:
            result = ops.replace_inf(result)
            result = ops.fill_na(result, 0)

        return result'''

    return code


def generate_factor_class(
    name: str,
    expression: str,
    description: str = "",
    category: str = "gp_mined",
    metrics: Dict[str, float] = None,
) -> str:
    """
    Generate a FactorBase class definition using ops for Panel Data.

    Args:
        name: Factor name (snake_case)
        expression: GP expression
        description: Factor description
        category: Factor category
        metrics: Performance metrics dict

    Returns:
        Python class definition code
    """
    class_name = ''.join(word.capitalize() for word in name.split('_')) + 'Factor'

    columns = detect_required_columns(expression)
    op_types = detect_operator_types(expression)

    factor_func = convert_expression_to_factor_func(expression)

    # Format metrics comment
    metrics_comment = ""
    if metrics:
        metrics_comment = f'''
    # Performance (backtested on Panel Data):
    # Sharpe: {metrics.get('sharpe', 0):.4f}
    # IC: {metrics.get('ic', 0):.4f}
    # Rank IC: {metrics.get('rank_ic', 0):.4f}
    # Returns: {metrics.get('returns', 0):.2f}%
    # Turnover: {metrics.get('turnover', 0):.0f}
'''

    # Operator type description
    if op_types['is_hybrid']:
        op_type_str = "Hybrid (TS + CS)"
    elif op_types['has_cs']:
        op_type_str = "Cross-sectional (CS)"
    else:
        op_type_str = "Time-series (TS)"

    code = f'''
@library.register
class {class_name}(FactorBase):
    """
    {description or f'GP-discovered factor: {name}'}

    Expression: {expression}
    Operator Type: {op_type_str}
    Category: {category}
    Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

    Works on Panel Data (DataFrame: rows=timestamps, columns=assets)
    """

    name = "{name}"
    description = "{description or 'GP-discovered factor'}"
    category = "{category}"
    require = {columns}
{metrics_comment}
{factor_func}
'''

    return code


def generate_standalone_function(
    name: str,
    expression: str,
) -> str:
    """
    Generate a standalone factor function using ops for Panel Data.

    Args:
        name: Factor name
        expression: GP expression

    Returns:
        Python function code
    """
    columns = detect_required_columns(expression)
    op_types = detect_operator_types(expression)

    # Build column variable assignments
    col_lines = []
    col_map = {}
    for col in columns:
        if col == 'return':
            var_name = 'ret'
        elif col == 'Open':
            var_name = 'open_'
        else:
            var_name = col.lower()
        col_map[col] = var_name
        col_lines.append(f"    {var_name} = panel_data['{col}']")

    col_code = '\n'.join(col_lines)

    # Convert expression
    result_expr = expression
    for col, var in col_map.items():
        result_expr = re.sub(rf'\b{col}\b', var, result_expr)

    # Convert ops.xxx_N format
    patterns = [
        (r'ops\.ts_mean_(\d+)\(([^)]+)\)', r'ops.ts_mean(\2, \1)'),
        (r'ops\.ts_sum_(\d+)\(([^)]+)\)', r'ops.ts_sum(\2, \1)'),
        (r'ops\.ts_std_(\d+)\(([^)]+)\)', r'ops.ts_std(\2, \1)'),
        (r'ops\.ts_var_(\d+)\(([^)]+)\)', r'ops.ts_var(\2, \1)'),
        (r'ops\.ts_zscore_(\d+)\(([^)]+)\)', r'ops.ts_zscore(\2, \1)'),
        (r'ops\.ts_rank_(\d+)\(([^)]+)\)', r'ops.ts_rank(\2, \1)'),
        (r'ops\.ts_skew_(\d+)\(([^)]+)\)', r'ops.ts_skew(\2, \1)'),
        (r'ops\.ts_kurt_(\d+)\(([^)]+)\)', r'ops.ts_kurt(\2, \1)'),
        (r'ops\.ts_min_(\d+)\(([^)]+)\)', r'ops.ts_min(\2, \1)'),
        (r'ops\.ts_max_(\d+)\(([^)]+)\)', r'ops.ts_max(\2, \1)'),
        (r'ops\.ts_slope_(\d+)\(([^)]+)\)', r'ops.ts_slope(\2, \1)'),
        (r'ops\.ts_median_(\d+)\(([^)]+)\)', r'ops.ts_median(\2, \1)'),
        (r'ops\.ts_minmax_norm_(\d+)\(([^)]+)\)', r'ops.ts_minmax_norm(\2, \1)'),
        (r'ops\.ts_rank_signed_(\d+)\(([^)]+)\)', r'ops.ts_rank_signed(\2, \1)'),
        (r'ops\.decay_linear_(\d+)\(([^)]+)\)', r'ops.decay_linear(\2, \1)'),
        (r'ops\.ts_ema_(\d+)\(([^)]+)\)', r'ops.ts_ema(\2, \1)'),
        (r'ops\.highday_(\d+)\(([^)]+)\)', r'ops.highday(\2, \1)'),
        (r'ops\.lowday_(\d+)\(([^)]+)\)', r'ops.lowday(\2, \1)'),
        (r'ops\.returns_(\d+)\(([^)]+)\)', r'ops.returns(\2, \1)'),
        (r'ops\.delay_(\d+)\(([^)]+)\)', r'ops.delay(\2, \1)'),
        (r'ops\.delta_(\d+)\(([^)]+)\)', r'ops.delta(\2, \1)'),
        (r'ops\.clip_3\(([^)]+)\)', r'ops.clip(\1, -3, 3)'),
        (r'ops\.clip_2\(([^)]+)\)', r'ops.clip(\1, -2, 2)'),
        (r'ops\.clip_1\(([^)]+)\)', r'ops.clip(\1, -1, 1)'),
        (r'ops\.filter_range_2\(([^)]+)\)', r'ops.filter_range(\1, -2, 2)'),
        (r'ops\.filter_range_1\.5\(([^)]+)\)', r'ops.filter_range(\1, -1.5, 1.5)'),
        (r'ops\.cs_softmax_([0-9.]+)\(([^)]+)\)', r'ops.cs_softmax(\2, tau=\1)'),
        (r'ops\.cs_long_short_(\d+)\(([^)]+)\)', r'ops.cs_long_short(\2, n=\1)'),
        (r'ops\.cs_clip_([0-9.]+)\(([^)]+)\)', r'ops.cs_clip(\2, n_std=\1)'),
    ]

    for pattern, replacement in patterns:
        result_expr = re.sub(pattern, replacement, result_expr)

    # Operator type description
    if op_types['is_hybrid']:
        op_type_str = "Hybrid (TS + CS)"
    elif op_types['has_cs']:
        op_type_str = "Cross-sectional (CS)"
    else:
        op_type_str = "Time-series (TS)"

    code = f'''
def {name}(
    panel_data: Dict[str, pd.DataFrame],
    normalize: bool = True,
    zscore_window: int = 1440,
    clip_range: float = 3.0
) -> pd.DataFrame:
    """
    GP-discovered factor: {name}

    Expression: {expression}
    Operator Type: {op_type_str}

    Works on Panel Data (DataFrame: rows=timestamps, columns=assets)
    - ts_* operators: Apply to each column independently
    - cs_* operators: Apply across columns at each row

    Output is normalized to [-clip_range, clip_range] (default [-3, 3]):
    1. Replace inf/-inf with 0
    2. Fill NaN with 0
    3. Rolling z-score normalization
    4. Clip to bounded range
    5. Final NaN fill with 0

    GUARANTEED: No NaN, No inf in output. All values in [-clip_range, clip_range].

    Args:
        panel_data: Dict of column_name -> DataFrame (rows=timestamps, cols=assets)
                    Required columns: {columns}
        normalize: Whether to normalize output (zscore + clip), default True
        zscore_window: Window for rolling zscore, default 1440 (1 day for 1-min data)
        clip_range: Clip range, default 3.0 (clips to [-3, 3])

    Returns:
        DataFrame with factor values (rows=timestamps, cols=assets)
    """
    from factorlib.utils.operators import ops
    import numpy as np
    import pandas as pd
    from typing import Dict

{col_code}

    result = {result_expr}

    # Post-processing: normalize to [-clip_range, clip_range], no NaN/inf allowed
    if isinstance(result, pd.DataFrame):
        result = ops.replace_inf(result)
        result = ops.fill_na(result, 0)

        if normalize:
            result = ops.ts_zscore(result, zscore_window)
            result = ops.replace_inf(result)
            result = ops.fill_na(result, 0)
            result = ops.clip(result, -clip_range, clip_range)
            result = ops.fill_na(result, 0)

    return result
'''

    return code


def export_factor(
    name: str,
    expression: str,
    description: str = "",
    category: str = "gp_mined",
    metrics: Dict[str, float] = None,
    output_format: str = "class"
) -> ExportedFactor:
    """
    Export a discovered factor.

    Args:
        name: Factor name
        expression: GP expression
        description: Factor description
        category: Factor category
        metrics: Performance metrics
        output_format: "class" or "function"

    Returns:
        ExportedFactor with generated code
    """
    class_code = generate_factor_class(name, expression, description, category, metrics)
    function_code = generate_standalone_function(name, expression)

    return ExportedFactor(
        name=name,
        expression=expression,
        class_code=class_code,
        function_code=function_code,
        description=description,
        category=category,
        sharpe=metrics.get('sharpe', 0) if metrics else 0,
        ic=metrics.get('ic', 0) if metrics else 0,
        rank_ic=metrics.get('rank_ic', 0) if metrics else 0,
        returns=metrics.get('returns', 0) if metrics else 0,
        turnover=metrics.get('turnover', 0) if metrics else 0,
    )


def print_factor_code(exported: ExportedFactor, format: str = "class"):
    """Print factor code for copy-paste."""
    print("=" * 60)
    print(f" Factor: {exported.name}")
    print("=" * 60)
    print(f"\nExpression: {exported.expression}")
    print(f"\nMetrics:")
    print(f"  Sharpe: {exported.sharpe:.4f}")
    print(f"  IC: {exported.ic:.4f}")
    print(f"  Rank IC: {exported.rank_ic:.4f}")
    print(f"  Returns: {exported.returns:.2f}%")
    print(f"  Turnover: {exported.turnover:.0f}")
    print("\n" + "=" * 60)

    if format == "class":
        print("\nClass Definition (add to library.py):")
        print("-" * 60)
        print(exported.class_code)
    else:
        print("\nStandalone Function:")
        print("-" * 60)
        print(exported.function_code)


__all__ = [
    'ExportedFactor',
    'export_factor',
    'generate_factor_class',
    'generate_standalone_function',
    'print_factor_code',
    'detect_required_columns',
    'detect_operator_types',
    'convert_expression_to_factor_func',
]
