"""Reads the VM's published status history (docs/status/latest.json commits on origin/main) and reports the forward paper track record of the
FROZEN configuration: days, trades, daily-equity Sharpe, PSR and how long PSR>=0.95 would take. Read-only.
Usage: python3 ops/forward_track.py [--start 2026-09-18T17:05:00Z] [--write]"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from astra.forward_test import psr, days_needed, daily_moments

ap = argparse.ArgumentParser()
ap.add_argument('--start', default='2026-09-18T17:05:00Z')
ap.add_argument('--write', action='store_true')
a = ap.parse_args()
start = pd.Timestamp(a.start)


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


subprocess.run(['git', 'fetch', '-q'], check=False)
commits = [l.split('|') for l in git('log', 'origin/main', '--format=%H|%cI', '--since', a.start, '--', 'docs/status/latest.json').splitlines()]
rows, events = [], {}
for h, _ in commits:
    try:
        d = json.loads(git('show', f'{h}:docs/status/latest.json'))
    except Exception:
        continue
    st, ok = d.get('state') or {}, d.get('okx') or {}
    if not st or ok.get('equity') is None:
        continue
    t = pd.Timestamp(d['generated_at_utc'])
    rows.append({'t': t, 'equity': float(ok['equity']), 'events': st.get('events_total'), 'position': st['kv'].get('position')})
    for e in st.get('recent_events', []):
        events[(e[0], e[1])] = e
df = pd.DataFrame(rows).sort_values('t') if rows else pd.DataFrame(columns=['t', 'equity', 'events', 'position'])
df = df[df.t >= start]
days = (df.t.max() - start) / pd.Timedelta(days=1) if len(df) else 0.
exits = sum(1 for (ts, kind) in events if kind == 'exit_reason' and pd.Timestamp(ts) >= start)
entries = sum(1 for (ts, kind) in events if kind == 'order_intent' and pd.Timestamp(ts) >= start)
daily = df.set_index('t').equity.resample('1D').last().dropna()
ret = daily.pct_change().dropna().to_numpy()

lines = ['# Prueba en vivo (papel) con configuracion congelada\n',
         f'Desde {a.start}. Generado {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Fuente: historial de docs/status/latest.json.\n',
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
