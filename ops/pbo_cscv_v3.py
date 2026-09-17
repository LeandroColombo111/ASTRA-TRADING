"""Same PBO/CSCV diagnostic as ops/pbo_cscv.py, applied to the OTHER
search that feeds the portfolio ensemble: the v3_trend daily/4-day sleeve
(reports/v3-trend-01), instead of the v4_hourly search. See that module's
docstring for the full explanation of what PBO measures and why it must
not be used as a tuning loop -- unchanged here.
"""
from itertools import combinations
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import daily_returns
from astra.v3_trend import TrendParams, daily_bars, maker_risk, backtest

RUN = Path('reports/v3-trend-01')
OUT = Path('reports/pbo-v3-trend-01')
S = 16


def load_configs():
    rows = [json.loads(l) for l in (RUN / 'attempts.jsonl').read_text().splitlines() if l.strip()]
    return [TrendParams(**r['params']) for r in rows]


def build_return_matrix(configs, bars, bounds):
    risk = maker_risk()
    series = []
    for i, p in enumerate(configs):
        equity, trades, _ = backtest(bars, p, risk, bounds[0], bounds[-1])
        r = daily_returns(equity, risk.capital)
        r.name = i
        series.append(r)
        if (i + 1) % 10 == 0:
            print(f'  backtested {i + 1}/{len(configs)} configs', flush=True)
    return pd.concat(series, axis=1).dropna()


def sharpe(x):
    sd = x.std(ddof=1)
    return float(np.sqrt(365) * x.mean() / sd) if sd > 0 else 0.


def compute_pbo(frame, s=S):
    T = len(frame)
    block_size = T // s
    if block_size < 5:
        raise ValueError(f'Not enough data for {s} blocks ({T} days)')
    blocks = [frame.iloc[i * block_size:(i + 1) * block_size] for i in range(s)]
    logits = []
    for train_idx in combinations(range(s), s // 2):
        test_idx = [i for i in range(s) if i not in train_idx]
        train = pd.concat([blocks[i] for i in train_idx])
        test = pd.concat([blocks[i] for i in test_idx])
        is_sharpe = train.apply(sharpe)
        oos_sharpe = test.apply(sharpe)
        best = is_sharpe.idxmax()
        rank = oos_sharpe.rank(method='average')[best]
        omega = min(max(rank / (len(oos_sharpe) + 1), 1e-6), 1 - 1e-6)
        logits.append(np.log(omega / (1 - omega)))
    logits = np.array(logits)
    return {
        'pbo': float((logits <= 0).mean()),
        'n_combinations': len(logits),
        'logit_mean': float(logits.mean()),
        'logit_median': float(np.median(logits)),
        'logit_std': float(logits.std()),
        'blocks': s, 'block_size_days': block_size,
    }


def main():
    hourly = pd.read_csv('data/BTCUSDT-1h.csv', index_col='time', parse_dates=True)
    hourly.index = pd.to_datetime(hourly.index, utc=True)
    bars = daily_bars(hourly)
    protocol = json.loads((RUN / 'protocol.json').read_text())
    bounds = [pd.Timestamp(b) for b in protocol['fold_bounds']]
    configs = load_configs()
    print(f'{len(configs)} configurations from {RUN}, full-period backtest each (bounds {bounds[0]}..{bounds[-1]})', flush=True)
    frame = build_return_matrix(configs, bars, bounds)
    print(f'return matrix: {frame.shape[0]} days x {frame.shape[1]} configs', flush=True)
    result = compute_pbo(frame)
    result.update(configurations=len(configs), data_days=int(frame.shape[0]), source_run=str(RUN))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'report.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f'=== DONE. See {OUT}/report.json ===')


if __name__ == '__main__':
    main()
