"""Model the execution/hedge-slippage risk the carry backtest (v6) assumes
away: it marks the two legs (spot, perp) as perfectly hedged every hour,
with no gap between when one leg fills and the other does. In reality
they are two separate orders; whatever gap exists between them exposes
the position to basis movement during that gap, not just funding.

We don't have tick-level execution data to measure that gap directly, but
we already measured the right proxy: BASIS_RISK_ANALYSIS.md found that
the real, dated hourly basis (perp vs spot) CHANGE distribution is exactly
what a hedge-desync would be exposed to -- and its worst moves cluster on
real crash dates (LUNA, FTX), not evenly through time. Reusing that same
empirical distribution here (rather than inventing a latency number we
cannot verify) is the same discipline this project uses everywhere else:
real data over an assumed constant.

Method: at every position open/flip in the taker-cost carry backtest (27
events), add a stochastic hedge-slippage cost drawn (bootstrap, with
replacement) from the REAL historical distribution of hourly basis
changes, applied to that event's notional. Run this 2000 times (Monte
Carlo) to see the distribution of outcomes, not a single point estimate --
the risk is much more about the tail (a bad draw landing on a real crash
date) than the average.
"""
from itertools import chain
from pathlib import Path
import glob
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import daily_returns, metrics

RAW_CANDLES = Path('data/raw/okx_native/candles')
OUT = Path('reports/v6-carry-01')
SIMULATIONS = 2000
SEED = 314


def load_candle_closes(inst_id):
    rows = []
    for f in (RAW_CANDLES / inst_id).glob('*.json'):
        for r in json.loads(f.read_text()):
            if r[8] == '1':
                rows.append((int(r[0]), float(r[4])))
    s = pd.DataFrame(rows, columns=['time', 'close']).drop_duplicates('time').set_index('time')['close']
    s.index = pd.to_datetime(s.index, unit='ms', utc=True)
    return s.sort_index()


def basis_change_distribution():
    perp = load_candle_closes('BTC-USDT-SWAP')
    spot = load_candle_closes('BTC-USDT')
    common = perp.index.intersection(spot.index)
    basis = (perp.loc[common] - spot.loc[common]) / spot.loc[common]
    return basis.diff().dropna().to_numpy()  # fraction of price, not bps


def main():
    changes = basis_change_distribution()
    print(f'basis-change sample: {len(changes)} hourly observations, '
          f'std {changes.std()*10000:.2f}bps, worst {np.abs(changes).max()*10000:.1f}bps', flush=True)

    flips = json.loads((OUT / 'flips_taker.json').read_text())
    equity = pd.read_csv(OUT / 'equity_taker.csv', index_col='time', parse_dates=True)['equity']
    capital = 10000.
    baseline = metrics(equity, [{'side': 1, 'net_pnl': 1} for _ in flips], capital)
    baseline_returns = daily_returns(equity, capital)
    baseline_sharpe = float(np.sqrt(365) * baseline_returns.mean() / baseline_returns.std(ddof=1))

    # Notional at each flip: reconstruct from equity right before that flip time.
    notionals = []
    for f in flips:
        t = pd.Timestamp(f['time'])
        prior = equity.loc[:t]
        notionals.append(float(prior.iloc[-2]) if len(prior) > 1 else capital)

    rng = np.random.default_rng(SEED)
    results = {'full_distribution': [], 'stress_tail_5pct': []}
    tail = changes[np.abs(changes) >= np.quantile(np.abs(changes), 0.95)]

    for scenario, source in (('full_distribution', changes), ('stress_tail_5pct', tail)):
        for _ in range(SIMULATIONS):
            draws = rng.choice(source, size=len(flips), replace=True)
            hit = float(np.sum(np.abs(draws) * np.array(notionals)))  # adverse-sign assumption: cost, not windfall
            final = float(equity.iloc[-1]) - hit
            total_return = final / capital - 1
            results[scenario].append(total_return)

    report = {
        'baseline_no_execution_risk': {
            'sharpe': baseline_sharpe, 'total_return': float(equity.iloc[-1] / capital - 1),
            'max_drawdown': baseline['max_drawdown'],
        },
        'basis_change_stats_bps': {
            'std': float(changes.std() * 10000), 'worst_abs': float(np.abs(changes).max() * 10000),
        },
        'flips_modelled': len(flips),
        'simulations': SIMULATIONS,
    }
    for scenario in ('full_distribution', 'stress_tail_5pct'):
        arr = np.array(results[scenario])
        report[scenario] = {
            'total_return_p05': float(np.quantile(arr, .05)), 'total_return_p50': float(np.quantile(arr, .50)),
            'total_return_p95': float(np.quantile(arr, .95)),
            'total_return_mean': float(arr.mean()),
            'probability_return_turns_negative': float((arr < 0).mean()),
        }
    (OUT / 'execution_risk_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f'=== DONE. See {OUT}/execution_risk_report.json ===')


if __name__ == '__main__':
    main()
