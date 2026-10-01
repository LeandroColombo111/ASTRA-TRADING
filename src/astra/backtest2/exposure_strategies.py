"""Signals for the fixed-exposure sizing mode (ExecutionSimulator reads an optional 'exposure' column).

All strategies here are long-only or long/short variants expressed through the
same engine as v4_hourly, so fees, funding, slippage and liquidation are
identical. The 'atr' column is only a stop-distance unit: these strategies use
1% of price per unit so stop_atr=25 means a 25% disaster stop, independent of
short-horizon volatility.
"""
from dataclasses import dataclass
from pathlib import Path
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


@dataclass(frozen=True)
class DynTimeParams(HourlyParams):
    """Per-trade time barrier from the volatility regime: T = max_hours * ratio**(-gamma), clipped.
    ratio = realised vol over short_days / over long_days at the signal bar. gamma>0: high-vol regimes get a SHORTER
    limit and calm ones a longer one; gamma<0 is the opposite (control). Price barriers are unchanged."""
    gamma: float = 1.0
    short_days: int = 7
    long_days: int = 60
    min_hours: float = 240.
    max_cap_hours: float = 960.


def dyntime_signal(bars, p):
    base = v4_features(bars, p)
    r = np.log(bars.close).diff()
    ratio = (r.rolling(p.short_days * 24).std() / r.rolling(p.long_days * 24).std()).to_numpy()
    limit = np.where(np.isfinite(ratio) & (ratio > 0), p.max_hours * np.power(np.where(ratio > 0, ratio, 1.), -p.gamma), p.max_hours)
    out = base.copy()
    out['max_hours'] = np.clip(limit, p.min_hours, p.max_cap_hours)
    return out


@dataclass(frozen=True)
class VolumeParams(HourlyParams):
    """Gate v4_hourly ENTRIES with participation, using only the hourly `volume` column.
    surge = mean volume over vol_short_hours / mean volume over vol_long_days; vol_ratio_min keeps only breakouts with above-normal
    participation, vol_ratio_max the opposite (control). obv_days > 0 additionally requires on-balance volume (signed by the candle,
    cumulative) above its EMA for longs and below it for shorts (accumulation / distribution)."""
    vol_short_hours: int = 24
    vol_long_days: int = 30
    vol_ratio_min: float = 0.0
    vol_ratio_max: float = 1e9
    obv_days: int = 0


def volume_signal(bars, p):
    base = v4_features(bars, p)
    v = bars.volume.astype(float)
    ratio = (v.rolling(p.vol_short_hours).mean() / v.rolling(p.vol_long_days * 24).mean()).to_numpy()
    ok = np.isfinite(ratio) & (ratio >= p.vol_ratio_min) & (ratio <= p.vol_ratio_max)
    sig = base['signal'].to_numpy()
    if p.obv_days > 0:
        obv = (np.sign(bars.close - bars.open) * v).cumsum()
        ema = obv.ewm(span=p.obv_days * 24, adjust=False, min_periods=p.obv_days * 24).mean()
        acc = (obv - ema).to_numpy()
        ok = ok & np.isfinite(acc) & (((sig == 1) & (acc > 0)) | ((sig == -1) & (acc < 0)))
    out = base.copy()
    out['signal'] = np.where(ok, sig, 0)
    return out


@dataclass(frozen=True)
class VwapDeviationParams(HourlyParams):
    """Gate v4_hourly ENTRIES by deviation from a rolling VWAP (volume-weighted average price, typical price x volume).
    mode='breakout_confirm': only take the breakout when price is already away from VWAP by at least dev_min (trend
    already has volume-weighted conviction). mode='reversion_block': block entries extended more than dev_max from
    VWAP (chasing a move already far from the volume-weighted average)."""
    vwap_hours: int = 168
    dev_min: float = 0.0
    dev_max: float = 1e9
    mode: str = 'breakout_confirm'


def vwap_deviation(bars, hours):
    typical = (bars.high + bars.low + bars.close) / 3.
    pv = (typical * bars.volume).rolling(hours).sum()
    v = bars.volume.rolling(hours).sum()
    vwap = pv / v
    return (bars.close - vwap) / vwap


def vwap_signal(bars, p):
    base = v4_features(bars, p)
    dev = vwap_deviation(bars, p.vwap_hours).to_numpy()
    sig = base['signal'].to_numpy()
    if p.mode == 'breakout_confirm':
        ok = np.isfinite(dev) & (((sig == 1) & (dev >= p.dev_min)) | ((sig == -1) & (dev <= -p.dev_min)))
    else:
        ok = np.isfinite(dev) & (np.abs(dev) <= p.dev_max)
    out = base.copy()
    out['signal'] = np.where(ok, sig, 0)
    return out


