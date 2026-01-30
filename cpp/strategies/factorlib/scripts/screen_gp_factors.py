#!/usr/bin/env python3
"""
GP Factor Screening Script

This script provides a convenient way to:
1. Load GP factors from the registry
2. Filter by metrics (sharpe, turnover, etc.)
3. Batch backtest on real data
4. Generate reports and rankings

Usage:
    # Quick view of top factors
    python screen_gp_factors.py --top 50

    # Filter by sharpe and turnover
    python screen_gp_factors.py --min-sharpe 4.0 --max-turnover 80000

    # Full backtest on data
    python screen_gp_factors.py --backtest --data-dir /home/ch/data/parquet

    # Generate report
    python screen_gp_factors.py --report --output /home/ch/data/result/gp_report.md
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pandas as pd
import numpy as np
from datetime import datetime


def load_panel_data(data_dir: str, instruments: list = None, limit_rows: int = None):
    """Load panel data from parquet files."""
    import pyarrow.parquet as pq

    data_path = Path(data_dir)

    # Find instruments
    if instruments is None:
        instruments = [f.stem for f in data_path.glob('*.parquet')]
        instruments = [i for i in instruments if not i.startswith('.')]

    print(f"Loading {len(instruments)} instruments...")

    # Load and organize as panel
    dfs = {}
    for inst in instruments:
        fpath = data_path / f"{inst}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(fpath)
        if limit_rows:
            df = df.tail(limit_rows)
        df.index = pd.to_datetime(df.index)
        dfs[inst] = df

    if not dfs:
        raise ValueError(f"No data found in {data_dir}")

    # Build panel data dict
    first_df = list(dfs.values())[0]
    columns = ['Close', 'Open', 'High', 'Low', 'Volume']
    columns = [c for c in columns if c in first_df.columns]

    panel_data = {}
    for col in columns:
        panel_data[col] = pd.DataFrame({
            inst: df[col] for inst, df in dfs.items() if col in df.columns
        })

    # Compute returns
    close_panel = panel_data['Close']
    returns = close_panel.pct_change()
    returns = returns.replace([np.inf, -np.inf], 0).fillna(0)

    print(f"Panel shape: {close_panel.shape}")
    print(f"Date range: {close_panel.index.min()} to {close_panel.index.max()}")

    return panel_data, returns


def main():
    parser = argparse.ArgumentParser(description='GP Factor Screening Tool')

    # View options
    parser.add_argument('--top', type=int, default=20,
                       help='Show top N factors')
    parser.add_argument('--list-all', action='store_true',
                       help='List all factors')

    # Filter options
    parser.add_argument('--min-sharpe', type=float, default=0,
                       help='Minimum sharpe ratio')
    parser.add_argument('--max-sharpe', type=float, default=float('inf'),
                       help='Maximum sharpe ratio')
    parser.add_argument('--min-turnover', type=float, default=0,
                       help='Minimum turnover')
    parser.add_argument('--max-turnover', type=float, default=float('inf'),
                       help='Maximum turnover')
    parser.add_argument('--sort-by', type=str, default='sharpe',
                       choices=['sharpe', 'returns', 'turnover'],
                       help='Sort by field')

    # Backtest options
    parser.add_argument('--backtest', action='store_true',
                       help='Run backtest on real data')
    parser.add_argument('--data-dir', type=str, default='/home/ch/data/parquet',
                       help='Data directory for backtest')
    parser.add_argument('--instruments', type=str, default=None,
                       help='Comma-separated instrument list')
    parser.add_argument('--limit-rows', type=int, default=None,
                       help='Limit data rows for quick test')

    # Output options
    parser.add_argument('--report', action='store_true',
                       help='Generate markdown report')
    parser.add_argument('--output', type=str, default=None,
                       help='Output file path')
    parser.add_argument('--csv', type=str, default=None,
                       help='Save results to CSV')

    args = parser.parse_args()

    # Load GP library
    from factorlib.factors.gp_factors import gp_library
    from factorlib.factors.gp_factors.screener import (
        screen_factors, generate_report, batch_backtest
    )

    print(f"GP Factor Library: {len(gp_library)} factors")

    # Filter factors
    filtered = gp_library.filter(
        min_sharpe=args.min_sharpe,
        max_sharpe=args.max_sharpe,
        min_turnover=args.min_turnover,
        max_turnover=args.max_turnover,
    )
    print(f"After filtering: {len(filtered)} factors")

    # Simple listing (no backtest)
    if not args.backtest:
        df = filtered.to_dataframe()
        df = df.sort_values(args.sort_by, ascending=(args.sort_by == 'turnover'))

        if args.list_all:
            display_df = df
        else:
            display_df = df.head(args.top)

        # Display
        print(f"\n{'=' * 80}")
        print(f"Top {len(display_df)} GP Factors (sorted by {args.sort_by})")
        print(f"{'=' * 80}")

        cols = ['factor_id', 'sharpe', 'returns', 'turnover', 'long_ratio', 'short_ratio']
        print(display_df[cols].to_string(index=False))

        # Show some expressions
        print(f"\n{'=' * 80}")
        print("Sample Expressions:")
        print(f"{'=' * 80}")
        for _, row in display_df.head(5).iterrows():
            print(f"\n{row['factor_id']} (sharpe={row['sharpe']:.2f}):")
            print(f"  {row['expression']}")

        # Save CSV if requested
        if args.csv:
            df.to_csv(args.csv, index=False)
            print(f"\nSaved to {args.csv}")

        return

    # Run backtest
    print("\nLoading data for backtest...")
    instruments = args.instruments.split(',') if args.instruments else None
    panel_data, returns = load_panel_data(
        args.data_dir,
        instruments=instruments,
        limit_rows=args.limit_rows
    )

    # Get factor IDs to test
    factor_ids = [f.factor_id for f in filtered.list_factors(limit=args.top if not args.list_all else None)]

    print(f"\nBacktesting {len(factor_ids)} factors...")
    results = screen_factors(
        panel_data=panel_data,
        returns=returns,
        library=filtered,
        factor_ids=factor_ids,
        top_k=None,
        verbose=True,
    )

    # Display results
    print(f"\n{'=' * 80}")
    print(f"Backtest Results (Top {min(20, len(results))})")
    print(f"{'=' * 80}")

    if len(results) > 0:
        cols = ['factor_id', 'sharpe', 'ic_mean', 'ir', 'turnover', 'max_drawdown', 'gp_sharpe']
        print(results[cols].head(20).to_string(index=False))

        # Compare GP sharpe vs backtested sharpe
        print(f"\n{'=' * 80}")
        print("GP Sharpe vs Backtested Sharpe Correlation:")
        print(f"{'=' * 80}")
        corr = results['sharpe'].corr(results['gp_sharpe'])
        print(f"  Correlation: {corr:.4f}")

    # Generate report if requested
    if args.report:
        report = generate_report(results, title="GP Factor Screening Report")
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"\nReport saved to {args.output}")
        else:
            print(f"\n{report}")

    # Save CSV if requested
    if args.csv:
        results.to_csv(args.csv, index=False)
        print(f"\nResults saved to {args.csv}")


if __name__ == '__main__':
    main()
