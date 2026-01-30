import argparse
import pandas as pd
import numpy as np
import os
from typing import List, Union, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from factorlib.backtest.engine import run_backtest, performance_by_year, plot_cum_return
from factorlib.tick import TickFactorProcessor


# ============================================================================
# Instrument Name Normalization
# ============================================================================

def normalize_instrument(name: str, suffix: str = '-SWAP') -> str:
    """
    标准化品种名称，自动添加后缀

    Args:
        name: 品种名称 (e.g., 'BTC-USDT' 或 'BTC-USDT-SWAP')
        suffix: 后缀 (默认 '-SWAP'，传 '' 或 None 则不添加)

    Returns:
        标准化后的名称
    """
    if not suffix:
        return name
    if not name.endswith(suffix):
        return name + suffix
    return name


def normalize_instruments(names: List[str], suffix: str = '-SWAP') -> List[str]:
    """批量标准化品种名称"""
    return [normalize_instrument(n, suffix) for n in names]


def _get_suffix_for_data_dir(data_dir: str) -> str:
    """
    根据数据目录判断是否需要 -SWAP 后缀

    - OKX_1m_candles_data_agg (合约) -> '-SWAP'
    - OKX_1m_candles_spot_data_agg (现货) -> ''
    """
    if data_dir and 'spot' in data_dir.lower():
        return ''  # 现货不加后缀
    return '-SWAP'  # 合约加后缀


# ============================================================================
# PanelData - Unified Multi-Asset Data Format
# ============================================================================

@dataclass
class PanelData:
    """
    Panel Data - 统一的多资产数据格式

    每个属性都是一个 DataFrame (rows=timestamps, cols=assets)
    支持 TS 和 CS 算子直接操作

    Usage:
        panel = load_panel_data(instruments=['BTC-USDT-SWAP', 'ETH-USDT-SWAP'])

        # 直接访问
        close = panel.Close      # DataFrame (rows=time, cols=assets)
        ret = panel.return_      # DataFrame

        # 也可以用 dict-like 访问
        close = panel['Close']

        # 获取所有可用列
        print(panel.columns)

        # 获取资产列表
        print(panel.assets)
    """
    Close: pd.DataFrame = None
    Open: pd.DataFrame = None
    High: pd.DataFrame = None
    Low: pd.DataFrame = None
    Volume: pd.DataFrame = None
    return_: pd.DataFrame = None  # 'return' is reserved keyword
    QuoteAssetVolume: pd.DataFrame = None
    TakerBuyBaseAssetVolume: pd.DataFrame = None
    TakerSellBaseAssetVolume: pd.DataFrame = None
    TakerBuyQuoteAssetVolume: pd.DataFrame = None
    TakerSellQuoteAssetVolume: pd.DataFrame = None
    NumberOfTrades: pd.DataFrame = None

    # 额外的列存储在这里
    _extra: Dict[str, pd.DataFrame] = field(default_factory=dict)

    # 原始 data_dict（可选，用于兼容旧代码）
    _data_dict: Dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)

    def __getitem__(self, key: str) -> pd.DataFrame:
        """支持 panel['Close'] 访问"""
        if key == 'return':
            return self.return_
        if hasattr(self, key) and getattr(self, key) is not None:
            return getattr(self, key)
        if key in self._extra:
            return self._extra[key]
        raise KeyError(f"Column '{key}' not found. Available: {self.columns}")

    def __setitem__(self, key: str, value: pd.DataFrame):
        """支持 panel['new_col'] = df 设置"""
        if key == 'return':
            self.return_ = value
        elif hasattr(self, key) and not key.startswith('_'):
            setattr(self, key, value)
        else:
            self._extra[key] = value

    def __contains__(self, key: str) -> bool:
        """支持 'Close' in panel"""
        if key == 'return':
            return self.return_ is not None
        if hasattr(self, key) and getattr(self, key) is not None:
            return True
        return key in self._extra

    @property
    def columns(self) -> List[str]:
        """返回所有可用的列名"""
        cols = []
        for attr in ['Close', 'Open', 'High', 'Low', 'Volume', 'return_',
                     'QuoteAssetVolume', 'TakerBuyBaseAssetVolume',
                     'TakerSellBaseAssetVolume', 'TakerBuyQuoteAssetVolume',
                     'TakerSellQuoteAssetVolume', 'NumberOfTrades']:
            if getattr(self, attr) is not None:
                name = 'return' if attr == 'return_' else attr
                cols.append(name)
        cols.extend(self._extra.keys())
        return cols

    @property
    def assets(self) -> List[str]:
        """返回资产列表"""
        for attr in ['Close', 'Open', 'High', 'Low', 'Volume', 'return_']:
            df = getattr(self, attr)
            if df is not None:
                return list(df.columns)
        return []

    @property
    def index(self) -> pd.DatetimeIndex:
        """返回时间索引"""
        for attr in ['Close', 'Open', 'High', 'Low', 'Volume', 'return_']:
            df = getattr(self, attr)
            if df is not None:
                return df.index
        return pd.DatetimeIndex([])

    @property
    def shape(self) -> tuple:
        """返回 (n_timestamps, n_assets)"""
        if self.Close is not None:
            return self.Close.shape
        return (0, 0)

    def to_dict(self) -> Dict[str, pd.DataFrame]:
        """转换为 {column_name -> DataFrame} 格式"""
        result = {}
        for col in self.columns:
            result[col] = self[col]
        return result

    def get_data_dict(self) -> Dict[str, pd.DataFrame]:
        """获取原始 data_dict（兼容旧代码）"""
        return self._data_dict

    def info(self):
        """打印数据信息"""
        print(f"PanelData:")
        print(f"  Assets: {len(self.assets)} ({', '.join(self.assets[:5])}{'...' if len(self.assets) > 5 else ''})")
        print(f"  Time range: {self.index.min()} -> {self.index.max()}")
        print(f"  Shape: {self.shape[0]:,} timestamps x {self.shape[1]} assets")
        print(f"  Columns: {self.columns}")


