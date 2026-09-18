"""Reproducible run behind reports/backtest2-v2/. Every number in that report comes from here.

Rules (see src/astra/backtest2/research.py): same warmup for all variants, fixed parameters,
always against HODL over the same windows. configs/selected.json is read, never written.
Usage: python3 ops/backtest2_research.py
"""
from dataclasses import replace
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import (
    WARMUP, HOUR, TRAIN, TEST, STEP, load_bars, build_sim, test_windows, evaluate, summarize,
    engine_variant, chained_maxdd, chain_stats, mix, mix_equities, chain, sharpe_from_equity, max_dd,
    hodl_window, time_in_market)
from astra.backtest2.exposure_strategies import (
    HoldParams, hold_signal, VolTargetParams, voltarget_signal, NearHighParams, nearhigh_signal,
    LongOnlyParams, longonly_signal)

OUT = Path('reports/backtest2-v2')
CFG = json.loads(Path('configs/selected.json').read_text())
BASE = CFG['params']
P = HourlyParams(**BASE)
RISK = Risk(**CFG['risk'])
NOGUARD = replace(RISK, max_drawdown=0.95)
SYMS = ['BTC', 'ETH', 'SOL']
DATA = {s: load_bars(s) for s in SYMS}
lines = []
results = {}


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


ROW_HEAD = ('| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | '
            'DD encadenado | % en mercado |')
ROW_SEP = '|---|---|---|---|---|---|---|---|'


def row(name, df):
    s = summarize(df)
    return (f"| {name} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | {s['negative']} | "
            f"{pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")


def hodl_row(df):
    s = summarize(df)
    w = np.cumprod(1 + df.hodl_ret.to_numpy())
    w = np.r_[1., w]
    dd = float((1 - w / np.maximum.accumulate(w)).max())
    return (f"| HODL (mismas ventanas) | {s['hodl_sharpe_mean']:.2f} / {s['hodl_sharpe_median']:.2f} | "
            f"{s['hodl_ge_1_5']}/{s['n']} | {int((df.hodl_sharpe < 0).sum())} | {pct(s['hodl_total_ret'])} | "
            f"{pct(s['hodl_worst_window'])} | {pct(dd)} | 100% |")


def run(name, params, fn, bars, rk=RISK, **kw):
    sim = build_sim(rk, kw.pop('impact_k', 1.0))
    return evaluate(engine_variant(name, params, fn, sim, rk), bars, rk, **kw)


# ----------------------------------------------------------------------------- baseline
out('## 0. Base: bot original vs HODL (warmup 250d, 14 ventanas de 90d, parametros fijos)')
for sym in SYMS:
    df = run('orig', P, features, DATA[sym])
    out(f'\n**{sym}**\n\n{ROW_HEAD}\n{ROW_SEP}\n{row("v4_hourly original", df)}\n{hodl_row(df)}')
    results[f'base_{sym}'] = summarize(df)
    if sym == 'BTC':
        s = summarize(df)
        out(f"\nBTC, ventanas donde BTC subio: HODL {pct(s['hodl_ret_up_windows'])} prom, bot {pct(s['ret_up_windows'])}. "
            f"Donde bajo: HODL {pct(s['hodl_ret_down_windows'])}, bot {pct(s['ret_down_windows'])}.")

# ----------------------------------------------------------------------------- A / B
out('\n## A. Objetivo realista y cartera hibrida')
out('\nCartera "manga": w en HODL y (1-w) en una cuenta del bot con su propio capital; se rebalancea al inicio de cada '
    'ventana. Las metricas encadenadas unen las 14 ventanas (retorno compuesto, Sharpe diario y DD sobre toda la cadena).')
out('\n| activo | w HODL | Sharpe encadenado | ganancia encadenada | DD encadenado | peor ventana | ganancia / DD |')
out('|---|---|---|---|---|---|---|')
hyb = {}
for sym in SYMS:
    kept = {}
    run('orig', P, features, DATA[sym], keep=kept)
    for w in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.0]:
        d = mix(kept, w, RISK.capital)
        cs = chain_stats(mix_equities(kept, w), RISK.capital)
        s = summarize(d)
        lab = 'solo HODL' if w == 1 else ('solo bot' if w == 0 else f'{w:.1f}')
        out(f"| {sym} | {lab} | {cs['chain_sharpe']:.2f} | {pct(cs['chain_ret'])} | {pct(cs['chain_maxdd'])} | "
            f"{pct(s['worst_window'])} | {cs['chain_ret'] / cs['chain_maxdd']:.1f} |")
        hyb[(sym, w)] = cs
    hyb[(sym, 'kept')] = kept
