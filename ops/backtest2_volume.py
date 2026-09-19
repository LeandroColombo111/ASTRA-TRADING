"""Volume as a confirmation for v4_hourly entries (breakout participation, on-balance volume). Writes reports/backtest2-v2/VOLUME.md.
Same rules as the other research scripts: fixed params, warmup 250d, neighbours, ETH/SOL, HODL alongside."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import (WARMUP, HOUR, load_bars, build_sim, evaluate, summarize, engine_variant, chained_maxdd)
from astra.backtest2.exposure_strategies import VolumeParams, volume_signal

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


out('# Volumen como confirmacion de entradas\n')
out('Datos: solo la columna `volume` horaria de OKX (contratos por vela). No hay separacion entre compras y ventas agresivas, '
    'asi que el "volumen acumulado" se aproxima con OBV (volumen acumulado con el signo de cada vela), que es un proxy tosco del order flow.\n')
out('## 1. Diagnostico: resultado de los trades del bot segun el volumen al entrar (corrida continua; terciles)\n')
out('Volumen relativo = promedio de 24h / promedio de 30 dias. Pocos trades por grupo.\n')
out('| activo | volumen al entrar | trades | ganancia media por trade | % ganadores |')
out('|---|---|---|---|---|')
for s in SYMS:
    b = DATA[s]
    v = b.volume.astype(float)
    ratio = v.rolling(24).mean() / v.rolling(30 * 24).mean()
    start = b.index[0] + WARMUP
    _, tr, _ = sim.run(b, features(b, P), P, RISK, start=start, end=b.index[-1] + HOUR)
    df = pd.DataFrame([{'ratio': ratio.loc[pd.Timestamp(t['entry_time']) - HOUR],
                        'pnl': t['net_pnl'] / (t['quantity'] * t['entry'])} for t in tr]).dropna()
    df['q'] = pd.qcut(df.ratio, 3, labels=['bajo', 'medio', 'alto'])
    for q, g in df.groupby('q', observed=True):
        out(f'| {s} | {q} | {len(g)} | {pct(g.pnl.mean())} | {(g.pnl > 0).mean():.0%} |')

HEAD = ('| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | '
        'DD encadenado | % en mercado |\n|---|---|---|---|---|---|---|---|')


def row(name, df):
    s = summarize(df)
    return (f"| {name} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | {s['negative']} | "
            f"{pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")


out('\n## 2. Filtros de entrada (14 ventanas de 90d, warmup 250d, valores fijos y vecinos)\n')
out('Hipotesis fijadas antes de correr:\n')
out('- **V1 quiebre confirmado por volumen:** entrar solo si el volumen de 24h supera su promedio de 30 dias por un factor k '
    '(k=1.0, vecinos 0.8 y 1.2). Los quiebres con participacion tienen mas continuidad (Karpoff 1987; Gervais et al. 2001). '
    'Contraste: volumen bajo (<= 1.0).')
out('- **V2 volumen acumulado (OBV):** largos solo con OBV sobre su media, cortos solo con OBV bajo su media (acumulacion / distribucion); '
    'media de 30 dias, vecinos 20 y 60.\n')
V = [(f'V1 volumen >= {k}x', VolumeParams(**BASE, vol_ratio_min=k)) for k in (0.8, 1.0, 1.2)]
V += [('V1 contraste: volumen <= 1.0x', VolumeParams(**BASE, vol_ratio_max=1.0))]
V += [(f'V2 OBV vs media {d}d', VolumeParams(**BASE, obv_days=d)) for d in (20, 30, 60)]
for s in SYMS:
    out(f'\n**{s}**\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), DATA[s], RISK)
    out(row('original', base))
    for name, par in V:
        out(row(name, evaluate(engine_variant(name, par, volume_signal, sim, RISK), DATA[s], RISK)))
    sm = summarize(base)
    out(f"| HODL | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | "
        f"{pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")
out('''
## 3. Conclusiones

- **V1 (quiebre con volumen alto): no adoptar.** No hay patron monotono: en BTC la ganancia baja al subir el umbral (55.6% / 44.3% / 41.0%
  contra 56.5%) y la Sharpe mediana cae de 1.11 a 0.42 y 0.63; en ETH el 1.2x pasa a -11.6%; en SOL el 1.0x mejora (33.0%) pero el 1.2x
  empeora (3.5%). Lo unico consistente es que operar solo con volumen bajo (contraste) rinde peor en BTC y ETH (13.5% y -2.0%), pero a costa
  de casi no operar (2% a 3% del tiempo), asi que informa poco.
- **V2 (OBV): no adoptar.** En BTC casi no filtra (62.2% contra 56.5%, mismo resultado con 20, 30 y 60 dias), en ETH es neutro y en SOL empeora
  con claridad (-4.4% a 1.8% contra 16.7%; Sharpe mediana -0.61 a -0.45). Falla la validacion cruzada en SOL.
- **Alcance:** solo se probo el volumen por vela. El OBV es un proxy tosco del order flow, asi que esto NO demuestra que el order flow real
  (compras contra ventas agresivas) no sirva; solo que el volumen agregado no agrega senal robusta a estas entradas.
- Suma 7 variantes al acumulado (~63 sobre BTC). `configs/selected.json` sin cambios.
''')
Path('reports/backtest2-v2/VOLUME.md').write_text('\n'.join(lines) + '\n')