def _build_panel_from_data_dict(
    data_dict: Dict[str, pd.DataFrame],
    columns: List[str] = None
) -> PanelData:
    """
    从 data_dict 构建 PanelData。

    Args:
        data_dict: Dict[instrument -> DataFrame]
        columns: 要提取的列（默认自动检测）

    Returns:
        PanelData 对象
    """
    if not data_dict:
        return PanelData()

    sample_df = next(iter(data_dict.values()))

    if columns is None:
        # 自动检测所有可用列
        candidate_cols = [
            'Close', 'Open', 'High', 'Low', 'Volume', 'return',
            'QuoteAssetVolume', 'TakerBuyBaseAssetVolume', 'TakerSellBaseAssetVolume',
            'TakerBuyQuoteAssetVolume', 'TakerSellQuoteAssetVolume', 'NumberOfTrades',
        ]
        columns = [c for c in candidate_cols if c in sample_df.columns]
        # 添加其他非标准列
        for col in sample_df.columns:
            if col not in columns and col not in ['instrument', 'instrument_name', 'OpenTime', 'datetime']:
                columns.append(col)

    panel = PanelData(_data_dict=data_dict)

    for col in columns:
        col_dict = {}
        for inst, df in data_dict.items():
            if col in df.columns:
                col_dict[inst] = df[col]

        if col_dict:
            panel_df = pd.DataFrame(col_dict)
            if col == 'return':
                panel.return_ = panel_df
            elif hasattr(panel, col):
                setattr(panel, col, panel_df)
            else:
                panel._extra[col] = panel_df

    return panel


def load_panel_data(
    instruments: List[str],
    start_date: str = '2021-01-01 00:00:00',
    max_workers: int = None,
    columns: List[str] = None,
    **kwargs
) -> PanelData:
    """
    加载多资产数据，返回统一的 PanelData 格式。

    Args:
        instruments: 资产列表
        start_date: 起始日期
        max_workers: 并行 workers 数
        columns: 要加载的列（默认自动检测）
        **kwargs: 传递给 load_kline_from_clickhouse 的参数

    Returns:
        PanelData 对象，每个属性都是 DataFrame (rows=time, cols=assets)

    Example:
        panel = load_panel_data(['BTC-USDT-SWAP', 'ETH-USDT-SWAP'])

        # 直接使用
        close = panel.Close      # DataFrame
        ret = panel.return_      # DataFrame

        # 或者 dict-like
        close = panel['Close']

        # 查看信息
        panel.info()
    """
    print(f"Loading {len(instruments)} instruments from {start_date}...")

    # 先加载为 data_dict
    data_dict = load_multi_instruments(
        instruments=instruments,
        start_date=start_date,
        max_workers=max_workers,
        **kwargs
    )

    if not data_dict:
        raise ValueError("No data loaded for any instrument")

    # 转换为 PanelData
    panel = _build_panel_from_data_dict(data_dict, columns)

    print(f"Loaded PanelData: {panel.shape[0]:,} timestamps x {len(panel.assets)} assets")
    print(f"Assets: {panel.assets}")

    return panel

# ============================================================================
# Configuration
# ============================================================================

def get_max_workers(frac: float = 0.8) -> int:
    """
    Get recommended max workers for parallel processing.

    Priority:
    1. Environment variable FACTORLIB_MAX_WORKERS
    2. frac * cpu_count (default 0.8)
    """
    env_val = os.getenv('FACTORLIB_MAX_WORKERS')
    if env_val:
        try:
            return max(1, int(env_val))
        except ValueError:
            pass
    cpu = os.cpu_count() or 4
    return max(1, int(cpu * frac))


# ============================================================================
# ClickHouse Data Loading
# ============================================================================

def load_kline_from_clickhouse(
    instrument_name: str = 'BTC-USDT-SWAP',
    start_date: str = '2021-01-01 00:00:00',
    host: str = '192.168.193.1',
    port: int = 9000,  # TCP port (changed from HTTP 8123)
    username: str = 'default',
    password: str = 'SQ2025',
    database: str = 'OKX',
    table: str = '1m_candles_data'
) -> pd.DataFrame:
    """Load K-line data for single instrument from ClickHouse (TCP connection)"""
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)

    from clickhouse_driver import Client

    client = Client(
        host=host, port=port, user=username,
        password=password, database=database
    )

    try:
        sql_query = f"""
            SELECT * FROM {table}
            WHERE instrument_name = '{instrument_name}'
              AND open_time >= toUnixTimestamp('{start_date}') * 1000
            ORDER BY open_time
        """
        df = client.query_dataframe(sql_query)

        if df.empty:
            raise ValueError(f"No data found for {instrument_name}")

        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
        df['CloseTime'] = df['open_time'] + pd.Timedelta(minutes=1) - pd.Timedelta(milliseconds=1)

        column_mapping = {
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
            'volume': 'Volume', 'quote_volume': 'QuoteAssetVolume',
            'vol': 'Volume', 'vol_ccy': 'QuoteAssetVolume',
            'taker_buy_volume': 'TakerBuyBaseAssetVolume',
            'taker_buy_quote_volume': 'TakerBuyQuoteAssetVolume',
            'trade_count': 'NumberOfTrades', 'open_time': 'OpenTime'
        }
        df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns}, inplace=True)

        df.set_index('CloseTime', inplace=True)
        df['return'] = (df['Close'] / df['Close'].shift(1) - 1).fillna(0)
        df['instrument'] = instrument_name

        if 'TakerBuyBaseAssetVolume' in df.columns and 'Volume' in df.columns:
            df['TakerSellBaseAssetVolume'] = df['Volume'] - df['TakerBuyBaseAssetVolume']
        if 'TakerBuyQuoteAssetVolume' in df.columns and 'QuoteAssetVolume' in df.columns:
            df['TakerSellQuoteAssetVolume'] = df['QuoteAssetVolume'] - df['TakerBuyQuoteAssetVolume']

        return df

    finally:
        client.disconnect()


