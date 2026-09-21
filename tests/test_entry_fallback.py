"""Entry ladder: post-only -> (rejected) -> post-only at a fresh quote -> (rejected) -> market, capped at 0.3% from the signal price.
Only OKX's post-only rejection (cancelSource 31) triggers it; a resting order that stays unfilled is cancelled and never chased."""
import time

import pandas as pd

from test_maker_entry import FakeOKX, make_service

CLOSED = pd.Timestamp('2026-09-21 08:00', tz='UTC')
SIGNAL = 83746.9


class LadderOKX(FakeOKX):
    """outcomes[i] scripts what OKX reports for the i-th placed order; quotes are consumed by ticker()."""

    def __init__(self, outcomes, quotes=()):
        super().__init__(['filled'])
        self.outcomes = list(outcomes)
        self.quotes = list(quotes)

    def order(self, client_id):
        idx = [b['clOrdId'] for b in self.placed].index(client_id)
        state, source = self.outcomes[idx]
        return {'state': state, 'cancelSource': source, 'accFillSz': '72' if state == 'filled' else '0',
                'avgPx': '83742.2', 'fee': '-1', 'feeCcy': 'USDT'}

    def ticker(self):
        ask, bid = self.quotes.pop(0)
        return {'askPx': str(ask), 'bidPx': str(bid), 'ts': str(int(time.time() * 1000))}


def run(tmp_path, outcomes, quotes):
    service, store, client = make_service(tmp_path, ['filled'])
    client = LadderOKX(outcomes, quotes)
    service.x = client
    service.enter_with_fallback(1, CLOSED, 300., 10000., SIGNAL, (SIGNAL, 83742.2))
    return service, store, client


def test_first_post_only_fills_no_ladder(tmp_path):
    _, store, client = run(tmp_path, [('filled', None)], [])
    assert [b['ordType'] for b in client.placed] == ['post_only']
    assert store.get('position') is not None


def test_rejected_once_then_post_only_at_fresh_quote_fills(tmp_path):
    _, store, client = run(tmp_path, [('canceled', '31'), ('filled', None)], [(SIGNAL + 2, SIGNAL - 3)])
    assert [b['ordType'] for b in client.placed] == ['post_only', 'post_only']
    assert client.placed[1]['px'] == str(SIGNAL - 3)  # re-quoted at the new touch
    assert len({b['clOrdId'] for b in client.placed}) == 2
    assert store.get('position') is not None


def test_rejected_twice_falls_back_to_market(tmp_path):
    _, store, client = run(tmp_path, [('canceled', '31'), ('canceled', '31'), ('filled', None)],
                           [(SIGNAL + 2, SIGNAL - 3), (SIGNAL + 5, SIGNAL - 1)])
    assert [b['ordType'] for b in client.placed] == ['post_only', 'post_only', 'market']
    assert 'px' not in client.placed[2]
    assert client.placed[2]['attachAlgoOrds'], 'the market fallback keeps its stop/target protection'
    assert store.get('position') is not None


def test_does_not_chase_when_price_moved_more_than_cap(tmp_path):
    moved = SIGNAL * 1.004  # 0.4% away > 0.3% cap
    _, store, client = run(tmp_path, [('canceled', '31')], [(moved, moved - 5)])
    assert len(client.placed) == 1
    assert store.get('position') is None and store.get('intent') is None


def test_cap_also_applies_before_the_market_fallback(tmp_path):
    moved = SIGNAL * 1.004
    _, store, client = run(tmp_path, [('canceled', '31'), ('canceled', '31')], [(SIGNAL + 1, SIGNAL - 1), (moved, moved - 5)])
    assert [b['ordType'] for b in client.placed] == ['post_only', 'post_only']
    assert store.get('position') is None


def test_other_cancellations_do_not_trigger_the_ladder(tmp_path):
    _, store, client = run(tmp_path, [('canceled', '1')], [(SIGNAL, SIGNAL - 1)])
    assert len(client.placed) == 1
    assert store.get('position') is None
