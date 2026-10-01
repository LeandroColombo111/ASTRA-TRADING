"""Reads the status history CSVs (the VM's /opt/astra/status/history.csv, fetched with
gcloud compute scp; default ./history.csv) and reports the forward paper track record of the
FROZEN configuration: days, trades, daily-equity Sharpe, PSR and how long PSR>=0.95 would take. Read-only.
Usage: python3 ops/forward_track.py [--start 2026-09-18T17:05:00Z] [--history A.csv B.csv] [--write]"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.forward_test import psr, days_needed, daily_moments

ap = argparse.ArgumentParser()
ap.add_argument('--start', default='2026-09-18T17:05:00Z')
ap.add_argument('--history', nargs='+', default=['history.csv'])
ap.add_argument('--write', action='store_true')
a = ap.parse_args()
start = pd.Timestamp(a.start)


frames = [pd.read_csv(path, parse_dates=['t']) for path in a.history if Path(path).exists()]
df = pd.concat(frames).drop_duplicates('t').sort_values('t') if frames else pd.DataFrame(columns=['t', 'equity', 'order_intents', 'exit_reasons'])
df = df[df.t >= start]
days = (df.t.max() - start) / pd.Timedelta(days=1) if len(df) else 0.
# order_intent / exit_reason counts are cumulative in the bot's event log, so measure them relative to the first snapshot at or after the start
entries = int(df.order_intents.iloc[-1] - df.order_intents.iloc[0]) if len(df) else 0
exits = int(df.exit_reasons.iloc[-1] - df.exit_reasons.iloc[0]) if len(df) else 0
daily = df.set_index('t').equity.resample('1D').last().dropna()
ret = daily.pct_change().dropna().to_numpy()

lines = ['# Prueba en vivo (papel) con configuracion congelada\n',
         f'Desde {a.start}. Generado {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Fuente: {", ".join(a.history)}.\n',
         f'- Dias transcurridos: {days:.1f}', f'- Snapshots leidos: {len(df)}',
         f'- Ordenes de entrada registradas: {entries}; salidas: {exits}',
         f"- Equity demo: {df.equity.iloc[0]:,.0f} -> {df.equity.iloc[-1]:,.0f}" if len(df) else '- Sin snapshots todavia']
m = daily_moments(ret)
if m is None or entries == 0:
    lines.append('- Sharpe / PSR: sin datos suficientes (todavia no hubo operaciones que medir).')
else:
    sr, sk, ku, n = m
    p = psr(ret)
    lines += [f'- Sharpe anual observado: {sr * np.sqrt(365):.2f} ({n} dias)', f'- PSR (probabilidad de Sharpe real > 0, sin descuento por trials): {p:.2f}',
              f'- Dias de historial necesarios para PSR >= 0.95 si el Sharpe real fuera el observado: {days_needed(sr, sk, ku):,.0f}']
lines.append('\nHitos fijados en docs/FORWARD_TEST.md: 10 trades (chequeo de ejecucion), 30 trades (calibracion de impact_k y primera revision), 60 trades (evaluacion).')
text = '\n'.join(lines) + '\n'
print(text)
if a.write:
    Path('docs/FORWARD_TEST_PROGRESS.md').write_text(text)
