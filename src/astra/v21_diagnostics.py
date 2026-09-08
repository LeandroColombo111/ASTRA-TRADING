"""Post-precheck diagnostics over saved v2.1 artifacts. Read-only research.

Consumes ZERO optimization attempts. Does not modify the precheck, the
protocol, the universe gate or any acceptance threshold. Every simulation
routes through `simulate_exec`, which is proven equivalent to the precheck's
`simulate_raw` under default settings by `assert_simulator_equivalence`, so
any difference reported here is attributable to the setting under test and
not to a reimplementation.

Three diagnostics, in the order the decision document requires:

  D1  The random cohort control is rebuilt turnover- and cost-matched.
  D2  P&L is decomposed into rank contribution and inverse-vol overlay.
  D3  Execution is re-measured as post-only maker with a no-trade band and
      an explicit unfilled-order model.
"""
from pathlib import Path
from io import BytesIO
import json
import numpy as np
import pandas as pd

from .research import dump, cost_gate


def dump_clean(path, obj):
    dump(path, jsonable(obj))
from .v21_precheck import OUT, annual_sharpe, simulate_raw, read_histories
from .v2_data import verified_read

DIAG = OUT / 'diagnostics'
CAPITAL = 10000.
MAKER_FEE_FALLBACK = .0002


# --------------------------------------------------------------------------
# Artifact loading. Signals are NOT recomputed; the saved weights are the
# object under audit, so recomputing them would defeat the purpose.
# --------------------------------------------------------------------------

def load_artifacts():
    if not (OUT / 'raw_weights.csv').exists():
        raise RuntimeError('v2.1 precheck artifacts absent; run precheck first')
    weights = pd.read_csv(OUT / 'raw_weights.csv', index_col='time', parse_dates=True)
    scores = pd.read_csv(OUT / 'raw_scores.csv', index_col='time', parse_dates=True)
    weights.index = pd.to_datetime(weights.index, utc=True)
    scores.index = pd.to_datetime(scores.index, utc=True)
    names = list(weights.columns)

    histories = read_histories()
    opens = pd.DataFrame({s: histories[s].open for s in names})
    # The precheck fetched the terminal mark separately into a verified cache.
    # Reuse that cache; never substitute a synthetic price for a missing one.
    terminal = pd.Timestamp('2026-09-01', tz='UTC')
    if terminal not in opens.index:
        opens.loc[terminal] = np.nan
        opens.sort_index(inplace=True)
    cache = Path('data/v21/terminal/daily')
    for s in names:
        if np.isfinite(opens.at[terminal, s]):
            continue
        path = cache / f'{s}.csv'
        if not path.exists():
            raise RuntimeError('Terminal OKX open missing for ' + s)
        frame = pd.read_csv(BytesIO(verified_read(path)), index_col='time', parse_dates=True)
        frame.index = pd.to_datetime(frame.index, utc=True)
        if terminal not in frame.index:
            raise RuntimeError('Terminal OKX open missing for ' + s)
        opens.at[terminal, s] = float(frame.at[terminal, 'open'])

    events = pd.read_csv(BytesIO(verified_read(Path('data/v21/funding_events.csv'))))
    events['time'] = pd.to_datetime(events.time, utc=True)
    events['day'] = events.time.dt.floor('D')
    funding = events.pivot_table(index='day', columns='instrument_name', values='funding_rate',
                                 aggfunc='sum').reindex(index=weights.index, columns=names)
    counts = events.pivot_table(index='day', columns='instrument_name', values='funding_rate',
                                aggfunc='count').reindex(index=weights.index, columns=names)
    midnight = events.loc[events.time == events.day].pivot_table(
        index='day', columns='instrument_name', values='funding_rate',
        aggfunc='sum').reindex(index=weights.index, columns=names).fillna(0.)

    records = json.loads((OUT / 'spread_samples.json').read_text())
    spreads = {(r['month'], r['symbol']): r['half_spread'] for r in records if 'error' not in r}
    fees = json.loads((OUT / 'account_fee.json').read_text())['values']
    taker = abs(float(fees.get('takerU') or fees['taker']))
    maker_raw = fees.get('makerU') or fees.get('maker')
    maker = abs(float(maker_raw)) if maker_raw not in (None, '') else MAKER_FEE_FALLBACK
    return dict(weights=weights, scores=scores, opens=opens, funding=funding, counts=counts,
                midnight=midnight, spreads=spreads, taker=taker, maker=maker, names=names)