def load_multi_instruments(
    instruments: List[str],
    start_date: str = '2021-01-01 00:00:00',
    max_workers: int = None,
    **kwargs
) -> Dict[str, pd.DataFrame]:
    """
    Load K-line data for multiple instruments in parallel.

    Args:
        instruments: List of instrument names
        start_date: Start date for data
        max_workers: Number of parallel workers (default: 0.8 * cpu_count)
        **kwargs: Additional arguments for load_kline_from_clickhouse

    Returns:
        Dict mapping instrument name to DataFrame
    """
    if max_workers is None:
        max_workers = get_max_workers()

    results = {}

    def load_one(inst):
        try:
            df = load_kline_from_clickhouse(
                instrument_name=inst,
                start_date=start_date,
                **kwargs
            )
            return inst, df
        except Exception as e:
            print(f"Warning: Failed to load {inst}: {e}")
            return inst, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(load_one, inst) for inst in instruments]
        for future in futures:
            inst, df = future.result()
            if df is not None:
                results[inst] = df

    return results


# ============================================================================
# Parquet Data Loading (Local Files)
# ============================================================================

# K线数据目录
KLINE_DIR_1M = '/home/ch/data/labels/OKX/OKX_1m_candles_data_agg'        # 1分钟合约
KLINE_DIR_1M_SPOT = '/home/ch/data/labels/OKX/OKX_1m_candles_spot_data_agg'  # 1分钟现货
KLINE_DIR_1S = '/home/ch/data/labels/OKX/OKX_1s_candles_data_agg'        # 1秒合约

# Orderbook 数据目录（仅合约）
ORDERBOOK_DIR = '/home/ch/data/orderbooks/OKX_PERP'

# 默认使用 1分钟合约
DEFAULT_PARQUET_DIR = KLINE_DIR_1M


def load_kline_from_parquet(
    instrument_name: str = 'BTC-USDT-SWAP',
    start_date: str = '2021-01-01 00:00:00',
    data_dir: str = DEFAULT_PARQUET_DIR,
) -> pd.DataFrame:
    """
    Load K-line data for single instrument from local parquet file.

    Args:
        instrument_name: Instrument name (e.g., 'BTC-USDT-SWAP')
        start_date: Start date for data filtering
        data_dir: Directory containing parquet files

    Returns:
        DataFrame with standardized columns
    """
    file_path = os.path.join(data_dir, f'{instrument_name}_labels.parquet')

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Parquet file not found: {file_path}")

    df = pd.read_parquet(file_path)

    if df.empty:
        raise ValueError(f"No data found for {instrument_name}")

    # 处理时间列
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
        df['CloseTime'] = df['datetime'] + pd.Timedelta(minutes=1) - pd.Timedelta(milliseconds=1)
    elif 'open_time' in df.columns:
        df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
        df['CloseTime'] = df['open_time'] + pd.Timedelta(minutes=1) - pd.Timedelta(milliseconds=1)

    # 列名映射 (parquet 格式)
    column_mapping = {
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
        'vol': 'Volume', 'vol_ccy': 'QuoteAssetVolume',
        'vol_ccy_quote': 'QuoteAssetVolumeQuote',
        'count': 'NumberOfTrades',
        'taker_buy_vol': 'TakerBuyBaseAssetVolume',
        'taker_buy_vol_ccy': 'TakerBuyQuoteAssetVolume',
        'taker_buy_vol_ccy_quote': 'TakerBuyQuoteAssetVolumeQuote',
        'taker_buy_count': 'TakerBuyCount',
        'open_time': 'OpenTime',
    }
    df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns}, inplace=True)

    # 设置索引
    df.set_index('CloseTime', inplace=True)

    # 过滤起始日期
    if start_date:
        start_dt = pd.to_datetime(start_date, utc=True)
        df = df[df.index >= start_dt]

    # 计算 return（如果没有）
    if 'return' not in df.columns:
        df['return'] = (df['Close'] / df['Close'].shift(1) - 1).fillna(0)

    df['instrument'] = instrument_name

    # 计算 Sell 成交量
    if 'TakerBuyBaseAssetVolume' in df.columns and 'Volume' in df.columns:
        df['TakerSellBaseAssetVolume'] = df['Volume'] - df['TakerBuyBaseAssetVolume']
    if 'TakerBuyQuoteAssetVolume' in df.columns and 'QuoteAssetVolume' in df.columns:
        df['TakerSellQuoteAssetVolume'] = df['QuoteAssetVolume'] - df['TakerBuyQuoteAssetVolume']

    return df


def load_multi_instruments_parquet(
    instruments: List[str],
    start_date: str = '2021-01-01 00:00:00',
    max_workers: int = None,
    data_dir: str = DEFAULT_PARQUET_DIR,
) -> Dict[str, pd.DataFrame]:
    """
    Load K-line data for multiple instruments from parquet files in parallel.

    Args:
        instruments: List of instrument names
        start_date: Start date for data
        max_workers: Number of parallel workers (default: 0.8 * cpu_count)
        data_dir: Directory containing parquet files

    Returns:
        Dict mapping instrument name to DataFrame
    """
    if max_workers is None:
        max_workers = get_max_workers()

    results = {}

    def load_one(inst):
        try:
            df = load_kline_from_parquet(
                instrument_name=inst,
                start_date=start_date,
                data_dir=data_dir,
            )
            return inst, df
        except Exception as e:
            print(f"Warning: Failed to load {inst}: {e}")
            return inst, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(load_one, inst) for inst in instruments]
        for future in futures:
            inst, df = future.result()
            if df is not None:
                results[inst] = df

    return results


