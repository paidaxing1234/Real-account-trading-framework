# -*- coding: utf-8 -*-
# @Desc: Strategy-only module. Expose: st.cal_target_position(df, n_layers) -> dict[Ticker->weight]
#        n means "number of layers (buckets)".
#        Match backtest: TOP_PCT = 1/n_layers, long top 1 bucket, short bottom 1 bucket.
# Warning: Using UTC time for all datetime processing.
#          Ensure your df['Time'] is in UTC timezone or naive datetime in UTC.
#          Volume column means "Volume in quote currency" (e.g. volCcy in OKX).
#          Ensure your df has sufficient history (at least 150 time points per asset).
#          Only trade assets in currency_pool.
#          Only change Position at UTC hour 00:00 EVERY 14 DAYS to match backtest.

import os
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

# 获取当前文件目录用于构建绝对路径
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENCY_POOL_FILE = os.path.join(_SCRIPT_DIR, "currency_pool_binance.txt")

# ======================
# 0) Hard config (match your backtest)
# ======================
SEQ_LEN = 120
PRED_HORIZONS = [4, 8, 12, 24, 48]
N_TASKS = len(PRED_HORIZONS)

FEATURES = ['feat_ret', 'feat_high_rel', 'feat_low_rel', 'feat_open_rel', 'feat_vol_chg']
N_FEATURES = len(FEATURES)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Liquidity control (match your backtest)
TURN_WIN = 24
TURN_MINP = 12
MIN_NODES = 5

# Model loading config (you can change these two lines only)
MODEL_DIR = "./model"
SEEDS = [2725, 3407, 42]
TOP_K_GRAPH = 10


# ======================
# 1) Model definition (same as training/backtest)
# ======================
class DynamicGraphGenerator(nn.Module):
    def __init__(self, top_k=10):
        super().__init__()
        self.top_k = top_k

    def forward(self, x):
        returns = x[:, :, 0]  # feat_ret
        mean = returns.mean(dim=1, keepdim=True)
        std = returns.std(dim=1, keepdim=True) + 1e-8
        norm_ret = (returns - mean) / std

        adj = torch.mm(norm_ret, norm_ret.t()) / (x.size(1) - 1)
        adj = torch.abs(adj)  # critical fix

        k = min(self.top_k, adj.size(0))
        topk_vals, topk_inds = torch.topk(adj, k=k, dim=-1)

        sparse_adj = torch.zeros_like(adj)
        sparse_adj.scatter_(-1, topk_inds, topk_vals)
        sparse_adj = sparse_adj + torch.eye(sparse_adj.size(0), device=x.device)

        row_sum = sparse_adj.sum(dim=1)
        d_inv_sqrt = torch.pow(row_sum, -0.5)
        d_inv_sqrt[torch.isinf(d_inv_sqrt)] = 0.0
        d_mat_inv_sqrt = torch.diag(d_inv_sqrt)

        norm_adj = torch.mm(torch.mm(d_mat_inv_sqrt, sparse_adj), d_mat_inv_sqrt)
        return norm_adj


class GeneralizedGraphDiffusion(nn.Module):
    def __init__(self, hidden_dim, max_diffusion_step=3):
        super().__init__()
        self.k = max_diffusion_step
        self.alpha = nn.Parameter(torch.ones(max_diffusion_step + 1))
        self.linear = nn.Linear(hidden_dim, hidden_dim)

    def forward(self, h, adj):
        out = self.alpha[0] * h
        curr_h = h
        for i in range(1, self.k + 1):
            curr_h = torch.mm(adj, curr_h)
            out = out + self.alpha[i] * curr_h
        return self.linear(out)


class HT_DiffGNN(nn.Module):
    def __init__(self, input_dim, hidden_dim=64, output_dim=1, top_k=10):
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_dim, num_layers=2, batch_first=True, dropout=0.3)
        self.graph_gen = DynamicGraphGenerator(top_k=top_k)
        self.node_embedding_fc = nn.Linear(hidden_dim, hidden_dim)
        self.ggd = GeneralizedGraphDiffusion(hidden_dim, max_diffusion_step=3)
        self.attn_norm = nn.LayerNorm(hidden_dim)
        self.attn = nn.MultiheadAttention(embed_dim=hidden_dim, num_heads=4, dropout=0.3, batch_first=True)

        self.head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.LeakyReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim // 2, output_dim)
        )

    def forward(self, x):
        gru_out, _ = self.gru(x)
        h_temp = gru_out[:, -1, :]

        adj = self.graph_gen(x)

        pe = self.node_embedding_fc(h_temp)
        h_emb = h_temp + pe

        h_diff = self.ggd(h_emb, adj)
        h_diff = F.leaky_relu(h_diff)

        # Keep identical to your backtest implementation for exact consistency
        h_in_attn = h_diff.unsqueeze(0)  # (1, N, H)
        attn_out, _ = self.attn(h_in_attn, h_in_attn, h_in_attn)
        h_out = self.attn_norm(h_in_attn + attn_out).squeeze(0)  # (N, H)

        out = self.head(h_out)  # (N, output_dim)
        return out


