"""Re-run the FROZEN v4_hourly params (configs/selected.json, unmodified) on
REAL OKX market data instead of the Binance-USD-M proxy used for the
original research. Same purpose as multi_asset_validation.py, different
data source: this removes the "Binance as OKX proxy" caveat, it does not
create a new independent holdout (same calendar period already searched).

Data sources (OKX public endpoints, no auth needed):
  - 1h candles: /api/v5/market/history-candles, paginated. Goes back to
    Dec 2019 for BTC-USDT-SWAP; ETH/SOL checked at runtime.
  - funding: OKX's live funding-rate-history endpoint only retains ~3
    months. Older funding comes from OKX's own daily bulk archive
    (market-data-history module=3, 'allswap-fundingrates-<date>.zip'),
    already used by v2_data.py's funding_file(). That archive's earliest
    day, checked by binary search, is 2022-01-17 -- so that is this
    script's evaluation start, later than the 2021-01-01 the Binance-proxy
    research used. This is a real data-availability limit, not filled in.
"""
from dataclasses import asdict
from hashlib import sha256
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import metrics, daily_returns
from astra.legacy_data import validate
from astra.legacy_research import monte_carlo, dump
from astra.v2_data import funding_file, verified_read, verified_write, LIMIT
from astra.v3_trend import maker_risk, taker_risk, attribution
from astra.v4_hourly import HourlyParams, backtest

DATA_DIR = Path('data')
OUT_DIR = Path('reports/v4-hourly-okx-native')
RAW = DATA_DIR / 'raw' / 'okx_native'

EVAL_START = pd.Timestamp('2022-01-17', tz='UTC')   # earliest day with a funding archive
END_EXCLUSIVE = pd.Timestamp('2026-09-01', tz='UTC')  # matches data/manifest.json window end
SYMBOLS = {'BTC': 'BTC-USDT-SWAP', 'ETH': 'ETH-USDT-SWAP', 'SOL': 'SOL-USDT-SWAP'}

CANDLES_URL = 'https://www.okx.com/api/v5/market/history-candles'