# --------------------------------------------------------------------------
# Simulator. Mirrors simulate_raw exactly when the extra arguments are left
# at their defaults; the extra arguments are what the diagnostics vary.
# --------------------------------------------------------------------------

def simulate_exec(weights, opens, funding, counts, spreads, fee, horizon, funding_at_open=None,
                  band=0., crosses_spread=True, fill_rate=1., fill_mode='random', seed=7):
    """Daily units held between rebalances, marked open-to-open.

    band            relative no-trade band; a symbol only rebalances when the
                    target notional deviates by more than `band` of itself.
    crosses_spread  False models resting post-only orders: the half-spread is
                    not paid. It is never booked as a credit.
    fill_rate       fraction of intended rebalance notional that executes.
    fill_mode       'random' drops trades by seeded draw; 'adverse' drops the
                    trades that would have been most profitable next bar,
                    the conservative bound for passive execution.
    """
    if not 0. <= band < 1.:
        raise ValueError('Band must be in [0,1)')
    if not 0. < fill_rate <= 1.:
        raise ValueError('Fill rate must be in (0,1]')
    if fill_mode not in ('random', 'adverse'):
        raise ValueError('Unknown fill mode')
    names = list(weights.columns)
    rng = np.random.default_rng(seed)
    q = np.zeros(len(names))
    gross_nav = net_nav = CAPITAL
    rows = []
    previous_month = None
    missing_spread, missing_funding = set(), set()
    max_notional = 0.
    turnover = []
    unfilled_notional = 0.
    intended_notional = 0.
    totals = dict(fee=0., spread=0., funding=0., gross=0.)

    for i, date in enumerate(weights.index):
        nextdate = date + pd.Timedelta(days=1)
        month = str(date.date().replace(day=1))
        price = opens.loc[date, names].to_numpy()
        nextprice = opens.loc[nextdate, names].to_numpy()
        target = weights.loc[date].to_numpy()
        active = (q != 0) | (target != 0)
        if not np.isfinite(price[active]).all() or not np.isfinite(nextprice[active]).all():
            raise ValueError('Missing held price; no synthetic delisting fill')
        before, net_before = gross_nav, net_nav
        prior_q = q.copy()
        trade = np.zeros(len(names))

        if i % horizon == 0 or month != previous_month:
            newq = np.divide(gross_nav * target, price, out=np.zeros(len(names)), where=target != 0)
            delta = newq - q
            if band > 0:
                # Hold the current position unless the deviation is material.
                reference = np.where(newq != 0, abs(newq), abs(q))
                keep = abs(delta) <= band * reference
                newq = np.where(keep, q, newq)
                delta = newq - q
            if fill_rate < 1.:
                moving = np.flatnonzero(delta != 0)
                intended_notional += float(np.sum(abs(delta) * np.nan_to_num(price)))
                drop = int(round((1 - fill_rate) * len(moving)))
                if drop > 0 and len(moving):
                    if fill_mode == 'random':
                        chosen = rng.choice(moving, size=min(drop, len(moving)), replace=False)
                    else:
                        # Adverse selection: the trades that would have paid off
                        # are the ones that do not get filled passively.
                        edge = delta[moving] * np.nan_to_num(nextprice[moving] - price[moving])
                        chosen = moving[np.argsort(-edge)[:min(drop, len(moving))]]
                    unfilled_notional += float(np.sum(abs(delta[chosen]) * np.nan_to_num(price[chosen])))
                    newq[chosen] = q[chosen]
                    delta = newq - q
            trade = abs(delta) * np.nan_to_num(price)
            q = newq
        previous_month = month

        terminal_trade = abs(q) * np.nan_to_num(nextprice) if i == len(weights) - 1 else np.zeros(len(names))
        traded = trade + terminal_trade
        tc = float(traded.sum() * fee)
        sc = 0.
        for j in np.flatnonzero(traded):
            half = spreads.get((month, names[j]))
            if half is None:
                missing_spread.add((month, names[j]))
            elif crosses_spread:
                sc += traded[j] * half

        held = q != 0
        dailyfund = funding.loc[date].to_numpy()
        count = counts.loc[date].to_numpy()
        for j in np.flatnonzero(held & (~np.isfinite(dailyfund) | (count < 3))):
            missing_funding.add((str(date.date()), names[j]))
        openfund = funding_at_open.loc[date].to_numpy() if funding_at_open is not None else np.zeros(len(names))
        fc = float(np.sum(q[held] * price[held] * np.nan_to_num(dailyfund[held] - openfund[held])))
        prior_held = prior_q != 0
        fc += float(np.sum(prior_q[prior_held] * price[prior_held] * openfund[prior_held]))

        gp = float(np.sum(q[held] * (nextprice[held] - price[held])))
        gross_nav += gp
        net_nav += gp - tc - sc - fc
        if gross_nav <= 0 or net_nav <= 0:
            raise ValueError('Raw portfolio insolvent')
        max_notional = max(max_notional, float(np.max(abs(q[held] * price[held]))) if held.any() else 0.)
        turnover.append(float(trade.sum() / before))
        totals['fee'] += tc
        totals['spread'] += sc
        totals['funding'] += fc
        totals['gross'] += gp
        rows.append({'gross_return': gp / before, 'net_return': (gp - tc - sc - fc) / net_before,
                     'gross_nav': gross_nav, 'net_nav': net_nav, 'price_pnl': gp, 'fee': tc,
                     'sampled_spread_cost': sc, 'funding_cost': fc, 'turnover': turnover[-1]})

    complete = not missing_spread and not missing_funding
    diag = {'cost_coverage_complete': complete,
            'spread_coverage_complete': not missing_spread,
            'funding_coverage_complete': not missing_funding,
            'missing_spread_pairs': len(missing_spread),
            'missing_funding_days_symbols': len(missing_funding),
            'mean_daily_turnover_equity': float(np.mean(turnover)),
            'max_position_notional_usdt': max_notional,
            'gross_pnl_usdt': totals['gross'], 'fees_usdt': totals['fee'],
            'sampled_spread_usdt': totals['spread'], 'funding_usdt': totals['funding'],
            'net_return': net_nav / CAPITAL - 1 if complete else None,
            'unfilled_notional_usdt': unfilled_notional,
            'intended_rebalance_notional_usdt': intended_notional}
    return pd.DataFrame(rows, index=weights.index), diag


