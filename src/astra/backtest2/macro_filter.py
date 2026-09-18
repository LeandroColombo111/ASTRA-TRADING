"""Causal macro trend filter gating v4_hourly's entries by a slower, independent timeframe.

Diagnostic finding (from the long/short x bull/bear split): trades whose
direction disagreed with how the quarter eventually resolved -- long trades
in quarters that ended bearish, short trades in quarters that ended
bullish -- lost money as a block, while aligned trades made money as a
block. That quarter-outcome label is hindsight and not implementable
directly. This module tests whether a causal daily EMA trend (using only
already-closed days, same reindex/ffill discipline as the existing 4h
anchor) can approximate that alignment without looking ahead.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from ..v4_hourly import HourlyParams, features as base_features


@dataclass(frozen=True)
class MacroFilteredParams:
    inner: HourlyParams
    macro_fast: int = 20
    macro_slow: int = 100

    def __post_init__(self):
        if not (1 < self.macro_fast < self.macro_slow):
            raise ValueError("macro_fast must be less than macro_slow")

    # Passthrough so ExecutionSimulator.step can read these directly off
    # whatever params object WalkForwardEngine hands it, without knowing
    # it's wrapped.
    @property
    def stop_atr(self): return self.inner.stop_atr

    @property
    def trail_atr(self): return self.inner.trail_atr

    @property
    def reward(self): return self.inner.reward

    @property
    def max_hours(self): return self.inner.max_hours

    @property
    def trail_start_r(self): return self.inner.trail_start_r


def macro_trend(bars: pd.DataFrame, fast: int, slow: int) -> pd.Series:
    """+1/-1/0 daily EMA-cross trend, causally aligned to bars.index (only ever sees fully closed prior days)."""
    daily = bars.close.resample("1D", closed="left", label="right").last()
    ema_fast = daily.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = daily.ewm(span=slow, adjust=False, min_periods=slow).mean()
    side = pd.Series(np.where(ema_fast > ema_slow, 1, np.where(ema_fast < ema_slow, -1, 0)), index=daily.index)
    return side.reindex(bars.index + pd.Timedelta(hours=1), method="ffill").fillna(0)


def macro_filtered_signal(bars: pd.DataFrame, p: MacroFilteredParams) -> pd.DataFrame:
    """v4_hourly's signal/anchor/atr, with new entries masked to fire only when aligned with the daily macro trend.

    Exits are untouched: the existing 4h anchor-flip and stop/target logic
    still governs when a position closes. Only entries are gated, so a
    trade already open when the macro trend flips is not force-closed by
    this filter alone.
    """
    base = base_features(bars, p.inner)
    macro = macro_trend(bars, p.macro_fast, p.macro_slow).to_numpy()
    raw_signal = base["signal"].to_numpy()
    gated_signal = np.where(raw_signal == macro, raw_signal, 0)
    out = base.copy()
    out["signal"] = gated_signal
    return out
