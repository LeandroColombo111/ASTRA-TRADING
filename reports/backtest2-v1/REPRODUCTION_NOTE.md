# Independent reproduction of the walk-forward headline results

Re-ran three results from scratch with the existing `src/astra/backtest2/`
engine (no engine changes), before reading this report. Same setup:
365d train / 90d test / 90d step, fixed params, real OKX data.

| | Reproduced | Documented |
|---|---|---|
| Baseline OOS Sharpe mean / median | -0.801 / -0.372 | -0.801 / -0.372 |
| Baseline windows >= 1.5 | 3/14 | 3/14 |
| Baseline corr(IS, OOS) | 0.020 | 0.020 |
| Macro EMA 20/100 (warmup >= 140d) mean / median / >= 1.5 | 0.424 / 0.843 / 7/14 | 0.424 / 0.843 / 7/14 |
| Buy-and-hold mean / median | 0.773 / 0.628 | 0.849 / 0.685 |

## Buy-and-hold discrepancy: method, not a bug

`ops/backtest2_walkforward_report.py` (`buy_and_hold_sharpes`) drops the
first day's return of each window. `engine.daily_returns()`, which scores
the bot, keeps it. Four variants tested: those that drop the first day give
0.849 / 0.685; those that keep it give ~0.77 / 0.63. Whether bars are
stamped at open or close makes no difference. The like-for-like comparison
with the bot is the one that keeps the first day (~0.77). The conclusion is
unchanged: buy-and-hold beats the bot (-0.80) either way.

## Warmup: empirical minimum is 140 days

For macro EMA(20)/EMA(100), swept warmup 0-700d and compared per window
against the 700d result:

- 0d: degenerate (0.000 everywhere, signal starved).
- 50-135d: unstable and non-monotonic (100d reproduces the 0.348 / -0.020
  in WARMUP_NOTE.md).
- >= 140d: bit-identical to 700d in every window.

The 150d (1.5x slow span) used in this report is correct and conservative;
140d is the empirical threshold for this data and these params.

## Not verified

An ad-hoc full-history run of macro(20,100) gave 88 trades vs 81 in
summary.json. Likely the report starting 150d in (warmup), but not checked.
Monte Carlo figures were not reproduced.
