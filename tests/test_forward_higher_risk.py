"""Offline tests for the higher-risk forward test: frozen configuration, the control run, and the in-place state file."""
import json
from datetime import date

import pandas as pd
import pytest

from astra import forward_higher_risk as fhr
from test_forward_smart_money import FakeArchive


def run_synthetic(tmp_path, now, **kw):
    arc = FakeArchive(last_published=(now - pd.Timedelta(days=1)).date(), **kw)
    return fhr.run(tmp_path, pre_reg_start=pd.Timestamp('2026-10-02 06:00', tz='UTC'), archive=arc, now=now)


def test_the_frozen_configuration_is_what_the_preregistration_says():
    assert fhr.RISK_FRACTION == 0.03 and fhr.MAX_DRAWDOWN == 0.40
    assert fhr.PRE_REG_START == pd.Timestamp('2026-10-02 06:00', tz='UTC')


def test_no_forward_evidence_right_after_pre_registration(tmp_path):
    r = run_synthetic(tmp_path, pd.Timestamp('2026-10-02 03:00', tz='UTC'))
    assert r['trades'] == 0 and r['equity_now'] == 10000. and r['control_2pct_dd25']['trades'] == 0
    assert r['risk_fraction'] == 0.03 and r['max_drawdown_limit'] == 0.40


def test_run_reports_the_main_run_and_the_control_on_the_same_data(tmp_path):
    r = run_synthetic(tmp_path, pd.Timestamp('2026-10-20 06:00', tz='UTC'))
    assert r['data_through'] == '2026-10-20 00:00:00+00:00'
    assert r['trades'] == len(r['trade_list'])
    assert 'equity_now' in r['control_2pct_dd25'] and r['control_2pct_dd25']['trades'] >= 0
    assert json.loads((tmp_path / 'state.json').read_text())['equity_now'] == r['equity_now']


def test_second_run_rewrites_the_file_and_appends_one_log_line(tmp_path):
    now = pd.Timestamp('2026-10-10 06:00', tz='UTC')
    run_synthetic(tmp_path, now)
    run_synthetic(tmp_path, now + pd.Timedelta(days=1))
    assert (tmp_path / 'log.csv').read_text().count('\n') == 3
    assert not list(tmp_path.glob('state.json.tmp'))


def test_a_hole_in_the_prices_fails_loudly_and_keeps_the_previous_state(tmp_path):
    run_synthetic(tmp_path, pd.Timestamp('2026-10-10 06:00', tz='UTC'))
    before = (tmp_path / 'state.json').read_text()
    arc = FakeArchive(last_published=date(2026, 10, 14), holes=[date(2026, 9, 20)])
    with pytest.raises(ValueError, match='gap'):
        fhr.run(tmp_path, pre_reg_start=pd.Timestamp('2026-10-02 06:00', tz='UTC'), archive=arc, now=pd.Timestamp('2026-10-15 06:00', tz='UTC'))
    assert (tmp_path / 'state.json').read_text() == before
