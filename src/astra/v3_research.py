"""Bounded walk-forward search for the v3 daily trend, with honest validation.

Budget is 60 configurations, deliberately inside the brief's 200 limit: every
additional trial raises the bar the Deflated Sharpe Ratio must clear, so
spending the full allowance would make a real edge harder to demonstrate, not
easier.

There is no independent holdout. The 2021-2026 BTC series was searched in
run-001 and again in run-002, and the horizon sweep that motivated this
configuration was run on it too. That is disclosed rather than disguised:
the only validation that can still be independent is forward paper trading.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json
import numpy as np
import pandas as pd

from .engine import metrics, daily_returns
from .legacy_research import monte_carlo, deflated_sharpe, dump
from .v3_trend import (TrendParams, daily_bars, features, backtest, maker_risk,
                       taker_risk, attribution, precheck)

OUT = Path('reports/v3-trend')
GRID = {'fast': [4, 6, 8, 10, 12], 'slow': [16, 20, 26, 32, 40],
        'breakout': [10, 20, 30, 40, 55], 'atr_period': [14, 20],
        'stop_atr': [2.5, 3., 4., 5.], 'trail_atr': [3., 4., 5., 6., 8.],
        'reward': [3., 4., 6., 10.], 'min_trend': [0., .01, .02],
        'max_hours': [30, 60, 90, 120], 'trail_start_r': [1., 1.5, 2.]}
FREE_PARAMETERS = len(GRID)


def candidates(seed, count):
    if not 1 <= count <= 200:
        raise ValueError('Budget must stay inside the brief limit of 200')
    rng = np.random.default_rng(seed)
    seen = set()
    guard = 0
    while len(seen) < count and guard < count * 200:
        guard += 1
        draw = {k: (int(rng.choice(v)) if isinstance(v[0], int) else float(rng.choice(v)))
                for k, v in GRID.items()}
        try:
            p = TrendParams(**draw)
        except ValueError:
            continue  # invalid combinations are rejected, not repaired
        if p in seen:
            continue
        seen.add(p)
        yield p


def fold_bounds(bars, folds=4, warmup_days=400):
    start = bars.index[0] + pd.Timedelta(days=warmup_days)
    end = bars.index[-1] + pd.Timedelta(days=1)
    edges = pd.date_range(start, end, periods=folds + 1)
    return [e.floor('D') for e in edges]


def evaluate(bars, p, risk, bounds, prepared, minimum_trades):
    folds = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        equity, trades, state = backtest(bars, p, risk, lo, hi, prepared=prepared)
        m = metrics(equity, trades, risk.capital)
        m['halted'] = state['halted']
        folds.append(m)
    sharpes = np.array([f['sharpe'] for f in folds])
    eligible = all(f['trades'] >= minimum_trades and not f['halted'] for f in folds)
    both_sides = sum(f['long_trades'] for f in folds) > 0 and sum(f['short_trades'] for f in folds) > 0
    score = float(np.median(sharpes) - .25 * sharpes.std())
    return folds, bool(eligible and both_sides), score


def search(data='data/BTCUSDT-1h.csv', output=OUT, attempts=60, seed=3141,
           folds=4, minimum_trades=4, simulations=2000):
    out = Path(output)
    if (out / 'protocol.json').exists():
        raise ValueError('Run directory already used; a budget cannot silently restart')
    out.mkdir(parents=True, exist_ok=True)

    hourly = pd.read_csv(data, index_col='time', parse_dates=True)
    hourly.index = pd.to_datetime(hourly.index, utc=True)
    bars = daily_bars(hourly)
    screen = precheck(bars)
    if screen['status'] != 'V3_PRECHECK_PASSED':
        dump(out / 'signal_precheck.json', screen)
        raise ValueError('Raw signal screen failed; family rejected before any attempt')
    dump(out / 'signal_precheck.json', screen)

    risk = maker_risk()
    bounds = fold_bounds(bars, folds)
    digest = sha256(pd.util.hash_pandas_object(bars, index=True).values.tobytes()).hexdigest()
    dump(out / 'protocol.json', {
        'brief': 'v1 eleven points preserved; point 8 released from 1h/4h to 1D/4D at the same 1:4 ratio',
        'asset': 'BTC perpetual (Binance USD-M series as OKX proxy)', 'directions': 'long and short',
        'instrument': 'linear perpetual futures, not spot',
        'risk_fraction': risk.fraction, 'risk_measured_at': 'effective stop, including the trailing rule',
        'execution': 'post-only maker 2bps per side, no spread crossed; taker 5bps+3bps reported as stress',
        'attempt_budget': attempts, 'brief_limit': 200, 'free_parameters': FREE_PARAMETERS,
        'seed': seed, 'folds': folds, 'fold_bounds': [str(b) for b in bounds],
        'minimum_trades_per_fold': minimum_trades, 'data_sha256': digest,
        'selection': 'median fold Sharpe minus 0.25 SD; every fold must clear the trade floor without halting, and both sides must trade',
        'independent_holdout': False,
        'holdout_disclosure': ('None exists. This price series was searched in run-001 and run-002, and the '
                               'horizon sweep motivating this configuration was measured on it. Walk-forward '
                               'folds reduce but do not remove that contamination. Only forward paper trading '
                               'can still be independent.'),
        'sample_size_disclosure': ('A single asset at this horizon yields tens of trades over 5.7 years. The '
                                   'standard error of an annualised Sharpe over this sample is roughly 0.42, '
                                   'so a measured 0.6 is under two standard errors from zero. This bounds what '
                                   'any result here can establish.'),
        'approved_for_live': False})

    records, choices = [], []
    for number, p in enumerate(candidates(seed, attempts), 1):
        prepared = features(bars, p)
        folds_result, eligible, score = evaluate(bars, p, risk, bounds, prepared, minimum_trades)
        record = {'attempt': number, 'params': asdict(p), 'folds': folds_result,
                  'mean_sharpe': float(np.mean([f['sharpe'] for f in folds_result])),
                  'score': score, 'eligible': eligible}
        records.append(record)
        choices.append((eligible, score, p, number))
        with (out / 'attempts.jsonl').open('a') as stream:
            stream.write(json.dumps(record, allow_nan=False) + '\n')
        if number % 10 == 0:
            print('Attempt %d/%d; best eligible score %.3f' % (
                number, attempts, max((c[1] for c in choices if c[0]), default=float('nan'))), flush=True)

    eligible, score, p, number = max(choices, key=lambda c: (c[0], c[1]))
    equity, trades, state = backtest(bars, p, risk, bounds[0], bounds[-1])
    full = metrics(equity, trades, risk.capital)
    returns = daily_returns(equity, risk.capital)
    mc = {str(block): monte_carlo(returns, simulations, seed + block, block_days=block)
          for block in (3, 7, 14)}
    dsr = deflated_sharpe(returns, [r['mean_sharpe'] for r in records])

    stress_equity, stress_trades, _ = backtest(bars, p, taker_risk(), bounds[0], bounds[-1])
    stress = metrics(stress_equity, stress_trades, risk.capital)

    gates = {'development_eligible': eligible,
             'sharpe_at_least_1_5': full['sharpe'] >= 1.5,
             'drawdown_under_25pct': full['max_drawdown'] <= .25,
             'not_halted': not state['halted'],
             'both_sides': min(full['long_trades'], full['short_trades']) > 0,
             'bootstrap_lower_bound_positive': mc['7']['sharpe_p05'] > 0,
             'dsr_at_least_95pct': dsr >= .95,
             'taker_stress_positive': stress['sharpe'] > 0}
    report = {'status': 'TARGET_MET' if all(gates.values()) else 'TARGET_NOT_MET',
              'attempts': attempts, 'selected_attempt': number, 'params': asdict(p),
              'risk': asdict(risk), 'full_period': full, 'monte_carlo': mc,
              'deflated_sharpe_probability': dsr, 'taker_stress': stress,
              'attribution': attribution(trades, risk.capital, risk), 'gates': gates,
              'approved_for_live': False,
              'limitations': [
                  'No independent holdout exists for this price series; forward paper trading is the only remaining independent test.',
                  'Binance USD-M series stands in for OKX; funding and basis differ between venues.',
                  'Tens of trades over 5.7 years cannot separate a Sharpe of 0.6 from zero at conventional confidence.',
                  'Post-only execution assumes fills that daily bars cannot verify; the taker case is reported as the bound.',
                  'Monte Carlo resamples realised returns and cannot prove the absence of overfitting; the DSR is the relevant statistic.']}
    dump(out / 'report.json', report)
    equity.to_csv(out / 'equity.csv', index_label='time')
    pd.DataFrame(trades).to_csv(out / 'trades.csv', index=False)
    print(json.dumps({'status': report['status'], 'sharpe': full['sharpe'],
                      'return': full['return'], 'max_drawdown': full['max_drawdown'],
                      'trades': full['trades'], 'dsr': dsr,
                      'mc_p05': mc['7']['sharpe_p05'], 'taker_sharpe': stress['sharpe']}, indent=2), flush=True)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempts', type=int, default=60)
    parser.add_argument('--output', default=str(OUT))
    args = parser.parse_args()
    search(output=args.output, attempts=args.attempts)
