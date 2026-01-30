#!/usr/bin/env python3
"""
Compute All Factors Script

Usage:
    # Default: compute for key5 instruments (5 coins)
    python scripts/compute_all_factors.py

    # Compute for all instruments
    python scripts/compute_all_factors.py --all

    # Custom number of workers
    python scripts/compute_all_factors.py --workers 16

    # Specific instruments
    python scripts/compute_all_factors.py --instruments BTC-USDT-SWAP ETH-USDT-SWAP

    # Custom start date
    python scripts/compute_all_factors.py --start-date 2023-01-01

Output:
    /home/ch/data/features/minute/{instrument}.parquet
"""

import os
import sys
import json
import argparse
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional

# Add project root to path
sys.path.insert(0, '/home/ch/hchen/factorlib/src')

from factorlib.factors.library import library
from factorlib.cli import load_multi_instruments, get_max_workers


# ============================================================================
# Configuration
# ============================================================================

CODE_LIST_PATH = '/home/ch/data/code_list.json'
OUTPUT_DIR = '/home/ch/data/features/minute'
DEFAULT_START_DATE = '2022-01-01 00:00:00'

# K-line only columns (OHLCV)
KLINE_COLUMNS = {'Open', 'High', 'Low', 'Close', 'Volume', 'return'}

# Tick data columns (not available in K-line data)
TICK_DATA_COLUMNS = {
    'TakerBuyQuoteAssetVolume', 'TakerSellQuoteAssetVolume',
    'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume',
    'NumberOfTrades', 'large_buy_ratio'
}


def get_kline_factors() -> List[str]:
    """Get factors that only require K-line data (exclude tick factors)."""
    kline_factors = []
    for name in library.list_factors():
        factor = library.get(name)
        required = set(factor.required_columns())
        # Check if any required column is tick data
        if not required.intersection(TICK_DATA_COLUMNS):
            kline_factors.append(name)
    return kline_factors


def load_instrument_list(use_all: bool = False) -> List[str]:
    """Load instrument list from code_list.json."""
    with open(CODE_LIST_PATH, 'r') as f:
        code_dict = json.load(f)

    if use_all and 'all' in code_dict:
        return code_dict['all']
    return code_dict.get('key5', [])


# ============================================================================
# Factor Computation
# ============================================================================

def compute_factors_for_instrument(
    inst: str,
    df: pd.DataFrame,
    factor_names: List[str]
) -> Tuple[str, pd.DataFrame, List[str], List[Tuple[str, str]]]:
    """
    Compute all factors for a single instrument.

    Returns:
        (instrument, result_df, computed_factors, failed_factors)
    """
    computed = []
    failed = []
    available_columns = set(df.columns)

    for name in factor_names:
        try:
            factor = library.get(name)
            required = set(factor.required_columns()) - {'return'}

            # Check missing columns
            missing = required - available_columns
            if missing:
                failed.append((name, f"missing: {missing}"))
                continue

            # Compute factor
            df = factor.compute(df)
            computed.append(name)

        except Exception as e:
            failed.append((name, str(e)[:80]))

    return inst, df, computed, failed


def process_instrument(args: Tuple) -> Tuple[str, Optional[str], List[str], List[Tuple[str, str]]]:
    """
    Process a single instrument: compute factors and save to parquet.

    Args:
        args: (inst, df, factor_names, output_dir)

    Returns:
        (instrument, output_path or None, computed_factors, failed_factors)
    """
    inst, df, factor_names, output_dir = args

    try:
        # Compute all factors
        inst, result_df, computed, failed = compute_factors_for_instrument(
            inst, df, factor_names
        )

        if not computed:
            return inst, None, [], failed

        # Prepare output columns
        essential_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'return']
        output_cols = [c for c in essential_cols if c in result_df.columns]
        output_cols.extend(computed)

        output_df = result_df[output_cols]

        # Save to parquet
        output_path = os.path.join(output_dir, f'{inst}.parquet')
        output_df.to_parquet(output_path, engine='pyarrow')

        return inst, output_path, computed, failed

    except Exception as e:
        return inst, None, [], [(f"instrument_error", str(e)[:80])]


# ============================================================================
# Main Functions
# ============================================================================

def show_available_factors(kline_only: bool = True) -> Tuple[int, List[str]]:
    """Display all available factors.

    Args:
        kline_only: If True, only show K-line factors (exclude tick factors)

    Returns:
        (total_count, factor_names)
    """
    print("\n[1/4] Available Factors in Library:")
    print("=" * 60)

    if kline_only:
        kline_factors = set(get_kline_factors())
        print("  (K-line factors only, tick factors excluded)")
    else:
        kline_factors = None

    by_category = library.list_by_category()
    total = 0
    factor_names = []
    skipped = []

    for category, factors in sorted(by_category.items()):
        cat_factors = []
        for name in factors:
            if kline_only and name not in kline_factors:
                skipped.append(name)
                continue
            cat_factors.append(name)
            factor_names.append(name)

        if cat_factors:
            print(f"\n  {category.upper()} ({len(cat_factors)} factors):")
            for name in cat_factors:
                factor = library.get(name)
                desc = factor.description[:45] + "..." if len(factor.description) > 45 else factor.description
                print(f"    - {name}: {desc}")
                total += 1

    print(f"\n  Total: {total} factors (K-line)")
    if skipped:
        print(f"  Skipped (tick data): {skipped}")
    print("=" * 60)
    return total, factor_names


