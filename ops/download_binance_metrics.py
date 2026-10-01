"""Download Binance USD-M daily 'metrics' archives (open interest, top-trader long/short ratio, account long/short
ratio, taker buy/sell volume ratio) for BTC/ETH/SOL, checksum-verified per file, no gaps filled. Proxy for OKX, NOT
OKX data (same disclosure as data/BTCUSDT-1h.csv etc). Resamples the native 5-minute rows to daily (last value of the
day) to match the OKX diagnostic in ops/backtest2_smart_money.py. Writes data/<SYMBOL>-metrics-daily.csv + manifest.
Earliest availability found by probing: BTC 2020-09-01, ETH/SOL 2021-12-01."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import sys
import time

import pandas as pd
import requests

DATA = Path('data')
CACHE = DATA / 'raw-metrics'
CACHE.mkdir(parents=True, exist_ok=True)
BASE = 'https://data.binance.vision/data/futures/um/daily/metrics'
END = pd.Timestamp('2026-10-01')  # exclusive
PLAN = {'BTCUSDT': pd.Timestamp('2020-09-01'), 'ETHUSDT': pd.Timestamp('2021-12-01'), 'SOLUSDT': pd.Timestamp('2021-12-01')}


def get(url, tries=4):
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=40)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def day(symbol, date):
    stem = f'{symbol}-metrics-{date:%Y-%m-%d}'
    zip_path, check_path = CACHE / f'{stem}.zip', CACHE / f'{stem}.zip.CHECKSUM'
    url = f'{BASE}/{symbol}/{stem}.zip'
    if not check_path.exists():
        check_path.write_bytes(get(url + '.CHECKSUM'))
    expected = check_path.read_text().split()[0]
    if not zip_path.exists() or sha256(zip_path.read_bytes()).hexdigest() != expected:
        payload = get(url)
        if sha256(payload).hexdigest() != expected:
            raise ValueError(f'Checksum mismatch: {url}')
        zip_path.write_bytes(payload)
    with ZipFile(BytesIO(zip_path.read_bytes())) as z:
        df = pd.read_csv(z.open(z.namelist()[0]))
    df['create_time'] = pd.to_datetime(df['create_time'], utc=True)
    return df, {'url': url, 'sha256': expected}


for symbol, start in PLAN.items():
    dates = pd.date_range(start, END, freq='D', inclusive='left')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda d: day(symbol, d), dates))
    frames = [r[0] for r in results]
    manifest = [r[1] for r in results]
    full = pd.concat(frames).sort_values('create_time')
    full = full[~full['create_time'].duplicated()]
    missing_days = len(dates) - full['create_time'].dt.normalize().nunique()
    full = full.set_index('create_time')
    cols = ['sum_open_interest', 'sum_open_interest_value', 'count_toptrader_long_short_ratio',
            'sum_toptrader_long_short_ratio', 'count_long_short_ratio', 'sum_taker_long_short_vol_ratio']
    daily = full[cols].resample('1D').last()  # last 5-minute snapshot of each UTC day; NaN where a day's file was empty/missing
    out = DATA / f'{symbol}-metrics-daily.csv'
    daily.to_csv(out, index_label='time')
    (DATA / f'{symbol}-metrics-manifest.json').write_text(json.dumps({
        'source': 'Binance USD-M futures, proxy for OKX; NOT OKX data',
        'start': str(start), 'end_exclusive': str(END), 'rows_5min': len(full), 'rows_daily': len(daily),
        'days_requested': len(dates), 'days_with_no_5min_rows': int(missing_days),
        'csv_sha256': sha256(out.read_bytes()).hexdigest(), 'archives': manifest,
        'known_gap': 'Binance itself has a real gap in count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio and '
                     'sum_taker_long_short_vol_ratio (and also count_long_short_ratio for ETH/SOL) from 2021-12-31 to '
                     '2022-12-13 (316 days), verified in the raw CSV (those fields are empty strings in the source, not a '
                     'download/parsing bug). sum_open_interest and sum_open_interest_value are populated throughout. '
                     'Never filled: consumers must dropna() per the column(s) they use.'
        }, indent=2))
    print(symbol, 'daily rows', len(daily), daily.index[0].date(), '->', daily.index[-1].date(),
          'missing days (no 5-min data that day):', missing_days, 'NaN rows:', int(daily.isna().any(axis=1).sum()), flush=True)
