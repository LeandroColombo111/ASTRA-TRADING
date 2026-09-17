# PBO/CSCV for the v3_trend search (reports/v3-trend-01)

Same method as `reports/pbo-v4-hourly-01/README.md`, applied to the daily/
4-day trend sleeve's search (60 configurations) instead of the hourly
one. See `ops/pbo_cscv_v3.py` and the v4 README for the full method and
why this is diagnostic-only, not a tuning loop.

## Result

```
pbo: 0.411
n_combinations: 12870
logit_mean: 0.169
data: 1669 days, 60 configurations
```

## Reading it, compared to v4_hourly

| | v4_hourly (hourly/4h sleeve) | v3_trend (daily/4-day sleeve) |
|---|---|---|
| PBO | 0.312 | **0.411** |

Both are below the 0.5 "no real selection skill" line, so neither search
looks like it just picked noise. But v3_trend's search is weaker by this
measure -- closer to the coin-flip line than v4_hourly's. This does not
change any gate (approved_for_live stays false either way), but it is a
real, disclosed difference between the two sleeves that feed the
portfolio ensemble: the hourly sleeve's selection process has more
supporting evidence than the daily sleeve's.
