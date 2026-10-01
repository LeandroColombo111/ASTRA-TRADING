"""Segunda prueba en vivo (docs/FORWARD_TEST_SMART_MONEY.md): replay del motor de backtest ya validado sobre datos reales
de Binance USD-M (BTCUSDT), recalculado desde cero en cada corrida.

Por que los ARCHIVOS y no la API en vivo: fapi.binance.com devuelve HTTP 451 desde IPs de EE.UU. (la VM esta en Iowa) y
el entorno de las rutinas en la nube lo bloquea; data.binance.vision (archivos publicos, con checksum) responde desde
ambos. Los archivos diarios de un dia D aparecen despues de que D termina, y el filtro ya usaba el dato de D recien
desde D+1 (ver exposure_strategies._causal_daily), asi que el retraso de ~1 dia coincide con la regla del backtest.

Sin estado que se corrompa: cada corrida baja (y cachea, verificando checksum) lo que falta, arma la serie completa
y vuelve a correr el simulador desde el inicio de la medicion. El resultado se REESCRIBE en <out-dir>/state.json (no se
commitea nada). Si falta un dia en el medio de la serie de precios, la corrida falla fuerte y deja el archivo anterior
intacto: nunca se rellena un hueco.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from .backtest2 import exposure_strategies as es
from .backtest2.research import WARMUP, build_sim, max_dd, sharpe_from_equity
from .engine import Risk

BASE = 'https://data.binance.vision/data/futures/um'
SYMBOL = 'BTCUSDT'
PRE_REG_START = pd.Timestamp('2026-10-01 23:00', tz='UTC')
DIVERGENCE_MIN = 1.1
HOUR = pd.Timedelta(hours=1)
METRIC_COLUMNS = ['sum_toptrader_long_short_ratio', 'count_long_short_ratio']
METRICS_LOOKBACK_DAYS = 5  # the causal align never reads further back than 2 days; a few extra for safety


def _get(url, retries=4):
    """Bytes of url, or None on 404 (the archive does not exist (yet)). Retries transport errors and 5xx/429."""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=40)
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 404:
            return None
        if r.status_code >= 500 or r.status_code == 429:
            if attempt == retries - 1:
                r.raise_for_status()
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.content


class Archive:
    """Checksum-verified, disk-cached access to data.binance.vision. fetch() returns the zip bytes or None when absent."""

    def __init__(self, cache_dir):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    def fetch(self, rel_path):
        zip_path = self.cache / rel_path.replace('/', '__')
        check_path = zip_path.with_name(zip_path.name + '.CHECKSUM')
        if zip_path.exists() and check_path.exists():
            expected = check_path.read_text().split()[0]
            data = zip_path.read_bytes()
            if hashlib.sha256(data).hexdigest() == expected:
                return data
        checksum = _get(f'{BASE}/{rel_path}.CHECKSUM')
        if checksum is None:
            return None
        payload = _get(f'{BASE}/{rel_path}')
        if payload is None:
            return None
        expected = checksum.decode().split()[0]
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError(f'Checksum mismatch: {rel_path}')
        zip_path.write_bytes(payload)
        check_path.write_bytes(checksum)
        return payload


def parse_klines(raw_zip):
    """OHLCV frame (UTC index) from a Binance klines zip. Tolerates a header row and ms/us open_time."""
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None)
    df = df[pd.to_numeric(df[0], errors='coerce').notna()].iloc[:, :6].astype(float)
    df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume']
    t = df.pop('open_time').astype('int64')
    unit = 'us' if int(t.iloc[0]) > 10 ** 14 else 'ms'
    df.index = pd.to_datetime(t, unit=unit, utc=True)
    return df


def _month_days(year, month):
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def load_bars(archive, first_day, last_day, today):
    """Hourly OHLCV for first_day..last_day (inclusive), complete months from the monthly archive when published and the
    daily archives otherwise. Days not published yet at the END of the range just end the series; a hole
    anywhere before the last published day raises (never filled)."""
    frames = []
    y, m = first_day.year, first_day.month
    while (y, m) <= (last_day.year, last_day.month):
        month_start, month_end = _month_days(y, m)
        raw = None
        if month_end < today:
            raw = archive.fetch(f'monthly/klines/{SYMBOL}/1h/{SYMBOL}-1h-{y}-{m:02d}.zip')
        if raw is not None:
            frames.append(parse_klines(raw))
        else:
            d = max(month_start, first_day)
            while d <= min(month_end, last_day):
                day_raw = archive.fetch(f'daily/klines/{SYMBOL}/1h/{SYMBOL}-1h-{d}.zip')
                if day_raw is not None:
                    frames.append(parse_klines(day_raw))
                d += timedelta(days=1)  # a missing day is judged below: a missing TAIL is fine, a hole is not
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    if not frames:
        raise ValueError('no kline archives available for the requested range')
    bars = pd.concat(frames).sort_index()
    bars = bars[~bars.index.duplicated()]
    bars = bars.loc[pd.Timestamp(first_day, tz='UTC'):pd.Timestamp(last_day, tz='UTC') + pd.Timedelta(hours=23)]
    if bars.empty or bars.index[0] != pd.Timestamp(first_day, tz='UTC'):
        raise ValueError(f'the BTC hourly series does not start at {first_day}: refusing to shorten the warmup window')
    gaps = bars.index.to_series().diff().dropna()
    if not (gaps == HOUR).all():
        bad = gaps[gaps != HOUR].index[0]
        raise ValueError(f'gap in the BTC hourly series at {bad}: refusing to fill it')
    return bars


def load_funding(archive, bars, today):
    """Real funding for months whose monthly archive exists; zeros elsewhere (the in-progress month, documented
    approximation). Same aggregation as legacy_data: settlements floored to the hour, summed."""
    funding = []
    seen = set()
    for ts in bars.index[::24]:
        key = (ts.year, ts.month)
        if key in seen:
            continue
        seen.add(key)
        _, month_end = _month_days(*key)
        if month_end >= today:
            continue
        raw = archive.fetch(f'monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-{key[0]}-{key[1]:02d}.zip')
        if raw is None:
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]))
        s = df['last_funding_rate'].astype(float)
        s.index = pd.to_datetime(df['calc_time'], unit='ms', utc=True)
        funding.append(s)
    if not funding:
        return pd.Series(0., index=bars.index)
    f = pd.concat(funding).sort_index()
    return f.groupby(f.index.floor('h')).sum().reindex(bars.index, fill_value=0.)


def load_metrics(archive, first_day, last_day):
    """Daily positioning frame: the LAST 5-minute snapshot of each UTC day (as in data/<SYM>-metrics-daily.csv). Days with
    no archive are simply absent (the causal align then reads them as unavailable, never as a guessed value)."""
    rows = []
    d = first_day
    while d <= last_day:
        raw = archive.fetch(f'daily/metrics/{SYMBOL}/{SYMBOL}-metrics-{d}.zip')
        if raw is not None:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                df = pd.read_csv(z.open(z.namelist()[0]))
            df['create_time'] = pd.to_datetime(df['create_time'], utc=True)
            rows.append(df.set_index('create_time')[METRIC_COLUMNS].resample('1D').last())
        d += timedelta(days=1)
    if not rows:
        return pd.DataFrame(columns=METRIC_COLUMNS, dtype=float)
    return pd.concat(rows).sort_index()


def _write_atomic(path, text):
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(text)
    os.replace(tmp, path)


def run(out_dir, pre_reg_start=PRE_REG_START, config='configs/selected.json', archive=None, now=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    archive = archive or Archive(out / 'cache')
    now = now or pd.Timestamp.now(tz='UTC')
    today = now.date()
    cfg = json.loads(Path(config).read_text())
    risk = Risk(**cfg['risk'])
    params = es.SmartMoneyParams(**cfg['params'], divergence_min=DIVERGENCE_MIN, symbol='BTC')
    sim = build_sim(risk)

    fetch_from = (pre_reg_start - WARMUP).date()
    yesterday = today - timedelta(days=1)
    bars = load_bars(archive, fetch_from, yesterday, today)
    bars['funding'] = load_funding(archive, bars, today)
    metrics = load_metrics(archive, (pre_reg_start - pd.Timedelta(days=METRICS_LOOKBACK_DAYS)).date(), yesterday)

    # smart_money_signal reads positioning through exposure_strategies.load_binance_metrics(symbol), which normally
    # points at the local archive CSV; for this run it is pointed at the frame built above.
    original_loader = es.load_binance_metrics
    es.load_binance_metrics = lambda symbol: metrics
    try:
        signal = es.smart_money_signal(bars, params)
    finally:
        es.load_binance_metrics = original_loader

    start = max(bars.index[0] + WARMUP, pre_reg_start)
    end = bars.index[-1] + HOUR
    if end <= start:
        # Pre-registration just happened and no complete day after it is published yet: no forward evidence exists.
        eq, trades, state = pd.Series([risk.capital], index=[start]), [], {'qty': 0.}
    else:
        eq, trades, state = sim.run(bars, signal, params, risk, start=start, end=end)
    daily = eq.resample('1D').last().dropna()
    result = {
        'generated_at_utc': now.isoformat(),
        'pre_registration_start': str(pre_reg_start),
        'divergence_min': DIVERGENCE_MIN,
        'data_through': str(bars.index[-1] + HOUR),
        'forward_days': round(max((end - pre_reg_start) / pd.Timedelta(days=1), 0.), 2),
        'equity_now': float(eq.iloc[-1]),
        'return_pct': float(eq.iloc[-1] / risk.capital - 1) * 100,
        'sharpe': sharpe_from_equity(eq, risk.capital) if len(eq) > 1 else 0.,
        'max_drawdown_pct': max_dd(eq, risk.capital) * 100,
        'trades': len(trades),
        'open_position': bool(state.get('qty', 0.)),
        'trade_list': trades,
        'equity_daily': {str(k.date()): round(float(v), 2) for k, v in daily.items()},
        'metrics_days_available': int(metrics.dropna().shape[0]),
    }
    _write_atomic(out / 'state.json', json.dumps(result, indent=2, default=str))
    log = out / 'log.csv'
    if not log.exists():
        log.write_text('generated_at_utc,data_through,forward_days,equity_now,return_pct,sharpe,max_drawdown_pct,trades\n')
    with open(log, 'a') as f:
        f.write(f"{result['generated_at_utc']},{result['data_through']},{result['forward_days']},"
                f"{result['equity_now']:.2f},{result['return_pct']:.3f},{result['sharpe']:.3f},"
                f"{result['max_drawdown_pct']:.3f},{result['trades']}\n")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out-dir', required=True, help='where state.json, log.csv and the download cache live (never committed)')
    ap.add_argument('--config', default='configs/selected.json')
    ap.add_argument('--pre-reg-start', default=None, help='TESTING ONLY; the VM wrapper never passes it (the frozen value is in the code)')
    args = ap.parse_args(argv)
    start = pd.Timestamp(args.pre_reg_start, tz='UTC') if args.pre_reg_start else PRE_REG_START
    result = run(args.out_dir, pre_reg_start=start, config=args.config)
    print(json.dumps({k: v for k, v in result.items() if k not in ('trade_list', 'equity_daily')}, indent=2, default=str))


if __name__ == '__main__':
    main()
