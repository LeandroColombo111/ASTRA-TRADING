"""Triple barrier with dynamic volatility: does a longer-memory volatility estimate improve the bot's barriers?
The bot already IS a triple barrier (stop = stop_atr * ATR24, target = reward * stop distance, time limit = max_hours);
this tests the volatility estimator behind it. Writes reports/backtest2-v2/TRIPLE_BARRIER.md."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import (load_bars, build_sim, evaluate, summarize, engine_variant, chained_maxdd)
from astra.backtest2.exposure_strategies import BlendVolParams, blendvol_signal

CFG = json.loads(Path('configs/selected.json').read_text())
BASE, P, RISK = CFG['params'], HourlyParams(**CFG['params']), Risk(**CFG['risk'])
SYMS = ['BTC', 'ETH', 'SOL']
DATA = {s: load_bars(s) for s in SYMS}
sim = build_sim(RISK)
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


out('# Triple barrera con volatilidad dinamica\n')
out('## 1. Lo que el bot ya hace\n')
out('Stop = `stop_atr` (3) x ATR de 24h; objetivo = `reward` (3) x la distancia del stop; limite de tiempo = `max_hours` (480h); '
    'ademas trailing y salida por cambio de tendencia. Distancia real del stop como % del precio al momento de las senales de entrada:\n')
out('| activo | mediana | p10 | p90 |')
out('|---|---|---|---|')
for s in SYMS:
    b = DATA[s]
    f = features(b, P)
    d = (f.atr * P.stop_atr / b.close)[f.signal != 0].dropna()
    out(f'| {s} | {pct(d.median())} | {pct(d.quantile(.1))} | {pct(d.quantile(.9))} |')

out('\n## 2. Memoria de la volatilidad: que tan lejos llega\n')
out('Correlacion entre la volatilidad de hoy y la de N dias despues (vol realizada de 7 dias contra la de los 7 dias que empiezan N dias despues) y entre |retorno| de un dia y el de N dias despues:\n')
out('| activo | vol 7d, +7d | +30d | +60d | \\|ret\\| diario, +1d | +20d | +60d |')
out('|---|---|---|---|---|---|---|')
for s in SYMS:
    r = np.log(DATA[s].close).diff().resample('1D').sum()
    rv = r.rolling(7).std()
    a = r.abs()
    out(f'| {s} | ' + ' | '.join(f'{rv.corr(rv.shift(-n)):.2f}' for n in (7, 30, 60)) + ' | '
        + ' | '.join(f'{a.corr(a.shift(-n)):.2f}' for n in (1, 20, 60)) + ' |')

HEAD = ('| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | '
        'DD encadenado | % en mercado |\n|---|---|---|---|---|---|---|---|')


def row(name, df):
    s = summarize(df)
    return (f"| {name} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | {s['negative']} | "
            f"{pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")


out('\n## 3. Barreras con estimador de volatilidad de mayor memoria (valores fijos y vecinos; 14 ventanas, warmup 250d)\n')
out('Hipotesis fijadas antes de correr (multiplicos stop/objetivo/tiempo de produccion, sin tocar):\n')
out('- **T1 memoria mas larga:** ATR de 168h (7d), con vecinos 72h y 720h, en lugar de 24h.')
out('- **T2 pronostico mezclado:** distancia = sqrt(w * ATR24^2 + (1-w) * ATR720^2), w=0.5 y vecinos 0.3/0.7. Estructura tipo GARCH(1,1): '
    'la volatilidad se agrupa a corto plazo y revierte a su nivel de largo plazo.\n')
V = [(f'T1 ATR {n}h', HourlyParams(**{**BASE, 'atr_period': n}), features) for n in (72, 168, 720)]
V += [(f'T2 mezcla w={w}', BlendVolParams(**BASE, blend_w=w), blendvol_signal) for w in (0.3, 0.5, 0.7)]
for s in SYMS:
    out(f'\n**{s}**\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), DATA[s], RISK)
    out(row('original (ATR 24h)', base))
    for name, par, fn in V:
        out(row(name, evaluate(engine_variant(name, par, fn, sim, RISK), DATA[s], RISK)))
    sm = summarize(base)
    out(f"| HODL | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | "
        f"{pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")
Path('reports/backtest2-v2/TRIPLE_BARRIER.md').write_text('\n'.join(lines) + '\n')
