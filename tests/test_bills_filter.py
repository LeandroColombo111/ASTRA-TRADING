"""Only transfer bills (type '1') feed the deposit adjustment, so the service asks OKX for only those. The filter is server-side and
optional in OKX.bills; the default (every type) is unchanged and pagination keeps working with the filter."""
import sys

import pytest

from astra.okx import OKX

sys.path.insert(0, 'tests')
from test_tick_consumption import NOW, TickOKX, make  # noqa: E402


class RecordingOKX(OKX):
    """Real OKX.bills code path with a scripted transport."""

    def __init__(self, pages):
        super().__init__(demo=True)
        self.pages = list(pages)
        self.requests = []

    def request(self, method, path, params=None, body=None, private=False):
        self.requests.append((path, dict(params or {})))
        return self.pages.pop(0)


def bill(i, kind='1', chg='10'):
    return {'billId': str(i), 'type': kind, 'balChg': chg, 'ts': '1'}


def test_default_bills_call_sends_no_type_filter():
    x = RecordingOKX([[bill(1)]])
    x.bills(1000)
    assert 'type' not in x.requests[0][1]


def test_bill_type_is_sent_to_okx_and_pagination_continues_with_it():
    full_page = [bill(i) for i in range(100)]
    x = RecordingOKX([full_page, [bill(200)]])
    out = x.bills(1000, bill_type='1')
    assert len(out) == 101
    assert [r[1]['type'] for r in x.requests] == ['1', '1']
    assert x.requests[1][1]['after'] == '99'


class CapturingOKX(TickOKX):
    def __init__(self):
        super().__init__()
        self.bill_args = []

    def bills(self, since_ms, bill_type=None):
        self.bill_args.append(bill_type)
        return []


def test_service_requests_only_transfer_bills_every_tick(tmp_path):
    client = CapturingOKX()
    service = make(tmp_path, client)
    service.s.save('inception_ms', 1_788_905_850_836)
    service.tick(NOW)
    assert client.bill_args == ['1']