def load_panel_data_parquet(
    instruments: List[str],
    start_date: str = '2021-01-01 00:00:00',
    max_workers: int = None,
    columns: List[str] = None,
    data_dir: str = DEFAULT_PARQUET_DIR,
    orderbook_dir: str = None,
    ob_levels: int = 5,
    use_cache: bool = True,
    cache_dir: str = None,
) -> 'PanelData':
    """
    加载多资产数据从 parquet 文件，返回统一的 PanelData 格式。

    Args:
        instruments: 资产列表（自动添加 -SWAP 后缀）
        start_date: 起始日期
        max_workers: 并行 workers 数
        columns: 要加载的列（默认自动检测）
        data_dir: parquet 文件目录
        orderbook_dir: orderbook 数据目录（可选，传入则加载 orderbook）
        ob_levels: orderbook 档位数（默认 5）
        use_cache: 是否使用 orderbook 缓存（默认 True，首次加载后缓存，后续直接读取）
        cache_dir: orderbook 缓存目录（默认 /home/ch/data/feature_research/orderbook_cache）

    Returns:
        PanelData 对象，每个属性都是 DataFrame (rows=time, cols=assets)

    Example:
        # 自动添加 -SWAP 后缀
        panel = load_panel_data_parquet(['BTC-USDT', 'ETH-USDT'])

        # 加载 K线 + Orderbook（启用缓存）
        panel = load_panel_data_parquet(
            ['BTC-USDT', 'ETH-USDT'],
            orderbook_dir='/home/ch/data/orderbook',
            ob_levels=5,
            use_cache=True  # 默认启用
        )

        # 禁用缓存，每次从原始文件加载
        panel = load_panel_data_parquet(
            ['BTC-USDT', 'ETH-USDT'],
            orderbook_dir='/home/ch/data/orderbook',
            use_cache=False
        )

        # 现货数据（不加 -SWAP）
        panel = load_panel_data_parquet(
            ['BTC-USDT', 'ETH-USDT'],
            data_dir='/home/ch/data/labels/OKX_1m_candles_spot_data_agg'
        )
    """
    # 根据 data_dir 自动判断是否添加 -SWAP 后缀
    suffix = _get_suffix_for_data_dir(data_dir)
    instruments = normalize_instruments(instruments, suffix)

    print(f"Loading {len(instruments)} instruments from parquet ({data_dir})...")

    # 加载为 data_dict
    data_dict = load_multi_instruments_parquet(
        instruments=instruments,
        start_date=start_date,
        max_workers=max_workers,
        data_dir=data_dir,
    )

    if not data_dict:
        raise ValueError("No data loaded for any instrument")

    # 转换为 PanelData
    panel = _build_panel_from_data_dict(data_dict, columns)

    print(f"Loaded PanelData: {panel.shape[0]:,} timestamps x {len(panel.assets)} assets")
    print(f"Assets: {panel.assets}")

    # 加载 Orderbook（如果指定且不是现货数据）
    if orderbook_dir is not None:
        # 现货数据不支持 orderbook
        if 'spot' in data_dir.lower():
            print("Warning: Orderbook not available for spot data, skipping...")
        else:
            from factorlib.utils.orderbook_loader import add_orderbook_to_panel, DEFAULT_CACHE_DIR
            panel = add_orderbook_to_panel(
                panel,
                orderbook_dir=orderbook_dir,
                ob_levels=ob_levels,
                cache_dir=cache_dir or DEFAULT_CACHE_DIR,
                use_cache=use_cache,
            )

    return panel


# ============================================================================
# Panel Data Backtest (因子值直接做仓位，和原来一样)
# ============================================================================

def _compute_ic_by_year_label(
    factor_panel: pd.DataFrame,
    panel: 'PanelData',
    labels: List[str] = None,
) -> pd.DataFrame:
    """
    计算因子与各个label在每年的IC（相关系数）。

    Args:
        factor_panel: 因子 Panel DataFrame (rows=timestamps, cols=assets)
        panel: PanelData 对象（包含 label 列）
        labels: 要计算的 label 列表（默认自动检测 ret#l#* 列）

    Returns:
        DataFrame: index=年份, columns=labels, values=IC (5个品种平均)
    """
    # 自动检测 ret 相关的 label 列
    if labels is None:
        labels = [col for col in panel.columns if col.startswith('ret#l#')]

    if not labels:
        return None

    # 按时间周期排序 labels
    def sort_key(label):
        # ret#l#1m -> (1, 'm'), ret#l#1h -> (1, 'h'), ret#l#1d -> (1, 'd')
        suffix = label.split('#')[-1]  # e.g., '1m', '15m', '1h', '1d'
        unit = suffix[-1]  # m, h, d
        val = int(suffix[:-1])
        unit_order = {'m': 0, 'h': 1, 'd': 2}
        return (unit_order.get(unit, 3), val)

    labels = sorted(labels, key=sort_key)

    assets = list(factor_panel.columns)

    # 提取年份
    factor_panel_with_year = factor_panel.copy()
    factor_panel_with_year['year'] = factor_panel_with_year.index.year
    years = sorted(factor_panel_with_year['year'].unique())

    # 计算每年、每个label的IC
    ic_results = []

    for year in years:
        year_mask = factor_panel_with_year['year'] == year
        row = {'Year': year}

        for label in labels:
            label_panel = panel[label]
            ics_per_asset = []

            for asset in assets:
                if asset not in label_panel.columns:
                    continue

                # 获取该资产该年的因子值和label值
                factor_vals = factor_panel.loc[year_mask, asset]
                label_vals = label_panel.loc[year_mask, asset] if asset in label_panel.columns else None

                if label_vals is None:
                    continue

                # 对齐索引
                common_idx = factor_vals.dropna().index.intersection(label_vals.dropna().index)
                if len(common_idx) < 100:
                    continue

                f = factor_vals.loc[common_idx]
                l = label_vals.loc[common_idx]

                # 计算相关系数
                if f.std() > 0 and l.std() > 0:
                    ic = f.corr(l)
                    if not np.isnan(ic):
                        ics_per_asset.append(ic)

            # 5个品种的平均IC
            if ics_per_asset:
                row[label] = round(np.mean(ics_per_asset), 3)
            else:
                row[label] = np.nan

        ic_results.append(row)

    # 添加总计行（所有年份平均）
    total_row = {'Year': 'Total'}
    for label in labels:
        values = [r.get(label) for r in ic_results if r.get(label) is not None and not np.isnan(r.get(label, np.nan))]
        if values:
            total_row[label] = round(np.mean(values), 3)
        else:
            total_row[label] = np.nan
    ic_results.append(total_row)

    ic_df = pd.DataFrame(ic_results)
    ic_df = ic_df.set_index('Year')

    return ic_df


