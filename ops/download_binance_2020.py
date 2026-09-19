"""Download Binance USD-M 1h klines + funding for 2020 (the archives start 2020-01) (verified by the archive's published SHA256; gaps are never filled).
Writes NEW files (data/<SYMBOL>-2020-1h.csv + manifest); existing data files are not touched."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import json
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.legacy_data import archive, validate

DATA = Path('data')
CACHE = DATA / 'raw-2020'
CACHE.mkdir(parents=True, exist_ok=True)
PLAN = {'BTCUSDT': ('2020-01-01', '2021-01-01'), 'ETHUSDT': ('2020-01-01', '2021-01-01')}

for symbol, (start, end) in PLAN.items():
    start, end = pd.Timestamp(start, tz='UTC'), pd.Timestamp(end, tz='UTC')
    months = pd.date_range(start, end, freq='MS', inclusive='left').strftime('%Y-%m')
    jobs = [(k, m) for m in months for k in ('klines', 'fundingRate')]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda km: archive(km[0], km[1], CACHE, symbol), jobs))
    bars, funds, manifest = [], [], []
    for (kind, month), (df, meta) in zip(jobs, results):
        manifest.append(meta)
        if kind == 'klines':
            df = df[pd.to_numeric(df[0], errors='coerce').notna()].iloc[:, :6].astype(float)
            df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
            df.index = pd.to_datetime(df.pop('time'), unit='ms', utc=True)
            bars.append(df)
        else:
            df.index = pd.to_datetime(df['calc_time'], unit='ms', utc=True)
            funds.append(df['last_funding_rate'].astype(float))
    frame = pd.concat(bars).sort_index()
    funding = pd.concat(funds).sort_index()
    frame['funding'] = funding.groupby(funding.index.floor('h')).sum().reindex(frame.index, fill_value=0.)
    frame = frame.loc[(frame.index >= start) & (frame.index < end)]
    validate(frame)
    assert len(frame) == int((end - start).total_seconds() / 3600), 'archive did not cover the requested dates'
    path = DATA / f'{symbol}-2020-1h.csv'
    frame.to_csv(path, index_label='time')
    (DATA / f'{symbol}-2020-manifest.json').write_text(json.dumps({
        'source': 'Binance USD-M futures, proxy for OKX; NOT OKX data', 'start': str(start), 'end_exclusive': str(end),
        'rows': len(frame), 'csv_sha256': sha256(path.read_bytes()).hexdigest(), 'archives': manifest}, indent=2))
    print(symbol, len(frame), 'rows', frame.index[0], '->', frame.index[-1], 'funding nonzero', int((frame.funding != 0).sum()), flush=True)