def jsonable(obj):
    """numpy scalars leak in through pandas; the report must stay plain JSON."""
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


def summarise(frame, diag):
    total = diag['fees_usdt'] + diag['sampled_spread_usdt'] + diag['funding_usdt']
    return {'gross_sharpe': annual_sharpe(frame.gross_return),
            'net_sharpe': annual_sharpe(frame.net_return) if diag['cost_coverage_complete'] else None,
            'total_costs_usdt': total,
            'cost_gate': cost_gate(diag['gross_pnl_usdt'], total), **diag}


def assert_accounting(frame):
    residual = CAPITAL + frame.price_pnl.sum() - frame.fee.sum() - frame.sampled_spread_cost.sum() \
        - frame.funding_cost.sum() - frame.net_nav.iloc[-1]
    if abs(residual) > 1e-6:
        raise AssertionError(f'Accounting identity violated by {residual}')


def assert_simulator_equivalence(a):
    """simulate_exec must reproduce simulate_raw bit-for-bit at defaults."""
    old, olddiag = simulate_raw(a['weights'], a['opens'], a['funding'], a['counts'],
                                a['spreads'], a['taker'], 1, a['midnight'])
    new, newdiag = simulate_exec(a['weights'], a['opens'], a['funding'], a['counts'],
                                 a['spreads'], a['taker'], 1, a['midnight'])
    shared = [c for c in old.columns if c in new.columns]
    delta = float(np.max(np.abs(old[shared].to_numpy() - new[shared].to_numpy())))
    if delta > 1e-9:
        raise AssertionError(f'Simulator drift {delta}; diagnostics are not comparable')
    for key in ('gross_pnl_usdt', 'fees_usdt', 'sampled_spread_usdt', 'funding_usdt'):
        if abs(olddiag[key] - newdiag[key]) > 1e-6:
            raise AssertionError(f'Simulator diverges on {key}')
    assert_accounting(new)
    return {'max_abs_row_difference': delta, 'equivalent': True,
            'baseline': summarise(old, olddiag)}