def backtest_panel(
    factor_panel: pd.DataFrame,
    panel: 'PanelData' = None,
    returns_panel: pd.DataFrame = None,
    factor_name: str = 'factor',
    compound: bool = True,
    plot: Union[bool, List[str]] = False,
    display: List[str] = None,
    show_ic_table: bool = True,
    mode: str = 'full',
    test_start: str = '2025-01-01',
) -> Dict:
    """
    Panel Data 回测 - 因子值直接做仓位（和原来逻辑一样）。

    对每个资产分别回测，计算平均绩效。

    Args:
        factor_panel: 因子 Panel DataFrame (rows=timestamps, cols=assets)
        panel: PanelData 对象（用于获取 returns）
        returns_panel: 收益率 Panel DataFrame（可选）
        factor_name: 因子名称
        compound: 是否使用复利计算
        plot: 绘图选项 - True/False 或 ['average', 'BTC-USDT-SWAP']
        display: 显示哪些结果 - ['all'], ['average'], 或具体资产
        show_ic_table: 是否显示 IC 表格（年份×label，默认 True）
        mode: 回测模式
            - 'full': 使用全部数据（默认）
            - 'train': 只使用 test_start 之前的数据（训练集）
            - 'test': 只使用 test_start 之后的数据（测试集）
        test_start: 测试集开始日期（默认 '2025-01-01'）

    Returns:
        Dict with individual results, average, and ic_table

    Example:
        panel = load_panel_data(['BTC-USDT-SWAP', 'ETH-USDT-SWAP'])

        def my_factor(p, ops):
            ret = p['return']
            return ops.ts_zscore(ret, 60)

        factor_panel = compute_factor_panel(panel, my_factor, 'zscore')

        # 全量回测
        result = backtest_panel(factor_panel, panel, factor_name='zscore', plot=True)

        # 只在测试集上回测（2025年之后）
        result = backtest_panel(factor_panel, panel, factor_name='zscore', mode='test')

        # 只在训练集上回测（2025年之前）
        result = backtest_panel(factor_panel, panel, factor_name='zscore', mode='train')
    """
    if display is None:
        display = ['average']

    # 获取 returns_panel
    if returns_panel is None:
        if panel is None:
            raise ValueError("Must provide either returns_panel or panel")
        returns_panel = panel['return']

    # 保存原始 factor_panel 用于 IC 计算（IC 表格始终使用完整数据）
    factor_panel_full = factor_panel

    # 根据 mode 过滤时间范围（只影响回测绩效和画图）
    test_start_dt = pd.to_datetime(test_start, utc=True)
    if mode == 'train':
        # 训练集：test_start 之前的数据
        factor_panel = factor_panel[factor_panel.index < test_start_dt]
        returns_panel = returns_panel[returns_panel.index < test_start_dt]
        mode_label = f"TRAIN (< {test_start})"
    elif mode == 'test':
        # 测试集：test_start 之后的数据
        factor_panel = factor_panel[factor_panel.index >= test_start_dt]
        returns_panel = returns_panel[returns_panel.index >= test_start_dt]
        mode_label = f"TEST (>= {test_start})"
    else:
        mode_label = "FULL"

    if len(factor_panel) == 0:
        raise ValueError(f"No data available for mode='{mode}' with test_start='{test_start}'")

    # 获取资产列表
    assets = list(factor_panel.columns)

    # 对每个资产分别回测
    results = {'individual': {}, 'average': None, 'plot_paths': {}, 'mode': mode, 'mode_label': mode_label}
    all_perf_rows = []
    all_bt_dfs = []

    for asset in assets:
        # 构建单资产 DataFrame
        df = pd.DataFrame({
            factor_name: factor_panel[asset],
            'return': returns_panel[asset] if asset in returns_panel.columns else 0,
        })
        df = df.dropna()

        if len(df) < 100:
            print(f"  Warning: {asset} has insufficient data, skipping")
            continue

        # 运行回测
        bt_df = run_backtest(df, factor_name, compound=compound)
        perf = performance_by_year(bt_df, factor_name, compound=compound)

        results['individual'][asset] = {'df': bt_df, 'perf': perf}
        all_bt_dfs.append((asset, bt_df))

        # 提取 Total 行
        total_row = perf[perf.iloc[:, 0] == 'Total'].iloc[0].to_dict()
        total_row['Asset'] = asset
        all_perf_rows.append(total_row)

    # 计算组合回测（平均仓位）
    if len(all_bt_dfs) > 1:
        # 计算平均因子值（仓位）和平均收益率
        avg_factor = factor_panel.mean(axis=1)
        avg_return = returns_panel.mean(axis=1)

        # 构建组合 DataFrame
        portfolio_df = pd.DataFrame({
            factor_name: avg_factor,
            'return': avg_return,
        }).dropna()

        # 运行组合回测
        portfolio_bt_df = run_backtest(portfolio_df, factor_name, compound=compound)
        portfolio_perf = performance_by_year(portfolio_bt_df, factor_name, compound=compound)

        results['portfolio'] = {'df': portfolio_bt_df, 'perf': portfolio_perf}
        all_bt_dfs.append(('portfolio', portfolio_bt_df))

    # 显示结果
    show_all = 'all' in display
    show_avg = 'average' in display

    print(f"\n{'='*70}")
    print(f" Panel Backtest - {factor_name} ({len(assets)} assets) [{mode_label}]")
    print(f"{'='*70}")

    if show_avg and results.get('portfolio'):
        print(f"\n[PORTFOLIO] Equal-weighted average position across {len(assets)} assets:")
        print(results['portfolio']['perf'].to_string(index=False))

    if show_all:
        for asset, res in results['individual'].items():
            print(f"\n[{asset}]")
            print(res['perf'].to_string(index=False))

    for item in display:
        if item in results['individual'] and item not in ('all', 'average'):
            print(f"\n[{item}]")
            print(results['individual'][item]['perf'].to_string(index=False))

    # 绘图 - 跟随 display 参数
    if plot:
        if isinstance(plot, bool):
            # plot=True 时使用 display 列表来决定画哪些图
            plot_list = display if plot else []
        else:
            plot_list = plot

        for plot_item in plot_list:
            if plot_item == 'all':
                # 绘制所有资产
                for asset in results['individual']:
                    title = f"{factor_name} - {asset}"
                    path = plot_cum_return(
                        results['individual'][asset]['df'],
                        factor_name, downsample=10, title=title, save=True
                    )
                    results['plot_paths'][asset] = path
            elif plot_item == 'average' and results.get('portfolio'):
                # 绘制组合（平均仓位）的累计收益曲线
                title = f"{factor_name} - PORTFOLIO ({len(assets)} assets)"
                path = plot_cum_return(
                    results['portfolio']['df'],
                    factor_name, downsample=10, title=title, save=True
                )
                results['plot_paths']['average'] = path
            elif plot_item in results['individual']:
                title = f"{factor_name} - {plot_item}"
                path = plot_cum_return(
                    results['individual'][plot_item]['df'],
                    factor_name, downsample=10, title=title, save=True
                )
                results['plot_paths'][plot_item] = path

    # 计算并显示 IC 表格（年份 × label）- 始终使用完整数据
    if show_ic_table and panel is not None:
        ic_table = _compute_ic_by_year_label(factor_panel_full, panel)
        if ic_table is not None and not ic_table.empty:
            results['ic_table'] = ic_table

            print(f"\n{'='*70}")
            print(f" IC Table (Year × Label) - {factor_name}")
            print(f" Values are average IC across {len(assets)} assets")
            print(f"{'='*70}")

            # 格式化列名：ret#l#1m -> 1m
            display_df = ic_table.copy()
            display_df.columns = [col.replace('ret#l#', '') for col in display_df.columns]

            # 打印表格
            print(display_df.to_string())

    return results


