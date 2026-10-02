"""Download Binance SPOT BTCUSDT 1h klines for 2017-08 .. 2019-12 (futures archives start 2019-09/2020-01, so spot is the only source for the 2017-2019 cycle)
verified by the archive's published SHA256. Gaps are never filled: a month with missing candles is reported and the series is split there.
Writes NEW files (data/BTCUSDT-spot-2017-2019-1h.csv + manifest); existing data files are not touched. Spot has no funding: the column is zero."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import sys

import pandas as pd
import requests

DATA = Path('data')
CACHE = DATA / 'raw-spot-2017-2019'
CACHE.mkdir(parents=True, exist_ok=True)
BASE = 'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h'


def get(url):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


months = pd.date_range('2017-08-01', '2019-12-01', freq='MS').strftime('%Y-%m')
bars, manifest = [], []
for m in months:
    stem = f'BTCUSDT-1h-{m}'
    url = f'{BASE}/{stem}.zip'
    path, check = CACHE / f'{stem}.zip', CACHE / f'{stem}.zip.CHECKSUM'
    if not check.exists():
        check.write_bytes(get(url + '.CHECKSUM'))
    expected = check.read_text().split()[0]
    if not path.exists() or sha256(path.read_bytes()).hexdigest() != expected:
        payload = get(url)
        if sha256(payload).hexdigest() != expected:
            raise ValueError(f'Checksum mismatch: {url}')
        path.write_bytes(payload)
    with ZipFile(BytesIO(path.read_bytes())) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None)
    df = df[pd.to_numeric(df[0], errors='coerce').notna()].iloc[:, :6].astype(float)
    df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
    unit = 'us' if df['time'].iloc[0] > 1e14 else 'ms'
    df.index = pd.to_datetime(df.pop('time'), unit=unit, utc=True)
    bars.append(df)
    manifest.append({'url': url, 'sha256': expected, 'rows': len(df)})

frame = pd.concat(bars).sort_index()
frame = frame[~frame.index.duplicated()]
frame = frame.loc[frame.index < pd.Timestamp('2020-01-01', tz='UTC')]
frame['funding'] = 0.
full = pd.date_range(frame.index[0], frame.index[-1], freq='h')
missing = full.difference(frame.index)
print('rows', len(frame), frame.index[0], '->', frame.index[-1], '| missing hourly candles:', len(missing))
if len(missing):
    runs = pd.Series(missing).diff().ne(pd.Timedelta(hours=1)).cumsum()
    for _, g in pd.Series(missing).groupby(runs):
        print('  hole', g.iloc[0], '->', g.iloc[-1], f'({len(g)}h)')
bad = ((frame.high < frame[['open', 'close', 'low']].max(axis=1)) | (frame.low > frame[['open', 'close']].min(axis=1))).sum()
print('invalid OHLC rows:', int(bad), '| zero-volume candles:', int((frame.volume == 0).sum()))
path = DATA / 'BTCUSDT-spot-2017-2019-1h.csv'
frame.to_csv(path, index_label='time')
(DATA / 'BTCUSDT-spot-2017-2019-manifest.json').write_text(json.dumps({
    'source': 'Binance SPOT BTCUSDT (no perpetual existed before 2019-09); NOT OKX data, no funding', 'rows': len(frame),
    'missing_hours': len(missing), 'csv_sha256': sha256(path.read_bytes()).hexdigest(), 'archives': manifest}, indent=2))
