# PBO/CSCV for the v4_hourly search (reports/v4-hourly-01)

Probability of Backtest Overfitting via Combinatorially Symmetric
Cross-Validation (Bailey, Borwein, Lopez de Prado & Zhu, 2017), run once
against the 60 configurations already tried in the original v4_hourly
search. Diagnostic only -- see `ops/pbo_cscv.py` docstring for why this
must not be used as a tuning loop.

## Result

```
pbo: 0.312
n_combinations: 12870 (C(16,8), the standard split count)
logit_mean: 0.601
data: 1669 days, 60 configurations
```

## Reading it

PBO is the fraction of in-sample/out-of-sample splits where the
configuration that looked best in-sample turns out to be below the
out-of-sample median. A selection process with no real skill -- picking
essentially at random relative to true performance -- lands at PBO ≈ 0.5.
0.31 is meaningfully below that: the search that produced the current
`configs/selected.json` params is not indistinguishable from picking a
winner at random.

## Relationship to the DSR gate

This does not change or substitute for the DSR (0.717, still below the
0.95 gate `configs/selected.json` requires). DSR and PBO ask different
questions -- DSR: is the winning Sharpe statistically distinguishable from
noise given how many configs were tried; PBO: is the selection procedure
itself reliable -- and here they point the same direction (neither says
"clearly overfit"), which is corroborating, not conclusive. `approved_for_live`
stays `false`; this is one more piece of evidence, not a new gate passed.
