#!/usr/bin/env python3
"""
GP Factor Mining Daemon

Continuous GP factor mining that runs in background.
Saves good factors (yearly Sharpe > 2) automatically.

Usage:
    # Direct run
    python scripts/gp_mining_daemon.py

    # Background run with nohup
    nohup python scripts/gp_mining_daemon.py > /home/ch/data/result/gp_mining.log 2>&1 &

    # Or use screen/tmux
    screen -S gp_mining
    python scripts/gp_mining_daemon.py
"""

import os
import sys
import json
import time
import random
import logging
import signal
import traceback
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from multiprocessing import Pool, cpu_count
from functools import partial
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

# Add project to path
sys.path.insert(0, '/home/ch/hchen/factorlib/src')

from deap import base, creator, tools, gp

from factorlib.gp_miner.primitives import (
    create_simple_primitive_set,
    evaluate_expression_simple,
)
from factorlib.gp_miner.fitness import FitnessEvaluator, FitnessConfig, FitnessResult


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class DaemonConfig:
    """Daemon configuration."""
    # Data
    instruments: List[str] = None
    start_date: str = '2022-01-01 00:00:00'

    # Evolution
    population_size: int = 300
    generations_per_run: int = 100
    max_depth: int = 5
    elite_size: int = 20

    # Parallel
    n_workers: int = 16  # Number of parallel workers

    # Good factor threshold
    min_sharpe_per_year: float = 2.0  # Yearly Sharpe > 2 is good

    # Turnover and position constraints
    max_turnover: float = 2000.0
    min_long_ratio: float = 0.45
    min_short_ratio: float = -0.45

    # Output
    output_dir: str = '/home/ch/data/result/gp_factors'
    good_factors_file: str = '/home/ch/data/result/gp_factors/good_factors.json'
    log_file: str = '/home/ch/data/result/gp_factors/daemon.log'

    # Run control
    max_runs: int = 0  # 0 = infinite
    sleep_between_runs: int = 10  # seconds

    def __post_init__(self):
        if self.instruments is None:
            self.instruments = [
                'BTC-USDT-SWAP',
                'ETH-USDT-SWAP',
                'SOL-USDT-SWAP',
                'XRP-USDT-SWAP',
                'ADA-USDT-SWAP',
            ]


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(log_file: str) -> logging.Logger:
    """Setup logging to file and console."""
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger('GPMiningDaemon')
    logger.setLevel(logging.INFO)

    # File handler
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


# =============================================================================
# Good Factor Storage
# =============================================================================

class GoodFactorStorage:
    """Storage for good factors (Sharpe > threshold)."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.factors = self._load()

    def _load(self) -> List[Dict]:
        """Load existing factors."""
        if Path(self.filepath).exists():
            try:
                with open(self.filepath, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save(self):
        """Save factors to file."""
        Path(self.filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(self.filepath, 'w') as f:
            json.dump(self.factors, f, indent=2, default=str)

    def add_factor(self, factor_info: Dict) -> bool:
        """Add a factor if it's unique."""
        expr = factor_info.get('expression', '')

        # Check if already exists
        for f in self.factors:
            if f.get('expression') == expr:
                return False

        self.factors.append(factor_info)
        self.save()
        return True

    def get_count(self) -> int:
        return len(self.factors)


# =============================================================================
# Parallel Evaluation
# =============================================================================

# Global variables for worker processes
_worker_data = {}
_worker_pset = None
_worker_fitness_evaluator = None


def init_worker(data_dict_serialized: Dict, columns: List[str], fitness_config_dict: Dict):
    """Initialize worker process."""
    global _worker_data, _worker_pset, _worker_fitness_evaluator

    # Reconstruct data
    _worker_data = {}
    for inst, data in data_dict_serialized.items():
        df = pd.DataFrame(data)
        df.index = pd.to_datetime(df.index)
        _worker_data[inst] = df

    # Create primitive set
    _worker_pset = create_simple_primitive_set(columns)

    # Create fitness evaluator
    fitness_config = FitnessConfig(**fitness_config_dict)
    _worker_fitness_evaluator = FitnessEvaluator(fitness_config)


