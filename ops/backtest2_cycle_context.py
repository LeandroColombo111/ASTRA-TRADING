"""Halving cycle as CONTEXT instead of a switch: the bot keeps taking every signal, but in months [6, 18) after a halving it acts with more caution.
R1: fraction of normal size (exposure column). R2: stop/target/trailing distances multiplied (wider room; risk-based sizing then makes the
position smaller). Same caveat as ops/backtest2_cycle.py: the window was chosen after seeing the bot's bad periods, so on the two available cycles
the result is favourable by construction; ETH is the informative check. Writes reports/backtest2-v2/CYCLE_CONTEXT.md."""
from dataclasses import dataclass
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import build_sim, evaluate, summarize, engine_variant, chained_maxdd

CFG = json.loads(Path('configs/selected.json').read_text())
BASE, P, RISK = CFG['params'], HourlyParams(**CFG['params']), Risk(**CFG['risk'])
sim = build_sim(RISK)
HALVINGS = [pd.Timestamp(x, tz='UTC') for x in ('2016-07-09', '2020-05-11', '2024-04-20')]
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


@dataclass(frozen=True)
class CycleContextParams(HourlyParams):
    mode: str = 'size'      # 'size' | 'stops'
    factor: float = 0.5
    from_m: float = 6.
    to_m: float = 18.


def months_since_halving(index):
    m = np.full(len(index), np.nan)
    for h in HALVINGS:
        m = np.where(index >= h, (index - h) / pd.Timedelta(days=30.4375), m)
    return m


def context_signal(bars, p):
    base = features(bars, p)
    m = months_since_halving(bars.index)
    inside = (m >= p.from_m) & (m < p.to_m)
    o = base.copy()
    if p.mode == 'size':
        # factor x the trade's NORMAL risk-based exposure (same formula as engine.size), not an absolute exposure
        unit_risk = p.stop_atr * base['atr'].to_numpy() / bars.close.to_numpy() + (2 * RISK.fee_bps + RISK.slippage_bps) / 10000
        normal = np.minimum(RISK.fraction / unit_risk, RISK.max_exposure)
        o['exposure'] = np.where(inside, p.factor * normal, np.nan)   # NaN -> normal risk-based sizing outside the window
    else:
        o['atr'] = base['atr'].to_numpy() * np.where(inside, p.factor, 1.)
    return o


def load(sym):
    parts = []
    for f in (f'data/{sym}USDT-2020-1h.csv', f'data/{sym}USDT-1h.csv'):
        b = pd.read_csv(f, index_col='time', parse_dates=True)
        b.index = pd.to_datetime(b.index, utc=True)
        parts.append(b)
    b = pd.concat(parts)
    return b[~b.index.duplicated()].sort_index()


HEAD = ('| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |'
        '\n|---|---|---|---|---|---|---|---|')


def row(name, df):
    s = summarize(df)
    return (f"| {name} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | {s['negative']} | {pct(s['total_ret'])} | "
            f"{pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")


out('# Ciclo del halving como contexto (no como interruptor)\n')
out('El bot sigue tomando todas sus senales; entre los 6 y 18 meses despues de cada halving (2020-05-11 y 2024-04-20) actua con mas cautela. '
    '**R1** opera con una fraccion del tamano normal. **R2** aleja los stops y objetivos (el tamano baja solo, porque se dimensiona por riesgo). '
    'Valores fijados antes de correr, con vecinos. **Aviso:** la ventana se eligio mirando los malos periodos del bot, asi que en los dos ciclos disponibles '
    'el resultado esta favorecido por construccion; ETH es la verificacion informativa.\n')
wins = [(pd.Timestamp('2020-05-01', tz='UTC') + pd.Timedelta(days=90 * k), pd.Timestamp('2020-05-01', tz='UTC') + pd.Timedelta(days=90 * (k + 1))) for k in range(25)]
V = [(f'R1 tamano x{f}', CycleContextParams(**BASE, mode='size', factor=f)) for f in (0.33, 0.5, 0.75)]
V += [(f'R2 stops y objetivos x{f}', CycleContextParams(**BASE, mode='stops', factor=f)) for f in (1.25, 1.5, 2.0)]
for sym in ('BTC', 'ETH'):
    b = load(sym)
    w = [x for x in wins if x[1] <= b.index[-1]]
    out(f'\n## {sym} ({len(w)} ventanas de 90d, calentamiento 120d)\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), b, RISK, warmup=pd.Timedelta(days=120), windows=w)
    out(row('original', base))
    for name, par in V:
        out(row(name, evaluate(engine_variant(name, par, context_signal, sim, RISK), b, RISK, warmup=pd.Timedelta(days=120), windows=w)))
    sm = summarize(base)
    out(f"| HODL | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | {pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")
out('''
## Lectura

- **R1 (menos tamano en la fase): no mejora, solo escala el riesgo.** Achicar el tamano en los meses 6 a 18 baja la ganancia y la caida en proporcion, sin mejorar el Sharpe (BTC: 0.31 a 0.35
  contra 0.36; ganancia 66.0% a 71.5% contra 73.5%; caida encadenada 16.7% a 19.5% contra 21.3%). En ETH el efecto casi no existe. Es el mismo intercambio de siempre: menos riesgo por menos retorno.
- **R2 (mas margen en la fase): resultado inconsistente entre activos.** En BTC solo el valor 1.25 mejora con claridad (ganancia 100.6% contra 73.5%, Sharpe 0.45, caida 12.6%), pero sus vecinos empeoran:
  1.5 da 55.9% y 2.0 da 60.1%, ambos por debajo del original. Es un pico aislado. En ETH mejora de forma monotona (26.2%, 35.3%, 47.0% contra 22.4%), lo que coincide con lo visto antes: en ETH los stops
  anchos rinden mejor, y eso parece una propiedad del activo mas que del ciclo. Falla la regla de validacion cruzada.
- **Conclusion: no adoptar ninguna.** Darle el ciclo como contexto en vez de interruptor da un resultado menos malo que el interruptor, pero no supera al bot original de forma robusta. Suma 6 variantes (unas
  73 sobre BTC). Se corrigio en el camino un defecto de la primera version de R1 (fijaba exposicion absoluta en vez de una fraccion del tamano normal). `configs/selected.json` sin cambios.
''')
Path('reports/backtest2-v2/CYCLE_CONTEXT.md').write_text('\n'.join(lines) + '\n')
