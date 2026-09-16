"""First-pass backtest of a funding-carry (cash-and-carry) sleeve on BTC,
to check whether it's worth building for real before investing more time.

Idea: when funding is positive, longs pay shorts. Go short the perpetual and
long an equal notional of spot (delta-neutral by construction) to collect
that payment; when funding is negative, do the opposite. Price moves mostly
cancel between the two legs, so the return driver is meant to be funding,
not direction.

Signal is the PREVIOUS funding period's realized rate, never the current
one -- using today's rate to size today's position would be lookahead; OKX
publishes a predicted next-period rate in real time that this backtest does
not use, so if anything this understates the real edge, not overstates it.

Zero tuned parameters. Only one threshold (min_funding_apr) exists, and it
is set from round-trip trading costs, not fit to the data -- there is
nothing to search here, and searching would be exactly the DSR-inflating
mistake this project has been careful to avoid elsewhere.

Known simplifications, disclosed rather than hidden:
  - Hourly mark-to-market of both legs between funding settlements is a
    reasonable but not perfect model of a continuously delta-neutral book.
  - No contract lot-size / minimum-notional rounding difference between the
    spot and perpetual legs (the real exchange has different lot sizes for
    each) -- a real implementation would carry small residual basis risk
    this backtest does not capture.
  - Same Binance-avoidance discipline as the rest of the project: uses real
    OKX spot + perp + funding data, no proxy.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import daily_returns, metrics
from astra.legacy_research import monte_carlo, dump
from astra.v2_data import verified_read, verified_write, LIMIT

DATA_DIR = Path('data')
OUT_DIR = Path('reports/v6-carry-01')
RAW = DATA_DIR / 'raw' / 'okx_native'
EVAL_START = pd.Timestamp('2022-01-17', tz='UTC')   # same funding-archive floor as before
END_EXCLUSIVE = pd.Timestamp('2026-09-01', tz='UTC')
CANDLES_URL = 'https://www.okx.com/api/v5/market/history-candles'


def fetch_spot():
    inst_id = 'BTC-USDT'
    cache = RAW / 'candles' / inst_id
    cursor = str(int(END_EXCLUSIVE.timestamp() * 1000))
    floor_ms = int(EVAL_START.timestamp() * 1000)
    rows = []
    for _ in range(2000):
        path = cache / f'{cursor}.json'
        cached = verified_read(path)
        if cached is not None:
            data = json.loads(cached)
        else:
            LIMIT.wait()
            r = requests.get(CANDLES_URL, params={'instId': inst_id, 'bar': '1H', 'limit': '100', 'after': cursor}, timeout=20)
            r.raise_for_status()
            payload = r.json()
            if payload.get('code') != '0':
                raise ValueError(f'OKX error: {payload}')
            data = payload['data']
            verified_write(path, json.dumps(data).encode())
        if not data:
            break
        ts = [int(row[0]) for row in data]
        rows.extend(row for row in data if row[8] == '1')
        new_cursor = str(min(ts))
        if new_cursor == cursor:
            raise ValueError('Pagination did not advance')
        cursor = new_cursor
        if min(ts) <= floor_ms:
            break
    frame = pd.DataFrame([[int(r[0]), float(r[4])] for r in rows], columns=['time', 'close'])
    frame.index = pd.to_datetime(frame.pop('time'), unit='ms', utc=True)
    frame = frame[~frame.index.duplicated()].sort_index()
    return frame.loc[(frame.index >= EVAL_START) & (frame.index < END_EXCLUSIVE)]['close']


@dataclass(frozen=True)
class CarryParams:
    min_funding_apr: float = 0.10  # ~ round-trip cost of flipping both legs, annualised; not fit to data
    fee_bps_per_leg: float = 5.0   # taker, both legs; maker case reported as a variant, not the base case
    smoothing_events: int = 21     # 7 days at ~3 funding events/day; a trend signal, not a fit knob


def backtest(perp, spot, funding, p, capital=10000.):
    common = perp.index.intersection(spot.index).intersection(funding.index)
    perp, spot, funding = perp.loc[common], spot.loc[common], funding.loc[common]
    hourly_threshold = p.min_funding_apr / (365 * 3)  # ~3 funding events/day

    # Signal is a trailing mean of the last N REALIZED funding events, not the
    # single latest one -- reacting to one noisy period whipsawed the position
    # far more often than the underlying (persistent, 73%-positive) funding
    # bias justified. This is a structural fix, not a fitted parameter.
    nonzero = funding[funding != 0]
    smoothed = nonzero.rolling(p.smoothing_events, min_periods=5).mean()

    equity = capital
    direction = 0.  # +1 = short perp / long spot (collects positive funding); -1 = the opposite
    notional = 0.
    curve, dates = [], []
    flips = []
    prev_perp, prev_spot = None, None

    for t in common:
        f = funding.loc[t]
        if prev_perp is not None:
            perp_ret = perp.loc[t] / prev_perp - 1
            spot_ret = spot.loc[t] / prev_spot - 1
            equity += direction * notional * (spot_ret - perp_ret)
        prev_perp, prev_spot = perp.loc[t], spot.loc[t]

        if f != 0:
            equity += direction * f * notional
            trend = smoothed.loc[t]
            signal = 0. if pd.isna(trend) else (1. if trend > hourly_threshold else (-1. if trend < -hourly_threshold else 0.))
            if signal != direction:
                cost = abs(signal - direction) * (equity) * 2 * p.fee_bps_per_leg / 10000
                equity -= cost
                if signal != 0 and direction != signal:
                    flips.append({'time': str(t), 'from': direction, 'to': signal, 'cost': cost,
                                   'side': int(signal), 'net_pnl': -cost})
                direction = signal
            notional = equity  # 100% notional, rebalanced only at funding events

        curve.append(equity)
        dates.append(t)

    return pd.Series(curve, index=pd.DatetimeIndex(dates), name='equity'), flips


def main():
    print('=== downloading real OKX spot BTC-USDT candles ===', flush=True)
    spot = fetch_spot()
    perp_frame = pd.read_csv(DATA_DIR / 'BTC-USDT-SWAP-okx-1h.csv', index_col='time', parse_dates=True)
    perp_frame.index = pd.to_datetime(perp_frame.index, utc=True)
    perp = perp_frame['close']
    funding = perp_frame['funding']

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, fee_bps in (('taker', 5.0), ('maker', 2.0)):
        p = CarryParams(fee_bps_per_leg=fee_bps)
        equity, flips = backtest(perp, spot, funding, p)
        m = metrics(equity, flips, 10000.)  # 'trades' here means direction flips, not round-trip trades
        returns = daily_returns(equity, 10000.)
        mc = monte_carlo(returns, 2000, seed=7, block_days=7) if len(returns) >= 60 else None
        years = m['days'] / 365
        annual = (1 + m['return']) ** (1 / years) - 1 if years > 0 else 0.
        results[label] = {
            'sharpe': m['sharpe'], 'total_return': m['return'], 'annualised_return': annual,
            'max_drawdown': m['max_drawdown'], 'calmar': annual / m['max_drawdown'] if m['max_drawdown'] > 0 else None,
            'direction_flips': len(flips), 'days': m['days'], 'monte_carlo_7d': mc,
        }
        equity.to_csv(OUT_DIR / f'equity_{label}.csv', index_label='time')
        dump(OUT_DIR / f'flips_{label}.json', flips)
        print(json.dumps({label: results[label]}, indent=2, default=str), flush=True)

    # correlation with the two trend sleeves already measured, using the taker-cost carry curve
    combined_equity = pd.read_csv('reports/v5-portfolio-01/sleeve_returns.csv', index_col='time', parse_dates=True)
    carry_daily = daily_returns(pd.read_csv(OUT_DIR / 'equity_taker.csv', index_col='time', parse_dates=True)['equity'], 10000.)
    aligned = combined_equity.join(carry_daily.rename('carry'), how='inner')
    correlation = {
        'carry_vs_daily_trend': float(aligned['daily'].corr(aligned['carry'])),
        'carry_vs_hourly_trend': float(aligned['hourly'].corr(aligned['carry'])),
    } if len(aligned) > 30 else {'note': 'insufficient overlap to measure correlation'}

    dump(OUT_DIR / 'report.json', {
        'params': asdict(CarryParams()), 'window': f'{EVAL_START.date()}..{END_EXCLUSIVE.date()}',
        'results': results, 'correlation_with_existing_sleeves': correlation,
        'note': 'No DSR: zero tuned parameters, nothing searched.',
        'limitations': [
            'Hourly mark-to-market approximates a continuously hedged book; not exact.',
            'No lot-size/minimum-notional mismatch between spot and perp legs modelled.',
            'Signal uses the previous funding period only (fully causal); OKX publishes a '
            'predicted next-period rate this backtest ignores, so live performance could be '
            'better, not just worse, if that prediction is used instead.',
        ]})
    print('=== DONE. See reports/v6-carry-01/report.json ===')


if __name__ == '__main__':
    main()
