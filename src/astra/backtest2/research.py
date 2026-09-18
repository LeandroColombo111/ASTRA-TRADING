"""Like-for-like research harness: fixed-parameter variants over the same rolling
test windows, same warmup for every variant, always reported against HODL.

Methodology rules enforced here (see reports/backtest2-v2/):
- one warmup for every variant (default 250d), never per-variant;
- parameters are fixed per variant, nothing is re-optimised per window;
- every variant reports Sharpe mean/median, windows >= 1.5, total return,
  worst window, % time in market, and the same numbers for HODL.
"""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

from ..engine import Risk
from .execution import ExecutionSimulator
from .friction.funding import FundingModel
from .friction.slippage import SlippageModel, NullLiquidityBook
from .friction.fees import FeeModel
from .friction.liquidation import LiquidationModel, PositionTiers

TRAIN = pd.Timedelta(days=365)
TEST = pd.Timedelta(days=90)
STEP = pd.Timedelta(days=90)
WARMUP = pd.Timedelta(days=250)
HOUR = pd.Timedelta(hours=1)
DATA = Path(__file__).resolve().parents[3] / 'data'


def load_bars(symbol='BTC'):
    bars = pd.read_csv(DATA / f'{symbol}-USDT-SWAP-okx-1h.csv', index_col='time', parse_dates=True)
    bars.index = pd.to_datetime(bars.index, utc=True)
    return bars


def build_sim(risk, impact_k=1.0):
    return ExecutionSimulator(
        funding_model=FundingModel(),
        slippage_model=SlippageModel(NullLiquidityBook(), impact_k=impact_k),
        fee_model=FeeModel.regular_tier(),
        liquidation_model=LiquidationModel(PositionTiers(), 'isolated'),
        leverage=risk.max_exposure)


def test_windows(index, first=TRAIN, test=TEST, step=STEP):
    out, start = [], index[0]
    while start + first + test <= index[-1]:
        out.append((start + first, start + first + test))
        start += step
    return out


def sharpe_from_equity(equity, capital):
    e = equity.copy()
    e.index = e.index - pd.Timedelta(nanoseconds=1)
    daily = e.resample('1D').last().dropna()
    r = daily.pct_change().fillna(daily.iloc[0] / capital - 1)
    sd = float(r.std(ddof=1))
    return float(np.sqrt(365) * r.mean() / sd) if sd > 0 else 0.


def max_dd(equity, capital):
    w = np.r_[capital, equity.to_numpy()]
    return float((1 - w / np.maximum.accumulate(w)).max())


def time_in_market(trades, start, end):
    total = (end - start) / HOUR
    held = 0.
    for t in trades:
        a, b = pd.Timestamp(t['entry_time']), pd.Timestamp(t['exit_time'])
        held += (min(b, end) - max(a, start)) / HOUR
    return max(0., held) / total, held


def hodl_window(bars, start, end, capital):
    seg = bars.loc[start:end - HOUR]
    px = seg.close
    eq = capital * px / px.iloc[0]
    eq.index = eq.index + HOUR
    return eq


@dataclass
class Variant:
    name: str
    run: callable  # (bars_with_warmup, start, end) -> (equity, trades)


def engine_variant(name, params, signal_fn, sim, risk):
    """A variant that uses the standard ExecutionSimulator (risk-sized entries)."""
    def run(bars, start, end):
        sig = signal_fn(bars, params)
        eq, trades, _ = sim.run(bars, sig, params, risk, start=start, end=end)
        return eq, trades
    return Variant(name, run)


def evaluate(variant, bars, risk, warmup=WARMUP, windows=None, first=TRAIN, test=TEST, step=STEP, keep=None):
    """One row per test window; compounding across windows is reported separately.
    keep: optional dict that receives {(start): (equity, hodl_equity, trades)} for portfolio maths."""
    windows = windows or test_windows(bars.index, first, test, step)
    rows = []
    for start, end in windows:
        seg = bars.loc[start - warmup:end]
        eq, trades = variant.run(seg, start, end)
        if keep is not None:
            keep[start] = (eq, hodl_window(bars, start, end, risk.capital), trades)
        h = hodl_window(bars, start, end, risk.capital)
        tim, _ = time_in_market(trades, start, end)
        rows.append({
            'start': start, 'end': end,
            'sharpe': sharpe_from_equity(eq, risk.capital),
            'ret': float(eq.iloc[-1] / risk.capital - 1),
            'maxdd': max_dd(eq, risk.capital),
            'time_in_market': tim,
            'trades': len(trades),
            'hodl_sharpe': sharpe_from_equity(h, risk.capital),
            'hodl_ret': float(h.iloc[-1] / risk.capital - 1),
            'hodl_maxdd': max_dd(h, risk.capital),
        })
    return pd.DataFrame(rows)


