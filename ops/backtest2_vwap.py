"""Rama de investigacion: VWAP (precio promedio ponderado por volumen) como filtro de entradas. Dos hipotesis fijadas
antes de correr: V1 confirmar el quiebre solo si el precio ya esta alejado del VWAP (conviccion con volumen detras);
V2 bloquear entradas cuando el precio esta MUY lejos del VWAP (perseguir un movimiento ya agotado). Mismas reglas de
siempre: parametros fijos, warmup 250d, 14 ventanas, BTC/ETH/SOL, HODL al lado. Solo investigacion.
Escribe reports/backtest2-v2/VWAP.md."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import load_bars, build_sim, evaluate, summarize, engine_variant, chained_maxdd
from astra.backtest2.exposure_strategies import VwapDeviationParams, vwap_signal

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


HEAD = ('| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |'
        '\n|---|---|---|---|---|---|---|---|')


def row(name, df):
    s = summarize(df)
    return (f"| {name} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | {s['negative']} | "
            f"{pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")


out('# VWAP (precio ponderado por volumen) como filtro de entradas\n')
out('VWAP calculado sobre las barras horarias (precio tipico x volumen, ventana movil de 7 dias = 168h, con vecinos '
    '72h y 336h). Hipotesis fijadas antes de correr:\n')
out('- **V1 confirmar el quiebre:** solo entrar si el precio ya esta `dev_min` o mas alejado del VWAP en la direccion del quiebre '
    '(el movimiento tiene conviccion ponderada por volumen, no es solo precio). dev_min = 1%, 2%, 3%.')
out('- **V2 bloquear si esta muy extendido:** no entrar si el precio esta a mas de `dev_max` del VWAP (perseguir algo que ya se '
    'alejo mucho del promedio con volumen). dev_max = 5%, 8%, 12%.\n')
V = [(f'V1 confirmar, dev>={d}%, VWAP 168h', VwapDeviationParams(**BASE, vwap_hours=168, dev_min=d/100, mode='breakout_confirm')) for d in (1,2,3)]
V += [(f'V1 confirmar, VWAP {h}h, dev>=2%', VwapDeviationParams(**BASE, vwap_hours=h, dev_min=0.02, mode='breakout_confirm')) for h in (72,336)]
V += [(f'V2 bloquear si dev>{d}%, VWAP 168h', VwapDeviationParams(**BASE, vwap_hours=168, dev_max=d/100, mode='reversion_block')) for d in (5,8,12)]
for sym in SYMS:
    out(f'\n**{sym}**\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), DATA[sym], RISK)
    out(row('original', base))
    for name, par in V:
        out(row(name, evaluate(engine_variant(name, par, vwap_signal, sim, RISK), DATA[sym], RISK)))
    sm = summarize(base)
    out(f"| HODL | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | "
        f"{pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")
out('''
## Lectura

- **V1 (confirmar el quiebre con VWAP) casi no cambia nada.** En BTC y SOL los resultados son identicos o casi
  identicos al original en la mayoria de los valores: un quiebre de 720h ya implica que el precio se movio bastante
  respecto de cualquier promedio reciente, asi que exigir ademas una distancia al VWAP es casi siempre redundante con
  la condicion que ya existe. No aporta informacion nueva.
- **V2 (bloquear si esta muy extendido) es ruidoso, no una ventaja.** Baja mucho el tiempo en mercado (hasta 0.2% en
  SOL con el umbral mas estricto) y los resultados saltan sin patron entre activos y entre umbrales vecinos: en SOL
  el 5% da -0.26 de Sharpe y el 12% da +0.50 con el mismo mecanismo, solo cambiando el numero. Eso es la firma de
  ruido estadistico sobre pocos trades, no de una señal real.
- **Conclusion: no adoptar.** Ninguna de las dos hipotesis mejora al original de forma consistente en los tres
  activos. El VWAP con los datos horarios que tenemos no aporta algo que el quiebre y la tendencia no esten
  capturando ya.
''')
Path('reports/backtest2-v2/VWAP.md').write_text('\n'.join(lines) + '\n')
