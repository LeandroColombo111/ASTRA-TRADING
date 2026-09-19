import math
import numpy as np
from astra.forward_test import psr, days_needed


def test_psr_is_undefined_without_data_and_half_for_zero_edge():
    assert psr([0.0] * 30) is None
    rng = np.random.default_rng(1)
    zero_mean = rng.normal(0, 0.01, 2000)
    zero_mean -= zero_mean.mean()
    assert abs(psr(zero_mean) - 0.5) < 0.01


def test_psr_rises_with_edge_and_history():
    rng = np.random.default_rng(2)
    a = rng.normal(0.001, 0.01, 200)
    b = np.concatenate([a, rng.normal(0.001, 0.01, 800)])
    assert psr(b) > psr(a) > 0.5


def test_days_needed_matches_known_case_and_is_infinite_for_no_edge():
    # normal returns, annual Sharpe 1.0 -> about (1.645^2 / (1/365)) ~ 990 days
    assert 900 < days_needed(1 / math.sqrt(365)) < 1100
    assert math.isinf(days_needed(-0.01))
