# Modeling the carry sleeve's execution risk

`BASIS_RISK_ANALYSIS.md` documented that the worst historical basis
(perp vs spot) swings land on real crash dates and that leveraging the
carry sleeve would multiply that risk exactly when execution is least
reliable. This note goes one step further: it actually models the cost,
using real data (`ops/carry_execution_risk.py`), instead of leaving it as
a qualitative caution.

## Method

At each of the 27 direction changes in the taker-cost carry backtest, a
stochastic hedge-slippage cost is drawn (bootstrap, with replacement) from
the REAL historical distribution of hourly basis changes (40,599 real
observations, std 1.49bps, worst 44.1bps -- the same series
BASIS_RISK_ANALYSIS.md measured) and applied against that event's
notional. Run 2000 times to see a distribution, not a point estimate, plus
a separate "stress" run that only samples from the worst 5% of historical
basis changes.

## Result

| | Baseline (no exec. risk) | + realistic exec. risk | + stress-tail exec. risk |
|---|---|---|
| Total return (4.6yr, taker) | 7.30% | 7.01% (p50) | 6.24% (p50) |
| Probability return turns negative | -- | 0% | 0% |

Even under the stress scenario, the modelled cost is small: a few tenths
of a percent of total return, not enough to flip the sleeve unprofitable.

## Why this likely UNDERSTATES the real risk, and should not be read as "execution risk is negligible"

The bootstrap treats each of the 27 flip events as an independent draw
from history. Real crashes are not independent single-hour events -- LUNA
and FTX each produced MULTIPLE consecutive hours of dislocated basis, and
a position caught mid-collapse would face correlated bad draws in a row,
not one random hour in isolation. This model also does not capture the
scenario where an exchange is congested or an API is degraded exactly
when you need to close or rebalance a leg -- it assumes you can always
execute at SOME real observed historical basis level, not that execution
itself might fail or queue during the event.

## Conclusion

This makes the earlier qualitative caution more precise, not less serious:
the AVERAGE cost of imperfect execution is small and would not have broken
this sleeve historically. The TAIL risk -- getting caught in a genuine,
multi-hour, correlated crash window with degraded execution -- is real and
is not fully captured here. Same recommendation as before: keep this
sleeve at 1x until that specific correlated-stress scenario is modelled,
which this note does not yet do.