# ============================================================================
# Unified Backtest Function (supports data_dict)
# ============================================================================

def backtest(
    df: pd.DataFrame = None,
    factor_col: str = None,
    instruments: Union[str, List[str]] = None,
    data_dict: Dict[str, pd.DataFrame] = None,
    start_date: str = '2021-01-01 00:00:00',
    compound: bool = True,
    plot: Union[bool, List[str]] = False,
    display: List[str] = None,
    group_by: str = 'auto',
    max_workers: int = None,
    title_suffix: str = '',
    **kwargs
) -> Dict:
    """
    Unified backtest function for single or multiple instruments.

    Args:
        df: Input DataFrame (for single instrument backtest)
        factor_col: Factor/signal column name
        instruments: Instrument(s) to load from ClickHouse (ignored if df/data_dict provided)
        data_dict: Pre-loaded data dict for multi-instrument backtest
        start_date: Start date for data loading
        compound: Use compound returns (default True)
        plot: Plot options:
            - False: no plot
            - True: plot all instruments
            - List[str]: plot specific instruments, e.g., ['BTC-USDT-SWAP', 'average']
        display: What to display - ['all'], ['average'], or specific instruments
        group_by: Performance grouping - 'year', 'month', 'auto'
        max_workers: Number of parallel workers for data loading

    Returns:
        Dict with:
        - Single instrument: {'df': bt_df, 'perf': perf_df, 'plot_path': str|None}
        - Multi instrument: {'individual': {...}, 'average': {...}, 'plot_paths': {...}}

    Examples:
        # Single instrument with DataFrame
        result = backtest(df=my_df, factor_col='ret_skew', plot=True)

        # Multi-instrument - plot specific instruments
        result = backtest(
            factor_col='ret_skew',
            data_dict=data_dict,
            display=['average', 'BTC-USDT-SWAP'],
            plot=['average', 'BTC-USDT-SWAP']  # Only plot these
        )

        # Multi-instrument - plot all
        result = backtest(factor_col='ret_skew', data_dict=data_dict, plot=True)
    """
    if factor_col is None:
        raise ValueError("factor_col is required")

    if display is None:
        display = ['all']

    if max_workers is None:
        max_workers = get_max_workers()

    # Determine mode: single or multi-instrument
    is_single = df is not None

    if is_single:
        # ===== Single Instrument Backtest =====
        return _backtest_single(df, factor_col, compound, plot, group_by, title_suffix=title_suffix)

    # ===== Multi-Instrument Backtest =====
    # Get data_dict
    if data_dict is None:
        if instruments is None:
            raise ValueError("Must provide df, data_dict, or instruments")
        if isinstance(instruments, str):
            instruments = [instruments]
        print(f"Loading {len(instruments)} instruments...")
        data_dict = load_multi_instruments(instruments, start_date, max_workers, **kwargs)
    else:
        print(f"Using pre-loaded data for {len(data_dict)} instruments...")

    if not data_dict:
        raise ValueError("No data loaded for any instrument")

    return _backtest_multi(data_dict, factor_col, compound, plot, display, group_by, title_suffix=title_suffix)


