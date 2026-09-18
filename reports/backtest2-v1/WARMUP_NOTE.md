# warmup must exceed min_periods, not just clear it

`WalkForwardEngine.run(..., warmup=...)` extends each window's visible
history so a slow indicator (e.g. the macro filter's EMA(100)) isn't
starved for data at the start of a window. The bug this parameter fixes
(see `walkforward.py`'s docstring) is real and was already fixed before
this session started.

What was NOT obvious, and cost a round of independent verification: the
warmup needed is bigger than what merely clears `min_periods`.

| warmup | OOS Sharpe mean | median | windows >= 1.5 |
|---|---|---|---|
| 0d | 0.000 (degenerate -- signal starved) | 0.000 | 0/14 |
| 100d (== macro_slow, clears min_periods) | +0.348 | -0.020 | 6/14 |
| 150d (1.5x macro_slow) | +0.424 | +0.843 | 7/14 |
| 200d+ | +0.424 | +0.843 | 7/14 (unchanged) |

`min_periods=100` only stops `EMA(100)` from returning `NaN` -- it does
not mean the EMA has converged to a value close to its steady state. The
numbers keep moving until warmup reaches roughly 1.5x the slow span, then
stabilize. 150 days is used everywhere in this report for anything using
the macro filter.

Anyone adding a new indicator with a lookback `L` to this framework should
default to `warmup >= 1.5 * L` and confirm by sweeping warmup upward until
results stop changing, the same way this was found -- don't assume
`warmup == L` is enough.
