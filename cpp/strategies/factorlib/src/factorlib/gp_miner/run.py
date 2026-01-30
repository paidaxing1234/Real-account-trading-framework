#!/usr/bin/env python3
"""
GP Factor Mining Runner Script - LARGE SCALE VERSION

Optimized for massive data (100GB+) and long runs (3+ days) with nohup.
Default data source: parquet files from /home/ch/data/labels/OKX_1m_candles_data_agg/
Default eval mode: IC with ret#l#15m as label

Usage:
    # IC模式 (默认) - 使用 ret#l#15m 作为 label
    nohup python -m factorlib.gp_miner.run --preset large > gp_mining.log 2>&1 &

    # IC模式 - 使用 ret#l#1h 作为 label
    nohup python -m factorlib.gp_miner.run --preset large --label ret#l#1h > gp_mining.log 2>&1 &

    # IC模式 - 使用 ret#l#1d 作为 label
    nohup python -m factorlib.gp_miner.run --preset large --label ret#l#1d > gp_mining.log 2>&1 &

    # Sharpe模式
    nohup python -m factorlib.gp_miner.run --preset large --eval-mode sharpe > gp_mining.log 2>&1 &

    # Quick test
    python -m factorlib.gp_miner.run --preset small

    # MASSIVE run (3+ days)
    nohup python -m factorlib.gp_miner.run --preset massive > gp_mining.log 2>&1 &

Presets:
    --preset small     : Quick test (pop=100, gen=20)
    --preset medium    : Normal run (pop=500, gen=100)
    --preset large     : Large run (pop=2000, gen=500)
    --preset massive   : Massive run (pop=10000, gen=10000, 3+ days)

Labels (for IC mode):
    ret#l#1m, ret#l#2m, ret#l#3m, ret#l#5m, ret#l#15m (default),
    ret#l#30m, ret#l#1h, ret#l#2h, ret#l#3h, ret#l#6h,
    ret#l#1d, ret#l#2d, ret#l#3d
"""

import argparse
import json
import os
import sys
import signal
import logging
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Configure logging for nohup runs
def setup_logging(output_dir: Path, run_timestamp: str):
    """Setup logging to both file and stdout."""
    log_file = output_dir / f"run_{run_timestamp}.log"

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Stream handler (stdout)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


# Presets for different scale runs
PRESETS = {
    'small': {
        'population': 100,
        'generations': 20,
        'elite_size': 10,
        'workers': 8,
        'gc_every': 5,
        'save_every': 5,
        'max_memory': 50,
    },
    'medium': {
        'population': 500,
        'generations': 100,
        'elite_size': 50,
        'workers': 16,
        'gc_every': 3,
        'save_every': 10,
        'max_memory': 100,
    },
    'large': {
        'population': 2000,
        'generations': 500,
        'elite_size': 100,
        'workers': 24,
        'gc_every': 3,
        'save_every': 10,
        'max_memory': 150,
    },
    'massive': {
        'population': 10000,
        'generations': 10000,
        'elite_size': 200,
        'workers': 32,
        'gc_every': 2,
        'save_every': 5,
        'max_memory': 180,
    },
}


