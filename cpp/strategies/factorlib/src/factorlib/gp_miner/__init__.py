"""
GP Factor Miner - Unified Panel Data Version

Genetic Programming based factor mining for multi-asset trading strategies.
All operations work on DataFrame format (rows=timestamps, columns=assets).

Supports both:
- Time-series (ts_*) operators: Apply to each asset column independently
- Cross-sectional (cs_*) operators: Apply across assets at each timestamp

Two evaluation modes:
- 'ic': Uses IC with specified label as primary metric (default)
- 'sharpe': Uses long-short portfolio Sharpe ratio

Usage Example:
    from factorlib.gp_miner import FactorMiner, EvolutionConfig, FitnessConfig
    from factorlib.cli import load_panel_data_parquet

    # 方式1: 使用 PanelData (推荐)
    panel = load_panel_data_parquet(
        instruments=['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP'],
        start_date='2022-01-01'
    )

    # IC模式 (默认) - 使用ret#l#15m作为label
    miner = FactorMiner(panel)

    # IC模式 - 使用ret#l#1h作为label
    miner = FactorMiner(panel, fitness_config=FitnessConfig(label_col='ret#l#1h'))

    # Sharpe模式
    miner = FactorMiner(panel, fitness_config=FitnessConfig(eval_mode='sharpe'))

    # 方式2: 使用 data_dict (兼容旧代码)
    data_dict = {'BTC-USDT-SWAP': df_btc, 'ETH-USDT-SWAP': df_eth}
    miner = FactorMiner(data_dict)

    # Run evolution
    result = miner.run()
    print(f"Best: {result.best_expression}")
    print(f"IC: {result.best_fitness.ic:.4f}")

Note:
    表达式深度限制为6层（包含外层zscore+clip），内部表达式最多4层。
"""

from .primitives import (
    # Primitive set
    create_primitive_set,
    # Expression evaluation
    evaluate_expression,
    # Panel data utilities
    build_panel_data,
    build_all_panels,
    panel_to_dict,
    get_available_columns,
    # Expression utilities
    tree_to_expression_string,
    expression_to_code,
    # Window constants
    SHORT_WINDOWS,
    MEDIUM_WINDOWS,
    LONG_WINDOWS,
    ALL_WINDOWS,
)

from .evolution import (
    FactorMiner,
    EvolutionConfig,
    EvolutionResult,
)

from .fitness import (
    FitnessResult,
    FitnessConfig,
    FitnessEvaluator,
    calculate_sharpe,
    calculate_turnover,
    calculate_ic,
)

from .exporter import (
    ExportedFactor,
    export_factor,
    generate_factor_class,
    generate_standalone_function,
    print_factor_code,
)

from .dimensions import (
    Dimension,
    DimensionTracker,
)

__all__ = [
    # Main classes
    'FactorMiner',
    'EvolutionConfig',
    'EvolutionResult',
    'FitnessResult',
    'FitnessConfig',
    'FitnessEvaluator',
    # Primitive set
    'create_primitive_set',
    # Panel data utilities
    'build_panel_data',
    'build_all_panels',
    'panel_to_dict',
    'get_available_columns',
    # Expression evaluation
    'evaluate_expression',
    'tree_to_expression_string',
    'expression_to_code',
    # Export
    'ExportedFactor',
    'export_factor',
    'generate_factor_class',
    'generate_standalone_function',
    'print_factor_code',
    # Dimensions
    'Dimension',
    'DimensionTracker',
    # Helper functions
    'calculate_sharpe',
    'calculate_turnover',
    'calculate_ic',
    # Window constants
    'SHORT_WINDOWS',
    'MEDIUM_WINDOWS',
    'LONG_WINDOWS',
    'ALL_WINDOWS',
]

__version__ = '1.0.0'  # Major version for unified Panel Data support
