"""Frozen v4_hourly on Binance 2020-2021, the least-contaminated history available. 2020 (downloaded after the search) was never seen by any
search. 2021 was only warmup for v4's selection folds (they start 2022-02-05) but the v3 daily search and horizon sweep touched that series
(see reports/v4-hourly-01/protocol.json), so it is NOT fully independent. No parameter is changed or tuned here.
Writes reports/backtest2-v2/OUT_OF_SAMPLE_2020_2021.md."""
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
P, RISK = HourlyParams(**CFG['params']), Risk(**CFG['risk'])
WARM = pd.Timedelta(days=120)  # 2020-01-01 + 121d = 2020-05-01, the first window
WARM_NOTE = None  # indicators are stable from ~120d of history (reports/backtest2-v1/CORRECTION_2026-09-18.md)
sim = build_sim(RISK)
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


def load(sym):
    parts = []
    for f in (f'data/{sym}USDT-2020-1h.csv', f'data/{sym}USDT-1h.csv'):
        b = pd.read_csv(f, index_col='time', parse_dates=True)
        b.index = pd.to_datetime(b.index, utc=True)
        parts.append(b)
    b = pd.concat(parts)
    b = b[~b.index.duplicated()].sort_index()
    b = b.loc[:'2022-02-05']
    assert (b.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all(), 'gap in the joined series'
    return b


out('# Prueba con 2020 y 2021 (los tramos menos contaminados): configuracion congelada\n')
out('Serie Binance USD-M como proxy de OKX. **2020 es completamente nuevo**: se bajo despues de la busqueda y ninguna prueba lo vio '
    '(incluye el crash de marzo de 2020 solo como calentamiento). 2021 fue solo calentamiento de la seleccion de v4, pero otras busquedas '
    'tocaron esa serie, asi que no es independiente del todo. Ningun parametro se cambia. Ventanas de 90d desde 2020-05-01 '
    '(121 dias de calentamiento), 7 ventanas hasta enero de 2022.\n')
HEAD = ('| activo | ventanas | Sharpe media / mediana | ganancia total | peor ventana | DD encadenado | % en mercado | HODL total | HODL peor ventana |'
        '\n|---|---|---|---|---|---|---|---|---|')
out(HEAD)
detail = []
for sym in ('BTC', 'ETH'):
    b = load(sym)
    wins = [(pd.Timestamp('2020-05-01', tz='UTC') + pd.Timedelta(days=90 * k),
             pd.Timestamp('2020-05-01', tz='UTC') + pd.Timedelta(days=90 * (k + 1))) for k in range(7)]
    df = evaluate(engine_variant('o', P, features, sim, RISK), b, RISK, warmup=WARM, windows=wins)
    s = summarize(df)
    out(f"| {sym} | {s['n']} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {pct(s['total_ret'])} | {pct(s['worst_window'])} | "
        f"{pct(chained_maxdd(df))} | {pct(s['time_in_market'])} | {pct(s['hodl_total_ret'])} | {pct(s['hodl_worst_window'])} |")
    detail.append((sym, df))
    fresh = summarize(df.iloc[:3])
    out(f"| {sym} (solo ventanas 1-3, casi todo 2020) | 3 | {fresh['sharpe_mean']:.2f} / {fresh['sharpe_median']:.2f} | {pct(fresh['total_ret'])} | "
        f"{pct(fresh['worst_window'])} | - | {pct(fresh['time_in_market'])} | {pct(fresh['hodl_total_ret'])} | {pct(fresh['hodl_worst_window'])} |")
out('\nDetalle por ventana:\n')
out('| activo | inicio | Sharpe | ganancia | HODL | trades |')
out('|---|---|---|---|---|---|')
for sym, df in detail:
    for _, r in df.iterrows():
        out(f"| {sym} | {r.start.date()} | {r.sharpe:.2f} | {pct(r.ret)} | {pct(r.hodl_ret)} | {int(r.trades)} |")
out('\nLimite: 7 ventanas por activo (unos 21 meses). Sirve para ver si el bot se rompe en un regimen distinto, no para estimar un Sharpe con precision.')
out('''
## Lectura

- **No se rompe, pero la ventaja es mucho menor que en la muestra original.** BTC: Sharpe mediana 0.38 (contra 1.00 en 2022-2026), ganancia +15.5% en
  21 meses (unos 8% anual), 3 de 7 ventanas negativas y drawdown encadenado de 4.0%. ETH: Sharpe medio -0.28 y -9.5% de ganancia total.
- **Frente al HODL pierde por mucho en un mercado alcista extremo** (BTC +343%, ETH +1225% en el mismo periodo), como ya se sabia: solo esta
  en mercado el 13% a 17% del tiempo. Lo que si hizo fue proteger capital en las ventanas bajistas de 2021 (BTC +1.7% y +2.8% mientras el HODL
  perdia -32.8% y -33.6%).
- **Conclusion:** sobre datos que la busqueda nunca vio, el bot sigue siendo defensivo y de bajo riesgo, pero su rentabilidad propia es chica
  y en ETH incluso negativa. Esto refuerza que lo razonable es usarlo como capa tactica sobre una tenencia, y que las cifras de 2022-2026 (Sharpe
  0.52 / 1.00) deben leerse como un techo optimista.
''')
Path('reports/backtest2-v2/OUT_OF_SAMPLE_2020_2021.md').write_text('\n'.join(lines) + '\n')