def compute_all_factors_parallel(
    data_dict: Dict[str, pd.DataFrame],
    factor_names: List[str],
    n_workers: int = 8,
    output_dir: str = OUTPUT_DIR
) -> Dict[str, dict]:
    """
    Compute all factors for all instruments in parallel.

    Args:
        data_dict: Dict mapping instrument name to DataFrame
        factor_names: List of factor names to compute
        n_workers: Number of parallel workers
        output_dir: Output directory for parquet files

    Returns:
        Dict mapping instrument to results summary
    """
    print(f"\n[3/4] Computing {len(factor_names)} factors ({n_workers} workers)...")

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    results = {}

    start_time = datetime.now()

    # Prepare arguments for parallel processing
    args_list = [
        (inst, df, factor_names, output_dir)
        for inst, df in data_dict.items()
    ]

    # Use ThreadPoolExecutor for I/O-bound operations (ClickHouse is already handled)
    # Each instrument runs sequentially within its thread to avoid memory issues
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(process_instrument, args): args[0]
            for args in args_list
        }

        for future in as_completed(futures):
            inst = futures[future]
            try:
                inst, output_path, computed, failed = future.result()

                status = "✓" if output_path else "✗"
                print(f"    {status} {inst}: {len(computed)} factors computed")

                if failed:
                    for name, reason in failed[:3]:  # Show first 3 failures
                        print(f"        - {name}: {reason}")
                    if len(failed) > 3:
                        print(f"        ... and {len(failed) - 3} more")

                results[inst] = {
                    'output_path': output_path,
                    'computed': computed,
                    'failed': failed,
                    'n_computed': len(computed),
                    'n_failed': len(failed)
                }

            except Exception as e:
                print(f"    ✗ {inst}: Error - {str(e)[:60]}")
                results[inst] = {
                    'output_path': None,
                    'computed': [],
                    'failed': [('error', str(e))],
                    'n_computed': 0,
                    'n_failed': 1
                }

    elapsed = (datetime.now() - start_time).total_seconds()

    # Summary
    total_computed = sum(r['n_computed'] for r in results.values())
    total_failed = sum(r['n_failed'] for r in results.values())
    n_success = sum(1 for r in results.values() if r['output_path'])

    print(f"\n    Summary:")
    print(f"    - Instruments processed: {n_success}/{len(data_dict)}")
    print(f"    - Total factors computed: {total_computed}")
    print(f"    - Total failures: {total_failed}")
    print(f"    - Time: {elapsed:.1f}s")

    return results


def save_metadata(results: Dict[str, dict], output_dir: str, instruments: List[str], factor_names: List[str]):
    """Save computation metadata."""
    print(f"\n[4/4] Saving metadata...")

    metadata = {
        'computed_at': datetime.now().isoformat(),
        'instruments': instruments,
        'output_dir': output_dir,
        'factor_names': factor_names,
        'results': {
            inst: {
                'output_path': r['output_path'],
                'n_computed': r['n_computed'],
                'n_failed': r['n_failed'],
                'computed_factors': r['computed'],
                'failed_factors': [(name, reason) for name, reason in r['failed']]
            }
            for inst, r in results.items()
        }
    }

    metadata_path = os.path.join(output_dir, '_metadata.json')
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2, default=str)

    print(f"    Metadata saved to: {metadata_path}")

    # Show output files
    print(f"\n    Output files:")
    for inst, r in results.items():
        if r['output_path']:
            file_size = os.path.getsize(r['output_path']) / (1024 * 1024)
            print(f"      - {inst}.parquet ({file_size:.1f} MB, {r['n_computed']} factors)")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Compute all library factors')
    parser.add_argument('--all', action='store_true',
                        help='Compute for all instruments (default: key5 only)')
    parser.add_argument('--workers', type=int, default=None,
                        help='Number of parallel workers (default: 0.8 * cpu_count)')
    parser.add_argument('--instruments', nargs='+', default=None,
                        help='Specific instruments to compute')
    parser.add_argument('--start-date', type=str, default=DEFAULT_START_DATE,
                        help=f'Start date for data (default: {DEFAULT_START_DATE})')
    parser.add_argument('--output-dir', type=str, default=OUTPUT_DIR,
                        help=f'Output directory (default: {OUTPUT_DIR})')

    args = parser.parse_args()

    # Configuration
    n_workers = args.workers or get_max_workers()

    print("=" * 60)
    print("FactorLib - Compute All Factors (Multi-Instrument)")
    print("=" * 60)

    # Show available factors (K-line only)
    _, factor_names = show_available_factors(kline_only=True)

    # Load instrument list
    if args.instruments:
        instruments = args.instruments
        print(f"\n[2/4] Loading specified instruments: {instruments}")
    else:
        instruments = load_instrument_list(use_all=args.all)
        mode = "ALL" if args.all else "key5"
        print(f"\n[2/4] Loading instruments ({mode}): {instruments}")

    # Load data for all instruments in parallel
    print(f"    Loading from ClickHouse (start: {args.start_date})...")
    data_dict = load_multi_instruments(
        instruments=instruments,
        start_date=args.start_date,
        max_workers=n_workers
    )

    if not data_dict:
        print("Error: No data loaded!")
        return 1

    print(f"    Loaded {len(data_dict)} instruments:")
    for inst, df in data_dict.items():
        print(f"      - {inst}: {len(df):,} rows")

    # Compute all factors in parallel
    results = compute_all_factors_parallel(
        data_dict=data_dict,
        factor_names=factor_names,
        n_workers=n_workers,
        output_dir=args.output_dir
    )

    # Save metadata
    save_metadata(results, args.output_dir, instruments, factor_names)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main())
