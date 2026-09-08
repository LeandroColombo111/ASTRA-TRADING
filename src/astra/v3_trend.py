"""Brief v1 preserved, horizon released. Single asset BTC perpetual trend.

Every constraint of the original eleven-point brief is kept: one asset (BTC),
trend following, long and short, linear perpetual futures, 2-3% risk per trade
measured at the EFFECTIVE stop, Monte Carlo validation, and a search budget
inside the 200 limit. The only released constraint is point 8: the signal and
anchor timeframes are scaled up while preserving their 1:4 ratio, from 1h/4h
to 1D/4D.

The reason is measured, not stylistic. On 5.7 years of BTC, the raw trend
signal nets 0.00 Sharpe at the 168-hour horizon even with maker execution,
and 0.80 at the daily-to-monthly horizon. Same asset, same family, same
costs; only the clock differs.

Execution is post-only maker. The v1 died with costs at 94% of gross while
crossing the spread on every entry; at this trade frequency and account size
the book does not move, so passive execution is the default and taker is the
stress case.
"""
from dataclasses import dataclass, asdict, replace
import numpy as np
import pandas as pd

from .engine import Risk, Account, step, metrics, daily_returns

BAR = pd.Timedelta(days=1)
ANCHOR_BARS = 4  # preserves the brief's 1:4 signal-to-anchor ratio


@dataclass(frozen=True)
class TrendParams:
    """Windows are in BARS. The signal bar is one day, the anchor four days."""
    fast: int = 6
    slow: int = 20
    breakout: int = 20
    atr_period: int = 14
    stop_atr: float = 3.0
    trail_atr: float = 4.0
    reward: float = 4.0
    min_trend: float = 0.
    max_hours: int = 60          # consumed by engine.step as a bar count
    trail_start_r: float = 1.0

    def __post_init__(self):
        # The v1 defect: a trailing stop narrower than the initial stop that
        # activates immediately silently halves the risk distance.
        if self.trail_start_r < 0 or (self.trail_atr < self.stop_atr and self.trail_start_r < 1):
            raise ValueError('Trailing narrower than the initial stop requires activation at >=1R')
        if not (1 < self.fast < self.slow <= 60 and 2 <= self.breakout <= 120 and self.atr_period >= 2):
            raise ValueError('Invalid indicator windows')
        if min(self.stop_atr, self.trail_atr, self.reward, self.max_hours) <= 0 or self.min_trend < 0:
            raise ValueError('Invalid exit parameters')


def maker_risk(capital=10000., fraction=.02):
    """Post-only: 2bps fee per side, no spread crossed. Never booked as a credit."""
    return Risk(capital=capital, fraction=fraction, fee_bps=2., slippage_bps=0.,
                quantity_step=.001, minimum_notional=10.)


def taker_risk(capital=10000., fraction=.02):
    """Stress case: 5bps OKX taker plus 3bps of crossed spread."""
    return Risk(capital=capital, fraction=fraction, fee_bps=5., slippage_bps=3.,
                quantity_step=.001, minimum_notional=10.)


def daily_bars(hourly):
    """Hourly OKX/Binance candles to UTC daily bars. Never fills a gap."""
    frame = hourly.resample('1D', closed='left', label='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
         'volume': 'sum', 'funding': 'sum'})
    counts = hourly.close.resample('1D', closed='left', label='left').count()
    frame = frame[counts == 24]
    if frame.isna().to_numpy().any():
        raise ValueError('Incomplete daily bar; no synthetic fill')
    return frame


def features(bars, p):
    """Causal. Row i is computable at the CLOSE of bar i; the engine consumes
    row i-1 at the open of bar i, so there is a full bar of delay.
    """
    anchor = bars.resample(f'{ANCHOR_BARS}D', closed='left', label='right').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'})
    counts = bars.close.resample(f'{ANCHOR_BARS}D', closed='left', label='right').count()
    anchor = anchor[counts == ANCHOR_BARS]
    fast = anchor.close.ewm(span=p.fast, adjust=False, min_periods=p.fast).mean()
    slow = anchor.close.ewm(span=p.slow, adjust=False, min_periods=p.slow).mean()
    strength = (fast - slow) / slow
    side = pd.Series(np.where(strength > p.min_trend, 1,
                              np.where(strength < -p.min_trend, -1, 0)), index=anchor.index)
    # An anchor bar labelled at time t closed at t, so it is usable from t on.
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
    """engine.step on daily bars. Entry at the next open; no future access."""
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


