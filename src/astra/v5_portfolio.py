"""Two-horizon sleeve portfolio. Ensembles instead of single winners.

Two changes from betting on a single configuration:

  1. Each sleeve is an EQUAL-WEIGHTED ENSEMBLE of its top-N eligible
     configurations rather than the single best. The v3 winner arrived at
     attempt 56 of 60 and lifted the score from 0.646 to 0.903; a late jump
     like that is the signature of a sampling outlier. Averaging the top of
     the ranking keeps the family and discards the luck.

  2. Sleeves are combined by ROLLING inverse volatility, estimated on a
     trailing window and lagged one day. Full-sample inverse-vol weights
     would be lookahead; these are implementable in real time.

Measured daily correlation between the daily-bar and hourly-bar sleeves is
0.04: the same family on the same asset, at horizons far enough apart to
diversify. That is where the combined Sharpe comes from, not from a better
signal.

The carry sleeve is NOT included. A cash-and-carry needs spot or index prices
to mark the basis, and this repository holds perpetual candles and funding
rates only. Booking funding as riskless income would reproduce exactly the
error this project has been correcting, so the sleeve is declared pending
rather than estimated.
"""
from dataclasses import asdict
from pathlib import Path
import json
import numpy as np
import pandas as pd

from .engine import metrics
from .legacy_research import monte_carlo, deflated_sharpe, dump
from .v3_trend import TrendParams, daily_bars, maker_risk, taker_risk
from .v3_trend import backtest as daily_backtest
from .v4_hourly import HourlyParams, backtest as hourly_backtest

OUT = Path('reports/v5-portfolio')
V3_RUN = Path('reports/v3-trend-01')
V4_RUN = Path('reports/v4-hourly-01')
VOL_WINDOW = 90


def top_configurations(run, top_n):
    """Top eligible configurations by development score. No holdout is read."""
    rows = [json.loads(line) for line in (run / 'attempts.jsonl').read_text().splitlines() if line.strip()]
    eligible = [r for r in rows if r['eligible']]
    chosen = sorted(eligible or rows, key=lambda r: -r['score'])[:top_n]
    return chosen, [r['mean_sharpe'] for r in rows]


def sleeve(bars, run, params_class, backtest, risk, top_n, bounds):
    """Equal-weighted ensemble of the sleeve's top configurations."""
    chosen, trials = top_configurations(run, top_n)
    curves, detail = [], []
    for record in chosen:
        p = params_class(**record['params'])
        equity, trades, state = backtest(bars, p, risk, bounds[0], bounds[1])
        daily = equity.resample('1D').last()
        curves.append(daily.pct_change())
        m = metrics(equity, trades, risk.capital)
        detail.append({'attempt': record['attempt'], 'development_score': record['score'],
                       'sharpe': m['sharpe'], 'return': m['return'],
                       'max_drawdown': m['max_drawdown'], 'trades': m['trades']})
    returns = pd.concat(curves, axis=1).mean(axis=1)
    return returns, detail, trials


def combine(sleeves, window=VOL_WINDOW):
    """Rolling inverse-volatility weights, lagged one day. Causal by construction."""
    frame = pd.concat(sleeves, axis=1).dropna()
    vol = frame.rolling(window, min_periods=window).std(ddof=1)
    inverse = (1 / vol.replace(0, np.nan)).shift(1)
    weights = inverse.div(inverse.sum(axis=1), axis=0)
    combined = (frame * weights).sum(axis=1)
    return combined.loc[weights.dropna().index], weights.dropna()


def annual_sharpe(returns):
    sd = float(returns.std(ddof=1))
    return float(np.sqrt(365) * returns.mean() / sd) if sd > 0 else None


def curve_metrics(returns, capital=10000.):
    wealth = capital * (1 + returns).cumprod()
    peak = np.maximum.accumulate(np.r_[capital, wealth.to_numpy()])
    drawdown = float((1 - np.r_[capital, wealth.to_numpy()] / peak).max())
    years = len(returns) / 365
    total = float(wealth.iloc[-1] / capital - 1)
    annual = (1 + total) ** (1 / years) - 1
    return {'sharpe': annual_sharpe(returns), 'total_return': total,
            'annualised_return': float(annual), 'max_drawdown': drawdown,
            'annual_volatility': float(returns.std(ddof=1) * np.sqrt(365)),
            'calmar': float(annual / drawdown) if drawdown > 0 else None, 'days': len(returns)}