def main():
    parser = argparse.ArgumentParser(
        description='Multi-Backend GP Factor Miner - Large Scale Version',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # ==========================================================================
    # PRESET SELECTION
    # ==========================================================================
    parser.add_argument(
        '--preset',
        type=str,
        choices=['small', 'medium', 'large', 'massive'],
        help='Use predefined configuration preset'
    )

    # ==========================================================================
    # DATA OPTIONS
    # ==========================================================================
    parser.add_argument(
        '--instruments', '-i',
        type=str,
        default='key5',
        help='Instruments: "key5", "all", "top50", or comma-separated list'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        default='2020-01-01 00:00:00',
        help='Start date for training data (earlier = more data)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        default='2024-12-31 23:59:59',
        help='End date for training data (default: 2024-12-31, NO 2025!)'
    )
    parser.add_argument(
        '--source',
        type=str,
        default='parquet',
        choices=['parquet', 'clickhouse'],
        help='Data source: parquet (local files) or clickhouse'
    )
    parser.add_argument(
        '--data-dir',
        type=str,
        default='/home/ch/data/labels/OKX_1m_candles_data_agg',
        help='Directory containing parquet files'
    )
    parser.add_argument(
        '--data-file',
        type=str,
        help='Load data from a single parquet file'
    )

    # ==========================================================================
    # BACKEND SELECTION
    # ==========================================================================
    parser.add_argument(
        '--backend', '-b',
        type=str,
        default='deap',
        choices=['deap', 'geppy', 'gplearn'],
        help='GP backend to use'
    )

    # ==========================================================================
    # EVOLUTION PARAMETERS (can be overridden by preset)
    # ==========================================================================
    parser.add_argument(
        '--population', '-p',
        type=int,
        default=None,
        help='Population size'
    )
    parser.add_argument(
        '--generations', '-g',
        type=int,
        default=None,
        help='Number of generations'
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        default=4,
        help='Maximum inner expression depth (total = depth + 2 for zscore+clip)'
    )
    parser.add_argument(
        '--elite-size',
        type=int,
        default=None,
        help='Number of elite individuals to preserve'
    )
    parser.add_argument(
        '--crossover-prob',
        type=float,
        default=0.6,
        help='Crossover probability'
    )
    parser.add_argument(
        '--mutation-prob',
        type=float,
        default=0.3,
        help='Mutation probability'
    )
    parser.add_argument(
        '--tournament-size',
        type=int,
        default=3,
        help='Tournament selection size'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Random seed (None for random)'
    )

    # ==========================================================================
    # PARALLEL & MEMORY (CRITICAL FOR LARGE RUNS)
    # ==========================================================================
    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=None,
        help='Number of parallel workers'
    )
    parser.add_argument(
        '--no-parallel',
        action='store_true',
        help='Disable parallel evaluation'
    )
    parser.add_argument(
        '--gc-every',
        type=int,
        default=None,
        help='Run garbage collection every N generations'
    )
    parser.add_argument(
        '--max-memory',
        type=int,
        default=None,
        help='Maximum memory in GB before aggressive GC'
    )
    parser.add_argument(
        '--save-every',
        type=int,
        default=None,
        help='Save checkpoint every N generations'
    )
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=None,
        help='Chunk size for parallel evaluation'
    )

    # ==========================================================================
    # FITNESS OPTIONS
    # ==========================================================================
    parser.add_argument(
        '--eval-mode',
        type=str,
        default='ic',
        choices=['ic', 'sharpe'],
        help='Evaluation mode: ic (default) or sharpe'
    )
    parser.add_argument(
        '--label',
        type=str,
        default='ret#l#15m',
        help='Label column for IC mode (e.g., ret#l#15m, ret#l#1h, ret#l#1d)'
    )
    parser.add_argument(
        '--max-turnover',
        type=float,
        default=3000.0,
        help='Maximum acceptable annual turnover'
    )
    parser.add_argument(
        '--target-turnover',
        type=float,
        default=2000.0,
        help='Target annual turnover'
    )
    parser.add_argument(
        '--min-coverage',
        type=float,
        default=0.15,
        help='Minimum non-NaN coverage'
    )
    parser.add_argument(
        '--position-clip',
        type=float,
        default=1.0,
        help='Clip position to [-clip, clip] range'
    )
    parser.add_argument(
        '--relaxed',
        action='store_true',
        default=True,
        help='Enable relaxed mode (soft constraints)'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Enable strict mode (hard constraints)'
    )

    # ==========================================================================
    # OUTPUT OPTIONS
    # ==========================================================================
    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        default='/home/ch/data/result/gp_factors',
        help='Output directory for results'
    )
    parser.add_argument(
        '--run-name',
        type=str,
        default=None,
        help='Custom name for this run (default: auto-generated timestamp)'
    )
    parser.add_argument(
        '--no-timestamp-folder',
        action='store_true',
        help='Disable timestamped subfolder'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress verbose output'
    )

    # ==========================================================================
    # EVALUATION MODE
    # ==========================================================================
    parser.add_argument(
        '--evaluate',
        type=str,
        help='Evaluate a specific expression instead of running evolution'
    )

    # ==========================================================================
    # RESUME FROM CHECKPOINT
    # ==========================================================================
    parser.add_argument(
        '--resume',
        type=str,
        help='Resume from checkpoint directory'
    )

    args = parser.parse_args()

    # ==========================================================================
    # APPLY PRESET
    # ==========================================================================
    if args.preset:
        preset = PRESETS[args.preset]
        # Only apply preset values if not explicitly set
        if args.population is None:
            args.population = preset['population']
        if args.generations is None:
            args.generations = preset['generations']
        if args.elite_size is None:
            args.elite_size = preset['elite_size']
        if args.workers is None:
            args.workers = preset['workers']
        if args.gc_every is None:
            args.gc_every = preset['gc_every']
        if args.save_every is None:
            args.save_every = preset['save_every']
        if args.max_memory is None:
            args.max_memory = preset['max_memory']

    # Apply defaults if still None
    args.population = args.population or 2000
    args.generations = args.generations or 500
    args.elite_size = args.elite_size or 100
    args.workers = args.workers or 24
    args.gc_every = args.gc_every or 3
    args.save_every = args.save_every or 10
    args.max_memory = args.max_memory or 180
    args.chunk_size = args.chunk_size or (args.population // args.workers * 2)

    # ==========================================================================
    # SETUP OUTPUT DIRECTORY & LOGGING
    # ==========================================================================
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or f"run_{run_timestamp}"

    if args.no_timestamp_folder:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(args.output_dir) / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup logging
    logger = setup_logging(output_dir, run_timestamp)
    logger.info("=" * 70)
    logger.info(" GP Factor Mining - LARGE SCALE VERSION")
    logger.info("=" * 70)

    # Save run configuration
    config_path = output_dir / f"config_{run_timestamp}.json"
    config_dict = vars(args).copy()
    config_dict['run_timestamp'] = run_timestamp
    config_dict['output_dir'] = str(output_dir)
    with open(config_path, 'w') as f:
        json.dump(config_dict, f, indent=2, default=str)
    logger.info(f"Configuration saved to: {config_path}")

    # ==========================================================================
    # IMPORT MODULES (after argument parsing for faster --help)
    # ==========================================================================
    try:
        from factorlib.cli import load_panel_data_parquet
        from factorlib.gp_miner.evolution import FactorMiner, EvolutionConfig
        from factorlib.gp_miner.fitness import FitnessConfig
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error("Make sure factorlib is installed: pip install -e .")
        sys.exit(1)

    verbose = not args.quiet

    # ==========================================================================
    # SIGNAL HANDLERS FOR GRACEFUL SHUTDOWN
    # ==========================================================================
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        if shutdown_requested:
            logger.warning("Force shutdown requested. Exiting immediately.")
            sys.exit(1)
        shutdown_requested = True
        logger.warning(f"Received signal {signum}. Will save checkpoint and exit after current generation.")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # ==========================================================================
    # LOAD INSTRUMENTS
    # ==========================================================================
    if args.instruments == 'all':
        # 从 parquet 目录扫描所有可用的资产
        instruments = []
        try:
            parquet_files = list(Path(args.data_dir).glob("*_labels.parquet"))
            instruments = [f.stem.replace('_labels', '') for f in parquet_files]
            logger.info(f"Found {len(instruments)} instruments from {args.data_dir}")
        except Exception as e:
            logger.warning(f"Could not scan parquet directory: {e}")
            # Fallback to code_list.json
            try:
                with open('/home/ch/data/code_list.json', 'r') as f:
                    code_dict = json.load(f)
                instruments = code_dict.get('all', [])
                logger.info(f"Loaded {len(instruments)} instruments from code_list.json")
            except Exception as e2:
                logger.error(f"Could not load instruments: {e2}")
                sys.exit(1)

        if not instruments:
            logger.error("No instruments found!")
            sys.exit(1)
    elif args.instruments == 'top50':
        try:
            with open('/home/ch/data/code_list.json', 'r') as f:
                code_dict = json.load(f)
            instruments = code_dict.get('top50', code_dict.get('key5', []))
        except:
            instruments = [
                'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP',
                'XRP-USDT-SWAP', 'ADA-USDT-SWAP', 'DOGE-USDT-SWAP',
                'DOT-USDT-SWAP', 'AVAX-USDT-SWAP', 'LINK-USDT-SWAP',
                'MATIC-USDT-SWAP'
            ]
    elif args.instruments == 'key5':
        try:
            with open('/home/ch/data/code_list.json', 'r') as f:
                code_dict = json.load(f)
            instruments = code_dict['key5']
        except:
            instruments = [
                'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP',
                'XRP-USDT-SWAP', 'ADA-USDT-SWAP'
            ]
    else:
        instruments = [s.strip() for s in args.instruments.split(',')]

    logger.info(f"Instruments ({len(instruments)}): {instruments[:10]}{'...' if len(instruments) > 10 else ''}")
    logger.info(f"Training period: {args.start_date} -> {args.end_date}")

    # ==========================================================================
    # LOAD DATA (使用 PanelData)
    # ==========================================================================
    logger.info("Loading data as PanelData...")
    data_load_start = datetime.now()

    try:
        # 使用 load_panel_data_parquet 加载为 PanelData
        logger.info(f"Loading from parquet files ({args.data_dir})...")
        panel = load_panel_data_parquet(
            instruments=instruments,
            start_date=args.start_date,
            data_dir=args.data_dir,
        )

        # 过滤 end_date (手动过滤每个 DataFrame)
        if args.end_date:
            end_date = pd.Timestamp(args.end_date, tz='UTC')
            for col in panel.columns:
                df = panel[col]
                if df is not None and len(df) > 0:
                    panel[col] = df[df.index <= end_date]
            logger.info(f"Filtered to end_date: {args.end_date}")

    except Exception as e:
        logger.error(f"Error loading data: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

    if panel is None:
        logger.error("No data loaded!")
        sys.exit(1)

    data_load_time = (datetime.now() - data_load_start).total_seconds()
    n_assets = len(panel['Close'].columns) if 'Close' in panel.columns else 0
    n_rows = len(panel['Close']) if 'Close' in panel.columns else 0

    logger.info(f"Data loaded in {data_load_time:.1f}s")
    logger.info(f"PanelData: {n_assets} assets, {n_rows:,} rows, columns: {panel.columns[:10]}...")

    # ==========================================================================
    # EVALUATION MODE
    # ==========================================================================
    if args.evaluate:
        logger.info(f"Evaluating expression: {args.evaluate}")

        fitness_config = FitnessConfig(
            eval_mode=args.eval_mode,
            label_col=args.label,
            max_turnover=args.max_turnover,
            target_turnover=args.target_turnover,
            min_coverage=args.min_coverage,
            position_clip=args.position_clip,
            relaxed_mode=args.relaxed and not args.strict,
        )

        miner = FactorMiner(
            panel,
            fitness_config=fitness_config,
        )

        result = miner.evaluate_expression_str(args.evaluate)
        logger.info(f"Evaluation Result:\n{result}")
        return

    # ==========================================================================
    # CREATE CONFIGS
    # ==========================================================================
    relaxed_mode = args.relaxed and not args.strict

    evolution_config = EvolutionConfig(
        population_size=args.population,
        generations=args.generations,
        max_depth=args.max_depth,
        elite_size=args.elite_size,
        crossover_prob=args.crossover_prob,
        mutation_prob=args.mutation_prob,
        tournament_size=args.tournament_size,
        seed=args.seed,
        checkpoint_dir=str(output_dir),
        gc_every_n_gens=args.gc_every,
        max_memory_gb=args.max_memory,
        save_every=args.save_every,
    )

    fitness_config = FitnessConfig(
        eval_mode=args.eval_mode,
        label_col=args.label,
        max_turnover=args.max_turnover,
        target_turnover=args.target_turnover,
        min_coverage=args.min_coverage,
        position_clip=args.position_clip,
        relaxed_mode=relaxed_mode,
    )

    # ==========================================================================
    # LOG RUN PARAMETERS
    # ==========================================================================
    logger.info("=" * 70)
    logger.info(" RUN PARAMETERS")
    logger.info("=" * 70)
    logger.info(f" Eval mode:      {args.eval_mode}")
    if args.eval_mode == 'ic':
        logger.info(f" Label:          {args.label}")
    logger.info(f" Population:     {args.population:,}")
    logger.info(f" Generations:    {args.generations:,}")
    logger.info(f" Max depth:      {args.max_depth} (+ zscore + clip = {args.max_depth + 2} total)")
    logger.info(f" Elite size:     {args.elite_size}")
    logger.info(f" GC every:       {args.gc_every} generations")
    logger.info(f" Save every:     {args.save_every} generations")
    logger.info(f" Max memory:     {args.max_memory}GB")
    logger.info(f" Relaxed mode:   {relaxed_mode}")
    logger.info(f" Output dir:     {output_dir}")
    logger.info("=" * 70)

    # Estimate run time
    est_evals_per_gen = args.population * 0.7  # ~70% need evaluation each gen
    est_total_evals = est_evals_per_gen * args.generations
    # Rough estimate: 100 evals/sec on large data
    est_evals_per_sec = 100  # Conservative estimate
    est_hours = est_total_evals / est_evals_per_sec / 3600
    logger.info(f" Estimated evaluations: {est_total_evals:,.0f}")
    logger.info(f" Estimated runtime: {est_hours:.1f} hours ({est_hours/24:.1f} days)")
    logger.info("=" * 70)

    # ==========================================================================
    # RUN EVOLUTION
    # ==========================================================================
    logger.info("\nStarting evolution...")
    evolution_start = datetime.now()

    try:
        miner = FactorMiner(
            panel,
            config=evolution_config,
            fitness_config=fitness_config,
        )

        result = miner.run(verbose=verbose)

    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Saving current state...")
        result = None
    except Exception as e:
        logger.error(f"Evolution failed: {e}")
        logger.error(traceback.format_exc())
        result = None

    evolution_time = (datetime.now() - evolution_start).total_seconds()
    logger.info(f"\nEvolution completed in {evolution_time/3600:.2f} hours")

    # ==========================================================================
    # SAVE RESULTS
    # ==========================================================================
    if result is None:
        logger.error("No results to save")
        sys.exit(1)

    clip_range = evolution_config.normalize_clip_range

    # Save best factor
    if result.best_fitness and result.best_fitness.sharpe > -100:
        best_factor_path = output_dir / f"best_factor_{run_timestamp}.json"
        inner_expr = result.best_expression
        normalize_window = getattr(result.best_fitness, 'normalize_window', None)
        if normalize_window is None:
            hash_val = hash(inner_expr)
            window_range = evolution_config.normalize_window_max - evolution_config.normalize_window_min
            normalize_window = evolution_config.normalize_window_min + (abs(hash_val) % window_range)
        full_expression = f"ops.clip(ops.ts_zscore({inner_expr}, {normalize_window}), -{clip_range}, {clip_range})"

        best_info = {
            'expression': full_expression,
            'inner_expression': inner_expr,
            'normalize_window': normalize_window,
            'clip_range': clip_range,
            'sharpe': result.best_fitness.sharpe,
            'returns': result.best_fitness.returns,
            'turnover': result.best_fitness.turnover,
            'long_ratio': result.best_fitness.long_ratio,
            'short_ratio': result.best_fitness.short_ratio,
            'max_drawdown': result.best_fitness.max_drawdown,
            'coverage': result.best_fitness.coverage,
            'valid': result.best_fitness.valid,
            'timestamp': run_timestamp,
            'runtime_hours': evolution_time / 3600,
            'total_evaluations': result.total_evaluations,
            'config': {
                'backend': args.backend,
                'population': args.population,
                'generations': args.generations,
                'max_depth': args.max_depth,
                'workers': args.workers,
                'instruments': instruments[:20],  # Save first 20
                'num_instruments': len(instruments),
            }
        }

        with open(best_factor_path, 'w') as f:
            json.dump(best_info, f, indent=2)
        logger.info(f"Best factor saved to: {best_factor_path}")

    # Save top factors
    top_factors_path = output_dir / f"top_factors_{run_timestamp}.json"
    top_factors = []
    for ind, fitness in result.top_individuals[:100]:  # Save top 100
        if fitness.sharpe > -50:
            inner_expr = str(ind)
            normalize_window = getattr(fitness, 'normalize_window', None)
            if normalize_window is None:
                hash_val = hash(inner_expr)
                window_range = evolution_config.normalize_window_max - evolution_config.normalize_window_min
                normalize_window = evolution_config.normalize_window_min + (abs(hash_val) % window_range)
            full_expression = f"ops.clip(ops.ts_zscore({inner_expr}, {normalize_window}), -{clip_range}, {clip_range})"
            top_factors.append({
                'expression': full_expression,
                'inner_expression': inner_expr,
                'normalize_window': normalize_window,
                'clip_range': clip_range,
                'sharpe': fitness.sharpe,
                'returns': fitness.returns,
                'turnover': fitness.turnover,
                'long_ratio': fitness.long_ratio,
                'short_ratio': fitness.short_ratio,
                'max_drawdown': fitness.max_drawdown,
                'coverage': fitness.coverage,
                'valid': fitness.valid,
            })

    top_factors.sort(key=lambda x: x['sharpe'], reverse=True)
    with open(top_factors_path, 'w') as f:
        json.dump(top_factors, f, indent=2)
    logger.info(f"Top {len(top_factors)} factors saved to: {top_factors_path}")

    # Append to accumulated files
    def append_factors_to_file(factors: list, filepath: Path):
        existing = []
        existing_expressions = set()
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    existing = json.load(f)
                    existing_expressions = {f['expression'] for f in existing}
            except:
                pass
        new_factors = [f for f in factors if f['expression'] not in existing_expressions]
        if new_factors:
            for f in new_factors:
                f['added_at'] = run_timestamp
            combined = existing + new_factors
            with open(filepath, 'w') as f:
                json.dump(combined, f, indent=2)
        return len(new_factors)

    # Save by sharpe level
    decent_factors = [f for f in top_factors if 1.0 < f['sharpe'] <= 2.0]
    if decent_factors:
        added = append_factors_to_file(decent_factors, output_dir / "sharpe_gt1.json")
        logger.info(f"Decent factors (1<sharpe<=2): {added} new factors added")

    excellent_factors = [f for f in top_factors if f['sharpe'] > 2.0]
    if excellent_factors:
        added = append_factors_to_file(excellent_factors, output_dir / "sharpe_gt2_GOOD.json")
        logger.info(f"*** GOOD factors (sharpe>2): {added} new factors added ***")

    # ==========================================================================
    # FINAL SUMMARY
    # ==========================================================================
    logger.info("\n" + "=" * 70)
    logger.info(" RUN COMPLETE")
    logger.info("=" * 70)
    logger.info(f" Total runtime:      {evolution_time/3600:.2f} hours")
    logger.info(f" Total evaluations:  {result.total_evaluations:,}")
    logger.info(f" Generations:        {result.total_generations}")
    if result.best_fitness:
        logger.info(f" Best Sharpe:        {result.best_fitness.sharpe:.4f}")
        logger.info(f" Best Returns:       {result.best_fitness.returns:.2f}%")
    logger.info(f" Output directory:   {output_dir}")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()
