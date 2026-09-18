"""Walk-forward comparison: baseline v4_hourly vs symmetric macro filter vs
asymmetric macro filter (longs strict, shorts loose) vs buy-and-hold, all
over the same rolling out-of-sample windows. Every config is FIXED per
run -- none are re-optimized window by window (that was already tried for
stop_atr/reward and min_trend and made things worse or no better; see
DISCUSSION in the report this script writes).

warmup=150 days for anything using the macro filter: min_periods=100 only
stops the slow EMA from being NaN, it does not mean it has converged.
150 days (1.5x macro_slow) was found empirically to be the point where
results stop changing as warmup grows further (see reports/backtest2-v1/
WARMUP_NOTE.md).
"""
from dataclasses import asdict
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import Risk
from astra.v4_hourly import HourlyParams, features
from astra.backtest2.execution import ExecutionSimulator
from astra.backtest2.walkforward import WalkForwardEngine
from astra.backtest2.montecarlo import MonteCarloEngine
from astra.backtest2.macro_filter import MacroFilteredParams, macro_filtered_signal
from astra.backtest2.asymmetric_macro_filter import AsymmetricMacroParams, asymmetric_macro_signal
from astra.backtest2.friction.funding import FundingModel
from astra.backtest2.friction.slippage import SlippageModel, NullLiquidityBook
from astra.backtest2.friction.fees import FeeModel
from astra.backtest2.friction.liquidation import LiquidationModel, PositionTiers

OUT = Path('reports/backtest2-v1')
TRAIN_SPAN = pd.Timedelta(days=365)
TEST_SPAN = pd.Timedelta(days=90)
STEP = pd.Timedelta(days=90)
MACRO_WARMUP = pd.Timedelta(days=150)


def build_sim(risk):
    return ExecutionSimulator(
        funding_model=FundingModel(),
        slippage_model=SlippageModel(NullLiquidityBook(), impact_k=1.0),
        fee_model=FeeModel.regular_tier(),
        liquidation_model=LiquidationModel(PositionTiers(), 'isolated'),
        leverage=risk.max_exposure,
    )


def buy_and_hold_sharpes(bars, windows):
    out = []
    for _, row in windows.iterrows():
        seg = bars.loc[row.test_start:row.test_end]
        daily_px = seg.close.resample('1D').last().dropna()
        rets = daily_px.pct_change().dropna()
        sd = rets.std(ddof=1)
        out.append(float(np.sqrt(365) * rets.mean() / sd) if sd > 0 else 0.)
    return np.array(out)


def summarize(label, result, bh):
    oos = result.out_of_sample_sharpe
    return {
        'label': label,
        'windows': len(result),
        'oos_sharpe_mean': float(oos.mean()), 'oos_sharpe_median': float(oos.median()),
        'windows_ge_1_5': int((oos >= 1.5).sum()), 'windows_total': len(oos),
        'corr_is_oos': float(result.in_sample_sharpe.corr(oos)) if result.in_sample_sharpe.std() > 0 else None,
        'buy_and_hold_sharpe_mean': float(bh.mean()), 'buy_and_hold_sharpe_median': float(np.median(bh)),
        'beats_buy_and_hold_mean': bool(oos.mean() > bh.mean()),
    }


def main():
    cfg = json.loads(Path('configs/selected.json').read_text())
    p = HourlyParams(**cfg['params'])
    risk = Risk(**cfg['risk'])
    bars = pd.read_csv('data/BTC-USDT-SWAP-okx-1h.csv', index_col='time', parse_dates=True)
    bars.index = pd.to_datetime(bars.index, utc=True)
    sim = build_sim(risk)

    configs = {
        'baseline_v4_hourly': (p, features, pd.Timedelta(0)),
        'symmetric_macro_filter': (MacroFilteredParams(inner=p, macro_fast=20, macro_slow=100), macro_filtered_signal, MACRO_WARMUP),
        'asymmetric_macro_filter': (AsymmetricMacroParams(inner=p, macro_fast=20, macro_slow=100), asymmetric_macro_signal, MACRO_WARMUP),
    }

    summary = []
    full_period_mc = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for label, (params, signal_fn, warmup) in configs.items():
        engine = WalkForwardEngine(execution_simulator=sim, signal_fn=signal_fn)
        result = engine.run(bars, param_grid=[params], risk=risk,
                             train_span=TRAIN_SPAN, test_span=TEST_SPAN, step=STEP, warmup=warmup)
        bh = buy_and_hold_sharpes(bars, result)
        row = summarize(label, result, bh)
        summary.append(row)
        result.to_csv(OUT / f'walkforward_{label}.csv', index=False)
        print(json.dumps(row, indent=2), flush=True)

        # Full-period (not walk-forward) Monte Carlo on this FIXED config, per task D:
        # required before ever treating a config as a live candidate.
        full_signal = signal_fn(bars, params)
        full_equity, full_trades, _ = sim.run(bars, full_signal, params, risk,
                                                start=bars.index[0] + warmup, end=bars.index[-1] + pd.Timedelta(hours=1))
        if len(full_trades) >= 10:
            mc_engine = MonteCarloEngine(trades=full_trades, capital=risk.capital)
            np.random.seed(42)
            bootstrap = mc_engine.bootstrap(n_sims=2000, block_size=7)
            shuffle = mc_engine.shuffle_order(n_sims=2000)
            mc = {'n_trades': len(full_trades),
                  'bootstrap_block7': mc_engine.summarize(bootstrap),
                  'shuffle_order': mc_engine.summarize(shuffle)}
        else:
            mc = {'n_trades': len(full_trades), 'note': 'too few trades for Monte Carlo'}
        full_period_mc[label] = mc
        print(f'{label} full-period Monte Carlo:', json.dumps(mc, indent=2), flush=True)

    (OUT / 'summary.json').write_text(json.dumps({
        'walkforward_windows': summary,
        'full_period_monte_carlo': full_period_mc,
        'note': 'Every config here is FIXED (not re-optimized per window). '
                'No change to configs/selected.json or approved_for_live regardless of outcome.',
    }, indent=2))
    print('=== DONE. See reports/backtest2-v1/summary.json ===')


if __name__ == '__main__':
    main()