def fetch_candles(inst_id):
    """Page backward from END_EXCLUSIVE to EVAL_START. Cached per page."""
    cache = RAW / 'candles' / inst_id
    cursor = str(int(END_EXCLUSIVE.timestamp() * 1000))
    rows = []
    floor_ms = int(EVAL_START.timestamp() * 1000)
    for page in range(2000):
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
                raise ValueError(f'OKX error for {inst_id}: {payload}')
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
    if not rows:
        raise ValueError(f'No candle rows fetched for {inst_id}')
    frame = pd.DataFrame(
        [[int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in rows],
        columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    frame.index = pd.to_datetime(frame.pop('time'), unit='ms', utc=True)
    frame = frame[~frame.index.duplicated()].sort_index()
    frame = frame.loc[(frame.index >= EVAL_START) & (frame.index < END_EXCLUSIVE)]
    return frame


def fetch_funding(inst_id):
    root = RAW
    days = pd.date_range(EVAL_START.floor('D'), END_EXCLUSIVE.floor('D'), freq='D')
    frames = []
    for day in days:
        frame, _ = funding_file(day, root)
        frames.append(frame[frame.instrument_name == inst_id][['time', 'funding_rate']])
    funding = pd.concat(frames).drop_duplicates('time').set_index('time').sort_index()['funding_rate'].astype(float)
    return funding


def build_symbol_frame(inst_id):
    print(f'  candles ({inst_id}) ...', flush=True)
    bars = fetch_candles(inst_id)
    print(f'  funding ({inst_id}) ...', flush=True)
    funding = fetch_funding(inst_id)
    bars['funding'] = funding.groupby(funding.index.floor('h')).sum().reindex(bars.index, fill_value=0.)
    validate(bars)
    return bars


def evaluate(label, bars, p, maker, taker):
    equity, trades, state = backtest(bars, p, maker)
    full = metrics(equity, trades, maker.capital)
    returns = daily_returns(equity, maker.capital)
    mc = monte_carlo(returns, 2000, seed=42, block_days=7)
    stress_equity, stress_trades, _ = backtest(bars, p, taker)
    stress = metrics(stress_equity, stress_trades, maker.capital)
    years = full['days'] / 365
    annual = (1 + full['return']) ** (1 / years) - 1 if years > 0 else 0.
    report = {
        'symbol': label, 'data_source': 'OKX native (public API), not Binance proxy',
        'window': f'{EVAL_START.date()}..{END_EXCLUSIVE.date()}',
        'params_source': 'configs/selected.json (frozen, unmodified)', 'params': asdict(p),
        'full_period_maker': full, 'annualised_return': annual,
        'calmar': annual / full['max_drawdown'] if full['max_drawdown'] > 0 else None,
        'monte_carlo_7d': mc, 'taker_stress': stress, 'halted': state['halted'],
        'attribution': attribution(trades, maker.capital, maker),
        'note': 'No DSR: same fixed hypothesis as the Binance-proxy research, re-evaluated on real OKX data.',
    }
    out = OUT_DIR / label
    out.mkdir(parents=True, exist_ok=True)
    dump(out / 'report.json', report)
    equity.to_csv(out / 'equity.csv', index_label='time')
    pd.DataFrame(trades).to_csv(out / 'trades.csv', index=False)
    return report


def main():
    cfg = json.loads(Path('configs/selected.json').read_text())
    p = HourlyParams(**cfg['params'])
    maker = maker_risk(cfg['risk']['capital'], cfg['risk']['fraction'])
    taker = taker_risk(cfg['risk']['capital'], cfg['risk']['fraction'])
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    for label, inst_id in SYMBOLS.items():
        print(f'=== {label} ({inst_id}): downloading real OKX candles + funding, '
              f'{EVAL_START.date()}..{END_EXCLUSIVE.date()} ===', flush=True)
        bars = build_symbol_frame(inst_id)
        path = DATA_DIR / f'{inst_id}-okx-1h.csv'
        bars.to_csv(path, index_label='time')
        (DATA_DIR / f'{inst_id}-okx-manifest.json').write_text(json.dumps({
            'source': 'OKX public API (history-candles + funding archive), NOT a proxy',
            'start': str(EVAL_START), 'end_exclusive': str(END_EXCLUSIVE), 'rows': len(bars),
            'csv_sha256': sha256(path.read_bytes()).hexdigest()}, indent=2))
        print(f'=== {label}: running frozen v4_hourly params (no refit) ===', flush=True)
        results[label] = evaluate(label, bars, p, maker, taker)
        r = results[label]
        print(json.dumps({
            'symbol': label, 'sharpe_maker': r['full_period_maker']['sharpe'],
            'sharpe_taker': r['taker_stress']['sharpe'], 'annualised_return': r['annualised_return'],
            'max_drawdown': r['full_period_maker']['max_drawdown'], 'calmar': r['calmar'],
            'trades': r['full_period_maker']['trades'], 'win_rate': r['full_period_maker']['win_rate'],
            'halted': r['halted'], 'mc_sharpe_p05_7d': r['monte_carlo_7d']['sharpe_p05'],
        }, indent=2), flush=True)

    dump(OUT_DIR / 'summary.json', {
        'window': f'{EVAL_START.date()}..{END_EXCLUSIVE.date()}',
        'btc_binance_proxy_reference': cfg['measured_research'],
        'btc_okx_native': {k: results['BTC'][k] for k in ('full_period_maker', 'annualised_return', 'calmar', 'taker_stress', 'monte_carlo_7d', 'halted')},
        'eth_okx_native': {k: results['ETH'][k] for k in ('full_period_maker', 'annualised_return', 'calmar', 'taker_stress', 'monte_carlo_7d', 'halted')},
        'sol_okx_native': {k: results['SOL'][k] for k in ('full_period_maker', 'annualised_return', 'calmar', 'taker_stress', 'monte_carlo_7d', 'halted')},
        'disclosure': ('Real OKX data (candles + funding archive), frozen BTC-selected params, unmodified. '
                       'Window starts 2022-01-17 (earliest funding archive day) instead of 2021-01-01: '
                       'this is a real data-availability limit, not a choice, and it shortens the window '
                       'versus the Binance-proxy research -- results are not directly comparable period-for-period. '
                       'Still not an independent holdout: same calendar period already used to design the strategy, '
                       'just the correct data source instead of the Binance stand-in.')})
    print('=== DONE. See reports/v4-hourly-okx-native/summary.json ===')


if __name__ == '__main__':
    main()
