# Why v5_portfolio doesn't get its own separate PBO

PBO/CSCV measures whether a SEARCH's selection procedure (try N
configurations, keep the one that looks best in-sample) is reliable. It
needs a population of independently-evaluated candidates to check against
each other.

`v5_portfolio.build()` does not run a new search of that kind: it takes
the already-selected top-5 configurations from the v3_trend and v4_hourly
searches (whose PBO is measured in `reports/pbo-v3-trend-01/` and
`reports/pbo-v4-hourly-01/`) and combines them by rolling inverse-volatility
weighting -- a fixed, deterministic construction rule (`top_n=5`,
`VOL_WINDOW=90`), not a choice picked from a family of alternatives that
were compared against each other.

So v5's overfitting risk is inherited from its two component searches,
not something separate to measure the same way:

| | PBO |
|---|---|
| v4_hourly search (hourly/4h sleeve) | 0.312 |
| v3_trend search (daily/4-day sleeve) | 0.411 |
| v5_portfolio construction | not applicable -- no independent candidate population to run CSCV against |

If `v5_portfolio` is ever extended to genuinely search over ensemble
construction choices (different `top_n` values, different weighting
schemes, compared against each other and the best one kept), THAT search
would be exactly the kind of thing PBO should then be run against -- and,
per the same discipline as everywhere else in this project, doing that
search at all would need its own DSR accounting, not just a PBO check
after the fact.
