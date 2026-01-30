"""
Dimension System for Factor Mining

Ensures dimensional consistency in factor expressions.
Prevents meaningless operations like adding price to volume.

Dimension Types:
- PRICE: Close, High, Low, Open (currency units)
- VOLUME: Volume, TakerBuyBaseAssetVolume, etc. (quantity units)
- QUOTE_VOLUME: QuoteAssetVolume (currency * quantity)
- RETURN: Price returns (dimensionless ratio)
- RATIO: Any dimensionless ratio
- SCALAR: Dimensionless scalar (1, constants)
- ANY: Can accept any dimension (for generic operations)
"""

from enum import Enum, auto
from typing import Union, Tuple, Optional
from dataclasses import dataclass


class Dimension(Enum):
    """Dimension types for factor inputs/outputs."""
    PRICE = auto()         # 价格类: Close, High, Low, Open
    VOLUME = auto()        # 成交量类: Volume, TakerBuyBaseAssetVolume
    QUOTE_VOLUME = auto()  # 成交额类: QuoteAssetVolume
    RETURN = auto()        # 收益率类: returns (无量纲)
    RATIO = auto()         # 比率类: 无量纲比率
    SCALAR = auto()        # 标量: 常数、窗口大小等
    ANY = auto()           # 任意: 可接受任何量纲
    TIME = auto()          # 时间类: highday, lowday 等
    COUNT = auto()         # 计数类: NumberOfTrades


@dataclass
class DimensionResult:
    """Result of a dimension operation."""
    dim: Dimension
    valid: bool
    message: str = ""


