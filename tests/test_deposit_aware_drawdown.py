"""Service.tick() must track drawdown against deposit-adjusted equity, not
raw equity -- otherwise a deposit inflates the peak and can mask a real
loss on the pre-deposit capital (see accounting.py for the mechanics)."""
import json

import pandas as pd
import pytest

from astra.engine import Risk
from astra.service import Service, Store
from astra.v4_hourly import HourlyParams
from astra.v4_hourly import features as hourly_features

INSTRUMENT = {'instId': 'BTC-USDT-SWAP', 'ctVal': '0.01', 'ctMult': '1',
              'lotSz': '0.01', 'minSz': '0.01', 'tickSz': '0.1'}


class FakeOKX:
    demo = True
    base = 'https://openapi.okx.com'

    def __init__(self, equity_sequence, bills_by_call=None):
        self.equity_sequence = list(equity_sequence)
        self.bills_by_call = list(bills_by_call or [])
        self._equity_calls = 0
        self._bills_calls = 0

    def instrument(self):
        return dict(INSTRUMENT)

    def config(self):
        return {'posMode': 'net_mode', 'acctLv': '2'}

    def request(self, method, path, params=None, body=None, private=False):
        if 'leverage-info' in path:
            return [{'lever': '2'}]
        raise AssertionError('Unexpected API call: ' + path)

    def positions(self):
        return []

    def pending(self):
        return []

    def algos(self):
        return []

    def equity(self):
        e = self.equity_sequence[self._equity_calls]
        self._equity_calls += 1
        return e

    def bills(self, since_ms):
        b = self.bills_by_call[self._bills_calls] if self._bills_calls < len(self.bills_by_call) else []
        self._bills_calls += 1
        return b


def make_service(tmp_path, equity_sequence, bills_by_call=None):
    params = HourlyParams(**json.load(open('configs/selected.json'))['params'])
    risk = Risk(**json.load(open('configs/selected.json'))['risk'])
    store = Store(str(tmp_path / 'state.db'))
    client = FakeOKX(equity_sequence, bills_by_call)
    service = Service(client, store, params, risk, mode='demo', features_fn=hourly_features)

    def fake_market():
        idx = pd.DatetimeIndex([pd.Timestamp('2026-01-01', tz='UTC')])
        bars = pd.DataFrame({'open': [1.], 'high': [1.], 'low': [1.], 'close': [1.], 'volume': [1.]}, index=idx)
        f = pd.DataFrame({'signal': [0], 'anchor': [0], 'atr': [1.]}, index=idx)
        return bars, f

    service.market = fake_market
    return service, store, client


def test_first_tick_records_inception_markers(tmp_path):
    service, store, client = make_service(tmp_path, equity_sequence=[75000.0], bills_by_call=[[]])
    service.tick()
    assert store.get('inception_equity') == 75000.0
    assert store.get('inception_ms') is not None
    assert store.get('peak') == 75000.0
    assert store.get('halted') is False
    store.close()


def test_deposit_does_not_inflate_peak(tmp_path):
    service, store, client = make_service(
        tmp_path,
        equity_sequence=[75000.0, 85000.0],
        bills_by_call=[[], [{'ts': '1', 'balChg': '10000', 'type': '1'}]],
    )
    service.tick()  # inception at 75000
    service.tick()  # deposit of 10000 -> raw equity 85000
    assert store.get('peak') == 75000.0, 'A deposit must not raise the drawdown peak'
    assert store.get('halted') is False
    store.close()


def test_real_loss_after_deposit_still_halts(tmp_path):
    """The scenario the fix targets: peak=75000, deposit 10000 (raw equity
    85000), then the ORIGINAL capital loses exactly 25% while the deposit
    stays intact -> raw equity 66250, which sits ABOVE a naive 75%-of-85000
    (63750) halt line. Deposit-adjusted tracking must still catch it."""
    service, store, client = make_service(
        tmp_path,
        equity_sequence=[75000.0, 85000.0, 66250.0],
        bills_by_call=[[], [{'ts': '1', 'balChg': '10000', 'type': '1'}],
                        [{'ts': '1', 'balChg': '10000', 'type': '1'}]],
    )
    service.tick()  # inception
    service.tick()  # deposit
    service.tick()  # real 25% loss on original capital
    assert store.get('halted') is True, 'A real 25% loss on original capital must halt, deposit or not'
    store.close()


def test_withdrawal_does_not_trigger_false_halt(tmp_path):
    service, store, client = make_service(
        tmp_path,
        equity_sequence=[75000.0, 65000.0],
        bills_by_call=[[], [{'ts': '1', 'balChg': '-10000', 'type': '1'}]],
    )
    service.tick()  # inception at 75000
    service.tick()  # withdrawal of 10000 -> raw equity 65000, adjusted back to 75000
    assert store.get('halted') is False, 'A withdrawal must not read as a trading loss'
    assert store.get('peak') == 75000.0
    store.close()