def _backtest_single(
    df: pd.DataFrame,
    factor_col: str,
    compound: bool,
    plot: Union[bool, List[str]],
    group_by: str,
    instrument: str = None,
    title_suffix: str = ''
) -> Dict:
    """Internal: single instrument backtest."""
    bt_df = run_backtest(df, factor_col, compound=compound)
    perf_df = performance_by_year(bt_df, factor_col, compound=compound) if group_by == 'year' else \
              performance_by_year(bt_df, factor_col, compound=compound)  # TODO: use performance_by_period

    # Get instrument name from df if available
    if instrument is None and 'instrument' in df.columns:
        instrument = df['instrument'].iloc[0] if len(df) > 0 else None

    # Print results
    mode_text = "Compound" if compound else "Simple Interest"
    inst_text = f" - {instrument}" if instrument else ""
    header = f"Backtest Results - {factor_col}{inst_text} ({mode_text})"
    table_str = perf_df.to_string(index=False)
    width = max((len(line) for line in table_str.splitlines()), default=len(header) + 2)
    print(_make_header(header, width))
    print(table_str)

    # Plot if requested
    plot_path = None
    if plot:
        title = f"{factor_col} - {instrument}{title_suffix}" if instrument else f"{factor_col}{title_suffix}"
        plot_path = plot_cum_return(bt_df, factor_col, downsample=10, title=title, save=True)

    return {'df': bt_df, 'perf': perf_df, 'plot_path': plot_path}


def _backtest_multi(
    data_dict: Dict[str, pd.DataFrame],
    factor_col: str,
    compound: bool,
    plot: Union[bool, List[str]],
    display: List[str],
    group_by: str,
    title_suffix: str = ''
) -> Dict:
    """Internal: multi-instrument backtest."""
    results = {'individual': {}, 'average': None, 'plot_paths': {}}
    all_perf_rows = []
    all_bt_dfs = []  # For average plot

    for inst, df in data_dict.items():
        if factor_col not in df.columns:
            print(f"  Warning: {factor_col} not in {inst}, skipping")
            continue

        bt_df = run_backtest(df, factor_col, compound=compound)
        perf = performance_by_year(bt_df, factor_col, compound=compound)

        results['individual'][inst] = {'df': bt_df, 'perf': perf}
        all_bt_dfs.append((inst, bt_df))

        # Extract total row for averaging
        total_row = perf[perf.iloc[:, 0] == 'Total'].iloc[0].to_dict()
        total_row['Instrument'] = inst
        all_perf_rows.append(total_row)

    # Calculate average performance
    if len(all_perf_rows) > 1:
        avg_perf = {}
        numeric_cols = ['Return', 'Sharpe', 'Turnover', 'Max Drawdown', 'Kamma Ratio', 'Ret/Turnover']
        for col in numeric_cols:
            values = [r.get(col, 0) for r in all_perf_rows if r.get(col) is not None]
            if values:
                avg_perf[col] = round(np.mean(values), 2)
        avg_perf['Instrument'] = 'AVERAGE'
        avg_perf['N'] = len(all_perf_rows)
        results['average'] = avg_perf

    # Display results
    show_all = 'all' in display
    show_avg = 'average' in display or 'avg' in display

    print("\n" + "=" * 70)
    print(f" Multi-Instrument Backtest - {factor_col}{title_suffix} ")
    print("=" * 70)

    if show_all or show_avg:
        if results['average']:
            print(f"\n[AVERAGE] across {results['average']['N']} instruments:")
            print(f"  Return: {results['average'].get('Return', 'N/A')}%")
            print(f"  Sharpe: {results['average'].get('Sharpe', 'N/A')}")
            print(f"  Max Drawdown: {results['average'].get('Max Drawdown', 'N/A')}")
            print(f"  Kamma Ratio: {results['average'].get('Kamma Ratio', 'N/A')}")

    for inst in display:
        if inst in ('all', 'average', 'avg'):
            if show_all:
                for inst_name, inst_result in results['individual'].items():
                    print(f"\n[{inst_name}]")
                    print(inst_result['perf'].to_string(index=False))
            continue
        if inst in results['individual']:
            print(f"\n[{inst}]")
            print(results['individual'][inst]['perf'].to_string(index=False))

    # Determine which instruments to plot
    if plot:
        if isinstance(plot, bool):
            # plot=True means plot all instruments
            plot_list = list(results['individual'].keys())
        else:
            # plot is a list of instruments to plot
            plot_list = plot

        cum_ret_col = f'{factor_col}_cum_ret'

        for plot_inst in plot_list:
            if plot_inst in ('average', 'avg'):
                # Plot average cumulative return
                if len(all_bt_dfs) > 1:
                    # Calculate average cumulative return
                    avg_cum_ret = None
                    for inst, bt_df in all_bt_dfs:
                        if cum_ret_col in bt_df.columns:
                            if avg_cum_ret is None:
                                avg_cum_ret = bt_df[cum_ret_col].copy()
                            else:
                                # Align and average
                                avg_cum_ret = avg_cum_ret.add(bt_df[cum_ret_col], fill_value=0)
                    if avg_cum_ret is not None:
                        avg_cum_ret = avg_cum_ret / len(all_bt_dfs)
                        # Create a temporary df for plotting
                        avg_df = pd.DataFrame({cum_ret_col: avg_cum_ret})
                        title = f"{factor_col} - AVERAGE ({len(all_bt_dfs)} instruments){title_suffix}"
                        path = plot_cum_return(avg_df, factor_col, downsample=10, title=title, save=True)
                        results['plot_paths']['average'] = path
            elif plot_inst in results['individual']:
                # Plot specific instrument
                title = f"{factor_col} - {plot_inst}{title_suffix}"
                path = plot_cum_return(
                    results['individual'][plot_inst]['df'],
                    factor_col,
                    downsample=10,
                    title=title,
                    save=True
                )
                results['plot_paths'][plot_inst] = path

    return results


# Keep old name as alias for backward compatibility
backtest_multi_instruments = backtest


def _make_header(title: str, target_width: int, fill_char: str = '=') -> str:
    """Generate header with target width"""
    inner = f" {title} "
    if target_width <= 0 or len(inner) >= target_width:
        return inner
    pad = target_width - len(inner)
    return f"{fill_char * (pad // 2)}{inner}{fill_char * (pad - pad // 2)}"


# ============================================================================
# CLI Commands
# ============================================================================

