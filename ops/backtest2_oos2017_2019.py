"""Frozen v4_hourly on Binance SPOT BTCUSDT 2017-2019 (the 2018 bear market and the 2019 recovery), a cycle no search ever touched. No parameter is changed
or tuned here. Data: ops/download_binance_spot_2017_2019.py (checksum-verified). Differences from the perp series used elsewhere: spot prices, no funding
(zero), and 139 hourly candles missing in 12 real Binance maintenance holes that are filled with FLAT candles (previous close, zero volume) so the engine
can run; the trades that touch a hole are counted and reported. Writes reports/backtest2-v2/OUT_OF_SAMPLE_2017_2019.md."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import build_sim, evaluate, summarize, engine_variant, chained_maxdd, sharpe_from_equity, max_dd, HOUR

CFG = json.loads(Path('configs/selected.json').read_text())
P, RISK = HourlyParams(**CFG['params']), Risk(**CFG['risk'])
WARM = pd.Timedelta(days=120)  # indicators are stable from ~120d of history (reports/backtest2-v1/CORRECTION_2026-09-18.md), same as OUT_OF_SAMPLE_2020_2021
sim = build_sim(RISK)
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


raw = pd.read_csv('data/BTCUSDT-spot-2017-2019-1h.csv', index_col='time')
raw.index = pd.to_datetime(raw.index, format='mixed', utc=True)
# 43 real candles of 2018-02-09/11 sit on a grid shifted by 28m14s after a Binance outage. Labelling them by the hour would use information up to 28 minutes
# early, so they are DROPPED and the whole stretch is treated as one more hole (filled flat below).
off_grid = int(((raw.index.minute != 0) | (raw.index.second != 0)).sum())
raw = raw[(raw.index.minute == 0) & (raw.index.second == 0)]
assert not raw.index.duplicated().any()
full = pd.date_range(raw.index[0], raw.index[-1], freq='h')
holes = full.difference(raw.index)
bars = raw.reindex(full)
last_close = bars.close.ffill()
for c in ('open', 'high', 'low'):
    bars[c] = bars[c].fillna(last_close)
bars['close'] = last_close
bars['volume'] = bars.volume.fillna(0.)
bars['funding'] = 0.
assert (bars.index.to_series().diff().dropna() == HOUR).all() and np.isfinite(bars.to_numpy()).all()
first = bars.index[0] + WARM
n_win = int((bars.index[-1] + HOUR - first) / pd.Timedelta(days=90))
wins = [(first + pd.Timedelta(days=90 * k), first + pd.Timedelta(days=90 * (k + 1))) for k in range(n_win)]

out('# Prueba con 2017-2019 (spot de Binance): configuracion congelada\n')
out(f'Binance spot BTCUSDT, {bars.index[0].date()} a {bars.index[-1].date()} (el contrato perpetuo no existia antes de septiembre de 2019, asi que se usa spot; '
    'sin funding). Ningun parametro se cambia. 120 dias de calentamiento y ventanas de 90 dias, como en OUT_OF_SAMPLE_2020_2021.md. '
    f'**Aproximaciones:** (1) {len(holes)} velas horarias faltan en {int(pd.Series(holes).diff().ne(HOUR).sum())} pausas reales de Binance '
    f'(la mas larga, {int(pd.Series(holes).groupby(pd.Series(holes).diff().ne(HOUR).cumsum()).size().max())} h) y se rellenan con velas planas (precio anterior, volumen cero); '
    f'no se inventa ningun movimiento. (2) {off_grid} velas reales de febrero de 2018 tienen la grilla corrida 28 minutos tras una pausa de Binance; se descartan '
    '(etiquetarlas por hora usaria informacion hasta 28 minutos antes) y ese tramo cuenta como hueco.\n')

df = evaluate(engine_variant('o', P, features, sim, RISK), bars, RISK, warmup=WARM, windows=wins)
s = summarize(df)
out('## Por ventanas\n')
out('| ventanas | Sharpe media / mediana | ganancia total | peor ventana | DD encadenado | % en mercado | HODL total | HODL peor ventana |')
out('|---|---|---|---|---|---|---|---|')
out(f"| {s['n']} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | "
    f"{pct(s['time_in_market'])} | {pct(s['hodl_total_ret'])} | {pct(s['hodl_worst_window'])} |")
out('\n| inicio | Sharpe | ganancia | HODL | trades |')
out('|---|---|---|---|---|')
for _, r in df.iterrows():
    out(f"| {r.start.date()} | {r.sharpe:.2f} | {pct(r.ret)} | {pct(r.hodl_ret)} | {int(r.trades)} |")

# one continuous pass over the whole period, for an annualized figure and the trades that touch a hole
eq, tr, st = sim.run(bars, features(bars, P), P, RISK, start=first, end=bars.index[-1] + HOUR)
years = (bars.index[-1] + HOUR - first) / pd.Timedelta(days=365.25)
total = eq.iloc[-1] / RISK.capital - 1
hold = bars.close.iloc[-1] / bars.close.loc[first:].iloc[0] - 1
touch = sum(1 for t in tr if ((holes >= pd.Timestamp(t['entry_time'])) & (holes <= pd.Timestamp(t['exit_time']))).any())
out('\n## Corrida continua\n')
out('| periodo | anios | ganancia total | **por anio (compuesto)** | Sharpe | DD max | trades | trades/anio | trades que tocan un hueco | HODL total | HODL por anio |')
out('|---|---|---|---|---|---|---|---|---|---|---|')
out(f"| {first.date()} a {bars.index[-1].date()} | {years:.2f} | {pct(total)} | **{pct((1 + total) ** (1 / years) - 1)}** | {sharpe_from_equity(eq, RISK.capital):.2f} | "
    f"{pct(max_dd(eq, RISK.capital))} | {len(tr)} | {len(tr) / years:.0f} | {touch} | {pct(hold)} | {pct((1 + hold) ** (1 / years) - 1)} |")
out('\nLimites: spot en vez de perpetuo (sin funding porque el perpetuo no existia), 13 huecos rellenados con velas planas, y un solo '
    'activo en un solo ciclo. Sirve para ver si el bot se rompe en un mercado bajista largo, no para estimar un Sharpe con precision.')
from astra.forward_test import psr
daily = eq.copy(); daily.index = daily.index - pd.Timedelta(nanoseconds=1)
daily = daily.resample('1D').last().dropna()
ret = daily.pct_change().fillna(daily.iloc[0] / RISK.capital - 1).to_numpy()
out(f'\nConfianza estadistica: PSR (probabilidad de que el Sharpe real sea > 0, sin descuento por pruebas multiples) = {psr(ret):.2f} con {len(tr)} operaciones. '
    'Con tan pocas operaciones y una sola serie, es una pista y no una prueba.')
Path('reports/backtest2-v2/OUT_OF_SAMPLE_2017_2019.md').write_text('\n'.join(lines) + '\n')
