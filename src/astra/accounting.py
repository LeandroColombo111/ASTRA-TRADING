"""Deposit-aware drawdown and time-weighted return.

Both fixes read the same source: OKX account bills, filtered to bill
type '1' (Transfer) -- funding<->trading transfers, which is how external
deposits and withdrawals reach the SWAP trading account this service
manages. Trade PnL, fees and funding settlements carry other bill types
and are correctly excluded.

Without this, a deposit inflates `peak` (service.py used raw equity), so
a real drawdown on the pre-deposit capital can hide beneath the new,
larger peak. Subtracting net transfers from equity before tracking the
peak makes deposits and withdrawals invisible to the drawdown ratio --
only trading PnL moves it.
"""
TRANSFER_BILL_TYPE = '1'


def net_transfers(bills):
    """Net external cashflow into the trading account (deposits positive,
    withdrawals negative) across the given bills."""
    return sum(float(b['balChg']) for b in bills if b.get('type') == TRANSFER_BILL_TYPE)


def deposit_adjusted_equity(raw_equity, bills):
    """Raw equity with external transfers netted out, so only trading PnL,
    fees and funding remain."""
    return raw_equity - net_transfers(bills)


def modified_dietz_return(begin_value, end_value, bills, period_start_ms, period_end_ms):
    """Modified Dietz holding-period return: a standard time-weighted-return
    approximation for a portfolio with irregular external cashflows.

    This is not a true daily-linked TWR -- that needs a valuation at the
    instant of every cashflow, which is not available retroactively here.
    Modified Dietz only needs the beginning and ending value plus each
    cashflow's amount and timing, weighting each by the fraction of the
    period it was actually invested.
    """
    period = period_end_ms - period_start_ms
    if period <= 0:
        raise ValueError('Invalid period: end must be after start')
    if begin_value <= 0:
        raise ValueError('Invalid beginning value: must be positive')
    net_cf = 0.0
    weighted_cf = 0.0
    for b in bills:
        if b.get('type') != TRANSFER_BILL_TYPE:
            continue
        ts = int(b['ts'])
        if not (period_start_ms <= ts <= period_end_ms):
            continue
        amount = float(b['balChg'])
        weight = (period_end_ms - ts) / period
        net_cf += amount
        weighted_cf += amount * weight
    denominator = begin_value + weighted_cf
    if denominator == 0:
        raise ValueError('Zero denominator; cannot compute Modified Dietz return')
    return (end_value - begin_value - net_cf) / denominator
