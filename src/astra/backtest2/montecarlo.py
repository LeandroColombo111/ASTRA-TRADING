"""Sharpe distribution over the closed trade sequence: bootstrap, order shuffle, and entry/exit timing perturbation.

Trades are converted to percentage returns relative to the equity available
before each one (execution.step records this as trade["equity_before"]), so
resampled/shuffled sequences can be compounded onto a fresh capital base and
compared on the same daily-Sharpe footing as engine.metrics(). The synthetic
equity path keeps the ORIGINAL trades' exit timestamps as its time skeleton
and only swaps which return lands in each slot -- so a permutation changes
which outcome happens when, not the calendar itself.

Timing perturbation is the one variant that cannot reuse closed trades; it
re-runs ExecutionSimulator because delaying a fill changes the real
price/funding/fee it would have received. It only delays (never advances)
signals, since advancing would use information not yet available at that
bar -- the same look-ahead discipline as engine.py and execution.py.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from ..engine import metrics
from .execution import ExecutionSimulator


@dataclass(frozen=True)
class MonteCarloEngine:
    trades: list[dict]
    capital: float

    def __post_init__(self):
        if self.capital <= 0:
            raise ValueError("capital must be positive")

    def _trade_returns(self) -> np.ndarray:
        """r_i = net_pnl_i / equity_before_trade_i for every closed trade, in original order."""
        if not self.trades:
            raise ValueError("No trades to build a return series from")
        returns = np.array([t["net_pnl"] / t["equity_before"] for t in self.trades], dtype=float)
        if not np.isfinite(returns).all():
            raise ValueError("Non-finite trade return; check equity_before values")
        return returns

    def _sharpe_from_returns(self, returns: np.ndarray) -> float:
        """Compounds returns over the original trades' exit-time skeleton, then reuses engine.py's daily-Sharpe definition."""
        exit_times = pd.DatetimeIndex([pd.Timestamp(t["exit_time"]) for t in self.trades])
        equity = self.capital
        curve = []
        for r in returns:
            equity *= (1. + r)
            curve.append(equity)
        series = pd.Series(curve, index=exit_times)
        shifted = series.copy()
        shifted.index = shifted.index - pd.Timedelta(nanoseconds=1)
        daily = shifted.resample("1D").last().ffill()
        if daily.isna().all():
            return 0.
        daily_returns = daily.pct_change().fillna(daily.iloc[0] / self.capital - 1.)
        sd = float(daily_returns.std(ddof=1))
        if sd <= 0:
            return 0.
        return float(np.sqrt(365) * daily_returns.mean() / sd)

    def bootstrap(self, n_sims: int, block_size: int = 1) -> np.ndarray:
        """Resample-with-replacement; block_size > 1 preserves streaks (trend regimes) instead of assuming iid trades."""
        if n_sims <= 0 or block_size <= 0:
            raise ValueError("n_sims and block_size must be positive")
        returns = self._trade_returns()
        n = len(returns)
        sharpes = np.empty(n_sims)
        for i in range(n_sims):
            if block_size == 1:
                sample = np.random.choice(returns, size=n, replace=True)
            else:
                n_blocks = int(np.ceil(n / block_size))
                starts = np.random.randint(0, n, size=n_blocks)
                blocks = [returns[np.arange(s, s + block_size) % n] for s in starts]
                sample = np.concatenate(blocks)[:n]
            sharpes[i] = self._sharpe_from_returns(sample)
        return sharpes

    def shuffle_order(self, n_sims: int) -> np.ndarray:
        """Same trade set, random permutations of order only."""
        if n_sims <= 0:
            raise ValueError("n_sims must be positive")
        returns = self._trade_returns()
        sharpes = np.empty(n_sims)
        for i in range(n_sims):
            sharpes[i] = self._sharpe_from_returns(np.random.permutation(returns))
        return sharpes

    def perturb_timing(self, bars: pd.DataFrame, signal: pd.DataFrame, execution_simulator: ExecutionSimulator,
                        p, risk, n_sims: int, max_shift_bars: int) -> np.ndarray:
        """Re-runs ExecutionSimulator with the whole signal delayed by a random 0..max_shift_bars, simulating execution latency."""
        if n_sims <= 0 or max_shift_bars < 0:
            raise ValueError("n_sims must be positive and max_shift_bars non-negative")
        sharpes = np.empty(n_sims)
        for i in range(n_sims):
            shift = int(np.random.randint(0, max_shift_bars + 1))
            shifted_signal = signal.shift(shift).fillna(0) if shift else signal
            equity, trades, _ = execution_simulator.run(bars, shifted_signal, p, risk)
            sharpes[i] = metrics(equity, trades, risk.capital)["sharpe"]
        return sharpes

    def summarize(self, sharpes: np.ndarray, threshold: float = 1.5) -> dict:
        """p5/p50/p95, mean, and prob(Sharpe < threshold) against the non-negotiable requirement."""
        if len(sharpes) == 0:
            raise ValueError("No simulated Sharpe values to summarize")
        return {
            "p5": float(np.percentile(sharpes, 5)),
            "p50": float(np.percentile(sharpes, 50)),
            "p95": float(np.percentile(sharpes, 95)),
            "mean": float(np.mean(sharpes)),
            "prob_below_threshold": float(np.mean(sharpes < threshold)),
        }
