"""A closed candle must be consumed only after every READ of a tick succeeded and before the first exchange WRITE.
Reads that fail (transient OKX errors) must retry the same candle on the next tick, inside the 2-minute entry window;
once an order may have been sent, a crash must never re-enter the same candle."""
import json
import sys
import time

import pandas as pd
import pytest

from astra.engine import Risk
from astra.okx import ExchangeError
from astra.service import Service, Store
from astra.v4_hourly import HourlyParams
from astra.v4_hourly import features as hourly_features

sys.path.insert(0, 'tests')
from test_maker_entry import FakeOKX  # noqa: E402

CLOSED = pd.Timestamp('2026-09-24 10:00', tz='UTC')
NOW = CLOSED + pd.Timedelta(seconds=20)
CLOSE_PX = 83000.


class TickOKX(FakeOKX):
    """Reads can be scripted to fail once; writes are recorded. order() reports the entry as filled."""

    def __init__(self, fail_once=None, fail_place=False, order_state='filled'):
        super().__init__([order_state])
        self.fail_once = set([fail_once] if isinstance(fail_once, str) else (fail_once or ()))
        self.fail_place = fail_place
        self.calls = []

    def _read(self, name, value):
        self.calls.append(name)
        if name in self.fail_once:
            self.fail_once.discard(name)
            raise ExchangeError('OKX HTTP 503 on /api/v5/' + name)
        return value

    def positions(self): return self._read('positions', [])
    def equity(self): return self._read('equity', 10000.)
    def bills(self, since_ms, bill_type=None): return self._read('bills', [])
    def pending(self): return self._read('pending', [])
    def algos(self): return self._read('algos', [])

    def ticker(self):
        self.calls.append('ticker')
        if 'ticker' in self.fail_once:
            self.fail_once.discard('ticker')
            raise ExchangeError('OKX HTTP 503 on /api/v5/ticker')
        return {'askPx': str(CLOSE_PX + 2), 'bidPx': str(CLOSE_PX - 2), 'last': str(CLOSE_PX),
                'ts': str(int(NOW.timestamp() * 1000))}

    def place(self, body):
        if self.fail_place:
            self.fail_place = False
            self.placed.append(body)
            raise ExchangeError('OKX transport failure on /api/v5/trade/order')
        return super().place(body)


def make(tmp_path, client):
    cfg = json.load(open('configs/selected.json'))
    service = Service(client, Store(str(tmp_path / 's.db')), HourlyParams(**cfg['params']), Risk(**cfg['risk']),
                      mode='demo', features_fn=hourly_features)
    idx = pd.date_range(end=CLOSED - pd.Timedelta(hours=1), periods=50, freq='h', tz='UTC')
    bars = pd.DataFrame({'open': CLOSE_PX, 'high': CLOSE_PX + 50, 'low': CLOSE_PX - 50, 'close': CLOSE_PX, 'volume': 1e5}, index=idx)
    feats = pd.DataFrame({'signal': 0, 'anchor': 1, 'atr': 600.}, index=idx)
    feats.iloc[-1, feats.columns.get_loc('signal')] = 1  # a real long signal on the candle that just closed
    service.market = lambda: (bars, feats)
    service.s.save('last_closed', str(CLOSED - pd.Timedelta(hours=1)))
    return service


@pytest.mark.parametrize('failing_read', ['positions', 'equity', 'bills', 'pending', 'algos', 'ticker'])
def test_failed_read_retries_the_same_candle_and_still_enters(tmp_path, failing_read):
    client = TickOKX(fail_once=failing_read)
    service = make(tmp_path, client)
    with pytest.raises(ExchangeError):
        service.tick(NOW)
    assert service.s.get('last_closed') == str(CLOSED - pd.Timedelta(hours=1)), 'a failed read must not consume the candle'
    assert client.placed == []
    service.tick(NOW + pd.Timedelta(seconds=10))          # next tick, still inside the 2-minute window
    assert len(client.placed) == 1 and client.placed[0]['side'] == 'buy'
    assert service.s.get('last_closed') == str(CLOSED)


def test_candle_is_consumed_before_the_first_write_so_a_crash_never_double_enters(tmp_path):
    client = TickOKX(fail_place=True, order_state='canceled')  # the POST never reached OKX
    service = make(tmp_path, client)
    with pytest.raises(ExchangeError):
        service.tick(NOW)                                  # the POST failed after being sent
    assert len(client.placed) == 1
    assert service.s.get('last_closed') == str(CLOSED), 'candle must already be consumed once an order may be in flight'
    try:
        service.tick(NOW + pd.Timedelta(seconds=10))
    except ExchangeError:
        pass                                               # the open intent may legitimately block the next tick
    assert len(client.placed) == 1, 'the same candle must never be entered twice'


def test_normal_tick_enters_exactly_once(tmp_path):
    client = TickOKX()
    service = make(tmp_path, client)
    service.tick(NOW)
    assert len(client.placed) == 1 and service.s.get('last_closed') == str(CLOSED)


def test_error_detail_logs_only_sanitised_error_types():
    import sqlite3
    from astra.okx import AmbiguousOrder
    from astra.service import error_detail
    assert error_detail(ExchangeError('OKX HTTP 503 on /api/v5/x')) == ': OKX HTTP 503 on /api/v5/x'
    assert error_detail(AmbiguousOrder('OKX transport failure on /api/v5/trade/order')).startswith(': OKX transport failure')
    assert error_detail(sqlite3.OperationalError('database is locked')) == ': database is locked'
    assert error_detail(KeyError('OK-ACCESS-KEY')) == '' and error_detail(ValueError('secret-token')) == ''
    assert len(error_detail(ExchangeError('x' * 1000))) == 202