def evaluate_individual_worker(individual_str: str) -> Dict:
    """Evaluate a single individual in worker process."""
    global _worker_data, _worker_pset, _worker_fitness_evaluator

    try:
        # Parse expression
        individual = gp.PrimitiveTree.from_string(individual_str, _worker_pset)

        # Evaluate on each instrument
        factor_dict = {}
        returns_dict = {}

        for inst, df in _worker_data.items():
            factor_values = evaluate_expression_simple(individual, df, _worker_pset)
            if factor_values is not None and not factor_values.isna().all():
                factor_dict[inst] = factor_values
                if 'return' in df.columns:
                    returns_dict[inst] = df['return']

        if not factor_dict:
            return {'fitness': -np.inf, 'valid': False}

        # Calculate fitness
        result = _worker_fitness_evaluator.evaluate_multi_instrument(
            factor_dict,
            returns_dict,
            expression=individual_str,
            tree_depth=individual.height,
            tree_nodes=len(individual)
        )

        return {
            'fitness': result.fitness,
            'sharpe': result.sharpe,
            'returns': result.returns,
            'turnover': result.turnover,
            'long_ratio': result.long_ratio,
            'short_ratio': result.short_ratio,
            'coverage': result.coverage,
            'max_drawdown': result.max_drawdown,
            'valid': result.valid,
            'expression': individual_str,
        }

    except Exception as e:
        return {'fitness': -np.inf, 'valid': False, 'error': str(e)}


# =============================================================================
# Main Mining Class
# =============================================================================