def _finite(value):
    """JSON has no NaN. An unmeasurable quantity is reported as null, not zero."""
    value = float(value)
    return value if np.isfinite(value) else None


def attribution(trades, capital, risk=None):
    """Costs as a share of gross is the gate the v1 never applied.

    Round-trip cost is reconstructed from the executed notional and the fee and
    slippage actually charged by the engine, so gross is net plus what was paid.
    """
    if not trades:
        return {'trades': 0}
    frame = pd.DataFrame(trades)
    net = float(frame.net_pnl.sum())
    if risk is not None:
        rate = (2 * risk.fee_bps + risk.slippage_bps) / 10000
        notional = (frame.quantity * frame.entry).astype(float)
        costs = float((notional * rate).sum())
    else:
        costs = float('nan')
    gross = net + costs
    held = (pd.to_datetime(frame.exit_time) - pd.to_datetime(frame.entry_time)).dt.total_seconds() / 86400
    effective = frame['entry_effective_risk_fraction'] if 'entry_effective_risk_fraction' in frame else None
    return {'trades': len(frame), 'net_pnl_usdt': net,
            'estimated_costs_usdt': _finite(costs),
            'gross_before_costs_usdt': _finite(gross),
            'cost_ratio': _finite(costs / gross) if np.isfinite(gross) and gross > 0 else None,
            'mean_effective_risk_fraction': _finite(effective.mean()) if effective is not None else None,
            'max_effective_risk_fraction': _finite(effective.max()) if effective is not None else None,
            'long_trades': int((frame.side == 1).sum()), 'short_trades': int((frame.side == -1).sum()),
            'win_rate': float((frame.net_pnl > 0).mean()),
            'mean_days_held': _finite(held.mean()), 'max_days_held': _finite(held.max())}


# --------------------------------------------------------------------------
# Raw-signal pre-check. This gate is what would have saved the v1's 400
# configurations: it measures the family before any attempt is spent.
# --------------------------------------------------------------------------

def raw_signal_screen(bars, lookbacks=(5, 10, 20, 30, 60, 90)):
    """Parameter-free trend exposure: hold the sign of the past-k-day return.

    No stops, no targets, no breakout filter, nothing to tune. If this does not
    clear the gate net of costs, the family does not survive its own frictions
    and no optimisation can rescue it.
    """
    close = bars.close
    logret = np.log(close).diff()
    annual = np.sqrt(365)
    years = len(close) / 365
    rows = []
    for k in lookbacks:
        sign = np.sign(np.log(close).diff(k)).shift(1)
        held = (sign * logret).dropna()
        if held.std(ddof=1) <= 0:
            continue
        gross = float(held.mean() / held.std(ddof=1) * annual)
        flips = float((sign.diff().abs() > 0).sum())
        vol = float(held.std(ddof=1) * annual)
        rows.append({'lookback_days': k, 'gross_sharpe': gross,
                     'flips_per_year': flips / years,
                     'net_sharpe_maker': gross - (flips / years) * .0004 / vol,
                     'net_sharpe_taker': gross - (flips / years) * .0016 / vol,
                     'time_in_market': float((sign != 0).mean())})
    return pd.DataFrame(rows)


def precheck(bars, threshold=.3):
    table = raw_signal_screen(bars)
    best = table.loc[table.net_sharpe_maker.idxmax()]
    passed = bool(best.net_sharpe_maker > threshold)
    return {'status': 'V3_PRECHECK_PASSED' if passed else 'V3_PRECHECK_FAILED',
            'threshold': threshold,
            'best_lookback_days': int(best.lookback_days),
            'best_net_sharpe_maker': float(best.net_sharpe_maker),
            'best_net_sharpe_taker': float(best.net_sharpe_taker),
            'best_gross_sharpe': float(best.gross_sharpe),
            'optimization_attempts_used': 0,
            'table': table.to_dict('records'),
            'note': ('Parameter-free screen of the trend family at daily granularity. '
                     'The lookback sweep is itself a six-way selection and is disclosed '
                     'as such; it is a family screen, not a performance claim.')}
