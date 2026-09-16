"""Cross-asset validation: run the FROZEN v4_hourly params from
configs/selected.json against ETH and SOL, changing nothing.

This is not a search. No parameter here is refit per asset -- the whole
point is to check whether the BTC-selected params produce a positive,
plausible edge elsewhere, or whether the BTC result was a curve fit. Reuses
the same Binance USD-M archive source and validation as the existing BTC
dataset (data/manifest.json) so results are comparable.

No DSR is computed: DSR penalizes a search over multiple configurations,
and there is no search here, just one fixed hypothesis evaluated twice.
"""
from dataclasses import asdict
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import Risk, metrics, daily_returns
from astra.legacy_data import archive, validate
from astra.legacy_research import monte_carlo, dump
from astra.v3_trend import maker_risk, taker_risk, attribution
from astra.v4_hourly import HourlyParams, backtest

DATA_DIR = Path('data')
OUT_DIR = Path('reports/v4-hourly-eth-sol')
START = pd.Timestamp('2021-01-01', tz='UTC')
END_EXCLUSIVE = pd.Timestamp('2026-09-01', tz='UTC')  # same window as data/manifest.json

# SOLUSDT's Binance archive has two real gaps (missing candles, not our data)
# in Feb/Apr 2022. We do not fill gaps -- validate() forbids it -- so the
# usable window for SOL starts after the second gap instead.
EVAL_START = {'SOLUSDT': pd.Timestamp('2022-05-01', tz='UTC')}


def download_symbol(symbol):
    cache = DATA_DIR / 'raw'
    cache.mkdir(parents=True, exist_ok=True)
    months = pd.date_range(START, END_EXCLUSIVE, freq='MS', inclusive='left').strftime('%Y-%m')
    bars, funds, manifest = [], [], []
    for month in months:
        df, meta = archive('klines', month, cache, symbol=symbol)
        manifest.append(meta)
        df = df[pd.to_numeric(df[0], errors='coerce').notna()].copy()
        df = df.iloc[:, :6].astype(float)
        df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
        df.index = pd.to_datetime(df.pop('time'), unit='ms', utc=True)
        bars.append(df)
        fdf, fmeta = archive('fundingRate', month, cache, symbol=symbol)
        manifest.append(fmeta)
        fdf.index = pd.to_datetime(fdf['calc_time'], unit='ms', utc=True)
        funds.append(fdf['last_funding_rate'].astype(float))
    frame = pd.concat(bars).sort_index()
    funding = pd.concat(funds).sort_index()
    frame['funding'] = funding.groupby(funding.index.floor('h')).sum().reindex(frame.index, fill_value=0.)
    eval_start = EVAL_START.get(symbol, START)
    frame = frame.loc[(frame.index >= eval_start) & (frame.index < END_EXCLUSIVE)]
    validate(frame)
    path = DATA_DIR / f'{symbol}-1h.csv'
    frame.to_csv(path, index_label='time')
    (DATA_DIR / f'{symbol}-manifest.json').write_text(json.dumps({
        'source': 'Binance USD-M futures, proxy for OKX; NOT OKX data',
        'start': str(eval_start), 'end_exclusive': str(END_EXCLUSIVE), 'rows': len(frame),
        'gap_disclosure': (f'Evaluation window starts at {eval_start.date()} instead of {START.date()} '
                            'because the Binance archive has real missing-candle gaps before that date '
                            '(not filled; filling gaps is explicitly forbidden by legacy_data.validate).'
                            if eval_start != START else None),
        'archives': manifest}, indent=2))
    return path


def evaluate(symbol, path, p, maker, taker):
    bars = pd.read_csv(path, index_col='time', parse_dates=True)
    bars.index = pd.to_datetime(bars.index, utc=True)
    equity, trades, state = backtest(bars, p, maker)
    full = metrics(equity, trades, maker.capital)
    returns = daily_returns(equity, maker.capital)
    mc = monte_carlo(returns, 2000, seed=42, block_days=7)
    stress_equity, stress_trades, _ = backtest(bars, p, taker)
    stress = metrics(stress_equity, stress_trades, maker.capital)
    years = full['days'] / 365
    annual = (1 + full['return']) ** (1 / years) - 1 if years > 0 else 0.
    report = {
        'symbol': symbol, 'params_source': 'configs/selected.json (frozen, unmodified)',
        'params': asdict(p),
        'full_period_maker': full, 'annualised_return': annual,
        'calmar': annual / full['max_drawdown'] if full['max_drawdown'] > 0 else None,
        'monte_carlo_7d': mc, 'taker_stress': stress,
        'halted': state['halted'],
        'attribution': attribution(trades, maker.capital, maker),
        'note': 'No DSR: this is one fixed hypothesis carried over from BTC, not a new search.',
    }
    out = OUT_DIR / symbol
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
    for symbol in ('ETHUSDT', 'SOLUSDT'):
        print(f'=== {symbol}: downloading Binance USD-M 1h + funding, {START.date()}..{END_EXCLUSIVE.date()} ===', flush=True)
        path = download_symbol(symbol)
        print(f'=== {symbol}: running frozen v4_hourly params (no refit) ===', flush=True)
        results[symbol] = evaluate(symbol, path, p, maker, taker)
        r = results[symbol]
        print(json.dumps({
            'symbol': symbol, 'sharpe_maker': r['full_period_maker']['sharpe'],
            'sharpe_taker': r['taker_stress']['sharpe'], 'annualised_return': r['annualised_return'],
            'max_drawdown': r['full_period_maker']['max_drawdown'], 'calmar': r['calmar'],
            'trades': r['full_period_maker']['trades'], 'win_rate': r['full_period_maker']['win_rate'],
            'halted': r['halted'], 'mc_sharpe_p05_7d': r['monte_carlo_7d']['sharpe_p05'],
        }, indent=2), flush=True)

    dump(OUT_DIR / 'summary.json', {
        'btc_reference': cfg['measured_research'],
        'eth': {k: results['ETHUSDT'][k] for k in ('full_period_maker', 'annualised_return', 'calmar', 'taker_stress', 'monte_carlo_7d', 'halted')},
        'sol': {k: results['SOLUSDT'][k] for k in ('full_period_maker', 'annualised_return', 'calmar', 'taker_stress', 'monte_carlo_7d', 'halted')},
        'disclosure': 'Frozen BTC params applied unmodified to ETH and SOL. No DSR: not a search. '
                      'Same Binance-as-OKX-proxy caveat as the BTC research applies.'})
    print('=== DONE. See reports/v4-hourly-eth-sol/summary.json ===')


if __name__ == '__main__':
    main()
