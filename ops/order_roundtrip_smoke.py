"""One-off manual test: exercise the REAL entry/close code path against the
OKX demo account, using a forced side/size instead of waiting for a real
strategy signal. Never touches strategy parameters or signal logic --
calls Service.submit() directly, the same function tick() calls once it
already knows the side.

Must be run with the production astra-demo container STOPPED (uses the
same demo.db state file the production service uses, so they must not
run concurrently -- the fcntl lock on Store would refuse a second opener
anyway, but stop the service first regardless).

Opens the smallest possible position, confirms both stop-loss and
take-profit triggers are visible on the exchange-confirmed algo order,
then closes it via the same close_position() path production uses.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, '/app/src')
from astra.engine import Risk
from astra.okx import OKX, load_env, entry_plan
from astra.service import Service, Store
from astra.v4_hourly import HourlyParams
from astra.v4_hourly import features as hourly_features

load_env('.env')

cfg = json.loads(Path('configs/selected.json').read_text())
params = HourlyParams(**cfg['params'])
risk = Risk(**cfg['risk'])

store = Store('state/demo.db')
client = OKX(demo=True)
svc = Service(client, store, params, risk, mode='demo', features_fn=hourly_features)

meta = client.instrument()
ticker = client.ticker()
price = float(ticker['last'])
equity = client.equity()

candles = client.candles()
prev = candles.close.shift(1)
tr = pd.concat([candles.high - candles.low, (candles.high - prev).abs(), (candles.low - prev).abs()], axis=1).max(axis=1)
atr = float(tr.ewm(alpha=1 / params.atr_period, adjust=False, min_periods=params.atr_period).mean().iloc[-1])

side = 1
now = pd.Timestamp.now(tz='UTC')
cid = 'astroundtriptest' + now.strftime('%H%M%S')
plan = entry_plan(meta, side, price, atr, params, risk, equity, cid)
print('=== ENTRY PLAN ===')
print(json.dumps(plan, indent=2))

print('=== SUBMITTING ENTRY (real demo order) ===')
svc.submit(plan, 'entry', now)
print('intent after submit:', store.get('intent'))
print('position after reconcile:', store.get('position'))

print('=== VERIFYING ON EXCHANGE ===')
positions = client.positions()
algos = client.algos()
print('positions:', json.dumps(positions, indent=2))
print('algos:', json.dumps(algos, indent=2))

protection = [a for a in algos if a['instId'] == 'BTC-USDT-SWAP' and a.get('algoClOrdId') == cid + 's']
assert protection, 'No protection algo order found on exchange'
assert protection[0].get('slTriggerPx'), 'slTriggerPx missing on confirmed algo order'
assert protection[0].get('tpTriggerPx'), 'tpTriggerPx missing on confirmed algo order'
print('CONFIRMED: both slTriggerPx and tpTriggerPx present on exchange-confirmed algo order.')
print('  slTriggerPx =', protection[0]['slTriggerPx'])
print('  tpTriggerPx =', protection[0]['tpTriggerPx'])

print('=== CLOSING POSITION (same code path as production) ===')
pos = positions[0]
svc.close_position(pos, 'manual_roundtrip_test', pd.Timestamp.now(tz='UTC'))
print('intent after close:', store.get('intent'))

print('=== FINAL EXCHANGE STATE ===')
print('positions:', client.positions())
print('pending:', client.pending())
print('algos:', client.algos())

store.close()
print('DONE')
