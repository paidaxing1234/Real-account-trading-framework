"""
Genetic Programming Factor Miner - Unified Panel Data Version

All operations work on DataFrame format:
- rows = timestamps
- columns = assets

Supports both TS (time-series) and CS (cross-sectional) operators.
"""

import random
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import json
import os
from pathlib import Path
import warnings
import gc

from deap import base, creator, tools, gp

from .primitives import (
    create_primitive_set,
    evaluate_expression,
    build_panel_data,
    build_all_panels,
    get_available_columns,
)
from .fitness import FitnessEvaluator, FitnessConfig, FitnessResult


# Suppress warnings
warnings.filterwarnings('ignore')


@dataclass
class EvolutionConfig:
    """Configuration for evolution."""
    # Population settings
    population_size: int = 2000
    generations: int = 500
    elite_size: int = 100
    hall_of_fame_size: int = 50

    # Tree constraints (内部表达式深度，外层有zscore+clip占2层，所以总深度=max_depth+2)
    max_depth: int = 4  # 内部表达式最大4层，加上zscore+clip总共6层
    min_depth: int = 1
    max_nodes: int = 50

    # Genetic operators
    crossover_prob: float = 0.6
    mutation_prob: float = 0.3
    tournament_size: int = 3

    # Mutation types
    mutation_subtree_prob: float = 0.4
    mutation_shrink_prob: float = 0.3
    mutation_uniform_prob: float = 0.3

    # Operator inclusion
    include_ts_ops: bool = True
    include_cs_ops: bool = True

    # Output
    checkpoint_dir: str = "/home/ch/data/result/gp_checkpoints"
    save_every: int = 10

    # Early stopping
    early_stop_generations: int = 500
    min_improvement: float = 0.0001

    # Random seed
    seed: int = None

    # Memory management
    gc_every_n_gens: int = 3
    max_memory_gb: int = 180

    # Normalization
    normalize_window_min: int = 30
    normalize_window_max: int = 14400
    normalize_clip_range: float = 3.0


