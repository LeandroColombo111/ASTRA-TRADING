"""Probability of Backtest Overfitting via Combinatorially Symmetric
Cross-Validation (Bailey, Borwein, Lopez de Prado & Zhu, 2017), applied to
the v4_hourly parameter search already run (reports/v4-hourly-01).

This is a DIAGNOSTIC, not a tuning tool. The DSR already used elsewhere in
this project asks "is the winning Sharpe distinguishable from noise given
how many configurations were tried?" PBO asks a different question: "how
likely is it that the SELECTION PROCEDURE ITSELF -- pick whatever looks
best in-sample -- would have picked a below-median performer out of
sample?" Running this repeatedly while adjusting the strategy to push PBO
down would reproduce exactly the overfitting it exists to measure: run
once, read the number, do not search against it.

Method: split the full backtest period into S=16 contiguous blocks (the
paper's standard default). For every way of splitting those 16 blocks into
two equal halves (C(16,8)=12,870 splits), treat one half as "in-sample",
the other as "out-of-sample". Whichever of the 60 searched configurations
had the best Sharpe in-sample is the one the original search would have
picked; check where THAT configuration ranks out-of-sample. If it's
consistently below the out-of-sample median across splits, the selection
procedure is overfitting the data, regardless of what the DSR of the
final pick says.
"""
from itertools import combinations
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import daily_returns
from astra.v3_trend import maker_risk
from astra.v4_hourly import HourlyParams, backtest

RUN = Path('reports/v4-hourly-01')
OUT = Path('reports/pbo-v4-hourly-01')
S = 16  # standard CSCV block count


def load_configs():
    rows = [json.loads(l) for l in (RUN / 'attempts.jsonl').read_text().splitlines() if l.strip()]
    return [HourlyParams(**r['params']) for r in rows]


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
    bars = pd.read_csv('data/BTCUSDT-1h.csv', index_col='time', parse_dates=True)
    bars.index = pd.to_datetime(bars.index, utc=True)
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