def load_binance_metrics(symbol):
    """Daily positioning metrics from Binance (proxy for OKX; NOT OKX data). Never fills the known 2021-12-31 to
    2022-12-13 gap (see data/<SYMBOL>-metrics-manifest.json): callers must dropna() per column they use."""
    path = Path(__file__).resolve().parents[3] / 'data' / f'{symbol}USDT-metrics-daily.csv'
    df = pd.read_csv(path, index_col='time', parse_dates=True)
    return df


def _causal_daily(series, bars_index, max_stale_days=2):
    """Align a metric known only at the end of day D to hourly bars: only visible from D+1 00:00 onward (never looks
    ahead into the day that produced it), same reindex+ffill discipline as macro_trend's daily EMA cross. Capped at
    max_stale_days: an unbounded ffill would silently bridge the known 316-day Binance outage with an up-to-a-year-
    stale value, which is filling a gap in disguise. Past the cap the value reads as unavailable (NaN), same as if
    there were no data that day -- entries relying on it are blocked, never guessed."""
    shifted = series.copy()
    shifted.index = shifted.index + pd.Timedelta(days=1)
    return shifted.reindex(bars_index + BAR, method='ffill', limit=max_stale_days * 24)


@dataclass(frozen=True)
class OpenInterestParams(HourlyParams):
    """Gate v4_hourly ENTRIES on open interest direction: only take a trade (long or short) when OI rose over the
    last oi_days, i.e. new money is entering alongside the move (vs a breakout driven by position unwinding /
    short-covering, which futures lore treats as weaker and more reversal-prone). Reasoned direction, not swept."""
    oi_days: int = 3
    symbol: str = 'BTC'


def oi_confirm_signal(bars, p):
    base = v4_features(bars, p)
    m = load_binance_metrics(p.symbol)
    oi_chg = m['sum_open_interest'].pct_change(p.oi_days)
    aligned = _causal_daily(oi_chg, bars.index).to_numpy()
    ok = np.isfinite(aligned) & (aligned > 0)
    out = base.copy()
    out['signal'] = np.where(ok, base['signal'].to_numpy(), 0)
    return out


@dataclass(frozen=True)
class SmartMoneyParams(HourlyParams):
    """'Smart money' divergence: gate entries on top-trader long/short positioning vs the all-account (mostly
    retail) ratio. Only take a LONG when top traders are relatively MORE long than the crowd (top_ratio > retail
    ratio x divergence_min); only take a SHORT when top traders are relatively more short. When top traders agree
    with the crowd or lean the other way, the signal is blocked. Fixed divergence_min, not swept."""
    divergence_min: float = 1.0  # top/retail ratio must exceed this to confirm a long (and its reciprocal to confirm a short)
    symbol: str = 'BTC'


def smart_money_signal(bars, p):
    base = v4_features(bars, p)
    m = load_binance_metrics(p.symbol)
    rel = (m['sum_toptrader_long_short_ratio'] / m['count_long_short_ratio']).dropna()
    aligned = _causal_daily(rel, bars.index).to_numpy()
    sig = base['signal'].to_numpy()
    ok = np.isfinite(aligned) & (((sig == 1) & (aligned >= p.divergence_min)) | ((sig == -1) & (aligned <= 1 / p.divergence_min)))
    out = base.copy()
    out['signal'] = np.where(ok, sig, 0)
    return out


@dataclass(frozen=True)
class TakerFlowParams(HourlyParams):
    """Gate v4_hourly ENTRIES by aggressor (taker) volume imbalance: only take a long when takers were net buyers
    over the last flow_days, only take a short when takers were net sellers (real order-flow confirmation, the
    closest proxy to true aggressor data this project has access to)."""
    flow_days: int = 3
    symbol: str = 'BTC'


def taker_flow_signal(bars, p):
    base = v4_features(bars, p)
    m = load_binance_metrics(p.symbol)
    ratio = m['sum_taker_long_short_vol_ratio'].rolling(p.flow_days).mean().dropna()
    aligned = _causal_daily(ratio, bars.index).to_numpy()
    sig = base['signal'].to_numpy()
    ok = np.isfinite(aligned) & (((sig == 1) & (aligned >= 1.0)) | ((sig == -1) & (aligned < 1.0)))
    out = base.copy()
    out['signal'] = np.where(ok, sig, 0)
    return out