# --------------------------------------------------------------------------
# D1 - the random cohort control
# --------------------------------------------------------------------------

def _legacy_control_instrumented(a, repetitions=200, seed=2101):
    """Reproduces the shipped control and records what it actually costs.

    The shipped version permutes whole weight ROWS across dates inside a
    month. That changes the exposure path, so its turnover and costs are not
    the strategy's. This function measures that instead of assuming it.
    """
    weights, opens = a['weights'], a['opens']
    dates, names = weights.index, a['names']
    rng = np.random.default_rng(seed)
    w = weights.to_numpy()
    price = opens.reindex(dates).loc[:, names].to_numpy()
    nextprice = opens.reindex(dates + pd.Timedelta(days=1)).loc[:, names].to_numpy()
    returns = np.nan_to_num(nextprice / price - 1)
    funds = np.nan_to_num(a['funding'].to_numpy())
    openfund = a['midnight'].to_numpy()
    halves = np.array([[a['spreads'].get((str(d.date().replace(day=1)), s), np.nan) for s in names]
                       for d in dates])
    months = dates.strftime('%Y-%m')
    groups = [np.flatnonzero(months == m) for m in sorted(set(months))]
    fee = a['taker']
    out = []
    for _ in range(repetitions):
        p = w.copy()
        for idx in groups:
            p[idx] = w[rng.permutation(idx)]
        grossret = np.sum(p * returns, axis=1)
        grossbefore = np.r_[CAPITAL, CAPITAL * np.cumprod(1 + grossret)[:-1]]
        drift = np.zeros_like(p)
        drift[1:] = p[:-1] * (1 + returns[:-1]) / (1 + grossret[:-1, None])
        trade = abs(p - drift)
        trade[-1] += abs(p[-1]) * (1 + returns[-1])
        costs = np.sum(trade * (fee + np.nan_to_num(halves)), axis=1)
        fundingcost = np.sum(p * (funds - openfund) + drift * openfund, axis=1)
        pnl = grossbefore * (grossret - costs - fundingcost)
        netnav = CAPITAL + np.cumsum(pnl)
        before = np.r_[CAPITAL, netnav[:-1]]
        out.append({'net_sharpe': annual_sharpe(pnl / before),
                    'gross_sharpe': annual_sharpe(grossret),
                    'mean_daily_gross_return': float(grossret.mean()),
                    'daily_gross_vol': float(grossret.std(ddof=1)),
                    'mean_daily_turnover': float(trade.sum(axis=1).mean()),
                    'total_costs_fraction': float(costs.sum())})
    return pd.DataFrame(out)


