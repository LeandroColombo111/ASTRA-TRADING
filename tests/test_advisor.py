import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "advisor"))

from advisor import cluster, rr_check, rsi, swings  # noqa: E402


def test_rr_long_blended_and_approval():
    r = rr_check("long", 100, 95, 110, 120)
    assert r["rr_tp1"] == 2.0 and r["rr_tp2"] == 4.0 and r["rr_blended"] == 3.0
    assert r["approved"]


def test_rr_short_rejected_below_two():
    r = rr_check("short", 100, 105, 95, 92)
    assert r["rr_blended"] == 1.3
    assert not r["approved"]


def test_rr_wrong_side_invalid():
    assert not rr_check("long", 100, 101, 110)["valid"]
    assert not rr_check("short", 100, 105, 101)["valid"]


def test_rr_warns_tight_stop():
    r = rr_check("long", 100, 99, 110, atr4h=2)
    assert r["warnings"]


def test_rsi_bounds_and_cluster():
    s = pd.Series(np.linspace(1, 50, 100))
    assert rsi(s).iloc[-1] > 99
    assert cluster([10, 10.2, 15, 15.1], 0.5) == [10.1, 15.05]


def test_swings_detects_peak_and_trough():
    h = [1, 2, 3, 9, 3, 2, 1, 2, 3, 4]
    l = [5, 4, 3, 2, 3, 4, 0, 4, 5, 6]
    df = pd.DataFrame({"high": h, "low": l})
    highs, lows = swings(df, k=3)
    assert 9 in highs and 0 in lows


def test_position_size_risk_based():
    from advisor import position_size
    r = position_size("long", 100, 98, capital=360, risk_pct=2, leverage=5)
    assert r["risk_usd"] == 7.2 and r["qty"] == 3.6 and r["margin_usd"] == 72.0
    assert not r["capped_by_leverage"]


def test_position_size_capped_by_leverage_and_liquidation():
    from advisor import position_size
    r = position_size("short", 100, 100.2, capital=360, risk_pct=2, leverage=5, max_positions=3)
    assert r["capped_by_leverage"] and r["notional_usd"] == 600.0 and r["risk_pct_real"] < 2
    bad = position_size("long", 100, 70, capital=360, risk_pct=2, leverage=5)
    assert not bad["valid"]


ACC = {"risk_per_trade_pct": 2, "max_risk_pct": 3, "counter_trend_risk_pct": 1,
       "min_rr_tp1_for_upper_tiers": 1.5,
       "risk_tiers": [{"min_rr": 3, "risk_pct": 2.5}, {"min_rr": 4, "risk_pct": 3}]}


def test_risk_tiers_scale_with_rr_and_cap():
    from advisor import risk_for_setup
    assert risk_for_setup(ACC, 2.2, 1.6, "a_favor_de_tendencia")["risk_pct"] == 2
    assert risk_for_setup(ACC, 3.4, 1.6, "a_favor_de_tendencia")["risk_pct"] == 2.5
    assert risk_for_setup(ACC, 9.0, 3.0, "a_favor_de_tendencia")["risk_pct"] == 3


def test_risk_tiers_do_not_scale_on_far_tp2_or_counter_trend():
    from advisor import risk_for_setup
    assert risk_for_setup(ACC, 4.5, 0.7, "a_favor_de_tendencia")["risk_pct"] == 2
    assert risk_for_setup(ACC, 6.0, 3.0, "contra_tendencia")["risk_pct"] == 1
    assert risk_for_setup(ACC, 5.0, 2.0, "rango_extremo")["risk_pct"] == 2
