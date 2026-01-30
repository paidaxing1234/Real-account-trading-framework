"""
Fitness Function for Factor Mining - Unified Panel Data Version

Evaluates factor quality on Panel Data (DataFrame: rows=timestamps, cols=assets).

Metrics:
1. Information Coefficient (IC): Correlation between factor and future returns
2. Rank IC: Spearman correlation (more robust to outliers)
3. IC IR: IC stability (mean IC / std IC)
4. Long-short portfolio Sharpe ratio
5. Turnover constraint
6. Coverage
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from factorlib.utils.operators import ops


@dataclass
class FitnessResult:
    """Result of fitness evaluation."""
    # Primary metrics
    sharpe: float = -np.inf
    returns: float = 0.0
    turnover: float = np.inf

    # IC metrics
    ic: float = 0.0
    rank_ic: float = 0.0
    ic_ir: float = 0.0

    # Position metrics
    long_ratio: float = 0.0
    short_ratio: float = 0.0
    position_balance: float = 0.0

    # Quality metrics
    coverage: float = 0.0
    max_drawdown: float = -1.0
    kamma_ratio: float = 0.0

    # Penalty factors
    complexity_penalty: float = 0.0
    turnover_penalty: float = 0.0
    position_penalty: float = 0.0

    # Final fitness
    fitness: float = -np.inf

    # Expression info
    expression: str = ""
    valid: bool = False
    error_message: str = ""

    def __repr__(self):
        return (
            f"FitnessResult(\n"
            f"  fitness={self.fitness:.4f},\n"
            f"  sharpe={self.sharpe:.4f},\n"
            f"  ic={self.ic:.4f},\n"
            f"  rank_ic={self.rank_ic:.4f},\n"
            f"  returns={self.returns:.2f}%,\n"
            f"  turnover={self.turnover:.0f},\n"
            f"  coverage={self.coverage:.2%},\n"
            f"  valid={self.valid}\n"
            f")"
        )


@dataclass
class FitnessConfig:
    """Configuration for fitness evaluation."""
    # Evaluation mode: 'ic' (default) or 'sharpe'
    eval_mode: str = 'ic'  # 'ic' 使用IC作为评判标准 (默认), 'sharpe' 使用收益回测

    # Label selection for IC mode (用于计算因子与未来收益的相关性)
    label_col: str = 'ret#l#15m'  # 默认使用15分钟未来收益作为label

    # Turnover constraint
    max_turnover: float = 3000.0
    target_turnover: float = 2000.0
    turnover_penalty_weight: float = 0.1

    # Position balance targets
    target_long_ratio: float = 0.5
    target_short_ratio: float = -0.5
    min_long_ratio: float = 0.1
    min_short_ratio: float = -0.1
    position_penalty_weight: float = 0.05

    # Complexity penalty
    max_depth: int = 4  # 内部表达式深度，加zscore+clip后为6层
    depth_penalty_weight: float = 0.02
    node_penalty_weight: float = 0.002

    # Coverage requirements
    min_coverage: float = 0.15

    # Position mode
    position_mode: str = 'long_short'  # 'long_short' or 'direct'
    position_clip: float = 3.0
    long_short_pct: float = 0.2  # Top/bottom percentage for long/short

    # Sharpe calculation
    annualization_factor: float = np.sqrt(365 * 24 * 60)  # 1-minute data

    # Fitness weighting for sharpe mode (IC vs Sharpe)
    ic_weight: float = 0.3
    rank_ic_weight: float = 0.3
    ic_ir_weight: float = 0.2
    sharpe_weight: float = 0.2

    # Fitness weighting for ic mode (纯IC模式)
    ic_mode_ic_weight: float = 0.4
    ic_mode_rank_ic_weight: float = 0.4
    ic_mode_ic_ir_weight: float = 0.2

    # Relaxed mode
    relaxed_mode: bool = True
    min_fitness_floor: float = -100.0


class FitnessEvaluator:
    """
    Unified Fitness Evaluator for Panel Data.

    Evaluates factor quality using both cross-sectional and time-series metrics.
    Works with panel data: DataFrame (rows=timestamps, columns=assets).

    Supports two evaluation modes:
    - 'sharpe': Uses long-short portfolio Sharpe ratio (default)
    - 'ic': Uses IC with specified label as primary metric
    """

    def __init__(self, config: FitnessConfig = None):
        self.config = config or FitnessConfig()
        self.label_panel = None  # 用于IC模式的label数据

    def set_label_panel(self, label_panel: pd.DataFrame):
        """设置IC模式使用的label panel"""
        self.label_panel = label_panel

    def evaluate_panel(
        self,
        factor_panel: pd.DataFrame,
        returns_panel: pd.DataFrame,
        expression: str = "",
        tree_depth: int = 0,
        tree_nodes: int = 0,
        label_panel: pd.DataFrame = None,
    ) -> FitnessResult:
        """
        Evaluate factor panel against returns panel.

        Args:
            factor_panel: Factor values (rows=timestamps, cols=assets)
            returns_panel: Asset returns (rows=timestamps, cols=assets)
            expression: Expression string for logging
            tree_depth: Expression tree depth
            tree_nodes: Number of nodes
            label_panel: Optional label panel for IC mode (overrides self.label_panel)

        Returns:
            FitnessResult with all metrics
        """
        result = FitnessResult(expression=expression)

        try:
            # 确定用于计算IC的目标panel
            # IC模式: 使用label_panel; Sharpe模式: 使用returns_panel
            if self.config.eval_mode == 'ic':
                target_panel = label_panel if label_panel is not None else self.label_panel
                if target_panel is None:
                    target_panel = returns_panel  # fallback
            else:
                target_panel = returns_panel

            # Align factor and target
            common_index = factor_panel.index.intersection(target_panel.index)
            common_cols = factor_panel.columns.intersection(target_panel.columns)

            if len(common_index) < 100 or len(common_cols) < 2:
                result.error_message = "Insufficient data for evaluation"
                if self.config.relaxed_mode:
                    result.fitness = self.config.min_fitness_floor
                return result

            factor_aligned = factor_panel.loc[common_index, common_cols]
            target_aligned = target_panel.loc[common_index, common_cols]
            returns_aligned = returns_panel.loc[common_index, common_cols]

            # Calculate coverage
            non_nan_ratio = factor_aligned.notna().mean().mean()
            result.coverage = non_nan_ratio

            if non_nan_ratio < self.config.min_coverage:
                if self.config.relaxed_mode:
                    coverage_penalty = (self.config.min_coverage - non_nan_ratio) * 50
                    result.error_message = f"Coverage low: {non_nan_ratio:.2%}"
                    result.fitness = self.config.min_fitness_floor - coverage_penalty
                    return result
                else:
                    result.error_message = f"Coverage too low: {non_nan_ratio:.2%}"
                    return result

            # ============================================================
            # Calculate Information Coefficient (IC)
            # IC模式使用target_panel(label), Sharpe模式使用returns_panel
            # ============================================================
            # 不需要shift，因为label本身就是未来收益
            # 但如果是returns_panel则需要shift
            if self.config.eval_mode == 'ic':
                # IC模式：label已经是未来收益，不需要shift factor
                factor_for_ic = factor_aligned
                target_for_ic = target_aligned
            else:
                # Sharpe模式：用当前factor预测下一期收益
                factor_for_ic = factor_aligned.shift(1)
                target_for_ic = returns_aligned

            # Calculate IC at each timestamp (row-wise correlation)
            ic_series = []
            rank_ic_series = []

            start_idx = 0 if self.config.eval_mode == 'ic' else 1
            for idx in factor_for_ic.index[start_idx:]:
                factor_row = factor_for_ic.loc[idx]
                target_row = target_for_ic.loc[idx]

                valid_mask = factor_row.notna() & target_row.notna()
                if valid_mask.sum() < 2:
                    continue

                f_vals = factor_row[valid_mask].values
                t_vals = target_row[valid_mask].values

                # Pearson correlation (IC)
                if np.std(f_vals) > 1e-10 and np.std(t_vals) > 1e-10:
                    ic = np.corrcoef(f_vals, t_vals)[0, 1]
                    if np.isfinite(ic):
                        ic_series.append(ic)

                # Spearman correlation (Rank IC)
                try:
                    from scipy import stats
                    rank_ic, _ = stats.spearmanr(f_vals, t_vals)
                    if np.isfinite(rank_ic):
                        rank_ic_series.append(rank_ic)
                except:
                    pass

            if len(ic_series) < 10:
                result.error_message = "Insufficient IC data points"
                if self.config.relaxed_mode:
                    result.fitness = self.config.min_fitness_floor
                return result

            # IC statistics
            ic_mean = np.mean(ic_series)
            ic_std = np.std(ic_series) if len(ic_series) > 1 else 1.0
            ic_ir = ic_mean / (ic_std + 1e-10)

            rank_ic_mean = np.mean(rank_ic_series) if rank_ic_series else ic_mean

            result.ic = ic_mean
            result.rank_ic = rank_ic_mean
            result.ic_ir = ic_ir

            # IC模式：直接用IC计算fitness，跳过Sharpe计算
            if self.config.eval_mode == 'ic':
                # Complexity penalty
                depth_penalty = max(0, tree_depth - self.config.max_depth) * self.config.depth_penalty_weight
                node_penalty = tree_nodes * self.config.node_penalty_weight
                result.complexity_penalty = depth_penalty + node_penalty

                # Calculate fitness for IC mode
                result.fitness = self._calculate_ic_fitness(result)
                result.valid = True
                return result

            # ============================================================
            # Calculate long-short portfolio performance
            # ============================================================
            positions = ops.cs_long_short(factor_aligned, pct=self.config.long_short_pct)
            positions_shifted = positions.shift(1)

            # Calculate strategy returns
            strategy_returns = positions_shifted * returns_aligned
            portfolio_returns = strategy_returns.mean(axis=1).dropna()

            if len(portfolio_returns) < 100:
                result.error_message = "Insufficient portfolio data"
                if self.config.relaxed_mode:
                    result.fitness = self.config.min_fitness_floor
                return result

            # Calculate Sharpe ratio
            mean_ret = portfolio_returns.mean()
            std_ret = portfolio_returns.std()

            if std_ret > 1e-10:
                result.sharpe = (mean_ret / std_ret) * self.config.annualization_factor
            else:
                result.sharpe = 0.0

            result.returns = mean_ret * len(portfolio_returns) * 100

            # Calculate turnover
            position_changes = positions_shifted.diff().abs().mean(axis=1).sum()
            n_periods = len(positions_shifted.dropna())
            result.turnover = (position_changes / n_periods) * 365 * 24 * 60 if n_periods > 0 else 0

            # Position statistics
            pos_flat = positions_shifted.values.flatten()
            pos_flat = pos_flat[np.isfinite(pos_flat)]
            result.long_ratio = np.mean(pos_flat[pos_flat > 0]) if np.any(pos_flat > 0) else 0
            result.short_ratio = np.mean(pos_flat[pos_flat < 0]) if np.any(pos_flat < 0) else 0

            # Max drawdown
            cum_ret = (1 + portfolio_returns).cumprod()
            peak = cum_ret.cummax()
            drawdown = (cum_ret - peak) / peak
            result.max_drawdown = float(drawdown.min())

            # Turnover penalty
            if result.turnover > self.config.max_turnover:
                excess = (result.turnover - self.config.max_turnover) / self.config.max_turnover
                result.turnover_penalty = excess * self.config.turnover_penalty_weight
            else:
                result.turnover_penalty = -0.1 * (1 - result.turnover / self.config.max_turnover)

            # Complexity penalty
            depth_penalty = max(0, tree_depth - self.config.max_depth) * self.config.depth_penalty_weight
            node_penalty = tree_nodes * self.config.node_penalty_weight
            result.complexity_penalty = depth_penalty + node_penalty

            # Calculate final fitness
            result.fitness = self._calculate_fitness(result)
            result.valid = True

        except Exception as e:
            result.error_message = str(e)
            if self.config.relaxed_mode:
                result.fitness = self.config.min_fitness_floor
            else:
                result.fitness = -np.inf

        return result

    def _calculate_fitness(self, result: FitnessResult) -> float:
        """
        Calculate final fitness score for Sharpe mode.

        Combines IC-based metrics and Sharpe ratio with configurable weights.
        """
        # Scale IC metrics
        ic_component = result.ic * 100
        rank_ic_component = result.rank_ic * 100
        ic_ir_component = result.ic_ir * 10
        sharpe_component = result.sharpe

        # Weighted combination
        base_fitness = (
            self.config.ic_weight * ic_component +
            self.config.rank_ic_weight * rank_ic_component +
            self.config.ic_ir_weight * ic_ir_component +
            self.config.sharpe_weight * sharpe_component
        )

        # Penalties
        total_penalty = (
            result.turnover_penalty * 0.3 +
            result.position_penalty * 0.2 +
            result.complexity_penalty * 0.1
        )

        # Coverage bonus
        coverage_bonus = result.coverage * 0.2 * max(base_fitness, 0.1)

        fitness = base_fitness - total_penalty + coverage_bonus

        if self.config.relaxed_mode:
            fitness = max(fitness, self.config.min_fitness_floor)

        return fitness

    def _calculate_ic_fitness(self, result: FitnessResult) -> float:
        """
        Calculate final fitness score for IC mode.

        Uses only IC-based metrics, no Sharpe ratio.
        """
        # Scale IC metrics (IC一般在0.01-0.05之间，需要放大)
        ic_component = result.ic * 100  # 0.01 -> 1.0
        rank_ic_component = result.rank_ic * 100
        ic_ir_component = result.ic_ir * 10  # IC_IR一般在0.1-0.5之间

        # Weighted combination (纯IC模式)
        base_fitness = (
            self.config.ic_mode_ic_weight * ic_component +
            self.config.ic_mode_rank_ic_weight * rank_ic_component +
            self.config.ic_mode_ic_ir_weight * ic_ir_component
        )

        # Complexity penalty
        total_penalty = result.complexity_penalty * 0.1

        # Coverage bonus
        coverage_bonus = result.coverage * 0.2 * max(base_fitness, 0.1)

        fitness = base_fitness - total_penalty + coverage_bonus

        if self.config.relaxed_mode:
            fitness = max(fitness, self.config.min_fitness_floor)

        return fitness


def calculate_sharpe(returns: pd.Series, annualize: bool = True) -> float:
    """
    Calculate Sharpe ratio.

    Args:
        returns: Strategy returns
        annualize: Whether to annualize (assumes 1-min data)

    Returns:
        Sharpe ratio
    """
    if returns is None or len(returns) == 0:
        return 0.0

    mean_ret = returns.mean()
    std_ret = returns.std()

    if std_ret < 1e-10:
        return 0.0

    sharpe = mean_ret / std_ret

    if annualize:
        sharpe *= np.sqrt(365 * 24 * 60)

    return sharpe


def calculate_turnover(positions: pd.Series, annualize: bool = True) -> float:
    """
    Calculate turnover.

    Args:
        positions: Position series
        annualize: Whether to annualize

    Returns:
        Turnover rate
    """
    if positions is None or len(positions) < 2:
        return 0.0

    changes = positions.diff().abs().sum()
    n_periods = len(positions)

    turnover = changes / n_periods

    if annualize:
        turnover *= 365 * 24 * 60

    return turnover


def calculate_ic(
    factor_panel: pd.DataFrame,
    returns_panel: pd.DataFrame,
    lag: int = 1
) -> Tuple[float, float, float]:
    """
    Calculate Information Coefficient metrics.

    Args:
        factor_panel: Factor values (rows=timestamps, cols=assets)
        returns_panel: Asset returns (rows=timestamps, cols=assets)
        lag: Lag for factor (default 1)

    Returns:
        (ic_mean, rank_ic_mean, ic_ir) tuple
    """
    # Align
    common_index = factor_panel.index.intersection(returns_panel.index)
    common_cols = factor_panel.columns.intersection(returns_panel.columns)

    factor_aligned = factor_panel.loc[common_index, common_cols].shift(lag)
    returns_aligned = returns_panel.loc[common_index, common_cols]

    ic_series = []
    rank_ic_series = []

    for idx in factor_aligned.index[lag:]:
        factor_row = factor_aligned.loc[idx]
        returns_row = returns_aligned.loc[idx]

        valid_mask = factor_row.notna() & returns_row.notna()
        if valid_mask.sum() < 2:
            continue

        f_vals = factor_row[valid_mask].values
        r_vals = returns_row[valid_mask].values

        if np.std(f_vals) > 1e-10 and np.std(r_vals) > 1e-10:
            ic = np.corrcoef(f_vals, r_vals)[0, 1]
            if np.isfinite(ic):
                ic_series.append(ic)

        try:
            from scipy import stats
            rank_ic, _ = stats.spearmanr(f_vals, r_vals)
            if np.isfinite(rank_ic):
                rank_ic_series.append(rank_ic)
        except:
            pass

    if not ic_series:
        return 0.0, 0.0, 0.0

    ic_mean = np.mean(ic_series)
    ic_std = np.std(ic_series) if len(ic_series) > 1 else 1.0
    ic_ir = ic_mean / (ic_std + 1e-10)
    rank_ic_mean = np.mean(rank_ic_series) if rank_ic_series else ic_mean

    return ic_mean, rank_ic_mean, ic_ir


__all__ = [
    'FitnessResult',
    'FitnessConfig',
    'FitnessEvaluator',
    'calculate_sharpe',
    'calculate_turnover',
    'calculate_ic',
]
