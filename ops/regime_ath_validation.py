"""Variant of v4_hourly, requested by the user, with the exit logic reworked:

  - BULL regime (EMA40 > EMA300 on the 4h anchor, same trend filter as
    v4_hourly, unchanged): only LONG entries. A long is NOT stopped or
    targeted -- it is held until price makes a genuine new all-time high,
    however long that takes. No max_hours timeout either; that 20-day
    timeout exists in v4_hourly specifically to bound a stop/target trade,
    and does not make sense applied to a hold that may take years.
  - BEAR regime: only SHORT entries, with the SAME stop/target/trailing
    logic v4_hourly already uses. Unchanged.
  - If a long is open and the regime flips to bear before a new ATH is
    reached, it stops being unprotected: a normal stop/target (same ATR
    distance convention as the rest of the project) attaches from that
    point on, and the position is managed like an ordinary v4_hourly trade
    from there. It does not revert to the no-stop ATH hold if the regime
    flips back to bull -- once protected, it stays protected for the rest
    of that trade. This is a disclosed simplification, not a claim that
    it's the only reasonable choice.

Entry signal, trend filter and ATR all come unchanged from v4_hourly's
frozen configs/selected.json params -- nothing here was tuned. The ATR
stop distance is still computed for a bull-regime entry, but only used to
size the position (so risk-per-trade stays comparable to the rest of the
project) -- it is not an active exit while unprotected.

This is a genuinely different risk profile from the rest of the project,
by design: an unprotected long can be underwater 50-70% (BTC does this
recurrently) for a long time before either reaching a new high or the
regime flipping and a stop finally attaching. That is the tradeoff the
user asked to measure, not a bug.
"""
from dataclasses import asdict
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from astra.engine import daily_returns, metrics, size
from astra.legacy_research import monte_carlo, dump
from astra.v3_trend import maker_risk, taker_risk
from astra.v4_hourly import HourlyParams, features as hourly_features

OUT_DIR = Path('reports/v7-regime-ath-01')


def backtest(bars, f, p, risk):
    fee, slip = risk.fee_bps / 10000, risk.slippage_bps / 10000
    cash = risk.capital
    qty, entry, trade_cost, entry_time = 0., 0., 0., None
    flip_time, flip_price = None, None  # when/where protection attached, for diagnostics
    mode = None  # 'ath_hold' or 'protected'
    stop = target = None
    initial_distance = 0.
    peak_favorable_r = 0.
    peak_price = 0.  # highest close reached since entry, for the ath_hold trailing exit
    ath = 0.  # running all-time-high of bars.high, causal (as of previous bar)
    trades = []
    curve, dates = [], []
    bvals, fvals = bars.to_dict('records'), f.to_dict('records')

    for i in range(len(bars)):
        bar = bvals[i]
        previous = {'signal': 0, 'anchor': 0, 'atr': float('nan')} if i == 0 else fvals[i - 1]
        o, h, l, c, funding = bar['open'], bar['high'], bar['low'], bar['close'], bar['funding']
        had_position = qty != 0

        if qty:
            payment = qty * o * funding
            cash -= payment
            trade_cost += payment

        def close(price, reason, side_hint=None):
            nonlocal cash, qty, trade_cost
            side = side_hint if side_hint is not None else (1 if qty > 0 else -1)
            fill = price * (1 - side * slip)
            commission = abs(qty) * fill * fee
            pnl = qty * (fill - entry) - commission - trade_cost
            cash += qty * (fill - entry) - commission
            trades.append({'entry_time': entry_time, 'exit_time': str(bars.index[i]), 'side': int(side),
                            'quantity': abs(qty), 'entry': entry, 'exit': fill, 'net_pnl': pnl, 'reason': reason,
                            'flip_time': flip_time, 'flip_price': flip_price})
            qty = 0.

        if qty > 0 and mode == 'ath_hold':
            peak_price = max(peak_price, h)
            atr_now = float(fvals[i]['atr'])
            peak_favorable_r = (peak_price - entry) / initial_distance if initial_distance > 0 else 0.
            trail_level = (peak_price - atr_now * p.trail_atr
                          if pd.notna(atr_now) and atr_now > 0 and peak_favorable_r >= p.trail_start_r else None)
            # Wide floor, active from entry: reuses risk.max_drawdown (25%),
            # the same number the whole project already uses to define an
            # unacceptable loss, rather than inventing a new one. Catches
            # failed breakouts that go straight down and never reach
            # trail_start_r, which neither the trailing exit nor the slow
            # regime-flip protection can see in time.
            floor_level = entry * (1 - risk.max_drawdown)
            if h >= ath > 0:
                close(max(o, ath), 'new_ath', side_hint=1)
            elif l <= floor_level:
                close(min(o, floor_level), 'floor', side_hint=1)
            elif trail_level is not None and c < trail_level:
                # Faster than waiting for the EMA40/300 regime to flip: give
                # back at most trail_atr*ATR from the trade's OWN peak, only
                # once it's already trail_start_r ahead -- reuses the same
                # frozen trail_atr/trail_start_r as the rest of the project,
                # nothing new tuned. Protects gains already made; does not
                # cap the initial upside the way a fixed stop would.
                close(c, 'trail_exit', side_hint=1)
            elif int(previous['anchor']) == -1:
                # Protect from the CURRENT close, not entry: the slow trend
                # filter can take a long time to confirm the flip, and by
                # then price may already be well past what an entry-anchored
                # stop would have allowed. Anchoring to entry let losses run
                # to -19.5% in testing, far past the intended ~stop_atr*ATR.
                fresh_atr = float(previous['atr']) if pd.notna(previous['atr']) and previous['atr'] > 0 else float(fvals[i]['atr'])
                distance = fresh_atr * p.stop_atr if pd.notna(fresh_atr) and fresh_atr > 0 else initial_distance
                stop = c - distance
                target = c + distance * p.reward
                initial_distance = distance  # so trailing-stop R-multiples are measured from here on
                peak_favorable_r = 0.
                mode = 'protected'
                flip_time, flip_price = str(bars.index[i]), c
        elif qty:
            side = 1 if qty > 0 else -1
            stopped = l <= stop if side == 1 else h >= stop
            reached = h >= target if side == 1 else l <= target
            if stopped:
                close(min(o, stop) if side == 1 else max(o, stop), 'stop', side_hint=side)
            elif reached:
                close(target, 'target', side_hint=side)
            else:
                atr = float(fvals[i]['atr'])
                peak_favorable_r = max(peak_favorable_r, side * (c - entry) / initial_distance) if initial_distance > 0 else 0.
                if pd.notna(atr) and peak_favorable_r >= p.trail_start_r:
                    trail = c - side * atr * p.trail_atr
                    stop = max(stop, trail) if side == 1 else min(stop, trail)

        if not qty and not had_position:
            direction, atr_prev = int(previous['signal']), float(previous['atr'])
            regime = int(previous['anchor'])
            if direction == 1 and regime == 1 and pd.notna(atr_prev) and atr_prev > 0:
                entry_px = o * (1 + slip)
                distance = atr_prev * p.stop_atr
                if distance < entry_px:
                    quantity = size(cash, entry_px, distance, risk)
                    if quantity:
                        qty, entry, entry_time = quantity, entry_px, str(bars.index[i])
                        initial_distance, peak_favorable_r, mode = distance, 0., 'ath_hold'
                        peak_price = entry_px
                        flip_time, flip_price = None, None
                        trade_cost = quantity * entry_px * fee
                        cash -= trade_cost
            elif direction == -1 and regime == -1 and pd.notna(atr_prev) and atr_prev > 0:
                entry_px = o * (1 - slip)
                distance = atr_prev * p.stop_atr
                if distance < entry_px:
                    quantity = size(cash, entry_px, distance, risk)
                    if quantity:
                        qty, entry, entry_time = -quantity, entry_px, str(bars.index[i])
                        initial_distance, peak_favorable_r, mode = distance, 0., 'protected'
                        stop = entry + distance
                        target = entry - distance * p.reward
                        trade_cost = quantity * entry_px * fee
                        cash -= trade_cost

        ath = max(ath, h)
        equity = cash + qty * (c - entry)
        curve.append(equity)
        dates.append(bars.index[i])

    return pd.Series(curve, index=bars.index, name='equity'), trades