results['hybrid'] = {f'{k[0]}_{k[1]}': v for k, v in hyb.items() if k[1] != 'kept'}

# bootstrap CI: hybrid vs HODL Sharpe difference (BTC)
def daily_ret(eqs):
    c = chain(eqs, RISK.capital) * RISK.capital
    c.index = c.index - pd.Timedelta(nanoseconds=1)
    d = c.resample('1D').last().dropna()
    return d.pct_change().dropna().to_numpy()


def boot_diff(a, b, block=20, n=2000, seed=11):
    rng = np.random.default_rng(seed)
    n_obs = len(a)
    diffs = []
    for _ in range(n):
        idx = []
        while len(idx) < n_obs:
            s0 = rng.integers(0, n_obs)
            idx.extend(range(s0, min(s0 + block, n_obs)))
        idx = np.array(idx[:n_obs])
        sa, sb = a[idx], b[idx]
        diffs.append(np.sqrt(365) * (sa.mean() / sa.std(ddof=1) - sb.mean() / sb.std(ddof=1)))
    return np.percentile(diffs, [2.5, 50, 97.5])


out('\nIncertidumbre (bootstrap por bloques de 20 dias, 2000 remuestreos): diferencia de Sharpe = cartera - HODL.')
out('\n| activo | cartera | diferencia Sharpe (IC 95%) | P(diferencia > 0) |')
out('|---|---|---|---|')
for sym in SYMS:
    kept = hyb[(sym, 'kept')]
    h = daily_ret(mix_equities(kept, 1.0))
    for w in [0.7, 0.5]:
        m = daily_ret(mix_equities(kept, w))
        rng = np.random.default_rng(11)
        lo, mid, hi = boot_diff(m, h)
        # probability > 0
        rng = np.random.default_rng(11)
        n_obs = len(m)
        cnt = 0
        for _ in range(2000):
            idx = []
            while len(idx) < n_obs:
                s0 = rng.integers(0, n_obs)
                idx.extend(range(s0, min(s0 + 20, n_obs)))
            idx = np.array(idx[:n_obs])
            a, b = m[idx], h[idx]
            cnt += (a.mean() / a.std(ddof=1) - b.mean() / b.std(ddof=1)) > 0
        out(f'| {sym} | {w:.1f} HODL + bot | {mid:.2f} [{lo:.2f}, {hi:.2f}] | {cnt / 2000:.0%} |')

out('\n## B. Modo de exposicion fija: tenencia larga con salida a efectivo cuando el macro diario pasa a bajista')
out('\nLa entrada usa `exposure=1.0` (100% del capital); el unico cierre es la salida por macro o un stop de desastre del 25%. '
    'Con el freno de drawdown del 25% de produccion la estrategia se congela (`halted=True`) tras la primera caida; '
    'se reporta con y sin freno.')
HOLDS = [('EMA 20/100', HoldParams(macro_fast=20, macro_slow=100)),
         ('EMA 10/50', HoldParams(macro_fast=10, macro_slow=50)),
         ('EMA 30/150', HoldParams(macro_fast=30, macro_slow=150)),
         ('precio vs SMA 200', HoldParams(macro_fast=2, macro_slow=200, kind='sma')),
         ('precio vs SMA 150', HoldParams(macro_fast=2, macro_slow=150, kind='sma'))]
for sym in SYMS:
    out(f'\n**{sym}** (ventanas de 90d)\n\n{ROW_HEAD}\n{ROW_SEP}')
    base = run('orig', P, features, DATA[sym])
    out(row('v4_hourly original', base))
    for name, hp in HOLDS:
        out(row(f'tenencia {name}, con freno 25%', run(name, hp, hold_signal, DATA[sym])))
        out(row(f'tenencia {name}, sin freno', run(name, hp, hold_signal, DATA[sym], rk=NOGUARD)))
    out(hodl_row(base))

