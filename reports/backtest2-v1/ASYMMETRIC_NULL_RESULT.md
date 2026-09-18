# Why the asymmetric macro filter matched the symmetric one exactly

Task A asked to test whether requiring stricter macro alignment for longs
than shorts (motivated by "long in an eventually-bearish quarter" being
the worst-performing cell in the long/short x regime split) improves on
the symmetric macro filter. One fixed rule was tested, not a grid:

- Longs: require `macro == +1` (unchanged, strict).
- Shorts: fire whenever `macro != +1` (bearish OR neutral -- looser than
  the symmetric filter's `macro == -1`).

Result: walk-forward OOS Sharpe mean/median/windows>=1.5, and the
full-period Monte Carlo, came out IDENTICAL to the symmetric filter to
several decimal places (81 trades either way).

## Why, verified rather than assumed

```
total raw short signals (v4_hourly's own signal, before any macro gate): 130
macro value at those moments:
  -1 (bearish):  100
  +1 (bullish):   28  -- blocked by BOTH the symmetric and asymmetric rule
   0 (neutral):    2  -- admitted ONLY by the asymmetric rule
```

Only 2 of 40,512 hourly bars in the full 2022-2026 dataset have a raw
short signal AND a neutral macro trend -- the one case where the two
rules actually differ. Neither of those 2 rare bars landed inside one of
the 14 walk-forward test windows while flat (no position already open).
The asymmetric rule was implemented correctly; it simply had almost no
surface area to act on in this particular history.

## Takeaway

This is a genuine negative result, not a bug to fix or a reason to widen
the loosening further to force a difference -- doing that would be
exactly the per-window re-tuning this project has repeatedly found
useless or harmful (stop_atr/reward, min_trend, macro_fast/slow all
showed the same pattern). If the asymmetry idea is worth revisiting, the
more promising variant from task A is the OTHER one not yet tested here:
reducing position size for longs during a bearish macro regime instead of
gating on a rare signal combination that almost never occurs.
