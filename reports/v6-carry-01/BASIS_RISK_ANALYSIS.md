# Why this sleeve should not be leveraged without more work

The carry backtest (`report.json`) assumes the spot and perpetual legs are
perfectly, instantly hedged every hour. In reality the two legs are two
separate orders on two separate books; they do not fill atomically, and the
gap between them (the "basis", `(perp_close - spot_close) / spot_close`)
can move against you in the seconds it takes to submit both. This note
measures how much, using the same real OKX spot + perpetual data as the
backtest (2022-01-17 to 2026-09-01, 40,512 hourly observations).

## Normal conditions: tight

- Basis level: mean -0.9bps, std 2.8bps of price. Spot and perp track each
  other closely almost all the time.

## Stress conditions: the basis jumps exactly when it matters most

The ten largest single-hour basis *changes* (i.e. how much you'd be caught
unhedged for that hour if the legs didn't move together) all cluster on
real, dated market stress:

| Date | Hourly basis swing |
|---|---|
| 2022-06-01 | 0.44% |
| 2022-06-01 | 0.35% |
| 2024-03-11 | 0.32% |
| 2022-04-09 | 0.22% |
| 2022-04-09 | 0.21% |
| 2024-12-05 | 0.20% |
| 2022-05-12 | 0.19% (LUNA collapse) |
| 2022-05-12 | 0.17% (LUNA collapse) |
| 2024-03-11 | 0.17% |
| 2022-11-09 | 0.15% (FTX collapse) |

The dates are not random: 2022-05-12 is the middle of the LUNA/UST death
spiral, 2022-11-09 is the FTX collapse, and both March and December 2024
are known BTC volatility spikes (new all-time highs). The basis widens most
exactly during the events where exchange congestion and execution latency
make it hardest to keep both legs in sync -- the opposite of when you want
your hedge to be weakest.

## Implication for sizing

At 1x notional (what the backtest actually measures), even the worst single
hour (0.44%) is a minor, survivable dent. The concern is leverage: scaling
this sleeve 3-5x, the way a real cash-and-carry position often is precisely
*because* it is meant to be market-neutral, means a stress-hour basis jump
gets multiplied by the same factor, arriving exactly when execution is
least reliable. This is a real, dated pattern in the data, not a
theoretical caveat.

## Recommendation

Keep this sleeve at 1x (unlevered) for now. Leveraging it would require, at
minimum, modelling execution latency and partial-fill risk between the two
legs -- neither is in this backtest, and both are exactly what breaks down
during the hours the basis moves most.
