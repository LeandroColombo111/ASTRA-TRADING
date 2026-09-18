# backtest2: realistic-friction walk-forward investigation of v4_hourly

Second execution engine (`src/astra/backtest2/`) with per-8h funding
settlement, book-aware/impact-model slippage, real OKX maker/taker fees,
and margin liquidation modeling, plus walk-forward and Monte Carlo
diagnostics. Independent of `engine.py`; does not replace it.

This investigation was started outside a tracked git commit and its
headline claims were independently reproduced here before being trusted
or acted on (see the WARMUP_NOTE below for the one real discrepancy found
and resolved during that verification).

## 1. The production config does not generalize (verified)

Walk-forward: 365-day train / 90-day test / 90-day step, 14 non-overlapping
test quarters, 2022-2026, real OKX data.

| Config | OOS Sharpe mean | OOS Sharpe median | Windows >= 1.5 | Corr(IS, OOS) |
|---|---|---|---|---|
| **Production (`configs/selected.json`), unmodified** | -0.80 | -0.37 | 3/14 (21%) | 0.02 |

In-sample Sharpe has essentially zero relationship with what the same
params achieve on the following quarter. Buy-and-hold over the identical
14 windows: mean Sharpe **+0.85**, median **+0.69** -- both clearly beat
the bot. The full-period Sharpe (~1.0) reported elsewhere in this repo is
not wrong, but a large share of it sits in the 2022 bear year, which
walk-forward only ever uses as training data and never re-tests
out-of-sample.

## 2. Re-tuning parameters per window does not fix it

Grids swept over `stop_atr`/`reward` and separately `min_trend`: in-sample
selection still does not correlate with out-of-sample result (corr ~0),
and the aggregate is flat-to-worse than leaving the config fixed. The
grid, left to choose, mostly re-selects the values already in production.
**Conclusion carried into every test below: never re-optimize a parameter
per window. Pick one fixed value with a stated reason, test it once.**

## 3. A causal daily macro filter helps, but not enough

`src/astra/backtest2/macro_filter.py`: entries gated by a causal daily
EMA(20)/EMA(100) cross (same reindex+ffill discipline as the existing 4h
anchor). Exits untouched. Fixed pair, not re-optimized.

| Config | OOS Sharpe mean | OOS Sharpe median | Windows >= 1.5 | Trades |
|---|---|---|---|---|
| Symmetric macro filter (longs and shorts both require alignment) | +0.42 | +0.84 | 7/14 (50%) | 81 |
| **Asymmetric macro filter** (longs strict, shorts fire whenever macro != bullish) | +0.42 | +0.84 | 7/14 (50%) | 81 |

The asymmetric rule (motivated by the long/short x regime split: aligned
trades made +13,470 as a block, misaligned trades lost -3,615 at a 17-20%
win rate, "long in an eventually-bearish quarter" the worst cell) was
tested as ONE fixed, reasoned design -- not a swept grid -- per the
discipline in section 2. It produced results IDENTICAL to the symmetric
filter: of 130 raw short signals in the full dataset, 100 already satisfy
the strict `macro == -1` rule and only 2 fall in the loosened
`macro == 0` case the asymmetric rule additionally admits -- and neither
of those 2 rare bars landed inside a test window with no position already
open. Real result, not a bug: this specific asymmetry had almost no
surface area to act on in this data. See `ASYMMETRIC_NULL_RESULT.md`.

Both macro-filtered variants clear the 1.5 gate in half the windows and
roughly double buy-and-hold's median, but the MEDIAN (0.84) is still
short of the project's non-negotiable 1.5, and the full-period Monte
Carlo bootstrap puts **96.2% probability of landing below 1.5** even on
this exact fixed config (see below). Per task D, this does not clear the
bar for touching `configs/selected.json` or `approved_for_live`.

## Full-period Monte Carlo (fixed configs, not re-optimized)

Block bootstrap (block=7 trades) and order-shuffle, 2000 simulations each,
threshold = 1.5:

| Config | Trades | Bootstrap p5 | p50 | p95 | P(Sharpe < 1.5) |
|---|---|---|---|---|---|
| Production (unmodified) | 118 | 0.27 | 0.97 | 1.58 | 91.9% |
| Macro filter (symmetric or asymmetric) | 81 | -0.15 | 0.73 | 1.46 | 96.2% |

Order-shuffle bands are tight in both cases (production: 0.95-1.02;
macro filter: 0.70-0.75), meaning the moderate full-period Sharpe is not
a lucky sequencing of trades -- it is a stable number that simply does
not reach 1.5, consistent with the walk-forward result above.

## Status against the project's gate (task D)

`configs/selected.json` and `approved_for_live` are UNCHANGED. Nothing
here clears "walk-forward median OOS Sharpe > 1.5, sustained, with Monte
Carlo showing low probability of falling below 1.5 on a config that was
not re-adjusted to get there." The macro filter is a real, verified
improvement in direction -- but not in degree.

## Task B: slippage model calibration

`SlippageModel.impact_k = 1.0` is NOT calibrated; every number above uses
that placeholder. No real signal-triggered fills exist yet to calibrate
from (the only historical fill is one manual round-trip validation test,
a single data point, not a distribution). Rather than fabricate a
calibration from one trade, `src/astra/service.py` now logs a
`_reference_price` alongside every `order_intent` event (the price the
decision was made against) so real (expected, actual-fill) pairs
accumulate from here on -- see the service.py commit. Revisit this
model once enough real fills exist.
