"""Rama de investigacion: filtros de entrada con 'smart money' (interes abierto, divergencia top traders vs cuentas
retail, desbalance de volumen tomador), ahora con AÑOS de historia en vez de 72-180 dias (ver
ops/download_binance_metrics.py: Binance publica estas metricas desde 2020-09 para BTC y 2021-12 para ETH/SOL,
verificado y bajado con checksum). Precios: series de Binance (mismo origen que las metricas, mismo disclaimer de
siempre: proxy de OKX, no OKX). Tres hipotesis fijadas antes de correr, cada una con un valor fijo y vecinos, nunca
una grilla barrida para elegir la mejor:
  SM1 interes abierto confirma el quiebre (entra solo si el OI subio en los ultimos N dias -- dinero nuevo entrando,
      no cierre de posiciones contrarias).
  SM2 divergencia 'smart money': los grandes traders mas cargados que el publico en la misma direccion del quiebre.
  SM3 volumen tomador confirma: compradores agresivos para largos, vendedores agresivos para cortos.
Aviso de datos: Binance tiene un hueco real de 316 dias (2021-12-31 a 2022-12-13) en las columnas de top traders y
volumen tomador (para ETH/SOL tambien en el ratio de cuentas). Nunca se rellena: esos dias quedan sin señal para los
filtros que dependen de esas columnas, igual que si no hubiera trade.
Escribe reports/backtest2-v2/SMART_MONEY_FILTERS.md."""
from pathlib import Path
import json
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.research import build_sim, evaluate, summarize, engine_variant, chained_maxdd, WARMUP
from astra.backtest2.exposure_strategies import (OpenInterestParams, oi_confirm_signal, SmartMoneyParams,
                                                  smart_money_signal, TakerFlowParams, taker_flow_signal,
                                                  load_binance_metrics)

CFG = json.loads(Path('configs/selected.json').read_text())
BASE, P, RISK = CFG['params'], HourlyParams(**CFG['params']), Risk(**CFG['risk'])
sim = build_sim(RISK)
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def pct(x): return f'{x * 100:.1f}%'


