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


@dataclass(frozen=True)
class VolRegimeParams(HourlyParams):
    """Gate v4_hourly ENTRIES by the volatility regime: ratio = realised vol over `short_days` / over `long_days`.
    ratio_min keeps only expanding-vol entries (persistence of high volatility); ratio_max keeps only calm ones.
    Exits, stops and sizing are v4_hourly's."""
    short_days: int = 7
    long_days: int = 60
    ratio_min: float = 0.0
    ratio_max: float = 1e9


def volregime_signal(bars, p):
    base = v4_features(bars, p)
    r = np.log(bars.close).diff()
    ratio = (r.rolling(p.short_days * 24).std() / r.rolling(p.long_days * 24).std()).to_numpy()
    ok = np.isfinite(ratio) & (ratio >= p.ratio_min) & (ratio <= p.ratio_max)
    out = base.copy()
    out['signal'] = np.where(ok, base['signal'].to_numpy(), 0)
    return out


@dataclass(frozen=True)
class BlendVolParams(HourlyParams):
    """Barriers scaled by a volatility FORECAST instead of the short ATR alone: a mix of the short estimate
    (atr_period, captures clustering) and a slow one (atr_slow, the long-run level volatility reverts to),
    like the GARCH(1,1) structure. blend_w is the weight on the SHORT estimate."""
    atr_slow: int = 720
    blend_w: float = 0.5


def blendvol_signal(bars, p):
    base = v4_features(bars, p)
    prev = bars.close.shift(1)
    tr = pd.concat([bars.high - bars.low, (bars.high - prev).abs(), (bars.low - prev).abs()], axis=1).max(axis=1)
    slow = tr.ewm(alpha=1 / p.atr_slow, adjust=False, min_periods=p.atr_slow).mean()
    out = base.copy()
    out['atr'] = np.sqrt(p.blend_w * base['atr'] ** 2 + (1 - p.blend_w) * slow ** 2).to_numpy()
    return out
