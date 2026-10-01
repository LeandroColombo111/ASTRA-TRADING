"""Diagnostico (NO backtest validado) de 'smart money': open interest, ratio long/short de cuentas y de grandes
traders, y volumen tomador comprador/vendedor, todo de los endpoints publicos de OKX. Limite real encontrado al
investigar: estos endpoints NO tienen historia profunda (se probo paginacion con 'after' y OKX devuelve siempre la
misma pagina, osea esta topeado del lado del servidor):
  - open-interest-history: 100 dias (desde 2026-06-24)
  - long-short-account-ratio: 180 dias (desde 2026-04-05)
  - taker-volume: 72 dias (desde 2026-07-22)
  - long-short-account-ratio-contract-top-trader: 100 dias (desde 2026-06-24)
Con 72 a 180 dias no se puede aplicar la metodologia del proyecto (warmup 250d, 14 ventanas de 90d, BTC/ETH/SOL).
Este script por lo tanto NO corre un backtest: mide correlaciones simples sobre la ventana disponible, a titulo
informativo, y lo dice explicitamente. Escribe reports/backtest2-v2/SMART_MONEY.md."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.backtest2.research import load_bars

RAW = Path('reports/backtest2-v2/raw_okx_stats')
lines = []


def out(s=''):
    print(s, flush=True)
    lines.append(s)


def load(name, cols):
    rows = json.loads((RAW / f'{name}.json').read_text())
    df = pd.DataFrame(rows, columns=cols)
    df['t'] = pd.to_datetime(df['ts'].astype('int64'), unit='ms', utc=True).dt.normalize()  # OKX daily stat rows are
    # timestamped at UTC+8 day-start (16:00 UTC); normalize to the calendar date for a clean daily join.
    df = df.drop(columns='ts').set_index('t').sort_index()
    return df.apply(pd.to_numeric)


out('# "Smart money": diagnostico de posicionamiento (OI, long/short, volumen tomador)\n')
out('**Esto NO es un backtest con la metodologia del proyecto.** Los endpoints publicos de OKX para open interest, '
    'ratio long/short y volumen tomador tienen muy poca historia (72 a 180 dias, topeados del lado del servidor; se '
    'confirmo probando la paginacion). Con eso no alcanza para warmup de 250 dias ni para 14 ventanas de 90 dias, y '
    'ni siquiera cubre un ciclo completo de mercado. Lo que sigue son correlaciones simples sobre la ventana '
    'disponible, para ver si hay algo que valga la pena seguir midiendo, NO una señal lista para usar.\n')

oi = load('open_interest_history_btc', ['ts', 'oi_contracts', 'oi_ccy', 'oi_usd'])
ls = load('long_short_account_ratio_btc', ['ts', 'ratio'])
tv = load('taker_volume_btc', ['ts', 'sell_vol', 'buy_vol'])
top = load('top_trader_long_short_btc', ['ts', 'top_ratio'])
bars = load_bars('BTC')
daily_close = bars.close.resample('1D').last()
daily_close.index = daily_close.index.normalize()
daily_ret = daily_close.pct_change()

out(f'Datos: OI {len(oi)} dias ({oi.index.min().date()} a {oi.index.max().date()}), ratio long/short cuentas {len(ls)} dias '
    f'({ls.index.min().date()} a {ls.index.max().date()}), top traders {len(top)} dias, volumen tomador {len(tv)} dias.\n')

out('## 1. El ratio long/short de cuentas retail, hoy, es contrarian o confirma la tendencia?\n')
out('Hipotesis "smart money" clasica: cuando el publico esta muy cargado de un lado (ratio extremo), suele ser señal '
    'de reversion, no de continuidad. Se mide la correlacion entre el ratio de HOY y el retorno del dia SIGUIENTE '
    '(para que sea causal, nunca mirar el futuro).\n')
j = pd.DataFrame({'ratio': ls['ratio'], 'ret_next': daily_ret.shift(-1)}).dropna()
out(f"- Observaciones: {len(j)} dias")
out(f"- Correlacion ratio(t) vs retorno(t+1): {j['ratio'].corr(j['ret_next']):.2f}")
j['extreme'] = pd.qcut(j['ratio'], 3, labels=['bajo (mas cortos)', 'medio', 'alto (mas largos)'])
g = j.groupby('extreme', observed=True)['ret_next'].agg(['mean', 'count'])
out('\n| ratio long/short (tercil) | retorno medio del dia siguiente | dias |')
out('|---|---|---|')
for idx, row in g.iterrows():
    out(f"| {idx} | {row['mean']*100:.2f}% | {int(row['count'])} |")

out('\n## 2. Variacion del open interest: confirma o contradice el movimiento del precio?\n')
out('Hipotesis clasica de futuros: precio sube + OI sube = posiciones nuevas entrando (conviccion real); precio sube '
    '+ OI baja = cierre de cortos (short covering, menos solido). Se mide sobre el mismo dia (no es una señal de '
    'entrada causal, es diagnostico de que paso).\n')
j2 = pd.DataFrame({'oi_chg': oi['oi_usd'].pct_change(), 'price_chg': daily_ret}).dropna()
out(f"- Correlacion variacion OI vs variacion precio (mismo dia): {j2['oi_chg'].corr(j2['price_chg']):.2f}")
up_oi_up_px = ((j2.oi_chg > 0) & (j2.price_chg > 0)).sum()
up_oi_dn_px = ((j2.oi_chg > 0) & (j2.price_chg < 0)).sum()
dn_oi_up_px = ((j2.oi_chg < 0) & (j2.price_chg > 0)).sum()
dn_oi_dn_px = ((j2.oi_chg < 0) & (j2.price_chg < 0)).sum()
out('\n| | precio sube | precio baja |')
out('|---|---|---|')
out(f"| OI sube | {up_oi_up_px} dias | {up_oi_dn_px} dias |")
out(f"| OI baja | {dn_oi_up_px} dias | {dn_oi_dn_px} dias |")

out('\n## 3. Volumen tomador: compradores vs vendedores agresivos\n')
out('Esto SI es order flow real (lado agresor), pero solo hay 72 dias. Se mide si el desbalance comprador/vendedor '
    'de HOY se relaciona con el retorno de MAÑANA.\n')
tv2 = tv.copy()
tv2['imbalance'] = (tv2['buy_vol'] - tv2['sell_vol']) / (tv2['buy_vol'] + tv2['sell_vol'])
j3 = pd.DataFrame({'imb': tv2['imbalance'], 'ret_next': daily_ret.shift(-1)}).dropna()
out(f"- Observaciones: {len(j3)} dias")
out(f"- Correlacion desbalance tomador(t) vs retorno(t+1): {j3['imb'].corr(j3['ret_next']):.2f}" if len(j3) > 5 else '- Muy pocas observaciones para correlacionar')

out('''
## Conclusion

Con 72 a 180 dias de historia ninguna de estas correlaciones es confiable: son 2 a 6 meses de un unico tramo de
mercado, sin ciclos alcistas y bajistas distintos, muy lejos del minimo que el proyecto exige en cualquier otro
hallazgo (14 ventanas de 90 dias, 3 activos, valores vecinos). No se puede ni sugerir una regla a partir de esto, y
mucho menos probarla con la disciplina habitual -- este diagnostico no reemplaza eso, solo muestra si hay algo
minimamente interesante para seguir acumulando.

**Camino recomendado si esto interesa:** empezar a archivar estos tres endpoints a diario (igual que se hizo con
`_reference_price` para calibrar el deslizamiento) y recien evaluar una regla real cuando haya 1 a 2 anos de historia
propia. Pedirle una señal de entrada a 2-6 meses de datos de un instrumento que ya mostro ser sensible a sobreajuste
con AÑOS de historia (ver reports/backtest2-v2/README.md y PURGED_CV.md) seria repetir el mismo error, agravado.
''')
Path('reports/backtest2-v2/SMART_MONEY.md').write_text('\n'.join(lines) + '\n')
