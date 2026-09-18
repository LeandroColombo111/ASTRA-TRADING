# Correction: the baseline walk-forward comparison was not like-for-like

**Retracted:** the claims that the production config "does not generalize"
(OOS Sharpe median -0.37) and that the macro filter "improves" it (median
+0.84). Both README.md and REPRODUCTION_NOTE.md in this directory repeat them.

## What was wrong

The baseline walk-forward was run with `warmup=0`, the macro variant with
`warmup=150d`. With no warmup, the ORIGINAL bot's own indicators (EMA of 300
4h-bars, 720h breakout) never converge inside a 90-day test window, so it
traded on unconverged signals or not at all (3 windows with zero trades).
The reproduction reproduced the numbers but not their validity.

Original bot, same windows, only the warmup changed:

| history before each test window | OOS Sharpe mean / median | windows >= 1.5 | negative |
|---|---|---|---|
| 0d (what the report used) | -0.80 / -0.37 | 3/14 | 7/14 |
| >= 120d (stable through 400d) | +0.52 / +1.00 | 5/14 | 4/14 |

## Like-for-like numbers (warmup 250d for every variant, fixed params)

| | Sharpe mean | median | >= 1.5 | negative | total return over the 14 test windows | worst window |
|---|---|---|---|---|---|---|
| Original v4_hourly | 0.52 | 1.00 | 5/14 | 4/14 | +56.5% | -11.3% |
| + daily macro filter (20/100) | 0.42 | 0.84 | 7/14 | 6/14 | +54.7% | -7.7% |
| Buy-and-hold BTC | 0.77 | 0.63 | 6/14 | 6/14 | +183.4% | -26.9% |

The macro filter does NOT improve the original when compared fairly.

## Still valid

- Full-period Monte Carlo and the long/short x bull/bear split (single
  full-history runs, no window slicing).
- SlippageModel impact_k=1.0 is uncalibrated.
- The bot does not beat buy-and-hold on total return.

## Not re-verified (ran with warmup=0, treat as unproven)

- "Re-tuning stop_atr/reward or min_trend per window does not help"; the
  corr(IS, OOS) ~ 0 claim. With correct warmup corr(IS, OOS) for both the
  original and the macro variant is -0.33 (14 points, noisy).

## Where the bot loses to buy-and-hold

Position open only 15% of the time (10% long, 5% short). In the 8 test
quarters where BTC rose: HODL +34.2% avg, bot +3.1%. In the 6 where BTC
fell: HODL -17.7%, bot +4.0%. It protects capital but captures ~10% of the
upside.

## Ideas tested this round (8 variants + 5 neighbour values, same BTC
windows: multiple-comparison risk applies)

- Exit when macro flips; let winners run (reward 10R, hold 90d): no gain.
- Persistent trend-follower (long/short, long-only, tight or wide stops):
  worse (total +12% to +25%).
- Faster entry (breakout 240h instead of 720h): best on BTC (Sharpe median
  1.38, +79.7%, worst window -5.3%) but a fragile peak: neighbours 120h/
  360h/480h give 0.64/0.80/1.09, and on ETH and SOL (not used to choose it)
  240h is WORSE than 720h (ETH -0.49 vs 0.34, SOL -0.33 vs 0.02). Not adopted.
- On ETH/SOL the original strategy has roughly no risk-adjusted edge.
