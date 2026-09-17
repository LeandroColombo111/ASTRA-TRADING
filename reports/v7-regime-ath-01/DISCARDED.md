# Regime-conditional "hold to ATH" exit: discarded

Idea tested: same frozen v4_hourly entry signal, but bull-regime longs are
never stopped or targeted -- held until a genuine new all-time high,
however long that takes. Bear-regime shorts keep the normal stop/target.
If regime flips to bear while a long is still open, it gets protection
attached from that point on.

Leverage was ruled out before backtesting anything: BTC's real drawdowns
(-67% in our own OKX data alone, -77% to -87% in prior cycles) would
liquidate any leveraged position long before an ATH could ever be reached.
Everything below is unlevered (1x).

## Four iterations, all worse than the current v4_hourly

| Variant | Sharpe (taker) | Max drawdown |
|---|---|---|
| Current v4_hourly (unchanged, for reference) | 1.07 | 19% |
| Base regime/ATH design | 0.27 | 37% |
| + protect from current price (not entry) on regime flip | 0.16 | 41% |
| + fast trailing exit from the trade's own peak | 0.07 | 42% |
| + wide floor at -25% (reuses risk.max_drawdown) | 0.07 (no change) | 42% (no change) |

## What was actually learned

- The core loss driver is unprotected long positions that never turn a
  profit: they erode -8.6% on average (worst -19.5%) before the slow
  EMA40/300 regime filter ever confirms the flip and attaches protection.
- A trailing exit from the trade's own peak works well for what it targets
  (locks in gains before giveback, 100% win rate on those 20 trades) but
  cannot see this problem at all -- it only activates after 2R of profit,
  and the losing trades here never get there.
- A wide floor reusing the project's own 25% catastrophic-drawdown
  constant never fired even once: the regime flip always arrives before
  a single trade decays that far, so it added nothing.
- Tightening the floor below the observed -19.5% worst case would work,
  but that number would have no principled anchor -- it would be invented
  specifically to make this backtest look better, which is exactly the
  kind of undisclosed search this project has been careful to avoid
  everywhere else (DSR, cross-asset validation, the ensemble weighting
  discussion).

## Conclusion

Not pursued further. Keeping a fixed stop-loss under the current
v4_hourly design outperforms every variant of "don't stop longs while
nominally in a bull regime" that was tried here.
