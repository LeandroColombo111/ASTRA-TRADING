"""Offline tests for the smart-money forward test: archive parsing, the monthly/daily fallback, hole detection (never
filled), funding, daily metrics and the end-to-end run against a synthetic 'Binance' archive."""
import io
import json
import zipfile
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from astra import forward_smart_money as fsm


def zipped(name, text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(name, text)
    return buf.getvalue()


def kline_rows(start, hours, header=False, unit='ms'):
    mult = 1000 if unit == 'ms' else 1_000_000
    lines = ['open_time,open,high,low,close,volume,close_time,quote_volume,count,tb,tq,ignore'] if header else []
    for k in range(hours):
        t = start + pd.Timedelta(hours=k)
        h = (t - pd.Timestamp('2026-01-01', tz='UTC')) / pd.Timedelta(hours=1)
        close = 50000 + 4000 * np.sin(h / 400.) + 150 * np.sin(h / 7.)
        lines.append(f'{int(t.timestamp()) * mult},{close - 20},{close + 60},{close - 60},{close},100.5,0,0,0,0,0,0')
    return '\n'.join(lines) + '\n'


def metrics_text(day, top=1.5, acct=1.0):
    rows = ['create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,'
            'sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio']
    for hh, val in ((0, 0.5), (12, 0.8), (23, 1.0)):
        rows.append(f'{day} {hh:02d}:00:00,BTCUSDT,1,1,1,{top * val},{acct},1')
    return '\n'.join(rows) + '\n'


class FakeArchive:
    """Binance-like archive generated on demand. monthly=False hides every monthly file (forces the daily path);
    holes are days whose daily kline file is missing; last_published is the newest day that exists."""

    def __init__(self, last_published, monthly=False, holes=(), header=False, unit='ms', top=1.5, funding_months=()):
        self.last_published, self.monthly, self.holes = last_published, monthly, set(holes)
        self.header, self.unit, self.top, self.funding_months = header, unit, top, set(funding_months)
        self.calls = []

    def fetch(self, rel):
        self.calls.append(rel)
        name = rel.rsplit('/', 1)[-1]
        if '/monthly/klines/' in '/' + rel:
            y, m = int(name[-11:-7]), int(name[-6:-4])
            if not self.monthly:
                return None
            first = date(y, m, 1)
            nxt = date(y + (m == 12), m % 12 + 1, 1)
            if nxt - timedelta(days=1) > self.last_published:
                return None
            return zipped(name[:-4] + '.csv', kline_rows(pd.Timestamp(first, tz='UTC'), 24 * (nxt - first).days, self.header, self.unit))
        if '/daily/klines/' in '/' + rel:
            d = date.fromisoformat(name[-14:-4])
            if d > self.last_published or d in self.holes:
                return None
            return zipped(name[:-4] + '.csv', kline_rows(pd.Timestamp(d, tz='UTC'), 24, self.header, self.unit))
        if '/daily/metrics/' in '/' + rel:
            d = date.fromisoformat(name[-14:-4])
            if d > self.last_published:
                return None
            return zipped(name[:-4] + '.csv', metrics_text(d, top=self.top))
        if '/monthly/fundingRate/' in '/' + rel:
            y, m = int(name[-11:-7]), int(name[-6:-4])
            if (y, m) not in self.funding_months:
                return None
            ts = int(pd.Timestamp(date(y, m, 28), tz='UTC').timestamp()) * 1000 + 8 * 3600 * 1000
            return zipped(name[:-4] + '.csv', f'calc_time,funding_interval_hours,last_funding_rate\n{ts},8,0.0001\n')
        return None


def test_parse_klines_tolerates_header_row_and_microsecond_timestamps():
    t0 = pd.Timestamp('2026-03-01', tz='UTC')
    for unit in ('ms', 'us'):
        df = fsm.parse_klines(zipped('k.csv', kline_rows(t0, 5, header=True, unit=unit)))
        assert list(df.index) == [t0 + pd.Timedelta(hours=k) for k in range(5)]
        assert list(df.columns) == ['open', 'high', 'low', 'close', 'volume']


def test_complete_month_uses_the_monthly_archive_and_current_month_uses_daily_files():
    arc = FakeArchive(last_published=date(2026, 4, 9), monthly=True)
    bars = fsm.load_bars(arc, date(2026, 3, 20), date(2026, 4, 9), today=date(2026, 4, 10))
    kinds = {'monthly' if '/' in c and c.startswith('monthly') else 'daily' for c in arc.calls if 'klines' in c}
    assert kinds == {'monthly', 'daily'}
    assert bars.index[0] == pd.Timestamp('2026-03-20', tz='UTC')           # trimmed to the requested start
    assert bars.index[-1] == pd.Timestamp('2026-04-09 23:00', tz='UTC')
    assert (bars.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all()


def test_falls_back_to_daily_files_when_the_monthly_archive_is_not_published_yet():
    arc = FakeArchive(last_published=date(2026, 4, 5), monthly=False)
    bars = fsm.load_bars(arc, date(2026, 3, 28), date(2026, 4, 5), today=date(2026, 4, 6))
    assert len(bars) == 9 * 24


def test_a_day_not_published_yet_at_the_end_just_ends_the_series():
    arc = FakeArchive(last_published=date(2026, 4, 3))
    bars = fsm.load_bars(arc, date(2026, 4, 1), date(2026, 4, 5), today=date(2026, 4, 6))
    assert bars.index[-1] == pd.Timestamp('2026-04-03 23:00', tz='UTC')


def test_a_missing_first_day_raises_instead_of_silently_shortening_the_warmup():
    arc = FakeArchive(last_published=date(2026, 4, 9), holes=[date(2026, 4, 1)])
    with pytest.raises(ValueError, match='does not start'):
        fsm.load_bars(arc, date(2026, 4, 1), date(2026, 4, 9), today=date(2026, 4, 10))


def test_a_hole_in_the_middle_raises_instead_of_being_filled():
    arc = FakeArchive(last_published=date(2026, 4, 9), holes=[date(2026, 4, 4)])
    with pytest.raises(ValueError, match='gap'):
        fsm.load_bars(arc, date(2026, 4, 1), date(2026, 4, 9), today=date(2026, 4, 10))


def test_funding_is_real_for_published_complete_months_and_zero_otherwise():
    arc = FakeArchive(last_published=date(2026, 4, 9), funding_months=[(2026, 3)])
    bars = fsm.load_bars(arc, date(2026, 3, 25), date(2026, 4, 9), today=date(2026, 4, 10))
    funding = fsm.load_funding(arc, bars, today=date(2026, 4, 10))
    assert funding.loc['2026-03-28 08:00'] == pytest.approx(0.0001)
    assert funding.loc['2026-04-01':].abs().sum() == 0.     # April is in progress: no archive, zeros, never invented
    assert len(funding) == len(bars)


def test_daily_metrics_take_the_last_snapshot_of_each_day_and_skip_missing_days():
    arc = FakeArchive(last_published=date(2026, 4, 3), top=2.0)
    m = fsm.load_metrics(arc, date(2026, 4, 1), date(2026, 4, 5))
    assert list(m.index.date) == [date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)]
    assert m['sum_toptrader_long_short_ratio'].iloc[0] == pytest.approx(2.0)   # last snapshot (23:00, factor 1.0)


def run_synthetic(tmp_path, now, top=1.5, **kw):
    arc = FakeArchive(last_published=(now - pd.Timedelta(days=1)).date(), top=top, **kw)
    return fsm.run(tmp_path, pre_reg_start=pd.Timestamp('2026-10-01 23:00', tz='UTC'), archive=arc, now=now), arc


def test_run_reports_no_forward_evidence_right_after_pre_registration(tmp_path):
    result, _ = run_synthetic(tmp_path, pd.Timestamp('2026-10-01 12:00', tz='UTC'))
    assert result['trades'] == 0 and result['equity_now'] == 10000. and result['forward_days'] == 0.
    assert json.loads((tmp_path / 'state.json').read_text())['trades'] == 0


def test_run_replays_the_forward_window_and_writes_state_without_touching_git(tmp_path):
    now = pd.Timestamp('2026-10-14 06:00', tz='UTC')
    result, arc = run_synthetic(tmp_path, now)
    assert result['data_through'] == '2026-10-14 00:00:00+00:00'
    assert result['forward_days'] == pytest.approx(12.04, abs=0.01)
    assert result['trades'] == len(result['trade_list'])
    saved = json.loads((tmp_path / 'state.json').read_text())
    assert saved['equity_now'] == result['equity_now']
    assert (tmp_path / 'log.csv').read_text().count('\n') == 2          # header + one run
    assert result['metrics_days_available'] >= 10


def test_a_second_run_rewrites_the_same_file_and_appends_one_log_line(tmp_path):
    now = pd.Timestamp('2026-10-05 06:00', tz='UTC')
    run_synthetic(tmp_path, now)
    run_synthetic(tmp_path, now + pd.Timedelta(days=1))
    assert (tmp_path / 'log.csv').read_text().count('\n') == 3
    assert not list(tmp_path.glob('state.json.tmp'))


def test_a_failed_run_leaves_the_previous_state_untouched(tmp_path):
    run_synthetic(tmp_path, pd.Timestamp('2026-10-05 06:00', tz='UTC'))
    before = (tmp_path / 'state.json').read_text()
    arc = FakeArchive(last_published=date(2026, 10, 9), holes=[date(2026, 9, 20)])
    with pytest.raises(ValueError, match='gap'):
        fsm.run(tmp_path, pre_reg_start=pd.Timestamp('2026-10-01 23:00', tz='UTC'), archive=arc,
                now=pd.Timestamp('2026-10-10 06:00', tz='UTC'))
    assert (tmp_path / 'state.json').read_text() == before


def test_the_frozen_configuration_is_what_the_preregistration_says():
    assert fsm.DIVERGENCE_MIN == 1.1
    assert fsm.PRE_REG_START == pd.Timestamp('2026-10-01 23:00', tz='UTC')
