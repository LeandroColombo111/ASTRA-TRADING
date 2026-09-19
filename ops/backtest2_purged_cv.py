"""Purged blocked cross-validation with embargo: hold out a middle block, choose parameters on the data BEFORE and AFTER it, leave an
embargo gap on both sides (covers trade length and indicator memory), then score the held-out block. Compared with the production params on
the same blocks. Binance series 2020-05 -> 2026-08 (2020 data is new to the project). Writes reports/backtest2-v2/PURGED_CV.md.
Rule fixed before running: 8 contiguous blocks, embargo 120d each side, pooled daily Sharpe as the selection score, grids below."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import build_sim, HOUR, sharpe_from_equity, max_dd, hodl_window

CFG = json.loads(Path('configs/selected.json').read_text())
BASE, PROD, RISK = CFG['params'], HourlyParams(**CFG['params']), Risk(**CFG['risk'])
sim = build_sim(RISK)
K, GAP, WARM = 8, pd.Timedelta(days=120), pd.Timedelta(days=120)
T0, T1 = pd.Timestamp('2020-05-01', tz='UTC'), pd.Timestamp('2026-09-01', tz='UTC')
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
    assert (b.index.to_series().diff().dropna() == HOUR).all(), 'gap in the joined series'
    return b


def daily_rets(eq):
    e = eq.copy()
    e.index = e.index - pd.Timedelta(nanoseconds=1)
    d = e.resample('1D').last().dropna()
    return d.pct_change().fillna(d.iloc[0] / RISK.capital - 1).to_numpy()


def run_seg(bars, p, start, end):
    seg = bars.loc[start - WARM:end]
    eq, _, _ = sim.run(seg, features(seg, p), p, RISK, start=start, end=end)
    return eq


def pooled_sharpe(bars, p, segs):
    r = np.concatenate([daily_rets(run_seg(bars, p, a, b)) for a, b in segs])
    sd = r.std(ddof=1)
    return float(np.sqrt(365) * r.mean() / sd) if sd > 0 else 0.


edges = [T0 + (T1 - T0) * i / K for i in range(K + 1)]
G1 = [{'stop_atr': a, 'reward': b, 'trail_atr': a if a > 3 else 3.0} for a in (2., 3., 4., 5.) for b in (2., 3., 4., 6.)]
G2 = [{'breakout': n} for n in (240, 480, 720, 960, 1200)]

out('# Validacion cruzada con purga y embargo (bloque del medio apartado)\n')
out(f'Serie Binance 2020-05-01 a 2026-08-31 (unida con los datos nuevos de 2020), {K} bloques contiguos de unos {(T1 - T0).days // K} dias. Para cada bloque: '
    f'se eligen los parametros con todo lo que queda **antes y despues**, dejando un embargo de {GAP.days} dias a cada lado (cubre el largo de los trades '
    'y la memoria de los indicadores), y se mide en el bloque apartado. Se compara con los parametros de produccion en los mismos bloques. '
    'Ojo: entrenar con datos posteriores al bloque no es una prueba hacia adelante; mide si los parametros generalizan a un periodo no visto.\n')
results = {}
for sym in ('BTC', 'ETH'):
    bars = load(sym)
    for label, grid in (('stop_atr x reward', G1), ('largo del breakout', G2)):
        rows = []
        for k in range(K):
            a, b = edges[k], edges[k + 1]
            train = [(s, e) for s, e in ((edges[0], a - GAP), (b + GAP, edges[K])) if e - s >= pd.Timedelta(days=90)]
            cands = [HourlyParams(**{**BASE, **g}) for g in grid]
            scores = [pooled_sharpe(bars, c, train) for c in cands]
            i = int(np.argmax(scores))
            chosen, prod_train = cands[i], pooled_sharpe(bars, PROD, train)
            e_c, e_p = run_seg(bars, chosen, a, b), run_seg(bars, PROD, a, b)
            h = hodl_window(bars, a, b, RISK.capital)
            rows.append({'bloque': f'{a.date()}', 'elegido': {kk: grid[i][kk] for kk in grid[i] if kk != 'trail_atr'}, 'is': scores[i],
                         'sh_c': sharpe_from_equity(e_c, RISK.capital), 'ret_c': e_c.iloc[-1] / RISK.capital - 1,
                         'sh_p': sharpe_from_equity(e_p, RISK.capital), 'ret_p': e_p.iloc[-1] / RISK.capital - 1,
                         'ret_h': h.iloc[-1] / RISK.capital - 1, 'prod_pick': bool(chosen == PROD)})
        df = pd.DataFrame(rows)
        comp = lambda x: float(np.prod(1 + x) - 1)
        out(f'\n## {sym}, grilla: {label}\n')
        out('| bloque | parametros elegidos | Sharpe en muestra | Sharpe fuera (elegido) | ganancia fuera (elegido) | Sharpe fuera (produccion) | ganancia fuera (produccion) | HODL |')
        out('|---|---|---|---|---|---|---|---|')
        for _, r in df.iterrows():
            out(f"| {r.bloque} | {r.elegido} | {r['is']:.2f} | {r.sh_c:.2f} | {pct(r.ret_c)} | {r.sh_p:.2f} | {pct(r.ret_p)} | {pct(r.ret_h)} |")
        corr = float(np.corrcoef(df['is'], df.sh_c)[0, 1])
        out(f"\nElegidos: Sharpe fuera media {df.sh_c.mean():.2f} / mediana {df.sh_c.median():.2f}, ganancia compuesta {pct(comp(df.ret_c))}. "
            f"Produccion: {df.sh_p.mean():.2f} / {df.sh_p.median():.2f}, {pct(comp(df.ret_p))}. HODL: {pct(comp(df.ret_h))}. "
            f"corr(Sharpe en muestra, fuera) = {corr:.2f}. Produccion fue la elegida en {int(df.prod_pick.sum())} de {K} bloques.")
        results[f'{sym}_{label}'] = {'chosen_out_sharpe_mean': float(df.sh_c.mean()), 'prod_out_sharpe_mean': float(df.sh_p.mean()), 'corr': corr}
out('''
## Lectura

- **Elegir parametros con datos de ambos lados no predice el rendimiento en el bloque apartado.** La correlacion entre el Sharpe en muestra y el Sharpe
  fuera del bloque es negativa en las cuatro busquedas (-0.61 a -0.83). Mejor Sharpe en muestra no significa mejor resultado afuera.
- **BTC:** los parametros elegidos por la validacion rinden peor que los de produccion en los mismos bloques (Sharpe 0.38 y 0.42 contra 0.55; ganancia
  +37.6% y +54.8% contra +76.4%). Esto es coherente con que los valores de produccion se ajustaron con estos mismos datos: los bloques desde 2022 no
  son independientes de esa eleccion. Los bloques nuevos de 2020-2021 (produccion: Sharpe 1.09, -0.91, 1.20; ganancia +17.3%, -9.1%, +15.4%) muestran
  el mismo perfil defensivo y modesto que la prueba fuera de muestra.
- **ETH:** la busqueda elige de forma estable un stop mas ancho (`stop_atr` 5) y ahi si supera a produccion (Sharpe 0.76 contra 0.41; ganancia
  +87.1% contra +35.6%). Coincide con lo visto en las 14 ventanas (stop 5 / reward 3: Sharpe mediana 1.10). Es una pista para ETH, no una razon para
  cambiar el bot (que opera solo BTC), y sigue siendo una ventaja chica frente al HODL (+1083.8%).
- **Ningun bloque muestra que el bot supere al HODL en ganancia total.** La conclusion de siempre se mantiene: es defensivo, no generador de retorno.
- **Hallazgo de infraestructura:** en la primera corrida una vela de Binance con volumen cero (pausa del exchange, 2024-10-28 20:00) hizo explotar el
  precio de fill del modelo de deslizamiento (dividia por el volumen de la vela) y aparecio un -100% falso. Se agrego un tope al impacto
  (`SlippageModel.max_impact`, 5%). Se re-corrio `ops/backtest2_research.py` completo con el arreglo: las tablas de `tables.md` quedaron **identicas**, es
  decir ningun informe anterior estaba afectado (las 9 velas de volumen cero de OKX del 2022-12-18 no cayeron sobre ninguna operacion).
''')
Path('reports/backtest2-v2/PURGED_CV.md').write_text('\n'.join(lines) + '\n')
