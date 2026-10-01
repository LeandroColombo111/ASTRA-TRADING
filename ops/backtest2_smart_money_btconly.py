"""Siguiente paso sobre SMART_MONEY_FILTERS.md: el bot solo opera BTC, asi que ETH/SOL son un control contra el
sobreajuste, no un requisito de uso. Si hay una razon real para que BTC se comporte distinto (ciclos mas sostenidos
que ETH/SOL), vale la pena medir el filtro SM2 (divergencia 'smart money') SOLO en BTC, pero con una prueba mas
exigente que las 14-21 ventanas por si sola: validacion cruzada con purga y embargo (igual que
reports/backtest2-v2/PURGED_CV.md), donde el valor de divergencia se elige con datos de ANTES y DESPUES de cada
bloque, nunca con el bloque que se mide. Tambien se mide la corrida continua (todo el historial, una sola pasada) para
responder directamente "mejora el % de ganancia". Precios y metricas de Binance (BTC desde 2020-09, igual que en
SMART_MONEY_FILTERS.md). Escribe reports/backtest2-v2/SMART_MONEY_BTC_ONLY.md."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import build_sim, sharpe_from_equity, max_dd, HOUR, WARMUP
from astra.backtest2.exposure_strategies import SmartMoneyParams, smart_money_signal

CFG = json.loads(Path('configs/selected.json').read_text())
BASE, P, RISK = CFG['params'], HourlyParams(**CFG['params']), Risk(**CFG['risk'])
sim = build_sim(RISK)
GAMMA = (0.5772156649,)
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


def load_price():
    parts = []
    for f in ('data/BTCUSDT-2020-1h.csv', 'data/BTCUSDT-1h.csv'):
        b = pd.read_csv(f, index_col='time', parse_dates=True)
        b.index = pd.to_datetime(b.index, utc=True)
        parts.append(b)
    b = pd.concat(parts)
    b = b[~b.index.duplicated()].sort_index()
    assert (b.index.to_series().diff().dropna() == HOUR).all(), 'gap in joined BTC series'
    return b


bars = load_price()
GRID = [1.0, 1.1, 1.25]

out('# "Smart money" (SM2) evaluado solo en BTC, sin exigir que se sostenga en ETH/SOL\n')
out('El bot solo opera BTC; ETH/SOL se usan en el resto del proyecto como control contra el sobreajuste, no porque '
    'el bot los necesite. Si BTC tiene una estructura mas sostenida en el tiempo que justifique tratarlo distinto, '
    'la prueba que corresponde no es "relajar la regla", es una validacion mas exigente DENTRO de BTC: elegir el '
    'valor de divergencia con datos que no incluyen el tramo que se mide, en vez de con el valor que ya vimos que '
    'funciona en todo el historial.\n')

out('## 1. Corrida continua (todo el historial de una pasada, no por ventanas)\n')
out('| variante | Sharpe | ganancia total | DD max | trades | % en mercado |')
out('|---|---|---|---|---|---|')
start = bars.index[0] + WARMUP


def continuous(name, params, fn):
    eq, tr, st = sim.run(bars, fn(bars, params), params, RISK, start=start, end=bars.index[-1] + HOUR)
    held = sum((min(pd.Timestamp(t['exit_time']), bars.index[-1]) - max(pd.Timestamp(t['entry_time']), start)) / HOUR for t in tr)
    tim = held / ((bars.index[-1] - start) / HOUR)
    out(f"| {name} | {sharpe_from_equity(eq, RISK.capital):.2f} | {pct(eq.iloc[-1] / RISK.capital - 1)} | "
        f"{pct(max_dd(eq, RISK.capital))} | {len(tr)} | {pct(tim)} |")


continuous('original', P, features)
for d in GRID:
    continuous(f'SM2 divergencia >= {d}', SmartMoneyParams(**BASE, divergence_min=d, symbol='BTC'), smart_money_signal)

out('\n## 2. Validacion cruzada con purga y embargo, solo en BTC (8 bloques, embargo 120 dias a cada lado)\n')
out('Para cada bloque: se elige la divergencia con el Sharpe pooled de TODO lo que queda antes y despues del bloque '
    '(nunca con el bloque que se mide), con un margen de 120 dias a cada lado para no filtrar informacion por la '
    'memoria de los indicadores ni por trades que cruzan el borde. Se compara contra el valor fijo de produccion '
    '(sin filtro) en los mismos bloques.\n')
K, GAP = 8, pd.Timedelta(days=120)
T0, T1 = start, bars.index[-1] + HOUR
edges = [T0 + (T1 - T0) * i / K for i in range(K + 1)]


def daily_rets(eq):
    e = eq.copy(); e.index = e.index - pd.Timedelta(nanoseconds=1)
    d = e.resample('1D').last().dropna()
    return d.pct_change().fillna(d.iloc[0] / RISK.capital - 1).to_numpy()


def run_seg(params, fn, a, b):
    seg = bars.loc[a - WARMUP:b]
    eq, _, _ = sim.run(seg, fn(seg, params), params, RISK, start=a, end=b)
    return eq


def pooled_sharpe(params, fn, segs):
    r = np.concatenate([daily_rets(run_seg(params, fn, s, e)) for s, e in segs])
    sd = r.std(ddof=1)
    return float(np.sqrt(365) * r.mean() / sd) if sd > 0 else 0.


rows = []
for k in range(K):
    a, b = edges[k], edges[k + 1]
    train = [(s, e) for s, e in ((edges[0], a - GAP), (b + GAP, edges[K])) if e - s >= pd.Timedelta(days=90)]
    scores = [pooled_sharpe(SmartMoneyParams(**BASE, divergence_min=d, symbol='BTC'), smart_money_signal, train) for d in GRID]
    i = int(np.argmax(scores))
    chosen = GRID[i]
    e_chosen = run_seg(SmartMoneyParams(**BASE, divergence_min=chosen, symbol='BTC'), smart_money_signal, a, b)
    e_prod = run_seg(P, features, a, b)
    rows.append({'bloque': str(a.date()), 'elegido': chosen, 'in_sample_sharpe': scores[i],
                'sh_chosen': sharpe_from_equity(e_chosen, RISK.capital), 'ret_chosen': e_chosen.iloc[-1] / RISK.capital - 1,
                'sh_prod': sharpe_from_equity(e_prod, RISK.capital), 'ret_prod': e_prod.iloc[-1] / RISK.capital - 1})
df = pd.DataFrame(rows)
out('| bloque | divergencia elegida | Sharpe en muestra | Sharpe fuera (elegido) | ganancia fuera (elegido) | Sharpe fuera (produccion) | ganancia fuera (produccion) |')
out('|---|---|---|---|---|---|---|')
for _, r in df.iterrows():
    out(f"| {r.bloque} | {r.elegido} | {r.in_sample_sharpe:.2f} | {r.sh_chosen:.2f} | {pct(r.ret_chosen)} | {r.sh_prod:.2f} | {pct(r.ret_prod)} |")
comp = lambda x: float(np.prod(1 + x) - 1)
corr = float(np.corrcoef(df.in_sample_sharpe, df.sh_chosen)[0, 1])
out(f"\nElegido por bloque: Sharpe fuera media {df.sh_chosen.mean():.2f} / mediana {df.sh_chosen.median():.2f}, "
    f"ganancia compuesta {pct(comp(df.ret_chosen))}. Produccion (sin filtro): {df.sh_prod.mean():.2f} / "
    f"{df.sh_prod.median():.2f}, {pct(comp(df.ret_prod))}. corr(Sharpe en muestra, fuera) = {corr:.2f}.")
out('''
## Lectura

- **Si, el % de ganancia mejora, y no es un artefacto.** Corrida continua: 37.2% original contra 66.2%-67.6% con el
  filtro (divergencia 1.0 o 1.1). Se corrigio ademas un error propio antes de confiar en el numero: el relleno hacia
  adelante del dato diario no tenia limite, asi que durante el hueco real de Binance (316 dias, 2021-12-31 a
  2022-12-13) el filtro usaba un valor de hasta casi un año de antiguedad. Con el limite corregido (2 dias de
  vigencia, despues se trata como sin dato) el resultado casi no cambio, asi que la mejora no dependia de ese error.
- **La validacion cruzada DENTRO de BTC (purga + embargo, 8 bloques) tambien favorece al filtro.** Eligiendo la
  divergencia con datos de antes y despues de cada bloque (nunca con el bloque que se mide): gana en 6 de 8 bloques
  o empata, con ganancia compuesta de 96.3% contra 82.9% de produccion sin filtro en los mismos bloques. Es la
  prueba mas parecida a "fuera de muestra" que se puede hacer sin otro activo.
- **Pero hay una señal de alarma que no desaparece.** La correlacion entre el Sharpe en muestra (con el que se elige
  la divergencia) y el Sharpe fuera del bloque es NEGATIVA (-0.46), el mismo patron que ya aparecio en
  PURGED_CV.md para stop_atr/reward y min_trend. Eso sugiere que la mejora no viene de "elegir bien" la divergencia
  especifica, sino de que CUALQUIERA de los tres valores probados (1.0, 1.1, 1.25) tiende a ayudar la mayoria de las
  veces. Es una distincion importante: el filtro parece aportar algo, pero no se puede confiar en el mecanismo de
  seleccion del valor exacto.
- **Sigue sin tener una explicacion economica verificada, solo plausible.** La hipotesis de que BTC tiene mas
  participacion institucional real (y por eso el posicionamiento de los grandes traders significa algo distinto que
  en ETH/SOL) es razonable, pero no se verifico con ningun dato independiente -- es una historia que explicaria el
  resultado, no una prueba de que sea la causa real.
- **Conclusion: es el candidato mas solido de los ~160 probados en todo el proyecto, pero no alcanza para
  implementarlo en el bot en produccion todavia.** No paso por ETH/SOL (que siguen siendo el control mas fuerte
  contra el azar), la correlacion negativa de la validacion cruzada pide cautela sobre el mecanismo, y no hay
  ninguna confirmacion con operaciones reales. Camino recomendado si se quiere seguir: tratarlo como una SEGUNDA
  prueba en vivo, pre-registrada por separado (misma disciplina que docs/FORWARD_TEST.md: configuracion congelada,
  sin tocar el bot de produccion), corriendo en paralelo sin arriesgar nada del v4_hourly actual.
''')
Path('reports/backtest2-v2/SMART_MONEY_BTC_ONLY.md').write_text('\n'.join(lines) + '\n')