@dataclass
class EvolutionResult:
    """Result of evolution run."""
    best_individual: Any = None
    best_fitness: FitnessResult = None
    best_expression: str = ""

    # Top N individuals
    top_individuals: List[Tuple[Any, FitnessResult]] = field(default_factory=list)

    # History
    generation_stats: List[Dict] = field(default_factory=list)
    fitness_history: List[float] = field(default_factory=list)

    # Metadata
    total_generations: int = 0
    total_evaluations: int = 0
    runtime_seconds: float = 0.0
    config: EvolutionConfig = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'best_expression': self.best_expression,
            'best_fitness': self.best_fitness.__dict__ if self.best_fitness else None,
            'top_expressions': [
                (str(ind), fr.__dict__) for ind, fr in self.top_individuals[:10]
            ],
            'generation_stats': self.generation_stats,
            'fitness_history': self.fitness_history,
            'total_generations': self.total_generations,
            'total_evaluations': self.total_evaluations,
            'runtime_seconds': self.runtime_seconds,
        }

    def save(self, path: str):
        """Save results to JSON."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)


class FactorMiner:
    """
    Genetic Programming Factor Miner - Unified Panel Data Version

    All operations work on DataFrame format (rows=timestamps, columns=assets).
    Supports both TS and CS operators.

    Usage:
        from factorlib.gp_miner import FactorMiner, EvolutionConfig, FitnessConfig
        from factorlib.cli import load_panel_data_parquet

        # 方式1: 使用 PanelData (推荐)
        panel = load_panel_data_parquet(instruments=['BTC-USDT-SWAP', 'ETH-USDT-SWAP'])
        miner = FactorMiner(panel)

        # 方式2: 使用 data_dict (兼容旧代码)
        data_dict = {'BTC-USDT-SWAP': df_btc, 'ETH-USDT-SWAP': df_eth}
        miner = FactorMiner(data_dict)

        # Run evolution
        result = miner.run()
        print(f"Best: {result.best_expression}")
    """

    def __init__(
        self,
        data,  # PanelData or Dict[str, pd.DataFrame]
        config: EvolutionConfig = None,
        fitness_config: FitnessConfig = None,
        columns: List[str] = None,
    ):
        """
        Initialize the factor miner.

        Args:
            data: PanelData object (推荐) OR Dict of instrument -> DataFrame (兼容)
            config: Evolution configuration
            fitness_config: Fitness evaluation configuration
            columns: Columns to use as terminals (default: auto-detect)

        Example:
            # 使用 PanelData (推荐)
            panel = load_panel_data_parquet(instruments)
            miner = FactorMiner(panel)

            # IC模式 - 使用ret#l#1h作为label
            miner = FactorMiner(panel, fitness_config=FitnessConfig(label_col='ret#l#1h'))

            # Sharpe模式
            miner = FactorMiner(panel, fitness_config=FitnessConfig(eval_mode='sharpe'))
        """
        self.data = data
        self.config = config or EvolutionConfig()
        self.fitness_config = fitness_config or FitnessConfig()

        # Detect available columns
        if columns is None:
            self.columns = self._detect_columns()
        else:
            self.columns = columns

        # Build panel data dict (critical for all operations)
        # 无论输入是 PanelData 还是 data_dict，都转换为 Dict[str, DataFrame] 格式
        self.panel_data = build_all_panels(data, self.columns)

        # Build returns panel for fitness evaluation
        self.returns_panel = build_panel_data(data, 'return')

        # Build label panel for IC mode
        self.label_panel = None
        if self.fitness_config.eval_mode == 'ic':
            label_col = self.fitness_config.label_col
            try:
                self.label_panel = build_panel_data(data, label_col)
                if self.label_panel is None or self.label_panel.empty:
                    print(f"Warning: label_col '{label_col}' not found, falling back to 'return'")
                    self.label_panel = self.returns_panel
            except (ValueError, KeyError):
                print(f"Warning: label_col '{label_col}' not found, falling back to 'return'")
                self.label_panel = self.returns_panel

        # Set random seed
        if self.config.seed is not None:
            random.seed(self.config.seed)
            np.random.seed(self.config.seed)
        else:
            self._actual_seed = random.randint(0, 2**31 - 1)
            random.seed(self._actual_seed)
            np.random.seed(self._actual_seed)

        # Setup DEAP
        self._setup_deap()

        # Statistics
        self._total_evaluations = 0
        self._generation = 0

        # Fitness evaluator
        self.fitness_evaluator = FitnessEvaluator(self.fitness_config)
        if self.label_panel is not None:
            self.fitness_evaluator.set_label_panel(self.label_panel)

        # Store fit_log for compatibility
        self.fit_log = None

    def _detect_columns(self) -> List[str]:
        """Detect available columns from data (排除 label 列)."""
        all_columns = get_available_columns(self.data)

        # 过滤掉所有 label 列 (带 #l# 的列是未来收益，不能作为因子输入)
        all_columns = [col for col in all_columns if '#l#' not in col]

        priority_columns = [
            'Close', 'High', 'Low', 'Open',
            'Volume', 'return',
            'QuoteAssetVolume',
            'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume',
        ]

        available = [col for col in priority_columns if col in all_columns]

        if 'Close' not in available:
            raise ValueError("Data must contain 'Close' column")
        if 'return' not in available:
            raise ValueError("Data must contain 'return' column")

        return available

    def _setup_deap(self):
        """Setup DEAP creator, toolbox, and operators."""
        # Clean up any existing creator classes
        if hasattr(creator, 'FitnessMax'):
            del creator.FitnessMax
        if hasattr(creator, 'Individual'):
            del creator.Individual

        # Create fitness and individual classes
        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax)

        # Create primitive set with both TS and CS operators
        self.pset = create_primitive_set(
            self.columns,
            include_ts_ops=self.config.include_ts_ops,
            include_cs_ops=self.config.include_cs_ops
        )

        # Create toolbox
        self.toolbox = base.Toolbox()

        # Expression generation
        self.toolbox.register(
            "expr",
            gp.genHalfAndHalf,
            pset=self.pset,
            min_=self.config.min_depth,
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
        self.toolbox.register("select", tools.selTournament, tournsize=self.config.tournament_size)
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
        self.toolbox.register("mutate_shrink", gp.mutShrink)

        # Evaluation
        self.toolbox.register("evaluate", self._evaluate_individual)

        # Depth limit decorators
        self.toolbox.decorate(
            "mate",
            gp.staticLimit(key=lambda ind: ind.height, max_value=self.config.max_depth)
        )
        self.toolbox.decorate(
            "mutate",
            gp.staticLimit(key=lambda ind: ind.height, max_value=self.config.max_depth)
        )

    def _get_normalize_window(self, individual) -> int:
        """Get normalize window for an individual based on expression hash."""
        expr_str = str(individual)
        hash_val = hash(expr_str)
        window_range = self.config.normalize_window_max - self.config.normalize_window_min
        window = self.config.normalize_window_min + (abs(hash_val) % window_range)
        return window

    def _evaluate_individual(self, individual) -> Tuple[float]:
        """
        Evaluate a single individual using panel data.

        Returns:
            Tuple with fitness value
        """
        self._total_evaluations += 1
        floor_value = self.fitness_config.min_fitness_floor if self.fitness_config.relaxed_mode else -np.inf

        try:
            expr_str = str(individual)

            # Check tree constraints
            depth_excess = max(0, individual.height - self.config.max_depth)
            node_excess = max(0, len(individual) - self.config.max_nodes)

            if depth_excess > 0 or node_excess > 0:
                penalty = depth_excess * 10 + node_excess * 2
                return (floor_value - penalty,)

            # Get normalize window
            normalize_window = self._get_normalize_window(individual)

            # Evaluate using panel data
            factor_panel = evaluate_expression(
                individual, self.panel_data, self.pset,
                normalize=True,
                zscore_window=normalize_window,
                clip_range=self.config.normalize_clip_range
            )

            if factor_panel is None or factor_panel.isna().all().all():
                return (floor_value - 10,)

            # Calculate fitness
            fitness_result = self.fitness_evaluator.evaluate_panel(
                factor_panel,
                self.returns_panel,
                expression=expr_str,
                tree_depth=individual.height,
                tree_nodes=len(individual)
            )

            if self.fitness_config.relaxed_mode:
                return (max(fitness_result.fitness, floor_value),)
            elif not fitness_result.valid:
                return (-np.inf,)

            return (fitness_result.fitness,)

        except Exception as e:
            return (floor_value - 20,)

    def _get_full_fitness(self, individual) -> FitnessResult:
        """Get full fitness result for an individual."""
        try:
            expr_str = str(individual)
            normalize_window = self._get_normalize_window(individual)

            factor_panel = evaluate_expression(
                individual, self.panel_data, self.pset,
                normalize=True,
                zscore_window=normalize_window,
                clip_range=self.config.normalize_clip_range
            )

            if factor_panel is None or factor_panel.isna().all().all():
                return FitnessResult(expression=expr_str, error_message="No valid factors")

            result = self.fitness_evaluator.evaluate_panel(
                factor_panel,
                self.returns_panel,
                expression=expr_str,
                tree_depth=individual.height,
                tree_nodes=len(individual)
            )

            result.normalize_window = normalize_window
            return result

        except Exception as e:
            return FitnessResult(expression=str(individual), error_message=str(e))

    def run(self, verbose: bool = True) -> EvolutionResult:
        """
        Run the factor mining evolution.

        Args:
            verbose: Print progress information

        Returns:
            EvolutionResult with best factors found
        """
        start_time = datetime.now()

        result = EvolutionResult(config=self.config)

        if verbose:
            n_assets = len(list(self.panel_data.values())[0].columns)
            print(f"\n{'='*70}")
            print(f" GP Factor Mining - Panel Data (TS + CS)")
            print(f"{'='*70}")
            print(f" Population: {self.config.population_size}")
            print(f" Generations: {self.config.generations}")
            print(f" Max depth: {self.config.max_depth} (+ zscore + clip = {self.config.max_depth + 2} total)")
            print(f" Assets: {n_assets}")
            print(f" Columns: {self.columns}")
            print(f" TS operators: {self.config.include_ts_ops}")
            print(f" CS operators: {self.config.include_cs_ops}")
            print(f" Eval mode: {self.fitness_config.eval_mode}")
            if self.fitness_config.eval_mode == 'ic':
                print(f" Label: {self.fitness_config.label_col}")
            print(f"{'='*70}\n")

        population = self.toolbox.population(n=self.config.population_size)

        # Statistics
        stats = tools.Statistics(lambda ind: ind.fitness.values[0])
        stats.register("avg", lambda x: np.mean([v for v in x if np.isfinite(v)]) if any(np.isfinite(v) for v in x) else -999)
        stats.register("max", lambda x: np.max([v for v in x if np.isfinite(v)]) if any(np.isfinite(v) for v in x) else -999)
        stats.register("min", lambda x: np.min([v for v in x if np.isfinite(v)]) if any(np.isfinite(v) for v in x) else -999)

        # Hall of fame
        hof = tools.HallOfFame(self.config.elite_size)

        # Evaluate initial population
        if verbose:
            print(f"Evaluating initial population ({len(population)} individuals)...")

        fitnesses = list(map(self.toolbox.evaluate, population))
        for ind, fit in zip(population, fitnesses):
            ind.fitness.values = fit

        hof.update(population)

        record = stats.compile(population)
        result.generation_stats.append({
            'gen': 0,
            'nevals': len(population),
            **record
        })
        result.fitness_history.append(record['max'])

        if verbose:
            print(f"Gen 0: avg={record['avg']:.4f}, max={record['max']:.4f}, evals={self._total_evaluations}")

        # Evolution loop
        best_fitness = record['max']
        no_improvement_count = 0
        gen = 0

        for gen in range(1, self.config.generations + 1):
            self._generation = gen
            gen_start = datetime.now()

            # Select offspring
            offspring = self.toolbox.select(population, len(population) - self.config.elite_size)
            offspring = list(map(self.toolbox.clone, offspring))

            # Apply crossover
            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if random.random() < self.config.crossover_prob:
                    self.toolbox.mate(child1, child2)
                    del child1.fitness.values
                    del child2.fitness.values

            # Apply mutation
            for mutant in offspring:
                if random.random() < self.config.mutation_prob:
                    r = random.random()
                    if r < self.config.mutation_subtree_prob:
                        self.toolbox.mutate(mutant)
                    elif r < self.config.mutation_subtree_prob + self.config.mutation_shrink_prob:
                        self.toolbox.mutate_shrink(mutant)
                    else:
                        self.toolbox.mutate(mutant)
                    del mutant.fitness.values

            # Evaluate offspring
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = list(map(self.toolbox.evaluate, invalid_ind))
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit

            # Add elites back
            elites = list(map(self.toolbox.clone, hof.items))
            offspring.extend(elites)

            # Replace population
            population[:] = offspring

            # Update hall of fame
            hof.update(population)

            # Record stats
            record = stats.compile(population)
            gen_time = (datetime.now() - gen_start).total_seconds()
            result.generation_stats.append({
                'gen': gen,
                'nevals': len(invalid_ind),
                'time': gen_time,
                **record
            })
            result.fitness_history.append(record['max'])

            if verbose and gen % 5 == 0:
                evals_per_sec = len(invalid_ind) / gen_time if gen_time > 0 else 0
                print(f"Gen {gen}: avg={record['avg']:.4f}, max={record['max']:.4f}, "
                      f"evals={self._total_evaluations}, {evals_per_sec:.1f} eval/s")

            # Check for improvement
            if record['max'] > best_fitness + self.config.min_improvement:
                best_fitness = record['max']
                no_improvement_count = 0
                if verbose:
                    print(f"  -> New best: {best_fitness:.4f}")
            else:
                no_improvement_count += 1

            # Early stopping
            if no_improvement_count >= self.config.early_stop_generations:
                if verbose:
                    print(f"\nEarly stopping at generation {gen}")
                break

            # Checkpoint
            if gen % self.config.save_every == 0:
                self._save_checkpoint(gen, hof, result)

            # Memory management
            if gen % self.config.gc_every_n_gens == 0:
                gc.collect()
                try:
                    import psutil
                    mem_gb = psutil.Process().memory_info().rss / (1024**3)
                    if mem_gb > self.config.max_memory_gb:
                        gc.collect()
                        gc.collect()
                        if verbose:
                            print(f"  [Memory] {mem_gb:.1f}GB > {self.config.max_memory_gb}GB limit, forced GC")
                except ImportError:
                    pass

        # Final results
        result.total_generations = gen
        result.total_evaluations = self._total_evaluations
        result.runtime_seconds = (datetime.now() - start_time).total_seconds()

        if hof:
            result.best_individual = hof[0]
            result.best_expression = str(hof[0])
            result.best_fitness = self._get_full_fitness(hof[0])

            for ind in hof:
                fitness = self._get_full_fitness(ind)
                result.top_individuals.append((ind, fitness))

        if verbose:
            self._print_summary(result)

        # Save final results
        self._save_final_results(result)

        self.fit_log = result
        return result

    def _save_checkpoint(self, gen: int, hof: tools.HallOfFame, result: EvolutionResult):
        """Save checkpoint during evolution."""
        try:
            os.makedirs(self.config.checkpoint_dir, exist_ok=True)

            checkpoint_path = os.path.join(
                self.config.checkpoint_dir,
                f"checkpoint_gen{gen}.json"
            )

            # Get full fitness for top individuals
            top_factors = []
            for ind in hof:
                fitness = self._get_full_fitness(ind)
                if fitness.sharpe > -50:
                    inner_expr = str(ind)
                    normalize_window = getattr(fitness, 'normalize_window', self._get_normalize_window(ind))
                    clip_range = self.config.normalize_clip_range
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
                        'coverage': fitness.coverage,
                        'valid': fitness.valid,
                    })

            checkpoint_data = {
                'generation': gen,
                'total_evaluations': self._total_evaluations,
                'best_sharpe': result.fitness_history[-1] if result.fitness_history else -999,
                'top_factors': top_factors,
                'fitness_history': result.fitness_history[-20:],
            }

            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)

            # Save factors by sharpe level
            sharpe_gt1 = [f for f in top_factors if f['sharpe'] > 1.0 and f['sharpe'] <= 2.0]
            sharpe_gt2 = [f for f in top_factors if f['sharpe'] > 2.0]

            def append_factors(factors, filepath):
                existing = []
                existing_expressions = set()
                if os.path.exists(filepath):
                    try:
                        with open(filepath, 'r') as f:
                            existing = json.load(f)
                            existing_expressions = {f['expression'] for f in existing}
                    except (json.JSONDecodeError, KeyError):
                        existing = []
                new_factors = [f for f in factors if f['expression'] not in existing_expressions]
                if new_factors:
                    for f in new_factors:
                        f['added_at_gen'] = gen
                    combined = existing + new_factors
                    with open(filepath, 'w') as f:
                        json.dump(combined, f, indent=2)
                return len(new_factors)

            gt1_added = 0
            if sharpe_gt1:
                gt1_path = os.path.join(self.config.checkpoint_dir, "sharpe_gt1.json")
                gt1_added = append_factors(sharpe_gt1, gt1_path)

            gt2_added = 0
            if sharpe_gt2:
                gt2_path = os.path.join(self.config.checkpoint_dir, "sharpe_gt2_GOOD.json")
                gt2_added = append_factors(sharpe_gt2, gt2_path)
                if gt2_added > 0:
                    print(f"  [Gen {gen}] *** {gt2_added} NEW GOOD factors (sharpe>2) added! ***")
            elif gt1_added > 0:
                print(f"  [Gen {gen}] {gt1_added} new decent factors (1<sharpe<=2) added")

        except Exception as e:
            print(f"Warning: Failed to save checkpoint: {e}")

    def _save_final_results(self, result: EvolutionResult):
        """Save final evolution results."""
        try:
            os.makedirs(self.config.checkpoint_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_path = os.path.join(
                self.config.checkpoint_dir,
                f"evolution_result_{timestamp}.json"
            )
            result.save(result_path)
            print(f"\nResults saved to: {result_path}")
        except Exception as e:
            print(f"Warning: Failed to save results: {e}")

    def _print_summary(self, result: EvolutionResult):
        """Print evolution summary."""
        print(f"\n{'='*60}")
        print(f" Evolution Complete")
        print(f"{'='*60}")
        print(f" Generations: {result.total_generations}")
        print(f" Evaluations: {result.total_evaluations}")
        print(f" Runtime: {result.runtime_seconds:.1f}s")

        if result.best_fitness and result.best_fitness.valid:
            print(f"\n Best Factor Found:")
            print(f"{'='*60}")
            print(f" Expression: {result.best_expression}")
            print(f"{'='*60}")
            print(f" Fitness:    {result.best_fitness.fitness:.4f}")
            print(f" Sharpe:     {result.best_fitness.sharpe:.4f}")
            if hasattr(result.best_fitness, 'ic'):
                print(f" IC:         {result.best_fitness.ic:.4f}")
            if hasattr(result.best_fitness, 'rank_ic'):
                print(f" Rank IC:    {result.best_fitness.rank_ic:.4f}")
            print(f" Turnover:   {result.best_fitness.turnover:.0f}")
            print(f" Coverage:   {result.best_fitness.coverage:.2%}")
            print(f"{'='*60}")

            print(f"\n Top {min(5, len(result.top_individuals))} Factors:")
            print(f"{'-'*60}")
            for i, (ind, fitness) in enumerate(result.top_individuals[:5]):
                if fitness.valid:
                    print(f" {i+1}. Sharpe={fitness.sharpe:.4f}, Turnover={fitness.turnover:.0f}")
                    print(f"    {str(ind)[:80]}...")

    def get_factor_panel(self, expression_str: str) -> pd.DataFrame:
        """
        Get factor panel (DataFrame) for an expression.

        Args:
            expression_str: Expression string

        Returns:
            DataFrame with factor values (rows=timestamps, cols=assets)
        """
        try:
            individual = gp.PrimitiveTree.from_string(expression_str, self.pset)
            return evaluate_expression(
                individual, self.panel_data, self.pset,
                normalize=True
            )
        except Exception as e:
            print(f"Error evaluating expression: {e}")
            return pd.DataFrame()

    def evaluate_expression_str(self, expression_str: str) -> FitnessResult:
        """
        Evaluate a specific expression string.

        Args:
            expression_str: Expression string to evaluate

        Returns:
            FitnessResult
        """
        try:
            individual = gp.PrimitiveTree.from_string(expression_str, self.pset)
            return self._get_full_fitness(individual)
        except Exception as e:
            return FitnessResult(expression=expression_str, error_message=str(e))

    def display_fitness(self):
        """Display fitness evolution history."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not available for plotting")
            return

        if self.fit_log is None:
            print("No fitness log available. Run evolution first.")
            return

        plt.figure(figsize=(10, 6))

        if hasattr(self.fit_log, 'fitness_history'):
            plt.plot(self.fit_log.fitness_history, label='max fit')
            if hasattr(self.fit_log, 'generation_stats'):
                avg_fits = [s.get('avg', 0) for s in self.fit_log.generation_stats]
                plt.plot(avg_fits, label='average fit')

        plt.xlabel('Generation')
        plt.ylabel('Fitness')
        plt.title('GP Evolution Progress')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()


__all__ = [
    'FactorMiner',
    'EvolutionConfig',
    'EvolutionResult',
]