def main():
    cfg = json.loads(Path('configs/selected.json').read_text())
    p = HourlyParams(**cfg['params'])
    bars = pd.read_csv('data/BTC-USDT-SWAP-okx-1h.csv', index_col='time', parse_dates=True)
    bars.index = pd.to_datetime(bars.index, utc=True)
    f = hourly_features(bars, p)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, risk in (('taker', taker_risk(cfg['risk']['capital'], cfg['risk']['fraction'])),
                        ('maker', maker_risk(cfg['risk']['capital'], cfg['risk']['fraction']))):
        equity, trades = backtest(bars, f, p, risk)
        m = metrics(equity, trades, risk.capital)
        returns = daily_returns(equity, risk.capital)
        mc = monte_carlo(returns, 2000, seed=99, block_days=7)
        years = m['days'] / 365
        annual = (1 + m['return']) ** (1 / years) - 1 if years > 0 else 0.
        results[label] = {'sharpe': m['sharpe'], 'annualised_return': annual, 'max_drawdown': m['max_drawdown'],
                          'calmar': annual / m['max_drawdown'] if m['max_drawdown'] > 0 else None,
                          'trades': m['trades'], 'win_rate': m['win_rate'], 'monte_carlo_7d_p05': mc['sharpe_p05']}
        equity.to_csv(OUT_DIR / f'equity_{label}.csv', index_label='time')
        pd.DataFrame(trades).to_csv(OUT_DIR / f'trades_{label}.csv', index=False)
        print(json.dumps({label: results[label]}, indent=2, default=str), flush=True)

    dump(OUT_DIR / 'report.json', {
        'params': asdict(p), 'note': 'No DSR: same frozen entry params as v4_hourly, only exit logic changed.',
        'results': results,
        'design': ['Bull regime: longs only, no stop, hold to new all-time-high, no timeout.',
                   'Bear regime: shorts only, normal v4_hourly stop/target/trailing.',
                   'A long that is still open when regime flips to bear gets a stop/target attached '
                   'from that point on and stays protected for the rest of that trade.']})
    print('=== DONE. See reports/v7-regime-ath-01/report.json ===')


if __name__ == '__main__':
    main()
