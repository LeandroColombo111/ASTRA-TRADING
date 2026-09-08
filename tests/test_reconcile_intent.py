"""reconcile_intent after a dirty crash. The highest-risk path in the service.

The smoke test could not exercise this: the strategy trades about 26 times a
year, so a crash during a live order is not something a fifteen-minute window
will produce. These tests drive it directly with a fake exchange client.

The property that matters is not that reconciliation succeeds. It is that an
order whose outcome is UNKNOWN is never resubmitted. A bot that retries a POST
it cannot confirm is a bot that doubles positions.
"""
import json

import pytest

from astra.engine import Risk
from astra.okx import ExchangeError
from astra.service import Service, Store
from astra.v4_hourly import HourlyParams
from astra.v4_hourly import features as hourly_features

INSTRUMENT = {'instId': 'BTC-USDT-SWAP', 'ctVal': '0.01', 'ctMult': '1',
              'lotSz': '0.01', 'minSz': '0.01', 'tickSz': '0.1'}


class FakeOKX:
    """Minimal stand-in. Records every write so tests can assert none happened."""

    demo = True
    base = 'https://openapi.okx.com'

    def __init__(self, order_response):
        self.order_response = order_response
        self.placed = []
        self.order_queries = []

    def instrument(self):
        return dict(INSTRUMENT)

    def config(self):
        return {'posMode': 'net_mode', 'acctLv': '2'}

    def request(self, method, path, params=None, body=None, private=False):
        if 'leverage-info' in path:
            return [{'lever': '2'}]
        raise AssertionError('Unexpected API call during reconciliation: ' + path)

    def order(self, client_id):
        self.order_queries.append(client_id)
        return dict(self.order_response)

    def place(self, body):
        self.placed.append(body)
        raise AssertionError('Reconciliation must never resubmit an order')


def make_service(tmp_path, order_response, intent=None):
    params = HourlyParams(**json.load(open('configs/selected.json'))['params'])
    risk = Risk(**json.load(open('configs/selected.json'))['risk'])
    store = Store(str(tmp_path / 'state.db'))
    if intent is not None:
        store.save('intent', intent)
    client = FakeOKX(order_response)
    service = Service(client, store, params, risk, mode='demo', features_fn=hourly_features)
    return service, store, client


ENTRY_INTENT = {'clOrdId': 'astdeadbeef0000000000000', 'kind': 'entry',
                'time': '2026-09-08 00:00:00+00:00', 'stop': '70000.0', 'target': '90000.0'}


def test_filled_entry_records_the_position_and_clears_the_intent(tmp_path):
    service, store, client = make_service(
        tmp_path, {'state': 'filled', 'accFillSz': '12', 'avgPx': '78000',
                   'fee': '-0.5', 'feeCcy': 'USDT'}, ENTRY_INTENT)
    service.reconcile_intent()
    position = store.get('position')
    assert position is not None, 'A filled entry must be recorded as an owned position'
    assert position['client_id'] == ENTRY_INTENT['clOrdId']
    assert position['stop'] == ENTRY_INTENT['stop']
    assert store.get('intent') is None, 'A resolved intent must be cleared'
    assert client.placed == []
    store.close()


def test_canceled_order_clears_the_intent_without_a_position(tmp_path):
    service, store, client = make_service(
        tmp_path, {'state': 'canceled', 'accFillSz': '0'}, ENTRY_INTENT)
    service.reconcile_intent()
    assert store.get('position') is None, 'A canceled order must not create a position'
    assert store.get('intent') is None
    assert client.placed == []
    store.close()


def test_filled_with_zero_fill_size_records_no_position(tmp_path):
    service, store, client = make_service(
        tmp_path, {'state': 'filled', 'accFillSz': '0'}, ENTRY_INTENT)
    service.reconcile_intent()
    assert store.get('position') is None
    assert store.get('intent') is None
    store.close()


@pytest.mark.parametrize('state', ['live', 'partially_filled'])
def test_incomplete_order_halts_and_never_resubmits(tmp_path, state):
    service, store, client = make_service(
        tmp_path, {'state': state, 'accFillSz': '5'}, ENTRY_INTENT)
    with pytest.raises(ExchangeError, match='manual reconciliation'):
        service.reconcile_intent()
    assert store.get('halted') is True, 'An incomplete order must halt the service'
    assert store.get('intent') is not None, (
        'The intent must survive so a human can reconcile it; clearing it would '
        'lose the record of an order that may still fill')
    assert client.placed == [], 'No resubmission is permitted'
    store.close()


def test_unknown_order_state_raises_and_never_resubmits(tmp_path):
    service, store, client = make_service(
        tmp_path, {'state': 'something_new_from_okx'}, ENTRY_INTENT)
    with pytest.raises(ExchangeError, match='Unknown order state'):
        service.reconcile_intent()
    assert store.get('intent') is not None
    assert client.placed == []
    store.close()


def test_no_intent_is_a_no_op(tmp_path):
    service, store, client = make_service(tmp_path, {'state': 'filled'}, intent=None)
    service.reconcile_intent()
    assert client.order_queries == [], 'With no intent the exchange must not be queried'
    assert client.placed == []
    store.close()


def test_exit_intent_does_not_create_a_position(tmp_path):
    exit_intent = {'clOrdId': 'astfeed0000000000000000f', 'kind': 'exit',
                   'time': '2026-09-08 00:00:00+00:00'}
    service, store, client = make_service(
        tmp_path, {'state': 'filled', 'accFillSz': '12'}, exit_intent)
    service.reconcile_intent()
    assert store.get('position') is None, 'An exit must never register a new position'
    assert store.get('intent') is None
    store.close()


def test_reconciliation_is_recorded_as_an_event(tmp_path):
    service, store, client = make_service(
        tmp_path, {'state': 'filled', 'accFillSz': '12', 'avgPx': '78000'}, ENTRY_INTENT)
    service.reconcile_intent()
    rows = store.db.execute("SELECT kind FROM events WHERE kind='order_reconciled'").fetchall()
    assert rows, 'Reconciliation must leave an audit trail'
    store.close()


def test_state_belongs_to_one_mode(tmp_path):
    """A state file carries a fingerprint of params, risk, mode and host."""
    params = HourlyParams(**json.load(open('configs/selected.json'))['params'])
    risk = Risk(**json.load(open('configs/selected.json'))['risk'])
    store = Store(str(tmp_path / 'state.db'))
    Service(FakeOKX({'state': 'filled'}), store, params, risk, mode='demo',
            features_fn=hourly_features)
    with pytest.raises(ValueError, match='different config/mode'):
        Service(FakeOKX({'state': 'filled'}), store, params, risk, mode='observe',
                features_fn=hourly_features)
    store.close()