class GPMiningDaemon:
    """Continuous GP factor mining daemon."""

    def __init__(self, config: DaemonConfig = None):
        self.config = config or DaemonConfig()
        self.logger = setup_logging(self.config.log_file)
        self.storage = GoodFactorStorage(self.config.good_factors_file)
        self.running = True
        self.run_count = 0
        self.total_good_factors = self.storage.get_count()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Data
        self.data_dict = None
        self.columns = None
        self.pset = None

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def load_data(self):
        """Load data from ClickHouse."""
        self.logger.info(f"Loading data for {len(self.config.instruments)} instruments...")

        from factorlib.cli import load_multi_instruments

        self.data_dict = load_multi_instruments(
            instruments=self.config.instruments,
            start_date=self.config.start_date
        )

        if not self.data_dict:
            raise ValueError("Failed to load data")

        # Detect columns
        sample_df = next(iter(self.data_dict.values()))
        priority_columns = [
            'Close', 'High', 'Low', 'Open', 'Volume', 'return',
            'QuoteAssetVolume',
            'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume',
        ]
        self.columns = [c for c in priority_columns if c in sample_df.columns]

        # Create primitive set
        self.pset = create_simple_primitive_set(self.columns)

        for inst, df in self.data_dict.items():
            self.logger.info(f"  [{inst}] {len(df):,} rows, {df.index.min()} -> {df.index.max()}")

    def _setup_deap(self):
        """Setup DEAP."""
        # Clean up
        if hasattr(creator, 'FitnessMax'):
            del creator.FitnessMax
        if hasattr(creator, 'Individual'):
            del creator.Individual

        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax)

        self.toolbox = base.Toolbox()

        # Expression generation
        self.toolbox.register(
            "expr",
            gp.genHalfAndHalf,
            pset=self.pset,
            min_=2,
            max_=self.config.max_depth
        )

        # Individual and population
        self.toolbox.register(
            "individual",
            tools.initIterate,
            creator.Individual,
            self.toolbox.expr
        )
        self.toolbox.register(
            "population",
            tools.initRepeat,
            list,
            self.toolbox.individual
        )

        # Genetic operators
        self.toolbox.register("select", tools.selTournament, tournsize=5)
        self.toolbox.register("mate", gp.cxOnePoint)
        self.toolbox.register(
            "expr_mut",
            gp.genFull,
            pset=self.pset,
            min_=0,
            max_=2
        )
        self.toolbox.register(
            "mutate",
            gp.mutUniform,
            expr=self.toolbox.expr_mut,
            pset=self.pset
        )

        # Depth limit
        self.toolbox.decorate(
            "mate",
            gp.staticLimit(key=lambda ind: ind.height, max_value=self.config.max_depth)
        )
        self.toolbox.decorate(
            "mutate",
            gp.staticLimit(key=lambda ind: ind.height, max_value=self.config.max_depth)
        )

    def _serialize_data(self) -> Dict:
        """Serialize data for multiprocessing."""
        serialized = {}
        for inst, df in self.data_dict.items():
            serialized[inst] = {
                'index': df.index.tolist(),
                **{col: df[col].tolist() for col in df.columns}
            }
        return serialized

    def _is_good_factor(self, result: Dict) -> bool:
        """Check if factor meets criteria."""
        if not result.get('valid', False):
            return False

        sharpe = result.get('sharpe', 0)
        turnover = result.get('turnover', np.inf)
        long_ratio = result.get('long_ratio', 0)
        short_ratio = result.get('short_ratio', 0)

        # Sharpe per year > threshold
        if sharpe < self.config.min_sharpe_per_year:
            return False

        # Turnover constraint
        if turnover > self.config.max_turnover:
            return False

        # Position constraints
        if long_ratio < self.config.min_long_ratio:
            return False
        if short_ratio > self.config.min_short_ratio:
            return False

        return True

    def run_single_evolution(self) -> List[Dict]:
        """Run a single evolution and return good factors found."""
        self._setup_deap()

        # Initialize population
        population = self.toolbox.population(n=self.config.population_size)

        # Hall of fame
        hof = tools.HallOfFame(self.config.elite_size)

        # Prepare data for workers
        data_serialized = self._serialize_data()
        fitness_config_dict = {
            'max_turnover': self.config.max_turnover,
            'min_long_ratio': self.config.min_long_ratio,
            'min_short_ratio': self.config.min_short_ratio,
        }

        good_factors = []

        # Create worker pool
        with Pool(
            processes=self.config.n_workers,
            initializer=init_worker,
            initargs=(data_serialized, self.columns, fitness_config_dict)
        ) as pool:

            # Initial evaluation
            individual_strs = [str(ind) for ind in population]
            results = pool.map(evaluate_individual_worker, individual_strs)

            for ind, result in zip(population, results):
                ind.fitness.values = (result.get('fitness', -np.inf),)

                # Check for good factors
                if self._is_good_factor(result):
                    result['found_generation'] = 0
                    result['found_time'] = datetime.now().isoformat()
                    good_factors.append(result)

            hof.update(population)

            best_fitness = max(ind.fitness.values[0] for ind in population)
            self.logger.info(f"  Gen 0: best={best_fitness:.4f}")

            # Evolution loop
            for gen in range(1, self.config.generations_per_run + 1):
                if not self.running:
                    break

                # Select and clone
                offspring = self.toolbox.select(population, len(population) - self.config.elite_size)
                offspring = list(map(self.toolbox.clone, offspring))

                # Crossover
                for child1, child2 in zip(offspring[::2], offspring[1::2]):
                    if random.random() < 0.7:
                        self.toolbox.mate(child1, child2)
                        del child1.fitness.values
                        del child2.fitness.values

                # Mutation
                for mutant in offspring:
                    if random.random() < 0.2:
                        self.toolbox.mutate(mutant)
                        del mutant.fitness.values

                # Evaluate invalid individuals
                invalid_ind = [ind for ind in offspring if not ind.fitness.valid]

                if invalid_ind:
                    individual_strs = [str(ind) for ind in invalid_ind]
                    results = pool.map(evaluate_individual_worker, individual_strs)

                    for ind, result in zip(invalid_ind, results):
                        ind.fitness.values = (result.get('fitness', -np.inf),)

                        if self._is_good_factor(result):
                            result['found_generation'] = gen
                            result['found_time'] = datetime.now().isoformat()
                            good_factors.append(result)

                # Add elites
                elites = list(map(self.toolbox.clone, hof.items))
                offspring.extend(elites)

                population[:] = offspring
                hof.update(population)

                # Log progress
                if gen % 10 == 0:
                    best_fitness = max(ind.fitness.values[0] for ind in population)
                    self.logger.info(f"  Gen {gen}: best={best_fitness:.4f}, good_found={len(good_factors)}")

        return good_factors

    def run(self):
        """Main daemon loop."""
        self.logger.info("=" * 60)
        self.logger.info(" GP Factor Mining Daemon Started")
        self.logger.info("=" * 60)
        self.logger.info(f" Population: {self.config.population_size}")
        self.logger.info(f" Generations per run: {self.config.generations_per_run}")
        self.logger.info(f" Max depth: {self.config.max_depth}")
        self.logger.info(f" Workers: {self.config.n_workers}")
        self.logger.info(f" Min Sharpe: {self.config.min_sharpe_per_year}")
        self.logger.info(f" Existing good factors: {self.total_good_factors}")
        self.logger.info("=" * 60)

        # Load data
        self.load_data()

        while self.running:
            self.run_count += 1

            self.logger.info(f"\n{'='*60}")
            self.logger.info(f" Run #{self.run_count}")
            self.logger.info(f"{'='*60}")

            try:
                start_time = time.time()

                # Run evolution
                good_factors = self.run_single_evolution()

                elapsed = time.time() - start_time

                # Save good factors
                new_count = 0
                for factor in good_factors:
                    if self.storage.add_factor(factor):
                        new_count += 1
                        self.total_good_factors += 1
                        self.logger.info(f"  NEW GOOD FACTOR! Sharpe={factor['sharpe']:.2f}, Turnover={factor['turnover']:.0f}")
                        self.logger.info(f"    Expression: {factor['expression'][:100]}...")

                self.logger.info(f"\n Run #{self.run_count} complete:")
                self.logger.info(f"   Time: {elapsed:.1f}s")
                self.logger.info(f"   Good factors found this run: {len(good_factors)}")
                self.logger.info(f"   New unique factors: {new_count}")
                self.logger.info(f"   Total good factors: {self.total_good_factors}")

                # Check max runs
                if self.config.max_runs > 0 and self.run_count >= self.config.max_runs:
                    self.logger.info(f"Reached max runs ({self.config.max_runs}), stopping...")
                    break

                # Sleep before next run
                if self.running:
                    self.logger.info(f"Sleeping {self.config.sleep_between_runs}s before next run...")
                    time.sleep(self.config.sleep_between_runs)

            except Exception as e:
                self.logger.error(f"Error in run #{self.run_count}: {e}")
                self.logger.error(traceback.format_exc())
                time.sleep(30)  # Sleep longer on error

        self.logger.info("\n" + "=" * 60)
        self.logger.info(" Daemon Stopped")
        self.logger.info(f" Total runs: {self.run_count}")
        self.logger.info(f" Total good factors: {self.total_good_factors}")
        self.logger.info("=" * 60)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='GP Factor Mining Daemon')
    parser.add_argument('--population', '-p', type=int, default=300, help='Population size')
    parser.add_argument('--generations', '-g', type=int, default=100, help='Generations per run')
    parser.add_argument('--workers', '-w', type=int, default=16, help='Number of workers')
    parser.add_argument('--min-sharpe', type=float, default=2.0, help='Minimum Sharpe for good factor')
    parser.add_argument('--max-runs', type=int, default=0, help='Max runs (0=infinite)')
    parser.add_argument('--output-dir', '-o', type=str, default='/home/ch/data/result/gp_factors')

    args = parser.parse_args()

    config = DaemonConfig(
        population_size=args.population,
        generations_per_run=args.generations,
        n_workers=args.workers,
        min_sharpe_per_year=args.min_sharpe,
        max_runs=args.max_runs,
        output_dir=args.output_dir,
        good_factors_file=f"{args.output_dir}/good_factors.json",
        log_file=f"{args.output_dir}/daemon.log",
    )

    daemon = GPMiningDaemon(config)
    daemon.run()


if __name__ == '__main__':
    main()
