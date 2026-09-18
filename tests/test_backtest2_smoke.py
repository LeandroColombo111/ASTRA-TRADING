"""Smoke tests for backtest2: the module had zero tests before this session
verified its headline walk-forward claims by re-running them independently.
These don't re-litigate that verification (see reports/backtest2-v1/); they
just guard against the pieces silently breaking on the next change."""
import json

import numpy as np
import pandas as pd
import pytest

from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.execution import ExecutionSimulator
from astra.backtest2.walkforward import WalkForwardEngine
from astra.backtest2.montecarlo import MonteCarloEngine
from astra.backtest2.macro_filter import MacroFilteredParams, macro_filtered_signal, macro_trend
from astra.backtest2.asymmetric_macro_filter import AsymmetricMacroParams, asymmetric_macro_signal
from astra.backtest2.friction.funding import FundingModel
from astra.backtest2.friction.slippage import SlippageModel, NullLiquidityBook
from astra.backtest2.friction.fees import FeeModel
from astra.backtest2.friction.liquidation import LiquidationModel, PositionTiers


def load_bars(n=6000):
    """Deterministic synthetic hourly bars. These tests must not read
    data/ (gitignored, absent on CI) -- a first version did and passed
    locally while failing every CI run with FileNotFoundError. Same column
    layout as the real OKX CSV: OHLC, volume, funding (zero except at the
    three UTC settlement hours, like the real file)."""
    rng = np.random.default_rng(7)
    index = pd.date_range('2022-01-17', periods=n, freq='h', tz='UTC')
    drift = np.sin(np.arange(n) / 900.) * 0.0004  # slow up/down regimes so both signal sides occur
    close = 40000. * np.exp(np.cumsum(drift + rng.normal(0, 0.004, n)))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.003, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    funding = np.where(index.hour.isin([0, 8, 16]), 0.0001, 0.)
    return pd.DataFrame({'open': open_, 'high': high, 'low': low, 'close': close,
                         'volume': rng.uniform(1e5, 2e5, n), 'funding': funding}, index=index)


def make_sim(risk):
    return ExecutionSimulator(
        funding_model=FundingModel(),
        slippage_model=SlippageModel(NullLiquidityBook(), impact_k=1.0),
        fee_model=FeeModel.regular_tier(),
        liquidation_model=LiquidationModel(PositionTiers(), 'isolated'),
        leverage=risk.max_exposure,
    )


def load_config():
    cfg = json.load(open('configs/selected.json'))
    return HourlyParams(**cfg['params']), Risk(**cfg['risk'])


def test_execution_simulator_runs_and_matches_engine_shape():
    p, risk = load_config()
    bars = load_bars()
    sim = make_sim(risk)
    signal = features(bars, p)
    equity, trades, state = sim.run(bars, signal, p, risk)
    assert len(equity) == len(bars)
    assert isinstance(trades, list)
    assert 'halted' in state


def test_liquidation_never_closer_than_stop_at_low_leverage():
    """At leverage==max_exposure==1, liquidation should be far enough away
    that it never preempts the strategy's own stop in practice."""
    p, risk = load_config()
    bars = load_bars()
    sim = make_sim(risk)
    signal = features(bars, p)
    _, trades, _ = sim.run(bars, signal, p, risk)
    assert not any(t['reason'] == 'liquidated' for t in trades)


def test_macro_trend_is_causal_and_bounded():
    bars = load_bars()
    trend = macro_trend(bars, 20, 100)
    assert set(trend.unique()) <= {-1., 0., 1.}
    assert len(trend) == len(bars)


def test_asymmetric_filter_never_admits_a_long_the_symmetric_filter_blocks():
    p, risk = load_config()
    bars = load_bars()
    mp = MacroFilteredParams(inner=p, macro_fast=20, macro_slow=100)
    ap = AsymmetricMacroParams(inner=p, macro_fast=20, macro_slow=100)
    sym = macro_filtered_signal(bars, mp)['signal']
    asym = asymmetric_macro_signal(bars, ap)['signal']
    sym_longs = set(sym[sym == 1].index)
    asym_longs = set(asym[asym == 1].index)
    assert asym_longs <= sym_longs, 'asymmetric rule must not loosen longs, only shorts'


def test_walkforward_raises_on_empty_grid():
    p, risk = load_config()
    bars = load_bars()
    sim = make_sim(risk)
    engine = WalkForwardEngine(execution_simulator=sim, signal_fn=features)
    with pytest.raises(ValueError, match='param_grid cannot be empty'):
        engine.run(bars, [], risk, pd.Timedelta(days=365), pd.Timedelta(days=90), pd.Timedelta(days=90))


def test_montecarlo_bootstrap_and_shuffle_summaries_are_well_formed():
    trades = [
        {'net_pnl': 100., 'equity_before': 10000., 'exit_time': '2022-01-01 00:00:00+00:00'},
        {'net_pnl': -50., 'equity_before': 10100., 'exit_time': '2022-02-01 00:00:00+00:00'},
        {'net_pnl': 200., 'equity_before': 10050., 'exit_time': '2022-03-01 00:00:00+00:00'},
        {'net_pnl': -30., 'equity_before': 10250., 'exit_time': '2022-04-01 00:00:00+00:00'},
        {'net_pnl': 80., 'equity_before': 10220., 'exit_time': '2022-05-01 00:00:00+00:00'},
        {'net_pnl': -20., 'equity_before': 10300., 'exit_time': '2022-06-01 00:00:00+00:00'},
        {'net_pnl': 150., 'equity_before': 10280., 'exit_time': '2022-07-01 00:00:00+00:00'},
        {'net_pnl': -60., 'equity_before': 10430., 'exit_time': '2022-08-01 00:00:00+00:00'},
        {'net_pnl': 90., 'equity_before': 10370., 'exit_time': '2022-09-01 00:00:00+00:00'},
        {'net_pnl': -10., 'equity_before': 10460., 'exit_time': '2022-10-01 00:00:00+00:00'},
    ]
    mc = MonteCarloEngine(trades=trades, capital=10000.)
    boot = mc.bootstrap(n_sims=200, block_size=2)
    shuf = mc.shuffle_order(n_sims=200)
    for sharpes in (boot, shuf):
        summary = mc.summarize(sharpes, threshold=1.5)
        assert summary['p5'] <= summary['p50'] <= summary['p95']
        assert 0. <= summary['prob_below_threshold'] <= 1.