def summarize(df):
    """Compounded total across the windows (each window starts from fresh capital)."""
    def comp(x): return float(np.prod(1 + x) - 1)
    up = df.hodl_ret > 0
    return {
        'sharpe_mean': float(df.sharpe.mean()), 'sharpe_median': float(df.sharpe.median()),
        'ge_1_5': int((df.sharpe >= 1.5).sum()), 'negative': int((df.sharpe < 0).sum()), 'n': len(df),
        'total_ret': comp(df.ret), 'sum_ret': float(df.ret.sum()),
        'worst_window': float(df.ret.min()), 'worst_maxdd': float(df.maxdd.max()),
        'time_in_market': float(df.time_in_market.mean()),
        'ret_up_windows': float(df.ret[up].mean()) if up.any() else float('nan'),
        'ret_down_windows': float(df.ret[~up].mean()) if (~up).any() else float('nan'),
        'hodl_sharpe_mean': float(df.hodl_sharpe.mean()), 'hodl_sharpe_median': float(df.hodl_sharpe.median()),
        'hodl_ge_1_5': int((df.hodl_sharpe >= 1.5).sum()),
        'hodl_total_ret': comp(df.hodl_ret), 'hodl_sum_ret': float(df.hodl_ret.sum()),
        'hodl_worst_window': float(df.hodl_ret.min()), 'hodl_worst_maxdd': float(df.hodl_maxdd.max()),
        'hodl_ret_up_windows': float(df.hodl_ret[up].mean()) if up.any() else float('nan'),
        'hodl_ret_down_windows': float(df.hodl_ret[~up].mean()) if (~up).any() else float('nan'),
    }


def chained_maxdd(df):
    """Max drawdown of the equity obtained by chaining the windows end to end (window returns compounded)."""
    w = np.cumprod(1 + df.ret.to_numpy())
    w = np.r_[1., w]
    return float((1 - w / np.maximum.accumulate(w)).max())


def chain(equities, capital):
    """Join per-window equity curves end to end (each window's return compounds on the previous one)."""
    out, level = [], 1.
    for e in equities:
        seg = level * e / capital
        out.append(seg)
        level = float(seg.iloc[-1])
    return pd.concat(out)


def chain_stats(equities, capital):
    c = chain(equities, capital) * capital
    return {'chain_sharpe': sharpe_from_equity(c, capital), 'chain_ret': float(c.iloc[-1] / capital - 1),
            'chain_maxdd': max_dd(c, capital)}


def mix_equities(kept, w_hodl):
    return [w_hodl * h.reindex(eq.index).ffill() + (1 - w_hodl) * eq for eq, h, _ in kept.values()]


def mix(kept, w_hodl, capital):
    """Sleeve portfolio per window: w_hodl in buy-and-hold, the rest in the bot (own capital), no rebalance inside a window.
    Returns a DataFrame shaped like evaluate() so summarize() applies unchanged."""
    rows = []
    for start, (eq, h, trades) in kept.items():
        e = w_hodl * h.reindex(eq.index).ffill() + (1 - w_hodl) * eq
        rows.append({'start': start, 'end': eq.index[-1],
                     'sharpe': sharpe_from_equity(e, capital), 'ret': float(e.iloc[-1] / capital - 1),
                     'maxdd': max_dd(e, capital), 'time_in_market': float('nan'), 'trades': len(trades),
                     'hodl_sharpe': sharpe_from_equity(h, capital), 'hodl_ret': float(h.iloc[-1] / capital - 1),
                     'hodl_maxdd': max_dd(h, capital)})
    return pd.DataFrame(rows)
