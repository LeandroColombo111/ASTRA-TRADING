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
