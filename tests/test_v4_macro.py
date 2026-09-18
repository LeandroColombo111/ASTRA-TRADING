"""The macro-gated v4 family: parity with the research code, entry-only gating, and fail-loud history."""
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from astra.engine import Risk
from astra.service import strategy_for, backtest_for
from astra.v4_hourly import features as hourly_features
from astra.v4_macro import MacroHourlyParams, features, macro_trend
from astra.backtest2.macro_filter import MacroFilteredParams, macro_filtered_signal

SMALL = dict(fast=10, slow=40, breakout=48, atr_period=24, stop_atr=3., trail_atr=3., reward=3.,
             max_hours=200, trail_start_r=2., macro_fast=10, macro_slow=30)


def bars(days=500, seed=7):
    n = days * 24
    rng = np.random.default_rng(seed)
    idx = pd.date_range('2024-01-01', periods=n, freq='1h', tz='UTC')
    log = np.cumsum(rng.normal(0, .004, n)) + .6 * np.sin(np.linspace(0, 14, n))
    close = 60000 * np.exp(log)
    return pd.DataFrame({'open': close, 'high': close * 1.002, 'low': close * .998, 'close': close,
                         'volume': 500.}, index=idx)


def test_matches_research_implementation_exactly():
    b = bars()
    p = MacroHourlyParams(**SMALL)
    ref = macro_filtered_signal(b, MacroFilteredParams(inner=p, macro_fast=10, macro_slow=30))
    got = features(b, p)
    pd.testing.assert_frame_equal(got, ref)


def test_only_signal_is_gated_and_never_against_macro():
    b = bars()
    p = MacroHourlyParams(**SMALL)
    base, got = hourly_features(b, p), features(b, p)
    macro = macro_trend(b, p.macro_fast, p.macro_slow).to_numpy()
    assert (got['anchor'] == base['anchor']).all() and got['atr'].equals(base['atr'])
    fired = (got['signal'] != 0).to_numpy()
    assert (got['signal'].to_numpy()[fired] == macro[fired]).all()
    assert (base['signal'] != 0).sum() > fired.sum() > 0, 'Test data must exercise both pass and block'


def test_refuses_history_too_short_for_the_macro_ema():
    p = MacroHourlyParams(**SMALL)
    with pytest.raises(ValueError, match='silently blocked'):
        features(bars(days=30), p)


def test_default_history_requirement_is_one_and_a_half_slow_spans():
    assert MacroHourlyParams().min_history_hours == 150 * 24


def test_invalid_macro_pair_is_refused():
    with pytest.raises(ValueError):
        MacroHourlyParams(macro_fast=100, macro_slow=20)


def test_shipped_macro_config_is_flat_serializable_and_routes():
    cfg = json.loads(Path('configs/selected_v4_macro.json').read_text())
    params_class, features_fn = strategy_for(cfg['strategy'])
    p = params_class(**cfg['params'])
    assert asdict(p)['macro_slow'] == 100
    assert features_fn is features and callable(backtest_for(cfg['strategy']))
    assert cfg['approved_for_live'] is False
    Risk(**cfg['risk'])


def test_backtest_runs_on_gated_signal():
    from astra.v4_macro import backtest
    b = bars()
    p = MacroHourlyParams(**SMALL)
    b['funding'] = 0.
    equity, trades, _ = backtest(b, p, Risk())
    assert len(equity) == len(b)
