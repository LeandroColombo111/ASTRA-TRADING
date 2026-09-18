"""Rolling train/test windows: fit on train, evaluate frozen params on the following out-of-sample test window.

A large in-sample vs out-of-sample gap across windows is the signature of
overfitting to the past rather than a genuine edge.

Pass warmup (a pd.Timedelta) to run() when a signal needs more lookback
than train_span/test_span alone provide -- e.g. a macro filter's slow
moving average computed fresh on a short window never finishes warming up
and silently suppresses every entry. warmup extends what signal_fn sees
without changing what gets scored (see run()'s docstring).
"""
from dataclasses import dataclass
from typing import Callable
import pandas as pd

from ..engine import metrics, Risk
from .execution import ExecutionSimulator

SignalFn = Callable[[pd.DataFrame, object], pd.DataFrame]


@dataclass(frozen=True)
class WalkForwardEngine:
    execution_simulator: ExecutionSimulator
    signal_fn: SignalFn  # e.g. v4_hourly.features, or directional_strategy.features

    def windows(self, index: pd.DatetimeIndex, train_span: pd.Timedelta,
                test_span: pd.Timedelta, step: pd.Timedelta) -> list[tuple[tuple, tuple]]:
        """[(train_range, test_range), ...] rolling forward by step; each test_range starts exactly where its train_range ends."""
        if train_span <= pd.Timedelta(0) or test_span <= pd.Timedelta(0) or step <= pd.Timedelta(0):
            raise ValueError("train_span, test_span and step must be positive")
        if len(index) == 0:
            raise ValueError("Empty index")
        start = index[0]
        end_limit = index[-1]
        out = []
        while start + train_span + test_span <= end_limit:
            train_range = (start, start + train_span)
            test_range = (start + train_span, start + train_span + test_span)
            out.append((train_range, test_range))
            start += step
        if not out:
            raise ValueError("No window fits inside the available history; shorten train_span/test_span or provide more data")
        return out

    def run(self, bars: pd.DataFrame, param_grid: list, risk: Risk,
            train_span: pd.Timedelta, test_span: pd.Timedelta, step: pd.Timedelta,
            warmup: pd.Timedelta = pd.Timedelta(0)) -> pd.DataFrame:
        """Per window: params selected in-sample, and the Sharpe/return achieved both in-sample and out-of-sample with them.

        warmup extends each slice backward before signal_fn sees it, so an
        indicator needing more history than train_span/test_span alone
        (e.g. a macro filter's slow moving average) isn't starved of data at
        the start of every window. ExecutionSimulator.run's start/end still
        restrict what's actually scored to the true window, so the warmup
        period only feeds indicators -- it is never counted as a trade.
        """
        if not param_grid:
            raise ValueError("param_grid cannot be empty")
        rows = []
        for train_range, test_range in self.windows(bars.index, train_span, test_span, step):
            train_bars = bars.loc[train_range[0] - warmup:train_range[1]]
            test_bars = bars.loc[test_range[0] - warmup:test_range[1]]
            if train_bars.empty or test_bars.empty:
                continue
            best_params, best_metrics = None, None
            for candidate in param_grid:
                train_signal = self.signal_fn(train_bars, candidate)
                equity, trades, _ = self.execution_simulator.run(
                    train_bars, train_signal, candidate, risk, start=train_range[0], end=train_range[1])
                candidate_metrics = metrics(equity, trades, risk.capital)
                if best_metrics is None or candidate_metrics["sharpe"] > best_metrics["sharpe"]:
                    best_params, best_metrics = candidate, candidate_metrics
            test_signal = self.signal_fn(test_bars, best_params)
            test_equity, test_trades, _ = self.execution_simulator.run(
                test_bars, test_signal, best_params, risk, start=test_range[0], end=test_range[1])
            test_metrics = metrics(test_equity, test_trades, risk.capital)
            rows.append({
                "train_start": train_range[0], "train_end": train_range[1],
                "test_start": test_range[0], "test_end": test_range[1],
                "params": best_params,
                "in_sample_sharpe": best_metrics["sharpe"], "out_of_sample_sharpe": test_metrics["sharpe"],
                "in_sample_return": best_metrics["return"], "out_of_sample_return": test_metrics["return"],
            })
        if not rows:
            raise ValueError("No window produced both non-empty train and test bars")
        return pd.DataFrame(rows)