out('\nCorrida continua (una sola pasada desde el fin del warmup, sin cortes en ventanas), BTC:')
out('\n| variante | Sharpe | ganancia | DD max | % en mercado | trades | congelado |')
out('|---|---|---|---|---|---|---|')
bars = DATA['BTC']
start = bars.index[0] + WARMUP


def continuous(name, params, fn, rk):
    sim = build_sim(rk)
    eq, tr, st = sim.run(bars, fn(bars, params), params, rk, start=start, end=bars.index[-1] + HOUR)
    tim, _ = time_in_market(tr, start, bars.index[-1])
    out(f"| {name} | {sharpe_from_equity(eq, rk.capital):.2f} | {pct(eq.iloc[-1] / rk.capital - 1)} | "
        f"{pct(max_dd(eq, rk.capital))} | {pct(tim)} | {len(tr)} | {st['halted']} |")


hd = hodl_window(bars, start, bars.index[-1] + HOUR, RISK.capital)
out(f"| HODL | {sharpe_from_equity(hd, RISK.capital):.2f} | {pct(hd.iloc[-1] / RISK.capital - 1)} | "
    f"{pct(max_dd(hd, RISK.capital))} | 100% | - | - |")
continuous('v4_hourly original', P, features, RISK)
for name, hp in HOLDS:
    continuous(f'tenencia {name}, con freno', hp, hold_signal, RISK)
    continuous(f'tenencia {name}, sin freno', hp, hold_signal, NOGUARD)

# ----------------------------------------------------------------------------- C
out('\n## C. Mas tiempo en mercado: hipotesis fijadas antes de correr (un valor + vecinos, sin grilla)')
out('\n- H1 tamano por volatilidad objetivo (Moskowitz/Ooi/Pedersen 2012; Harvey et al. 2018). Nota: con la config actual '
    'el tamano ya esta en el tope de 1x, asi que H1 solo puede BAJAR la exposicion; es una prueba de calidad, no de tiempo en mercado.')
out('- H2 entrada cuando el precio esta a menos de X% del maximo de 720h, no solo al romperlo (efecto de cercania al maximo, George & Hwang 2004). Es la unica que sube el tiempo en mercado.')
out('- H3 solo largos (deriva positiva estructural de BTC; los cortos pagan funding y sufren squeezes). Tampoco sube el tiempo en mercado.')
C = [('H3 solo largos', LongOnlyParams(**BASE), longonly_signal)]
C += [(f'H1 vol objetivo {tv:.0%}', VolTargetParams(**BASE, target_vol=tv), voltarget_signal) for tv in (0.2, 0.3, 0.4)]
C += [(f'H2 cerca del maximo {px:.0%}', NearHighParams(**BASE, proximity=px), nearhigh_signal) for px in (0.01, 0.03, 0.05)]
for sym in SYMS:
    out(f'\n**{sym}**\n\n{ROW_HEAD}\n{ROW_SEP}')
    base = run('orig', P, features, DATA[sym])
    out(row('v4_hourly original', base))
    for name, par, fn in C:
        out(row(name, run(name, par, fn, DATA[sym])))
    out(hodl_row(base))

# ----------------------------------------------------------------------------- D
out('\n## D. Re-verificacion con warmup correcto: stop_atr/reward y min_trend')


def wf_reselect(bars, keys):
    fixed = {k: run('g', HourlyParams(**{**BASE, **dict(k)}), features, bars) for k in keys}
    sim = build_sim(RISK)
    picks, ins = [], []
    for start, _ in test_windows(bars.index):
        ts = start - TRAIN
        seg = bars.loc[ts - WARMUP:start]
        best = None
        for k in keys:
            p = HourlyParams(**{**BASE, **dict(k)})
            eq, _t, _s = sim.run(seg, features(seg, p), p, RISK, start=ts, end=start)
            sh = sharpe_from_equity(eq, RISK.capital)
            if best is None or sh > best[0]:
                best = (sh, k)
        ins.append(best[0])
        picks.append(best[1])
    rows = [fixed[k].iloc[i] for i, k in enumerate(picks)]
    return fixed, pd.DataFrame(rows).reset_index(drop=True), np.array(ins)


G1 = [tuple(sorted({'stop_atr': a, 'reward': b, 'trail_atr': a if a > 3 else 3.0}.items()))
      for a in (2., 3., 4., 5.) for b in (2., 3., 4., 6.)]
