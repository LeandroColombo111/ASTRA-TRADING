# Why SOL's drawdown halt fired on OKX-native data

`SOL/report.json` shows `"halted": true` -- the account's own 25% max-drawdown
kill-switch (`configs/selected.json`'s `risk.max_drawdown`) tripped during the
backtest. This is the same circuit breaker that runs in production
(`src/astra/service.py`); it fired here exactly as designed. This note
records why, so the halt isn't mistaken for a bug.

## Not a single bad trade -- a two-year grind

Peak equity was 2023-12-25 (~$15,077). From there to the halt on 2026-01-29,
58 trades followed, only 16 winners (27.6% -- worse than SOL's own 32.5%
win rate over the full period). Net result of that stretch: -$2,998, a 25.0%
drawdown from peak, which is exactly the configured halt threshold.

## Ruled out: the trailing stop is not the cause

Hypothesis checked and rejected: that the trailing stop cuts SOL's winners
short more than BTC/ETH's, starving it of the big wins needed to offset a
low win rate. Measured directly from `trades.csv` (OKX-native, all three
symbols, same frozen params):

| | BTC | ETH | SOL |
|---|---|---|---|
| Win rate | 40.7% | 37.5% | 32.5% |
| Winners hitting full 3R target | 70.8% | 66.7% | 67.6% |
| Winners cut short by trailing stop | 29.2% | 33.3% | 32.4% |
| Avg R when cut short | 1.16R | 1.02R | 1.08R |
| **Expectancy (avg R per trade)** | **+0.38R** | **+0.23R** | **+0.08R** |

The trailing stop truncates almost the same fraction of winners, by almost
the same amount, in all three symbols. That rules it out as SOL-specific.

## The actual cause: SOL's edge is thin, not broken

SOL's per-trade expectancy (+0.08R) is barely positive -- an order of
magnitude thinner than BTC's (+0.38R). With that little margin, an
ordinary losing streak (not a rare event) is enough to erode 25% from
peak before the long-run average can reassert itself. BTC and ETH have
enough edge per trade to absorb the same kind of streak without tripping
the halt.

Cross-checked against the Binance-proxy SOL run (`reports/v4-hourly-eth-sol/SOLUSDT/report.json`):
max drawdown there was 23.66%, right at the same edge, on a different
data source and a different (longer) window. Same weak spot shows up
either way -- not a data-source artifact.

## Takeaway

The halt behaved correctly. The finding is about SOL, not about the
kill-switch: this exact frozen parameter set does not have enough edge on
SOL to be resilient to a normal losing streak. Do not run this config live
on SOL without revisiting it -- BTC and ETH did not show this weakness.
