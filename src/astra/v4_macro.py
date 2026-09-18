"""v4_hourly with a causal daily macro-trend gate on ENTRIES only.

Research (reports/backtest2-v1): trades whose direction disagreed with the
larger regime lost as a block. Gating new entries to fire only when the
1h/4h breakout agrees with a daily EMA(fast)/EMA(slow) trend improved
walk-forward out-of-sample Sharpe (median -0.37 -> +0.84) with the pair
fixed, not re-optimized. It still does not reach the project's 1.5 gate, so
configs using this family stay approved_for_live=false.

Only the `signal` column is gated. `anchor` (exits), ATR, stops and targets
are untouched, so a position already open is never force-closed by this
filter alone.

The daily EMA needs history to converge: with too little, it returns no
trend and every entry would be silently blocked. `features` therefore
refuses to run on less than `min_history_hours` instead of failing quiet.
"""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd

from .v4_hourly import HourlyParams, features as hourly_features, backtest as hourly_backtest

# Empirically, EMA(20)/EMA(100) results stop changing at 140 days of history
# (backtest2-v1/REPRODUCTION_NOTE.md); 1.5x the slow span is the conservative rule.
HISTORY_FACTOR = 1.5


@dataclass(frozen=True)
class MacroHourlyParams(HourlyParams):
    macro_fast: int = 20
    macro_slow: int = 100

    def __post_init__(self):
        HourlyParams.__post_init__(self)
        if not 1 < self.macro_fast < self.macro_slow:
            raise ValueError('macro_fast must be smaller than macro_slow')

    @property
    def min_history_hours(self):
        return math.ceil(HISTORY_FACTOR * self.macro_slow) * 24


def macro_trend(bars, fast, slow):
    """+1/-1/0 daily EMA-cross trend, causally aligned to bars.index.

    Same reindex+ffill discipline as the 4h anchor: at hourly close t+1h only
    fully closed days are visible.
    """
    daily = bars.close.resample('1D', closed='left', label='right').last()
    ema_fast = daily.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = daily.ewm(span=slow, adjust=False, min_periods=slow).mean()
    side = pd.Series(np.where(ema_fast > ema_slow, 1, np.where(ema_fast < ema_slow, -1, 0)), index=daily.index)
    return side.reindex(bars.index + pd.Timedelta(hours=1), method='ffill').fillna(0)


def features(bars, p):
    span = (bars.index[-1] - bars.index[0]) / pd.Timedelta(hours=1) + 1 if len(bars) else 0
    if span < p.min_history_hours:
        raise ValueError('Macro filter needs at least %d hours of history, got %d; '
                         'entries would be silently blocked' % (p.min_history_hours, span))
    base = hourly_features(bars, p)
    macro = macro_trend(bars, p.macro_fast, p.macro_slow).to_numpy()
    raw = base['signal'].to_numpy()
    out = base.copy()
    out['signal'] = np.where(raw == macro, raw, 0)
    return out


def backtest(bars, p, risk, start=None, end=None, prepared=None):
    """v4_hourly's engine replayed on the macro-gated signal."""
    f = features(bars, p) if prepared is None else prepared
    return hourly_backtest(bars, p, risk, start, end, prepared=f)
