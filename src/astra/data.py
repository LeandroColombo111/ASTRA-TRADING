"""Shared strict validation plus OKX-only downloads for Brief v2.

The original Binance import is preserved in legacy_data.py for archived audit
reproducibility. It is never used as a substitute in the v2 data path.
"""
from pathlib import Path
import re
import numpy as np
import pandas as pd


def validate(frame,frequency='1h',require_funding=True):
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError('Empty, duplicate or unsorted candles')
    if frame.index.tz is None:raise ValueError('Market timestamps must be timezone-aware')
    if not (frame.index.to_series().diff().dropna()==pd.Timedelta(frequency)).all():
        raise ValueError('Missing candles at required frequency')
    fields=['open','high','low','close']
    fields += [x for x in ['volume','quote_volume'] if x in frame]
    if require_funding:fields.append('funding')
    if not set(fields).issubset(frame.columns):raise ValueError('Missing market data fields')
    x=frame[fields]
    if not np.isfinite(x.to_numpy()).all():raise ValueError('Nonfinite market data')
    if (x[['open','high','low','close']]<=0).any().any():raise ValueError('Invalid prices')
    for v in ['volume','quote_volume']:
        if v in x and (x[v]<0).any():raise ValueError('Negative market volume')
    if ((x.high<x[['open','close','low']].max(axis=1))|(x.low>x[['open','close']].min(axis=1))).any():raise ValueError('Invalid OHLC')


def load(path,frequency='1h',require_funding=True):
    frame=pd.read_csv(path,index_col='time',parse_dates=True)
    frame.index=pd.to_datetime(frame.index,utc=True)
    validate(frame,frequency,require_funding)
    return frame


def download(start,end,directory,symbol='BTC-USDT-SWAP'):
    """Causal raw daily candles; funding/spread coverage is a separate hard gate."""
    from .v2_data import daily_history
    if not re.fullmatch(r'[A-Z0-9]+-USDT-SWAP',symbol):raise ValueError('Only OKX USDT SWAP symbols are supported')
    begin,finish=pd.Timestamp(start,tz='UTC'),pd.Timestamp(end,tz='UTC')
    if begin>=finish or finish>pd.Timestamp.now(tz='UTC').normalize():raise ValueError('Use a closed UTC daily interval')
    frame=daily_history(symbol,begin,finish,Path(directory))
    if frame is None:raise ValueError('No OKX history for symbol')
    validate(frame,'1d',require_funding=False)
    if not frame.index.equals(pd.date_range(begin,finish,freq='1D',inclusive='left')):raise ValueError('Incomplete OKX requested history; no proxy allowed')
    return Path(directory)/'daily'/f'{symbol}.csv'