G2 = [tuple({'min_trend': m}.items()) for m in (0., 0.005, 0.01, 0.02, 0.04)]
for label, grid, orig in [('stop_atr x reward', G1, {'stop_atr': 3., 'reward': 3., 'trail_atr': 3.}),
                          ('min_trend', G2, {'min_trend': 0.})]:
    for sym in SYMS:
        fixed, resel, ins = wf_reselect(DATA[sym], grid)
        out(f'\n**{label}, {sym}** (Sharpe mediana / ganancia total con cada valor fijo en las 14 ventanas)\n')
        out('| valores | Sharpe media | Sharpe mediana | ganancia total |')
        out('|---|---|---|---|')
        for k in grid:
            s = summarize(fixed[k])
            mark = ' **(produccion)**' if dict(k) == orig else ''
            out(f"| {dict(k)}{mark} | {s['sharpe_mean']:.2f} | {s['sharpe_median']:.2f} | {pct(s['total_ret'])} |")
        s = summarize(resel)
        so = summarize(fixed[[k for k in grid if dict(k) == orig][0]])
        c = np.corrcoef(ins, resel.sharpe)[0, 1]
        out(f"\nRe-eleccion por ventana (mejor Sharpe de los 365d previos): Sharpe {s['sharpe_mean']:.2f} / "
            f"{s['sharpe_median']:.2f}, ganancia {pct(s['total_ret'])}, corr(IS, OOS) = {c:.2f}. "
            f"Valor fijo de produccion: {so['sharpe_mean']:.2f} / {so['sharpe_median']:.2f}, {pct(so['total_ret'])}.")
        results[f'D_{label}_{sym}'] = {'resel': s, 'fixed_prod': so, 'corr': float(c)}

# ----------------------------------------------------------------------------- E
out('\n## E. Calibracion de impact_k')
out('\nFills reales con `_reference_price` registrados desde el despliegue del logging: **0** (el estado tiene 6 eventos, todos de la '
    'prueba manual del 15/9, anteriores al registro; no hubo ninguna entrada de estrategia). No hay base para calibrar; '
    'no se inventa un valor. Sensibilidad del resultado a impact_k (BTC, original, 14 ventanas):')
out('\n| impact_k | Sharpe media / mediana | ganancia total |')
out('|---|---|---|')
for k in (0.0, 1.0, 3.0, 10.0):
    s = summarize(run('orig', P, features, DATA['BTC'], impact_k=k))
    out(f"| {k} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {pct(s['total_ret'])} |")

# ----------------------------------------------------------------------------- F
out('\n## F. Mas periodos y activos')
out('\n**Ventanas adicionales.** Con parametros fijos no hace falta un ano de entrenamiento: las ventanas pueden empezar al '
    'terminar el warmup (250d). Eso suma ventanas de 2022 (mercado bajista). Aviso: los parametros de `selected.json` se eligieron '
    'con esta misma historia, asi que ninguna ventana es fuera de muestra en sentido estricto; esto mide estabilidad en el tiempo, '
    'no capacidad predictiva.')
for sym in SYMS:
    out(f'\n**{sym}**, ventanas de 90d desde el fin del warmup\n\n{ROW_HEAD}\n{ROW_SEP}')
    df = run('orig', P, features, DATA[sym], first=WARMUP)
    out(row('v4_hourly original', df))
    out(hodl_row(df))
out('\n**Sensibilidad a la definicion de ventana (BTC, original).**')
out(f'\n{ROW_HEAD}\n{ROW_SEP}')
for label, test, step, first in [('60d / paso 60d', 60, 60, 365), ('90d / paso 90d', 90, 90, 365),
                                  ('180d / paso 180d', 180, 180, 365), ('90d desfase +30d', 90, 90, 395),
                                  ('90d desfase +60d', 90, 90, 425)]:
    df = run('orig', P, features, DATA['BTC'], first=pd.Timedelta(days=first),
             test=pd.Timedelta(days=test), step=pd.Timedelta(days=step))
    out(row(label, df))

OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'tables.md').write_text('\n'.join(lines) + '\n')
(OUT / 'summary.json').write_text(json.dumps(results, indent=2, default=str))
print('written', OUT)
