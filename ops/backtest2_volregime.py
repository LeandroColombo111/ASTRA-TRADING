"""Volatility-clustering test: does gating v4_hourly entries by volatility regime help? Writes
reports/backtest2-v2/VOLATILITY_CLUSTERING.md. Same rules as ops/backtest2_research.py (fixed params, warmup 250d, HODL alongside)."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import (WARMUP, HOUR, load_bars, build_sim, evaluate, summarize, engine_variant, chained_maxdd)
from astra.backtest2.exposure_strategies import VolRegimeParams, volregime_signal

CFG = json.loads(Path('configs/selected.json').read_text())
BASE, P, RISK = CFG['params'], HourlyParams(**CFG['params']), Risk(**CFG['risk'])
SYMS = ['BTC', 'ETH', 'SOL']
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


out('# Clustering de volatilidad: diagnostico y filtro de regimen\n')
out('## 1. Diagnostico (no agrega variantes)\n')
out('Autocorrelacion del |retorno diario| (persistencia de la volatilidad) y del retorno mismo:\n')
out('| activo | rezago 1 | 2 | 5 | 10 | 20 | autocorr del retorno (rezago 1) |')
out('|---|---|---|---|---|---|---|')
DATA = {s: load_bars(s) for s in SYMS}
for s in SYMS:
    d = np.log(DATA[s].close).diff().resample('1D').sum()
    a = d.abs()
    out(f"| {s} | " + ' | '.join(f'{a.autocorr(l):.2f}' for l in (1, 2, 5, 10, 20)) + f' | {d.autocorr(1):.3f} |')

out('\nResultado de las operaciones del bot (corrida continua) segun el regimen de volatilidad al entrar '
    '(vol de 7d / vol de 60d, terciles). Ojo: pocos trades por grupo.\n')
out('| activo | regimen al entrar | trades | ganancia media por trade | % ganadores |')
out('|---|---|---|---|---|')
sim = build_sim(RISK)
for s in SYMS:
    bars = DATA[s]
    r = np.log(bars.close).diff()
    ratio = r.rolling(7 * 24).std() / r.rolling(60 * 24).std()
    start = bars.index[0] + WARMUP
    _, tr, _ = sim.run(bars, features(bars, P), P, RISK, start=start, end=bars.index[-1] + HOUR)
    df = pd.DataFrame([{'ratio': ratio.loc[pd.Timestamp(t['entry_time']) - HOUR],
                        'pnl': t['net_pnl'] / (t['quantity'] * t['entry'])} for t in tr]).dropna()
    df['q'] = pd.qcut(df.ratio, 3, labels=['calma', 'media', 'alta'])
    for q, g in df.groupby('q', observed=True):
        out(f'| {s} | {q} | {len(g)} | {pct(g.pnl.mean())} | {(g.pnl > 0).mean():.0%} |')

out('\n## 2. Filtro de entradas por regimen (valores fijos y vecinos; ventanas de 90d, warmup 250d)\n')
out('Hipotesis fijadas antes de correr: **alta** = solo entrar con volatilidad en expansion (la persistencia de la volatilidad '
    'haria que los quiebres tengan continuidad); **calma** = solo entrar con volatilidad comprimida (contraste: es lo que '
    'sugiere el diagnostico, que se miro sobre los mismos trades, asi que es la de mayor riesgo de sobreajuste).\n')
HEAD = ('| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | '
        'DD encadenado | % en mercado |\n|---|---|---|---|---|---|---|---|')


def row(name, df):
    s = summarize(df)
    return (f"| {name} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | {s['negative']} | "
            f"{pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")


V = [(f'alta: ratio >= {t}', VolRegimeParams(**BASE, ratio_min=t)) for t in (0.8, 1.0, 1.2)]
V += [(f'calma: ratio <= {t}', VolRegimeParams(**BASE, ratio_max=t)) for t in (0.8, 1.0, 1.2)]
for s in SYMS:
    out(f'\n**{s}**\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), DATA[s], RISK)
    out(row('v4_hourly original', base))
    for name, par in V:
        out(row(name, evaluate(engine_variant(name, par, volregime_signal, sim, RISK), DATA[s], RISK)))
    sm = summarize(base)
    out(f"| HODL | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | "
        f"{pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")
out('\n## 3. Estabilidad temporal del filtro de calma (primeras 7 ventanas vs ultimas 7)\n')
out('| activo | variante | ventanas 1-7: Sharpe mediana / ganancia | ventanas 8-14: Sharpe mediana / ganancia |')
out('|---|---|---|---|')
for s in SYMS:
    for name, par, fn in [('original', P, features), ('calma <= 1.0', VolRegimeParams(**BASE, ratio_max=1.0), volregime_signal),
                          ('calma <= 1.2', VolRegimeParams(**BASE, ratio_max=1.2), volregime_signal)]:
        df = evaluate(engine_variant(name, par, fn, sim, RISK), DATA[s], RISK)
        a, b = summarize(df.iloc[:7]), summarize(df.iloc[7:])
        out(f"| {s} | {name} | {a['sharpe_median']:.2f} / {pct(a['total_ret'])} | {b['sharpe_median']:.2f} / {pct(b['total_ret'])} |")
out('''
## 4. Conclusiones

- El clustering existe pero es corto: la autocorrelacion de la volatilidad diaria es 0.17 a 0.29 al dia siguiente y casi
  desaparece a los 10 a 20 dias. Los retornos en si no tienen autocorrelacion, asi que la volatilidad ayuda a estimar
  riesgo, no direccion.
- **Filtro "alta" (usar la persistencia de volatilidad alta para entrar): no adoptar.** Empeora BTC (mediana 1.00 a -0.44 / -0.10 / -0.19)
  y ETH, y en SOL es mixto. Con los datos, entrar cuando la volatilidad ya se disparo llega tarde.
- **Filtro "calma" (solo entrar con volatilidad comprimida): candidato, no adoptar todavia.** En BTC y ETH mejora la
  mediana de Sharpe y baja mucho el drawdown y el tiempo en mercado (BTC <= 1.0: 1.46 contra 1.00, DD 7.4% contra 15.8%,
  6.7% del tiempo contra 16.6%), con ganancia total parecida (54.0% contra 56.5%); es decir, la misma ganancia con menos
  exposicion, no una ganancia mayor. Se sostiene en ambas mitades de las ventanas en BTC y ETH; en SOL es mixto y el valor
  estricto (<= 0.8) empeora en ETH y SOL por casi no operar.
- **Riesgo de sobreajuste:** la direccion se miro sobre los mismos trades y esta prueba suma 6 variantes al acumulado
  (~50 sobre BTC). Necesita confirmarse con operacion real en demo o datos nuevos antes de tocar el bot.
- El tamano por volatilidad objetivo (ya probado como H1 en `README.md`) no mejoro el Sharpe.
''')
Path('reports/backtest2-v2/VOLATILITY_CLUSTERING.md').write_text('\n'.join(lines) + '\n')
