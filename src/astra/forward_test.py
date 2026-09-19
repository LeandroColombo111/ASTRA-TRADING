"""Forward (paper) track-record maths. The configuration is frozen before the data exists, so the number of trials is 1 and the
Sharpe is judged with the probabilistic Sharpe ratio, with no search-deflation term (Bailey & Lopez de Prado)."""
import math
import numpy as np
from scipy.stats import norm, skew, kurtosis


def daily_moments(returns):
    r = np.asarray(returns, dtype=float)
    if len(r) < 3 or r.std(ddof=1) == 0:
        return None
    sr = r.mean() / r.std(ddof=1)
    return sr, float(skew(r, bias=False)), float(kurtosis(r, fisher=False, bias=False)), len(r)


def psr(returns, benchmark_daily=0.0):
    """P(true Sharpe > benchmark) given the observed daily returns; None until there is something to measure."""
    m = daily_moments(returns)
    if m is None:
        return None
    sr, sk, ku, n = m
    denom = max(1 - sk * sr + (ku - 1) * sr * sr / 4, 1e-12)
    return float(norm.cdf((sr - benchmark_daily) * math.sqrt(n - 1) / math.sqrt(denom)))


def days_needed(sr_daily, skew_=0.0, kurt=3.0, target=0.95):
    """Track-record length (days) for PSR to reach `target` if the true daily Sharpe equals sr_daily."""
    if sr_daily <= 0:
        return math.inf
    z = norm.ppf(target)
    denom = max(1 - skew_ * sr_daily + (kurt - 1) * sr_daily ** 2 / 4, 1e-12)
    return z * z * denom / sr_daily ** 2 + 1
