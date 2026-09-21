"""Halving-cycle awareness: gate v4_hourly ENTRIES by months since the last Bitcoin halving. Halving dates are public and known in advance (no look-ahead),
but which window to skip was chosen after seeing that the bot's bad periods (2021, 2024-25) fall 6-18 months after a halving, so on the two cycles in the
data the result is favourable BY CONSTRUCTION; the informative checks are ETH and any earlier cycle. Rule fixed before running: skip entries when
months since halving is in [6, 18); neighbours [3, 15) and [9, 21); control: trade ONLY inside [6, 18). Writes reports/backtest2-v2/CYCLE.md."""
from dataclasses import dataclass
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import build_sim, evaluate, summarize, engine_variant, chained_maxdd, HOUR

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
class CycleParams(HourlyParams):
    skip_from: float = 6.
    skip_to: float = 18.
    only_inside: bool = False


def months_since_halving(index):
    m = np.full(len(index), np.nan)
    for h in HALVINGS:
        m = np.where(index >= h, (index - h) / pd.Timedelta(days=30.4375), m)
    return m


def cycle_signal(bars, p):
    base = features(bars, p)
    m = months_since_halving(bars.index)
    inside = (m >= p.skip_from) & (m < p.skip_to)
    allow = inside if p.only_inside else ~inside
    out_ = base.copy()
    out_['signal'] = np.where(allow, base['signal'].to_numpy(), 0)
    return out_


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


out('# Ciclos de Bitcoin (halving): filtro de entradas\n')
out('Halvings usados: 2016-07-09 (solo para la fase inicial de 2020), 2020-05-11 y 2024-04-20; fechas publicas y conocidas de antemano, sin mirar el futuro. '
    '**Aviso:** la ventana a evitar (6 a 18 meses despues del halving) se eligio despues de ver que los malos periodos del bot (2021 y 2024-25) caen ahi, asi que en los '
    'dos ciclos disponibles el resultado es favorable por construccion. Lo que informa de verdad es ETH y, si se consiguen, ciclos anteriores.\n')
out('Ventanas de 90 dias desde 2020-05-01 (121 dias de calentamiento), serie Binance 2020-2026.\n')
wins = [(pd.Timestamp('2020-05-01', tz='UTC') + pd.Timedelta(days=90 * k), pd.Timestamp('2020-05-01', tz='UTC') + pd.Timedelta(days=90 * (k + 1))) for k in range(25)]
V = [('C1 evitar meses 6 a 18', CycleParams(**BASE, skip_from=6, skip_to=18)),
     ('C1 vecino: evitar meses 3 a 15', CycleParams(**BASE, skip_from=3, skip_to=15)),
     ('C1 vecino: evitar meses 9 a 21', CycleParams(**BASE, skip_from=9, skip_to=21)),
     ('Contraste: operar SOLO meses 6 a 18', CycleParams(**BASE, skip_from=6, skip_to=18, only_inside=True))]
for sym in ('BTC', 'ETH'):
    b = load(sym)
    end = b.index[-1]
    w = [x for x in wins if x[1] <= end]
    out(f'\n## {sym} ({len(w)} ventanas)\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), b, RISK, warmup=pd.Timedelta(days=120), windows=w)
    out(row('original', base))
    for name, par in V:
        out(row(name, evaluate(engine_variant(name, par, cycle_signal, sim, RISK), b, RISK, warmup=pd.Timedelta(days=120), windows=w)))
    sm = summarize(base)
    out(f"| HODL | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | {pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")
out('''
## Lectura

- **No mejora al bot, ni siquiera en los datos donde estaba favorecida.** En BTC (25 ventanas) evitar los meses 6 a 18 post-halving baja el Sharpe medio de 0.36 a 0.27
  y la ganancia total de 73.5% a 60.3%; los vecinos dan 63.5% y 67.1%, tambien menos que el original. Lo unico que mejora es el riesgo: la caida encadenada baja de 21.3% a
  14.8% y las ventanas negativas de 11 a 8. La mediana de Sharpe cae a 0.00 porque, al operar menos, muchas ventanas quedan sin trades.
- **En ETH empeora en todo** (ganancia 22.4% contra 12.9%; los vecinos 9.8% y 11.1%), asi que tampoco pasa la validacion cruzada. El contraste (operar solo en esa fase) es peor todavia
  (BTC +6.9%).
- **Por que:** la fase evitada ocupa cerca de 40% del tiempo y tambien contiene trades buenos (por ejemplo la alza de 2020-21, donde el bot gano). Evitarla se lleva ganancias junto con
  las perdidas, y el bot ya se adapta a la fase de forma indirecta con su filtro de tendencia.
- **Conclusion: no adoptar.** Como falla incluso donde estaba favorecida por construccion, no hace falta bajar ciclos anteriores (2017-2019) para una prueba fuera de muestra:
  no hay nada que confirmar. Suma 4 variantes al acumulado (unas 67 sobre BTC). `configs/selected.json` sin cambios.
''')
Path('reports/backtest2-v2/CYCLE.md').write_text('\n'.join(lines) + '\n')