class DimensionTracker:
    """
    Track and validate dimensions through expression trees.

    Rules:
    1. Addition/Subtraction: Same dimension required
    2. Multiplication: Dimensions multiply (e.g., PRICE * VOLUME = QUOTE_VOLUME)
    3. Division: Returns RATIO for same dimensions, otherwise computed
    4. Time series ops (ts_*): Preserve input dimension
    5. Normalization ops (zscore, rank): Output RATIO
    6. Log/Exp: Output RATIO
    """

    # Column to dimension mapping
    COLUMN_DIMS = {
        # Price columns
        'Close': Dimension.PRICE,
        'Open': Dimension.PRICE,
        'High': Dimension.PRICE,
        'Low': Dimension.PRICE,

        # Volume columns
        'Volume': Dimension.VOLUME,
        'TakerBuyBaseAssetVolume': Dimension.VOLUME,
        'TakerSellBaseAssetVolume': Dimension.VOLUME,

        # Quote volume columns
        'QuoteAssetVolume': Dimension.QUOTE_VOLUME,
        'TakerBuyQuoteAssetVolume': Dimension.QUOTE_VOLUME,
        'TakerSellQuoteAssetVolume': Dimension.QUOTE_VOLUME,
        'vol_ccy_quote': Dimension.QUOTE_VOLUME,

        # Ratio/return columns
        'return': Dimension.RETURN,

        # Count columns
        'NumberOfTrades': Dimension.COUNT,
    }

    # Dimension multiplication table
    MULT_TABLE = {
        (Dimension.PRICE, Dimension.VOLUME): Dimension.QUOTE_VOLUME,
        (Dimension.VOLUME, Dimension.PRICE): Dimension.QUOTE_VOLUME,
        (Dimension.PRICE, Dimension.SCALAR): Dimension.PRICE,
        (Dimension.VOLUME, Dimension.SCALAR): Dimension.VOLUME,
        (Dimension.QUOTE_VOLUME, Dimension.SCALAR): Dimension.QUOTE_VOLUME,
        (Dimension.RETURN, Dimension.SCALAR): Dimension.RETURN,
        (Dimension.RATIO, Dimension.SCALAR): Dimension.RATIO,
        (Dimension.SCALAR, Dimension.SCALAR): Dimension.SCALAR,
        (Dimension.COUNT, Dimension.SCALAR): Dimension.COUNT,
    }

    # Operations that always return RATIO (dimensionless)
    RATIO_OPS = {
        'ts_zscore', 'ts_rank', 'ts_skew', 'ts_kurt',
        'cs_zscore', 'cs_rank', 'cs_demean',
        'log', 'exp', 'sign', 'abs',
        'correlation', 'covariance', 'beta',
        'ts_minmax_norm', 'ts_rank_signed', 'cs_rank_signed',
    }

    # Operations that preserve input dimension
    PRESERVE_OPS = {
        'ts_mean', 'ts_sum', 'ts_std', 'ts_var',
        'ts_min', 'ts_max', 'ts_median', 'ts_quantile',
        'ts_ema', 'decay_linear', 'ts_slope',
        'delay', 'delta', 'clip', 'fill_na', 'winsorize',
        'filter_range', 'replace_inf',
    }

    # Operations that return TIME dimension
    TIME_OPS = {
        'highday', 'lowday', 'ts_argmin', 'ts_argmax',
    }

    @classmethod
    def get_column_dim(cls, col_name: str) -> Dimension:
        """Get dimension of a column."""
        return cls.COLUMN_DIMS.get(col_name, Dimension.ANY)

    @classmethod
    def check_add_sub(cls, dim1: Dimension, dim2: Dimension) -> DimensionResult:
        """Check if addition/subtraction is valid."""
        # Same dimension or one is ANY/SCALAR
        if dim1 == dim2:
            return DimensionResult(dim1, True)
        if dim1 == Dimension.ANY:
            return DimensionResult(dim2, True)
        if dim2 == Dimension.ANY:
            return DimensionResult(dim1, True)
        if dim1 == Dimension.SCALAR:
            return DimensionResult(dim2, True)
        if dim2 == Dimension.SCALAR:
            return DimensionResult(dim1, True)
        # RATIO and RETURN are compatible
        if {dim1, dim2} == {Dimension.RATIO, Dimension.RETURN}:
            return DimensionResult(Dimension.RATIO, True)

        return DimensionResult(
            Dimension.ANY, False,
            f"Dimension mismatch in add/sub: {dim1.name} vs {dim2.name}"
        )

    @classmethod
    def check_multiply(cls, dim1: Dimension, dim2: Dimension) -> DimensionResult:
        """Check multiplication and compute result dimension."""
        # Check multiplication table
        key = (dim1, dim2)
        if key in cls.MULT_TABLE:
            return DimensionResult(cls.MULT_TABLE[key], True)

        # Reverse key
        rev_key = (dim2, dim1)
        if rev_key in cls.MULT_TABLE:
            return DimensionResult(cls.MULT_TABLE[rev_key], True)

        # ANY with anything
        if dim1 == Dimension.ANY or dim2 == Dimension.ANY:
            return DimensionResult(Dimension.ANY, True)

        # RATIO/RETURN with anything preserves the other
        if dim1 in (Dimension.RATIO, Dimension.RETURN):
            return DimensionResult(dim2, True)
        if dim2 in (Dimension.RATIO, Dimension.RETURN):
            return DimensionResult(dim1, True)

        # Same dimension multiplied -> need special handling
        if dim1 == dim2:
            return DimensionResult(Dimension.RATIO, True, "Same dimension multiplied")

        # Default: produce RATIO (may be invalid but allow exploration)
        return DimensionResult(Dimension.RATIO, True, "Unknown multiplication")

    @classmethod
    def check_divide(cls, dim1: Dimension, dim2: Dimension) -> DimensionResult:
        """Check division and compute result dimension."""
        # Same dimension -> RATIO
        if dim1 == dim2:
            return DimensionResult(Dimension.RATIO, True)

        # ANY with anything
        if dim1 == Dimension.ANY or dim2 == Dimension.ANY:
            return DimensionResult(Dimension.RATIO, True)

        # Dividing by SCALAR preserves dimension
        if dim2 == Dimension.SCALAR:
            return DimensionResult(dim1, True)

        # QUOTE_VOLUME / PRICE = VOLUME
        if dim1 == Dimension.QUOTE_VOLUME and dim2 == Dimension.PRICE:
            return DimensionResult(Dimension.VOLUME, True)

        # QUOTE_VOLUME / VOLUME = PRICE
        if dim1 == Dimension.QUOTE_VOLUME and dim2 == Dimension.VOLUME:
            return DimensionResult(Dimension.PRICE, True)

        # Default: produce RATIO
        return DimensionResult(Dimension.RATIO, True)

    @classmethod
    def get_op_output_dim(cls, op_name: str, input_dims: Tuple[Dimension, ...]) -> DimensionResult:
        """Get output dimension for an operator."""
        if op_name in cls.RATIO_OPS:
            return DimensionResult(Dimension.RATIO, True)

        if op_name in cls.TIME_OPS:
            return DimensionResult(Dimension.TIME, True)

        if op_name in cls.PRESERVE_OPS:
            # Preserve first input's dimension
            if input_dims:
                return DimensionResult(input_dims[0], True)
            return DimensionResult(Dimension.ANY, True)

        # Special cases
        if op_name == 'returns':
            return DimensionResult(Dimension.RETURN, True)

        if op_name == 'ts_atr':
            return DimensionResult(Dimension.PRICE, True)

        if op_name == 'ts_realized_vol':
            return DimensionResult(Dimension.RATIO, True)

        if op_name in ('add', 'subtract'):
            if len(input_dims) >= 2:
                return cls.check_add_sub(input_dims[0], input_dims[1])

        if op_name in ('multiply',):
            if len(input_dims) >= 2:
                return cls.check_multiply(input_dims[0], input_dims[1])

        if op_name in ('divide',):
            if len(input_dims) >= 2:
                return cls.check_divide(input_dims[0], input_dims[1])

        if op_name == 'sqrt':
            return DimensionResult(Dimension.RATIO, True)

        if op_name == 'power':
            return DimensionResult(Dimension.RATIO, True)

        # Default: preserve first input or ANY
        if input_dims:
            return DimensionResult(input_dims[0], True)
        return DimensionResult(Dimension.ANY, True)