# ======================
# 2) Preprocess: df(window) -> latest (tickers_valid, X_nodes)
#    Strictly match your preprocessing logic:
#      - features
#      - turnover mask: (Volume*Close).rolling(24,min_periods=12).mean() >= median(axis=1)
#      - cross-sectional zscore within mask, outside -> 0
#      - node set at latest time uses latest mask
# ======================
def _standardize_input_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Support both raw and mapped column names
    if "instId" in df.columns:
        rename = {
            "instId": "Tick",
            "timestamp": "Time",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volCcy": "Volume",   # match training/backtest: uses Volume
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        if "Volume" not in df.columns:
            # fallback if volCcy absent
            if "vol" in df.columns:
                df["Volume"] = df["vol"]
            elif "Contract" in df.columns:
                df["Volume"] = df["Contract"]
    else:
        rename = {"Ticker": "Tick"}
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    required = ["Tick", "Time", "Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"df missing required columns: {missing}")

    # Parse Time
    if np.issubdtype(df["Time"].dtype, np.number):
        tmax = float(np.nanmax(df["Time"].values))
        unit = "ms" if tmax > 1e12 else "s"
        df["Time"] = pd.to_datetime(df["Time"], unit=unit, errors="coerce")
    else:
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df["Time"] = df["Time"].dt.tz_localize(None)

    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Drop rows where key columns have NaN
    df = df.dropna(subset=["Tick", "Time", "Open", "High", "Low", "Close", "Volume"])
    
    # Filter out Tickers with less than 150 data points
    ticker_counts = df.groupby('Tick').size()
    valid_tickers = ticker_counts[ticker_counts >= 150].index
    df = df[df['Tick'].isin(valid_tickers)]

    df = df.sort_values(["Tick", "Time"]).reset_index(drop=True)
    return df

def _compute_features_trainmatched(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["feat_ret"] = np.log(df.groupby("Tick")["Close"].pct_change().fillna(0) + 1.0)
    df["feat_high_rel"] = np.log(df["High"] / df["Close"])
    df["feat_low_rel"]  = np.log(df["Low"] / df["Close"])
    df["feat_open_rel"] = np.log(df["Open"] / df["Close"])
    vol_pct = df.groupby("Tick")["Volume"].pct_change().fillna(0)
    df["feat_vol_chg"] = np.log1p(vol_pct)

    for col in FEATURES:
        df[col] = df[col].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return df


def _build_latest_X_nodes(df_raw: pd.DataFrame, seq_len: int = SEQ_LEN):
    df = _standardize_input_df(df_raw)

    # 去除重复的 (Time, Tick) 组合，保留最后一条
    df = df.drop_duplicates(subset=["Time", "Tick"], keep="last")

    df = _compute_features_trainmatched(df)

    # pivots (Time x Tick)
    pivot_close = df.pivot(index="Time", columns="Tick", values="Close").sort_index()
    pivot_vol   = df.pivot(index="Time", columns="Tick", values="Volume").sort_index()
    feat_pivots = {c: df.pivot(index="Time", columns="Tick", values=c).sort_index() for c in FEATURES}

    times = pivot_close.index
    assets = pivot_close.columns

    if len(times) < seq_len:
        return [], None

    # turnover mask (match backtest)
    turnover = pivot_vol * pivot_close
    roll_turnover = turnover.rolling(window=TURN_WIN, min_periods=TURN_MINP).mean()
    med_turnover = roll_turnover.median(axis=1, skipna=True)
    mask_turnover = roll_turnover.ge(med_turnover, axis=0)  # (T,A) bool

    t_idx = len(times) - 1
    last_times = times[t_idx - seq_len + 1 : t_idx + 1]

    # X_seq: (Seq, A, F)
    A = len(assets)
    X_seq = np.zeros((seq_len, A, N_FEATURES), dtype=np.float32)
    for i, f in enumerate(FEATURES):
        X_seq[:, :, i] = feat_pivots[f].reindex(index=last_times, columns=assets).values.astype(np.float32)

    # window mask per time (match training structure)
    mask_window = mask_turnover.reindex(index=last_times, columns=assets).values  # (Seq,A)
    X_masked = np.where(mask_window[:, :, None], X_seq, np.nan)

    mean_t = np.nanmean(X_masked, axis=1, keepdims=True)
    std_t  = np.nanstd(X_masked, axis=1, keepdims=True)
    X_norm = (X_masked - mean_t) / (std_t + 1e-8)
    X_final = np.nan_to_num(X_norm, nan=0.0).astype(np.float32)  # (Seq,A,F)

    # latest universe uses latest mask only
    curr_mask = mask_turnover.iloc[t_idx].values
    valid_idx = np.where(curr_mask)[0]

    if len(valid_idx) < MIN_NODES:
        return [], None

    tickers_valid = list(assets[valid_idx])
    X_slice = X_final[:, valid_idx, :]                 # (Seq,N,F)
    X_nodes = np.transpose(X_slice, (1, 0, 2)).astype(np.float32)  # (N,Seq,F)
    return tickers_valid, X_nodes


# ======================
# 3) Strategy wrapper: st.cal_target_position(df, n_layers)
#    n_layers means bucket count (e.g. 20 layers <-> TOP_PCT=0.05)
# ======================
class GNN_Strategy:
    def __init__(self, model_dir: str, seeds, top_k_graph: int = 10):
        self.model_dir = model_dir
        self.seeds = list(seeds)
        self.top_k_graph = int(top_k_graph)
        self.models = []
        self._loaded = False

    def _load_models_once(self):
        if self._loaded:
            return

        models = []
        for seed in self.seeds:
            path = os.path.join(self.model_dir, f"diffgnn_{seed}.pth")
            if not os.path.exists(path):
                raise FileNotFoundError(path)

            m = HT_DiffGNN(
                input_dim=N_FEATURES,
                hidden_dim=64,
                output_dim=N_TASKS,
                top_k=self.top_k_graph
            ).to(DEVICE)
            m.load_state_dict(torch.load(path, map_location=DEVICE))
            m.eval()
            models.append(m)

        if not models:
            raise RuntimeError("No models loaded.")
        self.models = models
        self._loaded = True

    @torch.no_grad()
    def _predict_scores(self, X_nodes: np.ndarray) -> np.ndarray:
        x = torch.from_numpy(X_nodes).float().to(DEVICE)  # (N,Seq,F)
        pred_sum = None
        for m in self.models:
            p = m(x)  # (N,tasks)
            pred_sum = p if pred_sum is None else pred_sum + p
        pred = (pred_sum / len(self.models)).detach().cpu().numpy()  # (N,tasks)
        scores = pred.mean(axis=1)  # mean over tasks
        return scores

    @staticmethod
    def _layer_long_short_indices(scores: np.ndarray, n_layers: int):
        """
        Match backtest TOP_PCT = 1/n_layers:
          k = floor(N / n_layers) (at least 1)
          long = top k, short = bottom k
        """
        N = len(scores)
        k = max(1, N // n_layers)  # strict: 0.05 <-> 20 layers
        if N < 2 * k:
            # extreme small-N guard
            k = max(1, N // 2)

        order = np.argsort(scores)
        short_idx = order[:k]
        long_idx  = order[-k:]
        return long_idx, short_idx, k

    def cal_target_position(self, df: pd.DataFrame, n: int) -> dict:
        """
        Public API:
          st.cal_target_position(df, n_layers) -> dict[Ticker -> weight]

        Constraints:
          - n is "number of layers"
          - long top 1 layer, short bottom 1 layer (k = floor(N/n))
          - equal weight
          - sum(long)=+0.5, sum(short)=-0.5 => sum(abs)=1
        """
        n_layers = int(n)
        if n_layers <= 1:
            return {}

        self._load_models_once()

        # select the currencies
        with open(CURRENCY_POOL_FILE, "r") as f:
            pool = [line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")]
    
        df = df[df['Ticker'].isin(pool)]
        tickers, X_nodes = _build_latest_X_nodes(df, seq_len=SEQ_LEN)
        if X_nodes is None or len(tickers) < MIN_NODES:
            return {}

        scores = self._predict_scores(X_nodes)

        # Need at least 2 layers worth of names
        if len(scores) < 2:
            return {}

        long_idx, short_idx, k = self._layer_long_short_indices(scores, n_layers)

        # Ensure non-trivial long/short
        if k <= 0 or len(long_idx) == 0 or len(short_idx) == 0:
            return {}

        unit = 0.5 / float(k)  # abs sum = 1
        w = {}
        for i in long_idx:
            w[str(tickers[i])] = +unit
        for i in short_idx:
            w[str(tickers[i])] = -unit
        return w


# ======================
# 4) Export singleton
# ======================
if __name__ == "__main__":
    import time
    
    st = GNN_Strategy(model_dir=MODEL_DIR, seeds=SEEDS, top_k_graph=TOP_K_GRAPH) # singleton
    df = pd.read_parquet('./test.parquet', engine='fastparquet') # load data, df must have columns: ['Ticker','Time','Open','High','Low','Close','Volume']
                                                                               # Time can be datetime,UTC time; Volume: Vol_ccy
    start_time = time.time()
    w = st.cal_target_position(df, n = 20) # example n_layers=20
    end_time = time.time()
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print(w)# w is dict[Ticker->weight], e.g. {'BTC-USDT': 0.025, 'ETH-USDT': -0.025, ...}, sum(abs)=1.0,'+' for long, '-' for short
