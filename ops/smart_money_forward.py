"""Segunda prueba en vivo (docs/FORWARD_TEST_SMART_MONEY.md): replay del motor de backtest ya validado, alimentado
con precio y posicionamiento REALES y actualizados de Binance (publico, sin credenciales). No usa la cuenta OKX ni
la VM del bot. Stateless y reproducible: cada corrida reconstruye todo desde el archivo historico + lo que falte
hasta ahora, nunca depende de un estado previo que se pueda corromper. Escribe reports/forward_smart_money/state.json
y agrega una linea a reports/forward_smart_money/log.csv. Uso: python3 ops/smart_money_forward.py"""
from pathlib import Path
from datetime import datetime, timezone
import json
import sys

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.backtest2.research import build_sim, HOUR, WARMUP, sharpe_from_equity, max_dd
from astra.backtest2.exposure_strategies import SmartMoneyParams, smart_money_signal

OUT = Path('reports/forward_smart_money')
OUT.mkdir(parents=True, exist_ok=True)
PRE_REG_START = pd.Timestamp('2026-10-01 23:00', tz='UTC')
DIVERGENCE_MIN = 1.1
CFG = json.loads(Path('configs/selected.json').read_text())
RISK = Risk(**CFG['risk'])
PARAMS = SmartMoneyParams(**CFG['params'], divergence_min=DIVERGENCE_MIN, symbol='BTC')
sim = build_sim(RISK)


def fetch_live_klines(start_ms):
    rows, url = [], 'https://fapi.binance.com/fapi/v1/klines'
    while True:
        r = requests.get(url, params={'symbol': 'BTCUSDT', 'interval': '1h', 'startTime': start_ms, 'limit': 1000}, timeout=30)
        r.raise_for_status()
        page = r.json()
        rows.extend(page)
        if len(page) < 1000:
            break
        start_ms = page[-1][0] + 1
    return rows


def load_price():
    parts = []
    for f in ('data/BTCUSDT-2020-1h.csv', 'data/BTCUSDT-1h.csv'):
        b = pd.read_csv(f, index_col='time', parse_dates=True)
        b.index = pd.to_datetime(b.index, utc=True)
        parts.append(b)
    hist = pd.concat(parts)
    hist = hist[~hist.index.duplicated()].sort_index()
    next_hour = hist.index[-1] + HOUR
    live_rows = fetch_live_klines(int(next_hour.timestamp() * 1000))
    if live_rows:
        live = pd.DataFrame([{'time': pd.Timestamp(r[0], unit='ms', tz='UTC'), 'open': float(r[1]), 'high': float(r[2]),
                              'low': float(r[3]), 'close': float(r[4]), 'volume': float(r[5]), 'funding': 0.}
                             for r in live_rows if pd.Timestamp(r[0], unit='ms', tz='UTC') + HOUR <= pd.Timestamp.now(tz='UTC')])
        live = live.set_index('time')
        hist = pd.concat([hist, live])
        hist = hist[~hist.index.duplicated()].sort_index()
    assert (hist.index.to_series().diff().dropna() == HOUR).all(), 'gap in the joined BTC price series'
    return hist


def load_metrics():
    hist = pd.read_csv('data/BTCUSDT-metrics-daily.csv', index_col='time', parse_dates=True)
    top = requests.get('https://fapi.binance.com/futures/data/topLongShortPositionRatio',
                       params={'symbol': 'BTCUSDT', 'period': '1d', 'limit': 30}, timeout=30).json()
    acct = requests.get('https://fapi.binance.com/futures/data/globalLongShortAccountRatio',
                        params={'symbol': 'BTCUSDT', 'period': '1d', 'limit': 30}, timeout=30).json()
    top_s = pd.Series({pd.Timestamp(r['timestamp'], unit='ms', tz='UTC').normalize(): float(r['longShortRatio']) for r in top})
    acct_s = pd.Series({pd.Timestamp(r['timestamp'], unit='ms', tz='UTC').normalize(): float(r['longShortRatio']) for r in acct})
    live = pd.DataFrame({'sum_toptrader_long_short_ratio': top_s, 'count_long_short_ratio': acct_s})
    live = live[~live.index.isin(hist.index)]
    full = pd.concat([hist, live]).sort_index()
    return full[~full.index.duplicated()]


def main():
    bars = load_price()
    metrics = load_metrics()
    # smart_money_signal reads metrics via exposure_strategies.load_binance_metrics(symbol), which only knows the
    # static archive file; for this run it's pointed at the live-extended frame built above instead.
    import astra.backtest2.exposure_strategies as es
    es.load_binance_metrics = lambda symbol: metrics
    sig = smart_money_signal(bars, PARAMS)
    start = max(bars.index[0] + WARMUP, PRE_REG_START)
    end = bars.index[-1] + HOUR
    if end <= start:
        # Pre-registration just happened and the next candle has not closed yet: genuinely no forward evidence
        # exists. Report that plainly instead of asking the engine for an empty range.
        eq = pd.Series([RISK.capital], index=[start])
        trades, state = [], {'qty': 0.}
    else:
        eq, trades, state = sim.run(bars, sig, PARAMS, RISK, start=start, end=end)
    result = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'pre_registration_start': str(PRE_REG_START),
        'divergence_min': DIVERGENCE_MIN,
        'last_bar': str(bars.index[-1]),
        'forward_days': round((bars.index[-1] + HOUR - PRE_REG_START) / pd.Timedelta(days=1), 2),
        'equity_now': float(eq.iloc[-1]) if len(eq) else RISK.capital,
        'return_pct': float(eq.iloc[-1] / RISK.capital - 1) * 100 if len(eq) else 0.,
        'sharpe': sharpe_from_equity(eq, RISK.capital) if len(eq) else 0.,
        'max_drawdown_pct': max_dd(eq, RISK.capital) * 100 if len(eq) else 0.,
        'trades': len(trades),
        'open_position': state.get('qty', 0.) != 0.,
        'last_trades': trades[-3:],
    }
    (OUT / 'state.json').write_text(json.dumps(result, indent=2, default=str))
    log_line = (f"{result['generated_at_utc']},{result['last_bar']},{result['forward_days']},"
               f"{result['equity_now']:.2f},{result['return_pct']:.3f},{result['sharpe']:.3f},"
               f"{result['max_drawdown_pct']:.3f},{result['trades']}\n")
    log = OUT / 'log.csv'
    if not log.exists():
        log.write_text('generated_at_utc,last_bar,forward_days,equity_now,return_pct,sharpe,max_drawdown_pct,trades\n')
    with open(log, 'a') as f:
        f.write(log_line)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
