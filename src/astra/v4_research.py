"""Bounded search at 1h/4h with the slow ranges opened. Point 8 preserved.

Budget accounting for the brief's 200 limit: the v3 daily search spent 60
configurations and this search spends 60 more, 120 cumulative. Every one of
those 120 enters the Deflated Sharpe Ratio, because the DSR must be penalised
for the whole search that produced the winner, not for the last run only.

No independent holdout exists for this price series. Walk-forward folds reduce
contamination; they do not remove it. Forward paper trading remains the only
test that can still be independent.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json
import numpy as np
import pandas as pd

from .engine import metrics, daily_returns
from .legacy_research import monte_carlo, deflated_sharpe, dump
from .v3_trend import maker_risk, taker_risk, attribution
from .v4_hourly import HourlyParams, features, backtest

OUT = Path('reports/v4-hourly')
GRID = {'fast': [12, 20, 30, 40, 60], 'slow': [100, 150, 200, 300],
        'breakout': [240, 480, 720, 960, 1200], 'atr_period': [24, 72, 168, 336],
        'stop_atr': [2.5, 3., 4., 5.], 'trail_atr': [3., 4., 5., 6., 8.],
        'reward': [3., 4., 6., 10.], 'min_trend': [0., .01, .02],
        'max_hours': [480, 720, 960, 1440], 'trail_start_r': [1., 1.5, 2.]}


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
            p = HourlyParams(**draw)
        except ValueError:
            continue
        if p in seen:
            continue
        seen.add(p)
        yield p


def prior_trial_sharpes():
    """Trials already spent this round. Omitting them would inflate the DSR."""
    path = Path('reports/v3-trend-01/attempts.jsonl')
    if not path.exists():
        return []
    return [json.loads(line)['mean_sharpe'] for line in path.read_text().splitlines() if line.strip()]


def search(data='data/BTCUSDT-1h.csv', output=OUT, attempts=60, seed=3141,
           folds=4, warmup_days=400, minimum_trades=8, simulations=2000):
    out = Path(output)
    if (out / 'protocol.json').exists():
        raise ValueError('Run directory already used; a budget cannot silently restart')
    out.mkdir(parents=True, exist_ok=True)

    bars = pd.read_csv(data, index_col='time', parse_dates=True)
    bars.index = pd.to_datetime(bars.index, utc=True)
    risk = maker_risk()
    start = bars.index[0] + pd.Timedelta(days=warmup_days)
    end = bars.index[-1] + pd.Timedelta(hours=1)
    bounds = [e.floor('h') for e in pd.date_range(start, end, periods=folds + 1)]
    prior = prior_trial_sharpes()

    dump(out / 'protocol.json', {
        'brief': 'All eleven points preserved, point 8 included: 1h signal bar, 4h anchor bar',
        'change_from_v1': ('Only the parameter ranges move. The v1 capped the breakout at 200 bars '
                           '(8.3 days) and the holding period at 480 hours, so the slow end of the '
                           'family was unreachable at hourly resolution. Point 8 fixes the bar size, '
                           'not the lookback or the holding period.'),
        'asset': 'BTC perpetual (Binance USD-M series as OKX proxy)',
        'directions': 'long and short', 'instrument': 'linear perpetual futures, not spot',
        'risk_fraction': risk.fraction, 'risk_measured_at': 'effective stop including the trailing rule',
        'execution': 'post-only maker 2bps per side; taker 5bps+3bps reported as stress',
        'attempt_budget_this_run': attempts, 'attempts_earlier_this_round': len(prior),
        'cumulative_attempts': len(prior) + attempts, 'brief_limit': 200,
        'seed': seed, 'folds': folds, 'fold_bounds': [str(b) for b in bounds],
        'minimum_trades_per_fold': minimum_trades,
        'data_sha256': sha256(pd.util.hash_pandas_object(bars, index=True).values.tobytes()).hexdigest(),
        'selection': 'median fold Sharpe minus 0.25 SD; every fold clears the trade floor without halting, both sides trade',
        'independent_holdout': False,
        'holdout_disclosure': ('None exists. This series was searched in run-001, run-002 and the v3 daily '
                               'search, and the horizon sweep that motivated the open ranges was measured on '
                               'it. Only forward paper trading can still be independent.'),
        'dsr_disclosure': 'The DSR penalty counts all %d configurations spent this round.' % (len(prior) + attempts),
        'approved_for_live': False})

    records, choices = [], []
    for number, p in enumerate(candidates(seed, attempts), 1):
        prepared = features(bars, p)
        folds_result = []
        for lo, hi in zip(bounds[:-1], bounds[1:]):
            equity, trades, state = backtest(bars, p, risk, lo, hi, prepared=prepared)
            m = metrics(equity, trades, risk.capital)
            m['halted'] = state['halted']
            folds_result.append(m)
        sharpes = np.array([f['sharpe'] for f in folds_result])
        eligible = (all(f['trades'] >= minimum_trades and not f['halted'] for f in folds_result)
                    and sum(f['long_trades'] for f in folds_result) > 0
                    and sum(f['short_trades'] for f in folds_result) > 0)
        score = float(np.median(sharpes) - .25 * sharpes.std())
        record = {'attempt': number, 'params': asdict(p), 'folds': folds_result,
                  'mean_sharpe': float(sharpes.mean()), 'score': score, 'eligible': bool(eligible)}
        records.append(record)
        choices.append((bool(eligible), score, p, number))
        with (out / 'attempts.jsonl').open('a') as stream:
            stream.write(json.dumps(record, allow_nan=False) + '\n')
        if number % 20 == 0:
            print('Attempt %d/%d' % (number, attempts), flush=True)

    eligible, score, p, number = max(choices, key=lambda c: (c[0], c[1]))
    equity, trades, state = backtest(bars, p, risk, bounds[0], bounds[-1])
    full = metrics(equity, trades, risk.capital)
    returns = daily_returns(equity, risk.capital)
    mc = {str(b): monte_carlo(returns, simulations, seed + b, block_days=b) for b in (3, 7, 14)}
    dsr = deflated_sharpe(returns, prior + [r['mean_sharpe'] for r in records])
    stress_equity, stress_trades, _ = backtest(bars, p, taker_risk(), bounds[0], bounds[-1])
    stress = metrics(stress_equity, stress_trades, risk.capital)

    years = full['days'] / 365
    annual = (1 + full['return']) ** (1 / years) - 1
    gates = {'development_eligible': eligible,
             'sharpe_at_least_1_5': full['sharpe'] >= 1.5,
             'drawdown_under_25pct': full['max_drawdown'] <= .25,
             'not_halted': not state['halted'],
             'both_sides': min(full['long_trades'], full['short_trades']) > 0,
             'bootstrap_lower_bound_positive': mc['7']['sharpe_p05'] > 0,
             'dsr_at_least_95pct': dsr >= .95,
             'taker_stress_positive': stress['sharpe'] > 0,
             'calmar_at_least_0_5': annual / full['max_drawdown'] >= .5 if full['max_drawdown'] > 0 else False}
    report = {'status': 'TARGET_MET' if all(gates.values()) else 'TARGET_NOT_MET',
              'point_8_preserved': True, 'signal_bar': '1h', 'anchor_bar': '4h',
              'attempts_this_run': attempts, 'cumulative_attempts_this_round': len(prior) + attempts,
              'selected_attempt': number, 'params': asdict(p), 'risk': asdict(risk),
              'full_period': full, 'annualised_return': annual,
              'calmar': annual / full['max_drawdown'] if full['max_drawdown'] > 0 else None,
              'monte_carlo': mc, 'deflated_sharpe_probability': dsr, 'taker_stress': stress,
              'attribution': attribution(trades, risk.capital, risk), 'gates': gates,
              'approved_for_live': False,
              'limitations': [
                  'No independent holdout exists for this price series; forward paper trading is the only remaining independent test.',
                  'Binance USD-M series stands in for OKX; funding and basis differ between venues.',
                  'Post-only execution assumes fills that bar data cannot verify; the taker case is the reported bound.',
                  'Monte Carlo resamples realised returns and cannot prove the absence of overfitting; the DSR is the relevant statistic.']}
    dump(out / 'report.json', report)
    equity.to_csv(out / 'equity.csv', index_label='time')
    pd.DataFrame(trades).to_csv(out / 'trades.csv', index=False)
    print(json.dumps({'status': report['status'], 'sharpe': full['sharpe'],
                      'annualised_return': annual, 'max_drawdown': full['max_drawdown'],
                      'calmar': report['calmar'], 'trades': full['trades'], 'dsr': dsr,
                      'mc_p05': mc['7']['sharpe_p05'], 'taker_sharpe': stress['sharpe']}, indent=2), flush=True)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempts', type=int, default=60)
    parser.add_argument('--output', default=str(OUT))
    args = parser.parse_args()
    search(output=args.output, attempts=args.attempts)
