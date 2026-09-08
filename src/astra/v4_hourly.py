"""Point 8 restored: 1h signal bar, 4h anchor bar. Only the RANGES move.

The v1 satisfied point 8 and failed. The v3 released point 8 and reached
Sharpe 1.05. That comparison conflated two different things:

  - the BAR SIZE, which point 8 fixes at 1h signal and 4h anchor, and
  - the LOOKBACK and HOLDING PERIOD, which point 8 says nothing about.

The v1 grid capped the breakout at 200 bars (8.3 days) and the holding period
at 480 hours (20 days), so it never explored the slow end at hourly
resolution. The v3 winner used a 40-day breakout held 30 days. If the edge
comes from the horizon rather than from the bar size, it should survive at
1h/4h once the ranges are opened.

This module keeps every one of the eleven points, including point 8.
"""
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from .engine import Risk, Account, step, metrics
from .v3_trend import maker_risk, taker_risk, attribution

BAR = pd.Timedelta(hours=1)
ANCHOR = '4h'


@dataclass(frozen=True)
class HourlyParams:
    """Windows in HOURS, except fast/slow which are spans of 4h anchor bars.

    Identical semantics to the v1 Params. The only change is that the window
    ceilings are raised so the slow end of the family becomes reachable; the
    v1 cap of 200 bars was an arbitrary bound, not a modelling choice.
    """
    fast: int = 20
    slow: int = 150
    breakout: int = 480
    atr_period: int = 168
    stop_atr: float = 4.
    trail_atr: float = 5.
    reward: float = 6.
    min_trend: float = 0.
    max_hours: int = 720
    trail_start_r: float = 1.

    def __post_init__(self):
        if self.trail_start_r < 0 or (self.trail_atr < self.stop_atr and self.trail_start_r < 1):
            raise ValueError('Trailing narrower than the initial stop requires activation at >=1R')
        if not (1 < self.fast < self.slow <= 400):
            raise ValueError('Invalid anchor EMA spans')
        if not (2 <= self.breakout <= 1500 and self.atr_period >= 2):
            raise ValueError('Invalid signal windows')
        if min(self.stop_atr, self.trail_atr, self.reward, self.max_hours) <= 0 or self.min_trend < 0:
            raise ValueError('Invalid exit parameters')


def features(bars, p):
    """Identical construction to the v1: 4h anchor, hourly breakout, one bar
    of delay. Causal; the engine consumes row i-1 at the open of bar i.
    """
    anchor = bars.resample(ANCHOR, closed='left', label='right').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
    counts = bars.close.resample(ANCHOR, closed='left', label='right').count()
    anchor = anchor[counts == 4]
    fast = anchor.close.ewm(span=p.fast, adjust=False, min_periods=p.fast).mean()
    slow = anchor.close.ewm(span=p.slow, adjust=False, min_periods=p.slow).mean()
    strength = (fast - slow) / slow
    side = pd.Series(np.where(strength > p.min_trend, 1,
                              np.where(strength < -p.min_trend, -1, 0)), index=anchor.index)
    aligned = side.reindex(bars.index + BAR, method='ffill').fillna(0).to_numpy()
    prev = bars.close.shift(1)
    tr = pd.concat([bars.high - bars.low, (bars.high - prev).abs(), (bars.low - prev).abs()],
                   axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / p.atr_period, adjust=False, min_periods=p.atr_period).mean()
    upper = bars.high.shift(1).rolling(p.breakout).max()
    lower = bars.low.shift(1).rolling(p.breakout).min()
    signal = np.where((aligned == 1) & (bars.close > upper), 1,
                      np.where((aligned == -1) & (bars.close < lower), -1, 0))
    return pd.DataFrame({'signal': signal, 'anchor': aligned, 'atr': atr}, index=bars.index)


def backtest(bars, p, risk, start=None, end=None, prepared=None):
    f = features(bars, p) if prepared is None else prepared
    lo = pd.Timestamp(start) if start is not None else bars.index[0]
    hi = pd.Timestamp(end) if end is not None else bars.index[-1] + BAR
    positions = np.flatnonzero((bars.index >= lo) & (bars.index < hi))
    if not len(positions):
        raise ValueError('Empty evaluation window')
    s = Account.new(risk)
    curve, trades, dates = [], [], []
    bvals, fvals = bars.to_dict('records'), f.to_dict('records')
    for n, i in enumerate(positions):
        previous = {'signal': 0, 'anchor': 0, 'atr': float('nan')} if i == 0 else fvals[i - 1]
        trades.extend(step(s, bars.index[i], bvals[i], previous, fvals[i], p, risk,
                           force_close=n == len(positions) - 1))
        curve.append(s.equity)
        dates.append(bars.index[i] + BAR)
    return pd.Series(curve, index=pd.DatetimeIndex(dates), name='equity'), trades, asdict(s)
