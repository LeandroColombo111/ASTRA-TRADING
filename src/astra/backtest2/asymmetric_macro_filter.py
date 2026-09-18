"""Asymmetric version of macro_filter.py's gate, motivated by the
long/short x regime split: trades aligned with the eventual quarterly
outcome made +13,470 as a block, misaligned trades lost -3,615 with a
17-20% win rate, and "long in a quarter that resolved bearish" was the
single worst cell -- worse than "short in a quarter that resolved
bullish". The symmetric macro filter (macro_filter.py) requires the SAME
strict alignment for both sides; this tests whether loosening it
specifically for shorts (while keeping longs strict) captures more of
the good short trades without reintroducing the bad long ones.

One fixed rule, not a grid: longs still require macro == +1 exactly
(unchanged from the symmetric filter); shorts fire whenever macro != +1
(bearish OR neutral), which is looser than the symmetric filter's
macro == -1 requirement. This is a single, reasoned design choice, not a
parameter swept and picked after the fact -- per the same discipline as
every other search in this project, sweeping this and keeping whichever
asymmetry "worked best" in walk-forward would just reproduce the
overfitting the walk-forward exists to catch.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from ..v4_hourly import HourlyParams, features as base_features
from .macro_filter import macro_trend


@dataclass(frozen=True)
class AsymmetricMacroParams:
    inner: HourlyParams
    macro_fast: int = 20
    macro_slow: int = 100

    def __post_init__(self):
        if not (1 < self.macro_fast < self.macro_slow):
            raise ValueError("macro_fast must be less than macro_slow")

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


def asymmetric_macro_signal(bars: pd.DataFrame, p: AsymmetricMacroParams) -> pd.DataFrame:
    """Longs require macro == +1 (strict); shorts fire whenever macro != +1 (loose). Exits untouched."""
    base = base_features(bars, p.inner)
    macro = macro_trend(bars, p.macro_fast, p.macro_slow).to_numpy()
    raw_signal = base["signal"].to_numpy()
    gated = np.where((raw_signal == 1) & (macro == 1), 1,
                      np.where((raw_signal == -1) & (macro != 1), -1, 0))
    out = base.copy()
    out["signal"] = gated
    return out