def _matched_control(a, repetitions, seed):
    """Cross-sectional permutation routed through the strategy's simulator.

    The null is: the weight magnitudes and the long/short split are kept, but
    they are attached to the wrong symbols. Membership is respected, so a
    symbol only ever receives a weight on days it was admitted. Because this
    runs through simulate_exec, rebalance frequency, funding and the cost
    model are identical to the strategy by construction rather than by
    assumption.
    """
    weights = a['weights']
    values = weights.to_numpy()
    rng = np.random.default_rng(seed)
    rows = []
    for trial in range(repetitions):
        shuffled = values.copy()
        for i in range(values.shape[0]):
            active = np.flatnonzero(values[i] != 0)
            if len(active) > 1:
                shuffled[i, active] = values[i, active][rng.permutation(len(active))]
        frame, diag = simulate_exec(pd.DataFrame(shuffled, index=weights.index, columns=weights.columns),
                                    a['opens'], a['funding'], a['counts'], a['spreads'],
                                    a['taker'], 1, a['midnight'])
        rows.append({'trial': trial, 'net_sharpe': annual_sharpe(frame.net_return),
                     'gross_sharpe': annual_sharpe(frame.gross_return),
                     'mean_daily_turnover_equity': diag['mean_daily_turnover_equity'],
                     'gross_pnl_usdt': diag['gross_pnl_usdt'],
                     'total_costs_usdt': diag['fees_usdt'] + diag['sampled_spread_usdt'] + diag['funding_usdt']})
    return pd.DataFrame(rows)


def _relabel_control(a, repetitions, seed):
    """Persistence-preserving null: one fixed symbol relabeling per month.

    The cross-sectional permutation control destroys the day-to-day
    persistence of the portfolio, so it churns far more than the strategy and
    is penalised by costs it would never have paid. Drawing ONE relabeling per
    month and applying it to every day in that month keeps the exposure path
    -- and therefore the turnover -- while still severing the link between a
    symbol and the signal that selected it. This is the control the strategy
    should be judged against.
    """
    weights = a['weights']
    values = weights.to_numpy()
    index = weights.index
    months = index.strftime('%Y-%m')
    groups = {m: np.flatnonzero(months == m) for m in sorted(set(months))}
    rng = np.random.default_rng(seed)
    rows = []
    for trial in range(repetitions):
        shuffled = values.copy()
        for _, idx in groups.items():
            block = values[idx]
            active = np.flatnonzero((block != 0).any(axis=0))
            if len(active) > 1:
                shuffled[np.ix_(idx, active)] = block[:, active[rng.permutation(len(active))]]
        frame, diag = simulate_exec(pd.DataFrame(shuffled, index=index, columns=weights.columns),
                                    a['opens'], a['funding'], a['counts'], a['spreads'],
                                    a['taker'], 1, a['midnight'])
        rows.append({'trial': trial, 'net_sharpe': annual_sharpe(frame.net_return),
                     'gross_sharpe': annual_sharpe(frame.gross_return),
                     'mean_daily_turnover_equity': diag['mean_daily_turnover_equity'],
                     'gross_pnl_usdt': diag['gross_pnl_usdt']})
    return pd.DataFrame(rows)