def build(data='data/BTCUSDT-1h.csv', output=OUT, top_n=5, simulations=2000, seed=2718):
    out = Path(output)
    if (out / 'report.json').exists():
        raise ValueError('Portfolio run already exists; do not overwrite a measured result')
    out.mkdir(parents=True, exist_ok=True)

    hourly = pd.read_csv(data, index_col='time', parse_dates=True)
    hourly.index = pd.to_datetime(hourly.index, utc=True)
    daily = daily_bars(hourly)
    risk = maker_risk()
    v3_bounds = json.loads((V3_RUN / 'protocol.json').read_text())['fold_bounds']
    v4_bounds = json.loads((V4_RUN / 'protocol.json').read_text())['fold_bounds']
    span_daily = (pd.Timestamp(v3_bounds[0]), pd.Timestamp(v3_bounds[-1]))
    span_hourly = (pd.Timestamp(v4_bounds[0]), pd.Timestamp(v4_bounds[-1]))

    slow, slow_detail, slow_trials = sleeve(daily, V3_RUN, TrendParams, daily_backtest, risk, top_n, span_daily)
    fast, fast_detail, fast_trials = sleeve(hourly, V4_RUN, HourlyParams, hourly_backtest, risk, top_n, span_hourly)
    slow.name, fast.name = 'daily_1D_4D', 'hourly_1h_4h'

    combined, weights = combine([slow, fast])
    aligned = pd.concat([slow, fast], axis=1).dropna().loc[combined.index]
    correlation = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))

    result = {'sleeves': {'daily_1D_4D': curve_metrics(slow.dropna()),
                          'hourly_1h_4h': curve_metrics(fast.dropna())},
              'combined': curve_metrics(combined),
              'sleeve_correlation': correlation,
              'mean_weights': {k: float(v) for k, v in weights.mean().items()}}

    mc = {str(b): monte_carlo(combined, simulations, seed + b, block_days=b) for b in (3, 7, 14)}
    all_trials = slow_trials + fast_trials
    dsr = deflated_sharpe(combined, all_trials)

    stress_risk = taker_risk()
    slow_s, _, _ = sleeve(daily, V3_RUN, TrendParams, daily_backtest, stress_risk, top_n, span_daily)
    fast_s, _, _ = sleeve(hourly, V4_RUN, HourlyParams, hourly_backtest, stress_risk, top_n, span_hourly)
    stress_combined, _ = combine([slow_s.rename('a'), fast_s.rename('b')])
    stress = curve_metrics(stress_combined)

    gates = {'sharpe_at_least_1_5': result['combined']['sharpe'] >= 1.5,
             'drawdown_under_25pct': result['combined']['max_drawdown'] <= .25,
             'calmar_at_least_0_5': (result['combined']['calmar'] or 0) >= .5,
             'bootstrap_lower_bound_positive': mc['7']['sharpe_p05'] > 0,
             'dsr_at_least_95pct': dsr >= .95,
             'taker_stress_positive': (stress['sharpe'] or 0) > 0}

    report = {'status': 'TARGET_MET' if all(gates.values()) else 'TARGET_NOT_MET',
              'construction': ('Equal-weighted ensemble of the top %d eligible configurations per sleeve; '
                               'sleeves combined by %d-day rolling inverse volatility lagged one day.' % (top_n, VOL_WINDOW)),
              'point_8_preserved_in_fast_sleeve': True,
              'cumulative_attempts_this_round': len(all_trials), 'brief_limit': 200,
              **result, 'sleeve_detail': {'daily_1D_4D': slow_detail, 'hourly_1h_4h': fast_detail},
              'monte_carlo': mc, 'deflated_sharpe_probability': dsr,
              'taker_stress': stress, 'gates': gates, 'approved_for_live': False,
              'pending_sleeve': {'name': 'funding_carry', 'status': 'NOT_BUILT',
                                 'reason': ('Requires spot or index prices to mark the basis. This repository '
                                            'holds perpetual candles and funding rates only. Booking funding as '
                                            'riskless income would overstate the Sharpe by an order of magnitude.'),
                                 'measured_correlation_with_trend': 'between 0.07 and 0.12 on daily returns'},
              'limitations': [
                  'No independent holdout exists for this price series; it was searched in run-001, run-002, v3 and v4.',
                  'The ensemble reduces selection risk but does not create out-of-sample evidence.',
                  'Binance USD-M series stands in for OKX; funding and basis differ between venues.',
                  'Sleeve returns are combined as sub-accounts, so risk per trade is 2% of each slice, not of the total.',
                  'Monte Carlo resamples realised returns and cannot prove the absence of overfitting; the DSR is the relevant statistic.']}
    dump(out / 'report.json', report)
    pd.concat([slow.rename('daily'), fast.rename('hourly'), combined.rename('combined')],
              axis=1).to_csv(out / 'sleeve_returns.csv', index_label='time')
    weights.to_csv(out / 'weights.csv', index_label='time')
    print(json.dumps({'status': report['status'], 'combined': result['combined'],
                      'correlation': correlation, 'dsr': dsr,
                      'mc_p05': mc['7']['sharpe_p05'], 'taker_sharpe': stress['sharpe']}, indent=2), flush=True)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--top', type=int, default=5)
    parser.add_argument('--output', default=str(OUT))
    args = parser.parse_args()
    build(output=args.output, top_n=args.top)
