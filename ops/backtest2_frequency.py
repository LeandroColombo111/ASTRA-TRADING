"""Rama de investigacion: hacia donde va el P&L si se aumenta la cantidad de operaciones. Dos vias, ambas con la
disciplina de siempre (parametros fijos, warmup 250d, 14 ventanas de 90d, HODL al lado, BTC/ETH/SOL): (1) barrido del
largo de la ruptura (el parametro que mas controla cuanto opera v4_hourly) para ver el P&L en funcion de la frecuencia;
(2) una cartera que opera BTC+ETH+SOL a la vez (mismo capital total repartido), que sube la frecuencia por diversificacion
en vez de por parametros mas sueltos. Solo investigacion: no toca configs/selected.json ni el bot. Escribe
reports/backtest2-v2/FREQUENCY.md."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import (WARMUP, HOUR, load_bars, build_sim, evaluate, summarize, engine_variant,
                                      chained_maxdd, chain, chain_stats, hodl_window, sharpe_from_equity, max_dd)

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


out('# Mas operaciones: hacia donde va el P&L\n')
out('Dos caminos para subir la frecuencia sin inventar reglas nuevas: (1) acortar la ruptura de entrada de v4_hourly '
    '(el parametro que mas controla cuanto opera), (2) operar BTC, ETH y SOL a la vez en vez de solo BTC. Mismas reglas '
    'de siempre: parametros fijos (nada se re-optimiza mirando el resultado), warmup 250d, 14 ventanas de 90d, '
    'comparacion contra HODL. Aviso de entrada: ya se sabe que acortar la ruptura a 240h mejora SOLO en BTC y empeora '
    'en ETH/SOL (reports/backtest2-v2/README.md, seccion C); este barrido muestra el patron completo, no busca un '
    'ganador nuevo.\n')

out('## 1. Barrido del largo de ruptura (trades/año en funcion del parametro)\n')
HEAD = ('| ruptura (horas) | trades/año | Sharpe media / mediana | ventanas >=1.5 | ganancia total | peor ventana | '
        'DD encadenado | % en mercado |\n|---|---|---|---|---|---|---|---|')
BREAKOUTS = [120, 180, 240, 320, 400, 480, 600, 720, 840, 960, 1200, 1500]
freq_rows = {}
for sym in SYMS:
    bars = DATA[sym]
    out(f'\n**{sym}**\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), bars, RISK)
    sb = summarize(base)
    out(f"| {BASE['breakout']} (produccion) | {sum(r['trades'] for _,r in base.iterrows())/ (len(bars)/24/365):.0f} | "
        f"{sb['sharpe_mean']:.2f} / {sb['sharpe_median']:.2f} | {sb['ge_1_5']}/{sb['n']} | {pct(sb['total_ret'])} | "
        f"{pct(sb['worst_window'])} | {pct(chained_maxdd(base))} | {pct(sb['time_in_market'])} |")
    years = (bars.index[-1] - bars.index[0]) / pd.Timedelta(days=365)
    for bo in BREAKOUTS:
        par = HourlyParams(**{**BASE, 'breakout': bo})
        df = evaluate(engine_variant('b', par, features, sim, RISK), bars, RISK)
        s = summarize(df)
        trades_yr = df.trades.sum() / years
        mark = ' **(produccion)**' if bo == BASE['breakout'] else ''
        out(f"| {bo}{mark} | {trades_yr:.0f} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | "
            f"{pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")
        freq_rows.setdefault(sym, []).append({'breakout': bo, 'trades_yr': trades_yr, 'total_ret': s['total_ret'],
                                              'sharpe_mean': s['sharpe_mean'], 'maxdd': chained_maxdd(df)})
    hs = summarize(base)
    out(f"| HODL | - | {hs['hodl_sharpe_mean']:.2f} / {hs['hodl_sharpe_median']:.2f} | {hs['hodl_ge_1_5']}/{hs['n']} | "
        f"{pct(hs['hodl_total_ret'])} | {pct(hs['hodl_worst_window'])} | - | 100% |")

out('\n## 2. Cartera BTC + ETH + SOL a la vez (mismo capital total, un tercio por activo)\n')
out('No se cambia ningun parametro: es el bot original corriendo en los tres activos en simultaneo, cada uno con un '
    'tercio del capital. Sube la frecuencia de trades porque hay tres fuentes de senales independientes, no porque '
    'se opere distinto.\n')
THIRD = Risk(**{**CFG['risk'], 'capital': CFG['risk']['capital'] / 3})
sim3 = build_sim(THIRD)
kept = {}
for sym in SYMS:
    evaluate(engine_variant('o', P, features, sim3, THIRD), DATA[sym], THIRD, keep=kept.setdefault(sym, {}))
windows = sorted(kept['BTC'].keys())
rows = []
for w in windows:
    eqs = [kept[s][w][0] for s in SYMS if w in kept[s]]
    trades = sum(len(kept[s][w][2]) for s in SYMS if w in kept[s])
    combined = sum(eqs)
    h = sum(kept[s][w][1] for s in SYMS if w in kept[s])
    rows.append({'start': w, 'sharpe': sharpe_from_equity(combined, CFG['risk']['capital']),
                'ret': float(combined.iloc[-1] / CFG['risk']['capital'] - 1), 'maxdd': max_dd(combined, CFG['risk']['capital']),
                'trades': trades, 'hodl_ret': float(h.iloc[-1] / CFG['risk']['capital'] - 1)})
port = pd.DataFrame(rows)
comp = lambda x: float(np.prod(1 + x) - 1)
out('| variante | trades totales (14 ventanas) | Sharpe media / mediana | ganancia total | peor ventana | DD peor ventana |')
out('|---|---|---|---|---|---|')
out(f"| Cartera BTC+ETH+SOL (1/3 cada uno) | {int(port.trades.sum())} | {port.sharpe.mean():.2f} / {port.sharpe.median():.2f} | "
    f"{pct(comp(port.ret))} | {pct(port.ret.min())} | {pct(port.maxdd.max())} |")
bbase = evaluate(engine_variant('o', P, features, sim, RISK), DATA['BTC'], RISK)
bs = summarize(bbase)
out(f"| Solo BTC (produccion) | {int(bbase.trades.sum())} | {bs['sharpe_mean']:.2f} / {bs['sharpe_median']:.2f} | "
    f"{pct(bs['total_ret'])} | {pct(bs['worst_window'])} | {pct(bs['worst_maxdd'])} |")
out(f"| HODL BTC (mismo capital) | - | {bs['hodl_sharpe_mean']:.2f} / {bs['hodl_sharpe_median']:.2f} | {pct(bs['hodl_total_ret'])} | "
    f"{pct(bs['hodl_worst_window'])} | {pct(bs['hodl_worst_maxdd'])} |")

out('''
## Lectura

- **Hay un punto donde mas operaciones SI mejoran el resultado en BTC, pero es un pico aislado, no una tendencia.**
  Bajar la ruptura de 720h a 180h sube los trades/año de 21 a 30 y el resultado en BTC mejora con claridad (Sharpe
  mediana 1.51 vs 1.00, ganancia 104.4% vs 56.5%, caida encadenada 5.6% vs 15.8%). Pero 120h (mas operaciones todavia)
  es PEOR que 180h (84.1% de ganancia), y subir a 1200-1500h destruye el resultado. No es "mas operaciones = mejor
  P&L" de forma monotona: hay un maximo local en algun punto entre 120h y 720h, y ese tipo de pico aislado es
  exactamente la firma de sobreajuste que el proyecto viene encontrando en cada parametro (ver README.md seccion D).
- **Falla la prueba cruzada.** En ETH, achicar la ruptura empeora casi siempre (240h da -6.6% contra 17.4% del
  original); en SOL el patron es ruidoso y sin tendencia clara. El "mejor" punto de BTC (180h) da en ETH apenas 4.7%
  (peor que el original) y en SOL 13.1% (tambien peor). Es la misma historia que la ruptura de 240h ya descartada:
  funciona en BTC porque ahi se eligio mirando BTC, no porque acortar la ruptura sea una ventaja real.
- **La cartera BTC+ETH+SOL sube la cantidad de operaciones (95 a 278 en las mismas 14 ventanas) pero NO sube el
  resultado.** Gana menos en total (32.0% contra 56.5% de BTC solo) porque reparte capital en ETH y SOL, que ya
  sabiamos que casi no tienen ventaja. Lo que si logra es bajar el riesgo: la peor ventana pasa de -11.3% a -4.9% y
  el drawdown de 12.7% a 7.8%. Es diversificacion, no una ventaja nueva: reduce varianza, no aumenta el retorno
  esperado.
- **Respuesta directa a "hacia donde va el P&L":** no hacia arriba de forma confiable. Mas operaciones en BTC solo
  (via ruptura mas corta) puede mejorar o empeorar segun el punto exacto elegido, sin un patron fiable entre activos.
  Mas operaciones via diversificacion (cartera de 3 activos) baja el riesgo pero tambien el retorno total, porque
  reparte capital en activos sin ventaja propia.
- **Conclusion: no adoptar ningun punto de la grilla.** Ninguno pasa la regla de sostenerse en BTC, ETH y SOL a la
  vez. La produccion (720h) sigue siendo una eleccion razonable: no es la mejor en ningun activo individualmente,
  pero tampoco es un extremo fragil como el 180h de BTC o el 1500h que arruina todo.
''')
Path('reports/backtest2-v2/FREQUENCY.md').write_text('\n'.join(lines) + '\n')
json.dump(freq_rows, open('reports/backtest2-v2/frequency_sweep.json', 'w'), indent=2)