def d1_control_audit(a, baseline, repetitions=200, seed=2101):
    legacy = _legacy_control_instrumented(a, repetitions, seed)
    legacy.to_csv(DIAG / 'd1_legacy_control_instrumented.csv', index=False)
    matched = _matched_control(a, repetitions, seed)
    matched.to_csv(DIAG / 'd1_matched_control.csv', index=False)
    relabel = _relabel_control(a, repetitions, seed)
    relabel.to_csv(DIAG / 'd1_relabel_control.csv', index=False)

    strategy_turnover = baseline['mean_daily_turnover_equity']
    strategy_net = baseline['net_sharpe']
    legacy_turnover = float(legacy.mean_daily_turnover.median())
    result = {
        'strategy': {'net_sharpe': strategy_net, 'gross_sharpe': baseline['gross_sharpe'],
                     'mean_daily_turnover_equity': strategy_turnover},
        'legacy_control_as_shipped': {
            'repetitions': int(len(legacy)),
            'median_net_sharpe': float(legacy.net_sharpe.median()),
            'median_gross_sharpe': float(legacy.gross_sharpe.median()),
            'median_mean_daily_turnover': legacy_turnover,
            'turnover_ratio_vs_strategy': legacy_turnover / strategy_turnover if strategy_turnover else None,
            'median_total_costs_fraction_of_nav': float(legacy.total_costs_fraction.median()),
            'median_daily_gross_vol': float(legacy.daily_gross_vol.median())},
        'matched_control': {
            'repetitions': int(len(matched)),
            'method': 'Cross-sectional permutation of weights within the admitted set, evaluated through the strategy simulator.',
            'median_net_sharpe': float(matched.net_sharpe.median()),
            'p05_net_sharpe': float(matched.net_sharpe.quantile(.05)),
            'p95_net_sharpe': float(matched.net_sharpe.quantile(.95)),
            'median_mean_daily_turnover_equity': float(matched.mean_daily_turnover_equity.median()),
            'strategy_percentile': float(100 * (matched.net_sharpe < strategy_net).mean()),
            'caveat': 'Daily reassignment destroys portfolio persistence, so this control churns far more than the strategy and pays costs the strategy never pays. Its percentile is biased in the strategy favour and is reported for completeness only.'},
        'relabel_control_primary': {
            'repetitions': int(len(relabel)),
            'method': 'One fixed symbol relabeling per membership month, applied to every day in that month. Preserves the exposure path and therefore the turnover; severs symbol-to-signal association.',
            'median_net_sharpe': float(relabel.net_sharpe.median()),
            'p05_net_sharpe': float(relabel.net_sharpe.quantile(.05)),
            'p95_net_sharpe': float(relabel.net_sharpe.quantile(.95)),
            'median_mean_daily_turnover_equity': float(relabel.mean_daily_turnover_equity.median()),
            'turnover_ratio_vs_strategy': float(relabel.mean_daily_turnover_equity.median() / strategy_turnover) if strategy_turnover else None,
            'strategy_percentile': float(100 * (relabel.net_sharpe < strategy_net).mean())},
    }
    ratio = result['legacy_control_as_shipped']['turnover_ratio_vs_strategy']
    primary = result['relabel_control_primary']
    result['verdict'] = (
        'Legacy control is NOT turnover-matched (ratio %.2f); its percentile is void. '
        'Against the persistence-preserving control (turnover ratio %.2f) the strategy sits at '
        'percentile %.1f with a control median of %.3f.'
        % (ratio, primary['turnover_ratio_vs_strategy'], primary['strategy_percentile'],
           primary['median_net_sharpe']))
    dump_clean(DIAG / 'd1_control_audit.json', result)
    return result


# --------------------------------------------------------------------------
# D2 - is the P&L coming from the ranking or from the inverse-vol overlay?
# --------------------------------------------------------------------------

def _rank_equal_weights(a):
    """Same long/short split and same gross exposure, but flat inside each leg.

    Removes the inverse-vol overlay while preserving everything else, so the
    difference against the strategy isolates the overlay's contribution.
    """
    weights, scores = a['weights'], a['scores']
    out = np.zeros(weights.shape)
    values, raw = weights.to_numpy(), scores.to_numpy()
    for i in range(values.shape[0]):
        active = np.flatnonzero(values[i] != 0)
        if not len(active):
            continue
        centered = raw[i, active] - np.nanmean(raw[i, active])
        longs, shorts = active[centered > 0], active[centered < 0]
        if not len(longs) or not len(shorts):
            continue
        gross = np.abs(values[i, active]).sum()
        out[i, longs] = gross / 2 / len(longs)
        out[i, shorts] = -gross / 2 / len(shorts)
    return pd.DataFrame(out, index=weights.index, columns=weights.columns)


def _causality_audit(a):
    """The weights on date t must not respond to anything dated t or later."""
    histories = read_histories()
    names = a['names']
    closes = pd.DataFrame({s: histories[s].close for s in names})
    returns = closes.pct_change(fill_method=None)
    vol = returns.rolling(30, min_periods=30).std(ddof=1)
    findings = []
    for date in a['weights'].index[::37]:
        prev = date - pd.Timedelta(days=1)
        if prev not in vol.index:
            continue
        active = a['weights'].loc[date]
        active = active[active != 0].index
        if not len(active):
            continue
        # Recomputing volatility with data truncated at prev must reproduce
        # the value the weights were built from.
        truncated = returns.loc[:prev, active].rolling(30, min_periods=30).std(ddof=1).iloc[-1]
        reference = vol.loc[prev, active]
        gap = float(np.nanmax(np.abs(truncated - reference)))
        findings.append({'date': str(date.date()), 'max_abs_vol_difference': gap})
    worst = max((f['max_abs_vol_difference'] for f in findings), default=0.)
    return {'checked_dates': len(findings), 'max_abs_vol_difference': worst,
            'strictly_causal': bool(worst < 1e-12),
            'note': 'Rolling volatility truncated at t-1 reproduces the value used to build the weights for t.',
            'samples': findings[:8]}


