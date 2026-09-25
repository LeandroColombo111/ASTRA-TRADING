"""The service must halt and close the position if EITHER the stop-loss or
the take-profit trigger is missing from the confirmed protection algo order,
not just the stop. Both travel in the same attachAlgoOrds call (okx.py's
entry_plan), so in practice they should always arrive together -- but the
guard exists specifically for the case where they don't, and it must not
have a blind spot for either leg."""
import json

import pandas as pd
import pytest

from astra.engine import Risk
from astra.service import Service, Store
from astra.v4_hourly import HourlyParams
from astra.v4_hourly import features as hourly_features

INSTRUMENT = {'instId': 'BTC-USDT-SWAP', 'ctVal': '0.01', 'ctMult': '1',
              'lotSz': '0.01', 'minSz': '0.01', 'tickSz': '0.1'}

OWNED_POSITION = {'client_id': 'astdeadbeef0000000000000', 'opened': '2026-01-01 00:00:00+00:00',
                   'stop': '70000.0', 'target': '90000.0', 'entry': 78000.0,
                   'initial_distance': 8000.0, 'peak_favorable_r': 0.}

EXCHANGE_POSITION = {'instId': 'BTC-USDT-SWAP', 'posSide': 'net', 'mgnMode': 'isolated',
                      'pos': '10', 'posId': 'pos1'}


class FakeOKX:
    demo = True
    base = 'https://openapi.okx.com'

    def __init__(self, algos):
        self._algos = algos
        self.placed = []

    def instrument(self):
        return dict(INSTRUMENT)

    def config(self):
        return {'posMode': 'net_mode', 'acctLv': '2'}

    def request(self, method, path, params=None, body=None, private=False):
        if 'leverage-info' in path:
            return [{'lever': '2'}]
        raise AssertionError('Unexpected API call: ' + path)

    def positions(self):
        return [dict(EXCHANGE_POSITION)]

    def pending(self):
        return []

    def algos(self):
        return self._algos

    def equity(self):
        return 75000.0

    def bills(self, since_ms, bill_type=None):
        return []

    def place(self, body):
        self.placed.append(body)
        return {'sCode': '0'}

    def order(self, client_id):
        return {'state': 'filled', 'accFillSz': '10', 'avgPx': '78000',
                'fee': '-0.5', 'feeCcy': 'USDT'}


def make_service(tmp_path, algos):
    params = HourlyParams(**json.load(open('configs/selected.json'))['params'])
    risk = Risk(**json.load(open('configs/selected.json'))['risk'])
    store = Store(str(tmp_path / 'state.db'))
    store.save('position', dict(OWNED_POSITION))
    client = FakeOKX(algos)
    service = Service(client, store, params, risk, mode='demo', features_fn=hourly_features)

    def fake_market():
        idx = pd.DatetimeIndex([pd.Timestamp('2026-01-02', tz='UTC')])
        bars = pd.DataFrame({'open': [1.], 'high': [1.], 'low': [1.], 'close': [1.], 'volume': [1.]}, index=idx)
        f = pd.DataFrame({'signal': [0], 'anchor': [1], 'atr': [1.]}, index=idx)
        return bars, f

    service.market = fake_market
    return service, store, client


def protection(sl='75000', tp='85000'):
    entry = {'instId': 'BTC-USDT-SWAP', 'algoClOrdId': OWNED_POSITION['client_id'] + 's'}
    if sl is not None:
        entry['slTriggerPx'] = sl
    if tp is not None:
        entry['tpTriggerPx'] = tp
    return [entry]


def test_both_triggers_present_does_not_halt(tmp_path):
    service, store, client = make_service(tmp_path, protection(sl='75000', tp='85000'))
    service.tick()
    assert store.get('halted') is False
    assert client.placed == []


def test_missing_stop_halts_and_closes(tmp_path):
    service, store, client = make_service(tmp_path, protection(sl=None, tp='85000'))
    with pytest.raises(Exception, match='Missing confirmed protection'):
        service.tick()
    assert store.get('halted') is True
    assert len(client.placed) == 1, 'must submit a closing order'


def test_missing_take_profit_halts_and_closes(tmp_path):
    """This is the gap: previously only slTriggerPx was checked, so a fill
    that lost its take-profit leg while keeping the stop would go
    undetected."""
    service, store, client = make_service(tmp_path, protection(sl='75000', tp=None))
    with pytest.raises(Exception, match='Missing confirmed protection'):
        service.tick()
    assert store.get('halted') is True
    assert len(client.placed) == 1, 'must submit a closing order'


def test_no_protection_at_all_halts_and_closes(tmp_path):
    service, store, client = make_service(tmp_path, [])
    with pytest.raises(Exception, match='Missing confirmed protection'):
        service.tick()
    assert store.get('halted') is True
    assert len(client.placed) == 1