def backtest_cmd(args):
    # Parse instruments (comma-separated)
    instruments = [s.strip() for s in args.instruments.split(',')]

    # Parse display options
    display = [s.strip() for s in args.display.split(',')] if args.display else ['all']

    if len(instruments) == 1:
        # Single instrument - use simple backtest
        df = load_kline_from_clickhouse(
            instrument_name=instruments[0],
            start_date=args.start_date
        )

        # Need to compute factor first
        from factorlib.factors.library import library
        df = library.compute(args.factor, df)

        df_bt = run_backtest(df, args.factor)
        perf = performance_by_year(df_bt, args.factor)
        header = f"Cumulative Return - {args.factor} ({instruments[0]})"
        table_str = perf.to_string()
        width = max((len(line) for line in table_str.splitlines()), default=len(header) + 2)
        print(_make_header(header, width))
        print(table_str)
        if args.plot:
            plot_cum_return(df_bt, args.factor)
    else:
        # Multi-instrument backtest
        from factorlib.factors.library import library

        # Load and compute factors for all instruments
        data_dict = load_multi_instruments(instruments, args.start_date)
        for inst, df in data_dict.items():
            data_dict[inst] = library.compute(args.factor, df)

        results = {'individual': {}, 'average': None}
        all_returns = []

        for inst, df in data_dict.items():
            df_bt = run_backtest(df, args.factor)
            perf = performance_by_year(df_bt, args.factor)
            results['individual'][inst] = {'df': df_bt, 'perf': perf}

            total_row = perf[perf.iloc[:, 0] == 'Total'].iloc[0]
            all_returns.append(total_row['Return'])

        # Show results
        show_all = 'all' in display

        print("\n" + "=" * 70)
        print(f" Multi-Instrument Backtest - {args.factor} ")
        print("=" * 70)

        if show_all or 'average' in display:
            if len(all_returns) > 1:
                print(f"\n[AVERAGE] across {len(all_returns)} instruments:")
                print(f"  Return: {np.mean(all_returns):.2f}%")

        for inst in display:
            if inst in ('all', 'average'):
                if show_all:
                    for inst_name, res in results['individual'].items():
                        print(f"\n[{inst_name}]")
                        print(res['perf'].to_string(index=False))
                continue
            if inst in results['individual']:
                print(f"\n[{inst}]")
                print(results['individual'][inst]['perf'].to_string(index=False))


def tick_compute_cmd(args):
    proc = TickFactorProcessor(data_dir=args.data_dir, output_dir=args.output_dir or '/home/ch/data/result')
    report = proc.run_factor_calculation(show_progress=True)
    if not report.get('save_success'):
        raise SystemExit('Tick factor calculation failed')
    out_file = report['output_file']
    df = pd.read_parquet(out_file)
    if 'datetime' in df.columns:
        df['CloseTime'] = pd.to_datetime(df['datetime'], unit='ms', utc=True)
        df = df.drop(columns=['datetime'])
    out = args.output or out_file
    df.to_parquet(out)
    print(f'Saved tick-minute factors: {out}')


def tick_backtest_cmd(args):
    instruments = [s.strip() for s in args.instruments.split(',')]

    if len(instruments) == 1:
        df_k = load_kline_from_clickhouse(
            instrument_name=instruments[0],
            start_date=args.start_date
        )
    else:
        data_dict = load_multi_instruments(instruments, args.start_date)
        df_k = pd.concat(data_dict.values(), keys=data_dict.keys())

    df_f = pd.read_parquet(args.tick_factors)
    if 'CloseTime' in df_f.columns:
        if not pd.api.types.is_datetime64_any_dtype(df_f['CloseTime']):
            df_f['CloseTime'] = pd.to_datetime(df_f['CloseTime'], utc=True, errors='coerce')
    elif 'datetime' in df_f.columns:
        df_f['CloseTime'] = pd.to_datetime(df_f['datetime'], unit='ms', utc=True, errors='coerce')
        df_f = df_f.drop(columns=['datetime'])
    else:
        raise SystemExit('tick_factors missing time column CloseTime/datetime')

    factor_col = args.factor_col
    if factor_col not in df_f.columns:
        raise SystemExit(f'Factor column not found: {factor_col}')
    df_f = df_f.set_index('CloseTime')
    df = df_k.join(df_f[[factor_col]], how='left')
    df[factor_col] = df[factor_col].ffill().fillna(0)
    df_bt = run_backtest(df, factor_col)
    perf = performance_by_year(df_bt, factor_col)
    print(perf)
    if args.plot:
        plot_cum_return(df_bt, factor_col)


def main():
    parser = argparse.ArgumentParser(description='FactorLib CLI')
    sub = parser.add_subparsers()

    # backtest subcommand
    p2 = sub.add_parser('backtest', help='Backtest factor')
    p2.add_argument('--instruments', '-i', default='BTC-USDT-SWAP',
                    help='Instrument(s), comma-separated. e.g., BTC-USDT-SWAP,ETH-USDT-SWAP')
    p2.add_argument('--start-date', default='2021-01-01 00:00:00', help='Start date')
    p2.add_argument('--factor', required=True, help='Factor name')
    p2.add_argument('--display', '-d', default='all',
                    help='Display mode: all, average, or specific instruments (comma-separated)')
    p2.add_argument('--plot', action='store_true')
    p2.set_defaults(func=backtest_cmd)

    # tick-compute subcommand
    p4 = sub.add_parser('tick-compute', help='Calculate tick factors')
    p4.add_argument('--data-dir', required=True, help='Tick data directory')
    p4.add_argument('--output-dir', help='Output directory')
    p4.add_argument('--output', help='Output file path')
    p4.set_defaults(func=tick_compute_cmd)

    # tick-backtest subcommand
    p5 = sub.add_parser('tick-backtest', help='Backtest tick factors')
    p5.add_argument('--instruments', '-i', default='BTC-USDT-SWAP',
                    help='Instrument(s), comma-separated')
    p5.add_argument('--start-date', default='2021-01-01 00:00:00', help='Start date')
    p5.add_argument('--tick-factors', required=True, help='Tick factor parquet file')
    p5.add_argument('--factor-col', default='trade_vol_perc')
    p5.add_argument('--plot', action='store_true')
    p5.set_defaults(func=tick_backtest_cmd)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