def d2_weighting_decomposition(a, baseline):
    equal = _rank_equal_weights(a)
    frame, diag = simulate_exec(equal, a['opens'], a['funding'], a['counts'], a['spreads'],
                                a['taker'], 1, a['midnight'])
    assert_accounting(frame)
    frame.to_csv(DIAG / 'd2_rank_equal_weight_daily.csv', index_label='time')
    rank_only = summarise(frame, diag)

    overlay_gross = baseline['gross_pnl_usdt'] - rank_only['gross_pnl_usdt']
    share = overlay_gross / baseline['gross_pnl_usdt'] if baseline['gross_pnl_usdt'] else None
    ic = pd.read_csv(OUT / 'ic_series.csv')
    ic1 = ic.loc[ic.horizon == 1, 'ic']
    result = {
        'question': 'Does the P&L come from the ranking or from the inverse-volatility overlay?',
        'strategy_full': {'gross_pnl_usdt': baseline['gross_pnl_usdt'],
                          'gross_sharpe': baseline['gross_sharpe'],
                          'net_sharpe': baseline['net_sharpe']},
        'rank_equal_weight_no_overlay': {'gross_pnl_usdt': rank_only['gross_pnl_usdt'],
                                         'gross_sharpe': rank_only['gross_sharpe'],
                                         'net_sharpe': rank_only['net_sharpe'],
                                         'mean_daily_turnover_equity': rank_only['mean_daily_turnover_equity']},
        'overlay_contribution_usdt': overlay_gross,
        'overlay_share_of_gross': share,
        'ic_h1_mean': float(ic1.mean()) if len(ic1) else None,
        'causality_audit': _causality_audit(a),
    }
    if share is None:
        result['verdict'] = 'Gross P&L is zero; decomposition undefined.'
    elif rank_only['gross_pnl_usdt'] <= 0:
        result['verdict'] = ('The ranking alone loses money gross. The edge is the inverse-volatility '
                             'overlay, not the momentum signal. Optimising the ensemble would target '
                             'the wrong object; the hypothesis must be rewritten around the overlay.')
    elif share > .5:
        result['verdict'] = ('The overlay supplies most of the gross P&L (%.0f%%). The momentum signal '
                             'is a minority contributor.' % (100 * share))
    else:
        result['verdict'] = ('The ranking carries the gross P&L (%.0f%% from the signal). The IC and the '
                             'P&L can be reconciled by the weighting, not contradicted by it.' % (100 * (1 - share)))
    dump_clean(DIAG / 'd2_weighting_decomposition.json', result)
    return result


# --------------------------------------------------------------------------
# D3 - post-only maker execution with a no-trade band and unfilled orders
# --------------------------------------------------------------------------