def load_price(symbol):
    files = {'BTC': ('data/BTCUSDT-2020-1h.csv', 'data/BTCUSDT-1h.csv'),
             'ETH': ('data/ETHUSDT-1h.csv',), 'SOL': ('data/SOLUSDT-1h.csv',)}[symbol]
    parts = []
    for f in files:
        b = pd.read_csv(f, index_col='time', parse_dates=True)
        b.index = pd.to_datetime(b.index, utc=True)
        parts.append(b)
    b = pd.concat(parts)
    b = b[~b.index.duplicated()].sort_index()
    assert (b.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all(), f'gap in {symbol} joined series'
    return b


SYMS = ['BTC', 'ETH', 'SOL']
PRICE = {s: load_price(s) for s in SYMS}
METRICS_START = {'BTC': pd.Timestamp('2020-09-01', tz='UTC'), 'ETH': pd.Timestamp('2021-12-01', tz='UTC'),
                 'SOL': pd.Timestamp('2021-12-01', tz='UTC')}


def windows_for(symbol):
    start = max(PRICE[symbol].index[0], METRICS_START[symbol]) + WARMUP
    end = PRICE[symbol].index[-1]
    out_ = []
    while start + pd.Timedelta(days=90) <= end:
        out_.append((start, start + pd.Timedelta(days=90)))
        start += pd.Timedelta(days=90)
    return out_


HEAD = ('| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | '
        'DD encadenado | % en mercado |\n|---|---|---|---|---|---|---|---|---|')


def row(name, df):
    s = summarize(df)
    return (f"| {name} | {s['n']} | {s['sharpe_mean']:.2f} / {s['sharpe_median']:.2f} | {s['ge_1_5']}/{s['n']} | {s['negative']} | "
            f"{pct(s['total_ret'])} | {pct(s['worst_window'])} | {pct(chained_maxdd(df))} | {pct(s['time_in_market'])} |")


out('# Filtros de "smart money" sobre años de historia (Binance: OI, top traders, volumen tomador)\n')
out('Precios de Binance (mismo origen que las metricas): BTC desde 2020-09-2 (uniendo los datos nuevos de 2020 con '
    'la serie principal), ETH desde 2021-12-01, SOL desde 2021-12-01 (limitado por donde arranca el precio de SOL '
    'en estos datos, 2022-05-01). Ventanas de 90 dias, calentamiento 250 dias, parametros fijos.\n')

out('## SM1: el interes abierto confirma el quiebre (sube junto con el precio)\n')
V1 = [(f'OI sube en {d}d', OpenInterestParams(**BASE, oi_days=d)) for d in (1, 3, 7)]
for sym in SYMS:
    bars = PRICE[sym]; w = windows_for(sym)
    out(f'\n**{sym}** ({len(w)} ventanas, desde {w[0][0].date()})\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), bars, RISK, windows=w)
    out(row('original', base))
    for name, par in V1:
        par = type(par)(**{**par.__dict__, 'symbol': sym})
        out(row(name, evaluate(engine_variant(name, par, oi_confirm_signal, sim, RISK), bars, RISK, windows=w)))
    sm = summarize(base)
    out(f"| HODL | {sm['n']} | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | "
        f"{pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")

out('\n## SM2: divergencia "smart money" (top traders mas cargados que el publico en la direccion del quiebre)\n')
out('Solo confiable desde ~2023-01 (antes el hueco de Binance deja sin datos el ratio de top traders o el de '
    'cuentas, segun el activo); las ventanas que caen antes se corren igual pero sin filtro disponible, nunca se '
    'inventa el dato.\n')
V2 = [(f'divergencia >= {d}', SmartMoneyParams(**BASE, divergence_min=d)) for d in (1.0, 1.1, 1.25)]
for sym in SYMS:
    bars = PRICE[sym]; w = windows_for(sym)
    out(f'\n**{sym}**\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), bars, RISK, windows=w)
    out(row('original', base))
    for name, par in V2:
        par = type(par)(**{**par.__dict__, 'symbol': sym})
        out(row(name, evaluate(engine_variant(name, par, smart_money_signal, sim, RISK), bars, RISK, windows=w)))
    sm = summarize(base)
    out(f"| HODL | {sm['n']} | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | "
        f"{pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")

out('\n## SM3: el volumen tomador (order flow real) confirma la direccion\n')
V3 = [(f'volumen tomador, media {d}d', TakerFlowParams(**BASE, flow_days=d)) for d in (1, 3, 7)]
for sym in SYMS:
    bars = PRICE[sym]; w = windows_for(sym)
    out(f'\n**{sym}**\n\n{HEAD}')
    base = evaluate(engine_variant('o', P, features, sim, RISK), bars, RISK, windows=w)
    out(row('original', base))
    for name, par in V3:
        par = type(par)(**{**par.__dict__, 'symbol': sym})
        out(row(name, evaluate(engine_variant(name, par, taker_flow_signal, sim, RISK), bars, RISK, windows=w)))
    sm = summarize(base)
    out(f"| HODL | {sm['n']} | {sm['hodl_sharpe_mean']:.2f} / {sm['hodl_sharpe_median']:.2f} | {sm['hodl_ge_1_5']}/{sm['n']} | - | "
        f"{pct(sm['hodl_total_ret'])} | {pct(sm['hodl_worst_window'])} | - | 100% |")

out('''
## Lectura

**Aviso sobre el baseline "original" de esta tabla:** no es el mismo que el de README.md (Sharpe 0.52/1.00, +56.5%
en BTC). Esas cifras usan 14 ventanas con precios de OKX desde 2022-01-17. Aca, para aprovechar los años extra de
metricas, se usan precios de Binance desde antes (BTC desde 2021-05, igual que en reports/backtest2-v2/CYCLE.md),
con mas ventanas (21 en vez de 14). Es el mismo bot, mismos parametros: la diferencia es solo que historia se
incluye, consistente con lo ya documentado en README.md ("Sensibilidad a la definicion de ventana").

- **SM1 (OI confirma el quiebre): no adoptar.** Mejora en BTC con 3-7 dias de ventana (Sharpe mediana 0.60-0.97
  contra 0.78) pero empeora con fuerza en ETH en los tres valores (-10.0% a 9.8% contra 18.7%) y en SOL es parejo
  sin ventaja clara. Falla la regla de sostenerse en los tres activos.
- **SM2 (divergencia "smart money" top traders vs retail): el mas interesante de los tres, y el mas peligroso.**
  A diferencia de casi todo lo probado hasta ahora, en BTC NO es un pico aislado: los tres valores vecinos (1.0,
  1.1, 1.25) mejoran de forma mas o menos pareja (ganancia 89.3% a 117.3% contra 54.5%, Sharpe mediana 0.97 a 1.51
  contra 0.78), con MENOS ventanas negativas (6-7 contra 8). Eso es justo el tipo de patron que en otras pruebas
  hubiera sido una señal de que vale la pena mirarlo mas. Pero falla duro en SOL (los tres valores dan perdida neta,
  -8.3% a -20.1%, Sharpe mediana negativo en los tres) y es debil e inconsistente en ETH (mejora con 1.0 y 1.1 pero
  se cae con 1.25). La regla del proyecto es clara: sin sostenerse en los tres activos, no se adopta, sin importar
  que tan prolijo se vea el patron en uno solo. Con cerca de 160 variantes probadas en total sobre BTC en todo el
  proyecto (ver recuento abajo), encontrar un patron que se ve bien en un activo por puro azar es exactamente lo
  esperable, no una sorpresa.
- **SM3 (volumen tomador confirma): no adoptar.** Resultado sin ningun patron entre activos ni entre valores
  vecinos (mejora con 1 dia en BTC y ETH pero empeora con 1 dia en SOL; se invierte con 7 dias). Ruido.
- **Recuento de comparaciones multiples:** esta ronda sumo unas 88 variantes nuevas evaluadas (37 de frecuencia, 24
  de VWAP, 27 de smart money) a las ~73 que ya existian, unas 160 en total sobre BTC en todo el proyecto. Cuantas
  mas se prueban, mas probable es encontrar algo que "se ve bien" en un solo activo sin ser real -- es la razon
  exacta por la que la regla de sostenerse en BTC, ETH y SOL a la vez no es negociable.
- **Conclusion: ninguna de las tres entra al bot.** La mas prometedora (SM2) queda documentada ya que, si en el
  futuro se junta mas historia de ETH/SOL o aparece una explicacion economica de por que fallaria justo en SOL, vale
  la pena revisarla -- pero hoy no pasa la validacion cruzada y no se adopta.
''')
Path('reports/backtest2-v2/SMART_MONEY_FILTERS.md').write_text('\n'.join(lines) + '\n')
