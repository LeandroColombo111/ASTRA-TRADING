"""How likely is it to lose the gains? Empirical rolling-year results plus block-bootstrap of the bot's own daily returns (BTC,
Binance 2020-05 -> 2026-08 and OKX 2022-09 -> 2026-08). Writes reports/backtest2-v2/LOSS_RISK.md. Not a forecast: history is the only input."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import build_sim, HOUR, load_bars, WARMUP

CFG = json.loads(Path('configs/selected.json').read_text())
P, RISK = HourlyParams(**CFG['params']), Risk(**CFG['risk'])
NOGUARD = Risk(**{**CFG['risk'], 'max_drawdown': 0.95})  # measure the raw risk, not the effect of the 25% halt
sim = build_sim(NOGUARD)
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


def binance():
    parts = []
    for f in ('data/BTCUSDT-2020-1h.csv', 'data/BTCUSDT-1h.csv'):
        b = pd.read_csv(f, index_col='time', parse_dates=True)
        b.index = pd.to_datetime(b.index, utc=True)
        parts.append(b)
    b = pd.concat(parts)
    return b[~b.index.duplicated()].sort_index()


def daily_returns(bars, start):
    eq, _, st = sim.run(bars, features(bars, P), P, NOGUARD, start=start, end=bars.index[-1] + HOUR)
    e = eq.copy()
    e.index = e.index - pd.Timedelta(nanoseconds=1)
    d = e.resample('1D').last().dropna()
    return d.pct_change().fillna(d.iloc[0] / NOGUARD.capital - 1)


def path_stats(r):
    w = np.cumprod(1 + r)
    peak = np.maximum.accumulate(np.r_[1., w])[1:]
    dd = (1 - w / peak).max()
    return w[-1] - 1, dd, w.max() - 1


def bootstrap(r, days=365, n=20000, block=20, seed=5):
    rng = np.random.default_rng(seed)
    r = np.asarray(r)
    rows = []
    for _ in range(n):
        idx = []
        while len(idx) < days:
            s = rng.integers(0, len(r))
            idx.extend(range(s, min(s + block, len(r))))
        rows.append(path_stats(r[np.array(idx[:days])]))
    a = np.array(rows)
    end, dd, peakgain = a[:, 0], a[:, 1], a[:, 2]
    up10 = peakgain >= 0.10
    return {
        'mean_year': float(end.mean()), 'median_year': float(np.median(end)), 'p05': float(np.quantile(end, .05)), 'p95': float(np.quantile(end, .95)),
        'p_loss': float((end < 0).mean()), 'p_below_5': float((end < .05).mean()),
        'dd_gt10': float((dd > .10).mean()), 'dd_gt20': float((dd > .20).mean()), 'dd_gt25': float((dd > .25).mean()),
        'p_reached_10': float(up10.mean()),
        'p_giveback_all_given_10': float((end[up10] <= 0).mean()) if up10.any() else float('nan'),
        'p_giveback_half_given_10': float((end[up10] <= 0.05).mean()) if up10.any() else float('nan')}


out('# Riesgo de perder las ganancias\n')
out('Se reconstruye el retorno diario del bot (configuracion congelada, sin el freno del 25% para medir el riesgo puro) y se simulan 20.000 anos '
    'posibles remuestreando bloques de 20 dias. Es historia reordenada, no un pronostico: si el futuro es peor que el pasado, estas cifras son optimistas.\n')
sources = {}
b = binance()
sources['BTC Binance 2020-05 a 2026-08 (6.3 anos, incluye 2020-2021 nuevos)'] = daily_returns(b, pd.Timestamp('2020-05-01', tz='UTC'))
o = load_bars('BTC')
sources['BTC OKX 2022-09 a 2026-08 (4 anos)'] = daily_returns(o, o.index[0] + WARMUP)
sources['BTC Binance 2020-05 a 2021-12 solo datos nuevos (1.7 anos)'] = daily_returns(b.loc[:'2022-01-01'], pd.Timestamp('2020-05-01', tz='UTC'))
for name, r in sources.items():
    yr = (1 + r).prod() ** (365 / len(r)) - 1
    out(f'\n## {name}\n')
    rolling = (1 + r).rolling(365).apply(np.prod, raw=True).dropna() - 1
    if len(rolling):
        out(f'- Retorno anual promedio de la serie: {pct(yr)}. Anos moviles de 365 dias (empirico, {len(rolling)} ventanas solapadas): '
            f'{pct((rolling < 0).mean())} terminan en perdida, peor {pct(rolling.min())}, mejor {pct(rolling.max())}.')
    if len(r) >= 365:
        s = bootstrap(r)
        out(f"- Simulacion (20.000 anos): retorno medio {pct(s['mean_year'])}, mediana {pct(s['median_year'])}, rango 90% [{pct(s['p05'])}, {pct(s['p95'])}].")
        out(f"- Probabilidad de terminar el ano en perdida: **{pct(s['p_loss'])}**; de ganar menos de 5%: {pct(s['p_below_5'])}.")
        out(f"- Probabilidad de una caida maxima dentro del ano mayor a 10%: {pct(s['dd_gt10'])}; mayor a 20%: {pct(s['dd_gt20'])}; mayor a 25% (el freno): {pct(s['dd_gt25'])}.")
        out(f"- De los anos que llegaron a estar +10% arriba en algun momento ({pct(s['p_reached_10'])} de los anos): terminaron en 0% o peor el "
            f"**{pct(s['p_giveback_all_given_10'])}** (devolvieron toda la ganancia) y en 5% o menos el {pct(s['p_giveback_half_given_10'])}.")
    else:
        out(f'- Solo {len(r)} dias: muy corto para una simulacion anual confiable.')

out('\n## Por ano calendario y por fase del ciclo de Bitcoin (BTC Binance, corrida continua desde 2020-05)\n')
out('Las fases del ciclo se marcaron a posteriori (fechas aproximadas de halvings y maximos/minimos): sirven para entender, no para operar, '
    'porque en tiempo real no se sabe en que fase se esta.\n')
px = b.close.loc['2020-05-01':]
eq_full, tr_full, _ = sim.run(b, features(b, P), P, NOGUARD, start=pd.Timestamp('2020-05-01', tz='UTC'), end=b.index[-1] + HOUR)
out('| periodo | bot | caida max | trades | BTC (comprar y mantener) |')
out('|---|---|---|---|---|')


def seg(label, a, z):
    a, z = pd.Timestamp(a, tz='UTC'), pd.Timestamp(z, tz='UTC')
    e, h = eq_full.loc[a:z], px.loc[a:z]
    w = e.to_numpy()
    n = sum(1 for t in tr_full if a <= pd.Timestamp(t['entry_time']) < z)
    out(f"| {label} | {pct(e.iloc[-1] / e.iloc[0] - 1)} | {pct((1 - w / np.maximum.accumulate(w)).max())} | {n} | {pct(h.iloc[-1] / h.iloc[0] - 1)} |")


for label, a, z in [('2020 (mayo-dic)', '2020-05-01', '2020-12-31'), ('2021', '2021-01-01', '2021-12-31'), ('2022', '2022-01-01', '2022-12-31'),
                    ('2023', '2023-01-01', '2023-12-31'), ('2024', '2024-01-01', '2024-12-31'), ('2025', '2025-01-01', '2025-12-31'),
                    ('2026 (ene-ago)', '2026-01-01', '2026-08-31'),
                    ('Fase: alza post-halving 2020-05 a 2021-11', '2020-05-11', '2021-11-10'), ('Fase: bajista 2021-11 a 2022-11', '2021-11-10', '2022-11-21'),
                    ('Fase: recuperacion 2022-11 a 2024-04', '2022-11-21', '2024-04-19'), ('Fase: post-halving y alza 2024-04 a 2025-10', '2024-04-20', '2025-10-06'),
                    ('Fase: correccion 2025-10 a 2026-08', '2025-10-06', '2026-08-31')]:
    seg(label, a, z)
out('''
Lectura: el bot termino en perdida en 2 de los 7 periodos anuales (2021 y 2024), coherente con el ~30% de la simulacion. Los malos periodos son las
expansiones alcistas volatiles (2021: -1.3%; 2024: -5.1%, y la fase 2024-04 a 2025-10: -11.9% con caida maxima de 26.7%, que habria activado el freno
del 25%). Los buenos son la recuperacion tras un minimo (2023: +30.9%) y las correcciones (2026: +22.7% en 8 meses). Solo hay ~1.5 ciclos de datos,
asi que las probabilidades tienen mucha incertidumbre, y el ciclo de 4 anos puede no repetirse igual.
''')
Path('reports/backtest2-v2/LOSS_RISK.md').write_text('\n'.join(lines) + '\n')