def is_dimension_compatible(expr_dim: Dimension, expected_dim: Dimension) -> bool:
    """Check if expression dimension is compatible with expected dimension."""
    if expected_dim == Dimension.ANY:
        return True
    if expr_dim == Dimension.ANY:
        return True
    if expr_dim == expected_dim:
        return True
    # RATIO and RETURN are compatible
    if {expr_dim, expected_dim} == {Dimension.RATIO, Dimension.RETURN}:
        return True
    # SCALAR is compatible with anything for most purposes
    if expr_dim == Dimension.SCALAR:
        return True
    return False


# Allowed column names for GP terminals
ALLOWED_COLUMNS = [
    'Close', 'Open', 'High', 'Low',
    'Volume', 'QuoteAssetVolume',
    'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume',
    'TakerBuyQuoteAssetVolume', 'TakerSellQuoteAssetVolume',
    'NumberOfTrades', 'return',
]

# Columns grouped by dimension type
PRICE_COLUMNS = ['Close', 'Open', 'High', 'Low']
VOLUME_COLUMNS = ['Volume', 'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume']
QUOTE_COLUMNS = ['QuoteAssetVolume', 'TakerBuyQuoteAssetVolume', 'TakerSellQuoteAssetVolume']
RETURN_COLUMNS = ['return']
COUNT_COLUMNS = ['NumberOfTrades']


__all__ = [
    'Dimension',
    'DimensionResult',
    'DimensionTracker',
    'is_dimension_compatible',
    'ALLOWED_COLUMNS',
    'PRICE_COLUMNS',
    'VOLUME_COLUMNS',
    'QUOTE_COLUMNS',
    'RETURN_COLUMNS',
    'COUNT_COLUMNS',
]
