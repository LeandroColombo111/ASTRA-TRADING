"""Dynamic time barrier: per-trade time limit scaled by the volatility regime. Writes reports/backtest2-v2/TIME_BARRIER.md.
Same rules as the other research scripts (fixed params, warmup 250d, neighbours, ETH/SOL, HODL alongside)."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import (WARMUP, HOUR, load_bars, build_sim, evaluate, summarize, engine_variant, chained_maxdd)
from astra.backtest2.exposure_strategies import DynTimeParams, dyntime_signal

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


out('# Limite de tiempo dinamico\n')
out('## 1. Cuanto pesa hoy el limite de tiempo (bot original, corrida continua, sin cortes)\n')
out('| activo | trades | salen por stop | por objetivo | por tendencia o tiempo | duracion mediana (h) | trades con >= 480h |')
out('|---|---|---|---|---|---|---|')
for s in SYMS:
    b = DATA[s]
    start = b.index[0] + WARMUP
    _, tr, _ = sim.run(b, features(b, P), P, RISK, start=start, end=b.index[-1] + HOUR)
    hrs = np.array([(pd.Timestamp(t['exit_time']) - pd.Timestamp(t['entry_time'])) / HOUR for t in tr])
    rs = pd.Series([t['reason'] for t in tr]).value_counts()
    out(f"| {s} | {len(tr)} | {rs.get('stop', 0)} | {rs.get('target', 0)} | {rs.get('anchor_or_timeout', 0)} | "
        f"{np.median(hrs):.0f} | {(hrs >= 480).sum()} |")

HEAD = ('| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | '
        'DD encadenado | % en mercado |\n|---|---|---|---|---|---|---|---|')


def row(name, df):
    s = summarize(df)
    return (f"| {name} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | {s['negative']} | "
            f"{pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")


out('\n## 2. Limite dinamico (14 ventanas de 90d, warmup 250d, valores fijos y vecinos)\n')
out('Hipotesis fijadas antes de correr. Limite = 480h x ratio^(-gamma), ratio = vol de 7d / vol de 60d, acotado a [240h, 960h]; '
    'stops y objetivos sin tocar.\n')
out('- **D1 (gamma > 0):** volatilidad alta acorta el limite, calma lo alarga. Justificacion: el clustering dura 10 a 20 dias, '
    'en un regimen agitado la tesis del trade se resuelve antes; en calma la tendencia necesita mas tiempo.')
out('- **D2 (gamma < 0), contraste:** el efecto opuesto.\n')
V = [(f'D1 gamma={g}', DynTimeParams(**BASE, gamma=g)) for g in (0.5, 1.0, 1.5)]
V += [(f'D2 gamma={-g}', DynTimeParams(**BASE, gamma=-g)) for g in (0.5, 1.0, 1.5)]
for s in SYMS:
    out(f'\n**{s}**\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), DATA[s], RISK)
    out(row('original (480h fijo)', base))
    for name, par in V:
        out(row(name, evaluate(engine_variant(name, par, dyntime_signal, sim, RISK), DATA[s], RISK)))
    sm = summarize(base)
    out(f"| HODL | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | "
        f"{pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")
out('''
## 3. Conclusiones

- **El limite de tiempo no actua.** En la corrida continua los trades duran 22 a 28 horas de mediana y solo 1 de 104
  (BTC), 0 de 91 (ETH) y 0 de 98 (SOL) llegan a las 480h. Casi todo cierra por stop (71% a 78%) o por objetivo (22% a 29%).
  Hacer dinamico un limite que casi nunca se alcanza no puede cambiar el resultado.
- **Resultado medido:** ETH y SOL identicos al original en las 6 variantes; BTC cambia en +-7 puntos de ganancia total por
  un unico trade (49.4% a 57.0% contra 56.5%), sin patron entre D1 y D2 y sin tocar la mediana de Sharpe. **No adoptar.**
- **Para liberar capital no hace falta:** el bot esta fuera del mercado 83% a 88% del tiempo y cada trade libera el capital
  en aproximadamente un dia por stop u objetivo.
- **Lo que si seria una pregunta distinta:** un limite MUCHO mas corto (por ejemplo 24 a 96h) que cierre trades que se
  quedan sin moverse. No se probo aca para no sumar mas variantes sin necesidad; se puede hacer si se quiere.
''')
Path('reports/backtest2-v2/TIME_BARRIER.md').write_text('\n'.join(lines) + '\n')