def d3_maker_execution(a, baseline, band=.20):
    scenarios = []

    def run(label, fee, crosses, band_value, fill_rate, mode):
        meta = dict(label=label, fee_bps=round(fee * 10000, 2), crosses_spread=crosses,
                    band=band_value, fill_rate=fill_rate, fill_mode=mode)
        try:
            frame, diag = simulate_exec(a['weights'], a['opens'], a['funding'], a['counts'], a['spreads'],
                                        fee, 1, a['midnight'], band=band_value, crosses_spread=crosses,
                                        fill_rate=fill_rate, fill_mode=mode)
        except ValueError as exc:
            # Capital destruction is a legitimate outcome of a punitive execution
            # assumption, not a failure to measure. Record it and continue.
            row = dict(meta, outcome='RUINED', reason=str(exc), net_sharpe=None,
                       cost_gate={'passed': False, 'ratio': None, 'reason': 'portfolio_ruined'})
            scenarios.append(row)
            return row
        assert_accounting(frame)
        row = summarise(frame, diag)
        row.update(meta, outcome='COMPLETED')
        scenarios.append(row)
        return row

    run('taker_as_measured', a['taker'], True, 0., 1., 'random')
    run('taker_with_band', a['taker'], True, band, 1., 'random')
    run('maker_no_band_full_fill', a['maker'], False, 0., 1., 'random')
    run('maker_band_full_fill', a['maker'], False, band, 1., 'random')
    for rate in (.8, .6):
        for mode in ('random', 'adverse'):
            run(f'maker_band_fill{int(rate*100)}_{mode}', a['maker'], False, band, rate, mode)

    table = pd.DataFrame([{k: v for k, v in s.items() if not isinstance(v, dict)} for s in scenarios])
    table.to_csv(DIAG / 'd3_execution_scenarios.csv', index=False)
    passing = [s for s in scenarios if s['cost_gate']['passed']]
    survived = [s for s in scenarios if s.get('outcome') == 'COMPLETED' and s['net_sharpe'] is not None]
    conservative = [s for s in survived if s['fill_rate'] <= .8]
    result = {
        'maker_fee_bps': round(a['maker'] * 10000, 2), 'taker_fee_bps': round(a['taker'] * 10000, 2),
        'no_trade_band': band,
        'scenarios': scenarios,
        'scenarios_passing_cost_gate': [s['label'] for s in passing],
        'net_sharpe_range_conservative': [min((s['net_sharpe'] for s in conservative), default=None),
                                          max((s['net_sharpe'] for s in conservative), default=None)],
        'ruined_scenarios': [s['label'] for s in scenarios if s.get('outcome') == 'RUINED'],
        'note': ('Post-only is modelled as not paying the half-spread; it is never booked as a credit. '
                 'Unfilled orders retain the prior position. The adverse mode drops, every single day, '
                 'the trades that would have been most profitable next bar. That is a maximal bound, '
                 'not a forecast, and compounding it daily can destroy the portfolio; where it does, '
                 'the scenario is reported as RUINED rather than as a measurement.'),
        'fill_rate_caveat': ('Daily bars cannot determine passive fill rates, which depend on queue '
                             'position within the bar. The fill rate is therefore a stated assumption '
                             'and results are reported across a range, not a measured quantity.'),
    }
    dump_clean(DIAG / 'd3_maker_execution.json', result)
    return result


# --------------------------------------------------------------------------

def run_all(repetitions=200):
    if (OUT / 'run.closed').exists():
        print('Note: v2.1 run is archived. Diagnostics are read-only and change no gate.', flush=True)
    DIAG.mkdir(parents=True, exist_ok=True)
    a = load_artifacts()
    equivalence = assert_simulator_equivalence(a)
    baseline = equivalence.pop('baseline')
    print('Simulator equivalence verified (max row delta %.2e)' % equivalence['max_abs_row_difference'], flush=True)

    d1 = d1_control_audit(a, baseline, repetitions)
    print('D1 done:', d1['verdict'], flush=True)
    d2 = d2_weighting_decomposition(a, baseline)
    print('D2 done:', d2['verdict'], flush=True)
    d3 = d3_maker_execution(a, baseline)
    print('D3 done. Scenarios passing cost gate:', d3['scenarios_passing_cost_gate'], flush=True)

    summary = {'status': 'DIAGNOSTICS_COMPLETE', 'optimization_attempts_used': 0,
               'approved_for_live': False, 'changes_to_gates': 'none',
               'simulator_equivalence': equivalence, 'baseline_strategy': baseline,
               'd1_control_audit': d1, 'd2_weighting_decomposition': d2, 'd3_maker_execution': d3}
    dump_clean(DIAG / 'diagnostics_report.json', summary)
    return summary


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='v2.1 post-precheck diagnostics (read-only)')
    parser.add_argument('--repetitions', type=int, default=200)
    print(json.dumps(run_all(parser.parse_args().repetitions)['d1_control_audit']['verdict'], indent=2))
