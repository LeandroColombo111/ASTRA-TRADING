"""Signals for the fixed-exposure sizing mode (ExecutionSimulator reads an optional 'exposure' column).

All strategies here are long-only or long/short variants expressed through the
same engine as v4_hourly, so fees, funding, slippage and liquidation are
identical. The 'atr' column is only a stop-distance unit: these strategies use
1% of price per unit so stop_atr=25 means a 25% disaster stop, independent of
short-horizon volatility.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from ..v4_hourly import HourlyParams, features as v4_features, BAR


@dataclass(frozen=True)
class HoldParams:
    """Fixed-exposure trend holding. Stop/target/timeout fields exist because the engine reads them;
    they are set so that only the macro exit (anchor) and the disaster stop can close a trade."""
    macro_fast: int = 20
    macro_slow: int = 100
    exposure: float = 1.0
    disaster_stop_pct: float = 25.0     # in 'atr' units of 1% of price
    kind: str = 'ema'                   # 'ema' cross or 'sma' (price vs slow SMA, macro_fast ignored)
    long_only: bool = True
    stop_atr: float = 25.0
    trail_atr: float = 25.0
    reward: float = 1e9
    max_hours: int = 10**9
    trail_start_r: float = 1e9


def macro_state(bars, p):
    daily = bars.close.resample('1D', closed='left', label='right').last()
    if p.kind == 'sma':
        slow = daily.rolling(p.macro_slow, min_periods=p.macro_slow).mean()
        raw = np.where(daily > slow, 1, np.where(daily < slow, -1, 0))
        valid = slow.notna().to_numpy()
    else:
        f = daily.ewm(span=p.macro_fast, adjust=False, min_periods=p.macro_fast).mean()
        sl = daily.ewm(span=p.macro_slow, adjust=False, min_periods=p.macro_slow).mean()
        raw = np.where(f > sl, 1, np.where(f < sl, -1, 0))
        valid = sl.notna().to_numpy()
    side = pd.Series(np.where(valid, raw, 0), index=daily.index)
    return side.reindex(bars.index + BAR, method='ffill').fillna(0).to_numpy()


def hold_signal(bars, p):
    macro = macro_state(bars, p)
    if p.long_only:
        anchor = np.where(macro == 1, 1, 0)
    else:
        anchor = macro
    signal = anchor.copy()
    return pd.DataFrame({'signal': signal, 'anchor': anchor, 'atr': bars.close.to_numpy() * 0.01,
                         'exposure': p.exposure}, index=bars.index)


@dataclass(frozen=True)
class VolTargetParams(HourlyParams):
    """v4_hourly signals unchanged; only the size changes: exposure = target_vol / realised_vol, capped at 1."""
    target_vol: float = 0.30       # annualised
    vol_days: int = 30
    long_only: bool = False


def voltarget_signal(bars, p):
    base = v4_features(bars, p)
    r = np.log(bars.close).diff()
    vol = r.rolling(p.vol_days * 24).std() * np.sqrt(365 * 24)
    expo = (p.target_vol / vol).clip(upper=1.0)
    out = base.copy()
    out['exposure'] = expo.to_numpy()
    if p.long_only:
        out['signal'] = np.where(out['signal'] == 1, 1, 0)
        out['anchor'] = np.where(out['anchor'] == 1, 1, 0)
    return out


@dataclass(frozen=True)
class NearHighParams(HourlyParams):
    """Entry when the anchor trend is up and price is within `proximity` of the rolling `breakout`-hour high
    (instead of strictly above it). Exits, stops and sizing are v4_hourly's."""
    proximity: float = 0.03


def nearhigh_signal(bars, p):
    base = v4_features(bars, p)
    upper = bars.high.shift(1).rolling(p.breakout).max()
    near = (bars.close >= upper * (1 - p.proximity)).to_numpy()
    out = base.copy()
    aligned = base['anchor'].to_numpy()
    out['signal'] = np.where((aligned == 1) & near, 1, base['signal'].to_numpy() * (base['signal'].to_numpy() == -1))
    return out


@dataclass(frozen=True)
class LongOnlyParams(HourlyParams):
    pass


def longonly_signal(bars, p):
    base = v4_features(bars, p)
    out = base.copy()
    out['signal'] = np.where(base['signal'] == 1, 1, 0)
    out['anchor'] = np.where(base['anchor'] == 1, 1, 0)
    return out
