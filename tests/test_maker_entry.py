"""Post-only (maker) entries do not resolve instantly like a market order:
they can sit 'live' waiting for price to come to them. reconcile_intent()
treats a 'live' order as a crash-recovery emergency requiring a human --
correct for a market order, wrong for a maker order that's simply resting.

submit_maker_entry() must absorb that difference itself: wait a bounded
time for a natural fill, and if it's still resting, cancel it -- so that by
the time reconcile_intent() (never modified) looks at the order, it is
already in a terminal state that function already knows how to handle.
"""
import json

import pandas as pd
import pytest

from astra.engine import Risk
from astra.service import Service, Store
from astra.v4_hourly import HourlyParams
from astra.v4_hourly import features as hourly_features

INSTRUMENT = {'instId': 'BTC-USDT-SWAP', 'ctVal': '0.01', 'ctMult': '1',
              'lotSz': '0.01', 'minSz': '0.01', 'tickSz': '0.1'}

BODY = {'instId': 'BTC-USDT-SWAP', 'tdMode': 'isolated', 'posSide': 'net', 'clOrdId': 'astmakertest0000000000',
        'side': 'buy', 'ordType': 'post_only', 'sz': '0.1', 'px': '77950',
        'attachAlgoOrds': [{'attachAlgoClOrdId': 'astmakertest0000000000s', 'slTriggerPx': '75000',
                            'slOrdPx': '-1', 'slTriggerPxType': 'last', 'tpTriggerPx': '85000',
                            'tpOrdPx': '-1', 'tpTriggerPxType': 'last'}]}


class FakeOKX:
    """order() replays a scripted sequence of states, one per call (holds the
    last entry once exhausted). cancel_order() can advance to a different
    post-cancel sequence, to simulate the race where a fill lands right as
    we try to cancel."""
    demo = True
    base = 'https://openapi.okx.com'

    def __init__(self, states, post_cancel_states=None):
        self.states = list(states)
        self.post_cancel_states = list(post_cancel_states or ['canceled'])
        self.placed = []
        self.cancelled = []

    def instrument(self):
        return dict(INSTRUMENT)

    def config(self):
        return {'posMode': 'net_mode', 'acctLv': '2'}

    def request(self, method, path, params=None, body=None, private=False):
        if 'leverage-info' in path:
            return [{'lever': '2'}]
        raise AssertionError('Unexpected API call: ' + path)

    def place(self, body):
        self.placed.append(body)
        return {'sCode': '0'}

    def order(self, client_id):
        if self.cancelled:
            state = self.post_cancel_states.pop(0) if len(self.post_cancel_states) > 1 else self.post_cancel_states[0]
        else:
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {'state': state, 'accFillSz': '10' if state in ('filled', 'partially_filled') else '0',
                'avgPx': '77950', 'fee': '-0.5', 'feeCcy': 'USDT'}

    def cancel_order(self, client_id):
        self.cancelled.append(client_id)
        return {'sCode': '0'}


def make_service(tmp_path, states, post_cancel_states=None):
    params = HourlyParams(**json.load(open('configs/selected.json'))['params'])
    risk = Risk(**json.load(open('configs/selected.json'))['risk'])
    store = Store(str(tmp_path / 'state.db'))
    client = FakeOKX(states, post_cancel_states)
    service = Service(client, store, params, risk, mode='demo', features_fn=hourly_features)
    return service, store, client


def test_immediate_fill_never_cancels(tmp_path, monkeypatch):
    monkeypatch.setattr('time.sleep', lambda s: None)
    service, store, client = make_service(tmp_path, states=['filled'])
    service.submit_maker_entry(dict(BODY), pd.Timestamp('2026-01-01', tz='UTC'))
    assert client.cancelled == []
    assert store.get('position') is not None
    assert store.get('intent') is None


def test_unfilled_after_timeout_cancels_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr('time.sleep', lambda s: None)
    service, store, client = make_service(tmp_path, states=['live'], post_cancel_states=['canceled'])
    service.submit_maker_entry(dict(BODY), pd.Timestamp('2026-01-01', tz='UTC'), poll_attempts=3)
    assert client.cancelled == [BODY['clOrdId']]
    assert store.get('position') is None  # entry skipped, not recorded
    assert store.get('intent') is None
    assert store.get('halted') is not True


def test_fill_races_the_cancel(tmp_path, monkeypatch):
    """A fill can land in the instant we try to cancel. reconcile_intent
    must still record the position correctly, not silently drop it."""
    monkeypatch.setattr('time.sleep', lambda s: None)
    service, store, client = make_service(tmp_path, states=['live'], post_cancel_states=['filled'])
    service.submit_maker_entry(dict(BODY), pd.Timestamp('2026-01-01', tz='UTC'), poll_attempts=3)
    assert client.cancelled == [BODY['clOrdId']]
    assert store.get('position') is not None
    assert store.get('intent') is None


def test_still_ambiguous_after_cancel_halts(tmp_path, monkeypatch):
    """If even the post-cancel state is not a terminal one reconcile_intent
    recognizes, it must halt exactly as it already does for a market order
    -- this test exists to confirm reconcile_intent() itself was NOT
    weakened to accommodate maker entries."""
    monkeypatch.setattr('time.sleep', lambda s: None)
    service, store, client = make_service(tmp_path, states=['live'], post_cancel_states=['live'])
    with pytest.raises(Exception, match='Order incomplete'):
        service.submit_maker_entry(dict(BODY), pd.Timestamp('2026-01-01', tz='UTC'), poll_attempts=3)
    assert store.get('halted') is True
