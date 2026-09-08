import pytest
from astra.accounting import net_transfers, deposit_adjusted_equity, modified_dietz_return

DAY = 86400000


def bill(ts, chg, kind='1'):
    return {'ts': str(ts), 'balChg': str(chg), 'type': kind}


def test_net_transfers_only_counts_transfer_type():
    bills = [bill(0, 1000), bill(1, -50, kind='2'), bill(2, -300)]
    assert net_transfers(bills) == 700


def test_deposit_adjusted_equity_removes_deposit():
    bills = [bill(0, 10000)]
    # equity jumped by exactly the deposit; adjusted equity should be unchanged
    assert deposit_adjusted_equity(85000, bills) == 75000


def test_deposit_adjusted_equity_ignores_withdrawals_and_pnl():
    bills = [bill(0, -5000), bill(1, 20, kind='8')]  # withdrawal + funding fee (not a transfer)
    assert deposit_adjusted_equity(70000, bills) == 75000


def test_deposit_masks_real_loss_without_adjustment_but_not_with_it():
    # Pre-deposit: peak=75000. Then deposit 10000 (equity->85000). Then the
    # original 75000 loses exactly 25% (-18750), leaving total equity
    # 85000-18750=66250 -- above a naive 75%-of-85000=63750 halt line, so an
    # unadjusted check would miss the breach. The adjusted equity strips the
    # deposit back out and should show the real 25% loss.
    bills = [bill(0, 10000)]
    equity_after_loss = 66250
    adjusted = deposit_adjusted_equity(equity_after_loss, bills)
    assert adjusted == 56250
    assert adjusted <= 75000 * (1 - 0.25)


def test_modified_dietz_no_cashflow_is_simple_return():
    r = modified_dietz_return(100000, 110000, [], 0, 10 * DAY)
    assert r == pytest.approx(0.10)


def test_modified_dietz_mid_period_deposit_not_counted_as_return():
    # Deposit exactly halfway through a 10-day period; ending value rose by
    # exactly the deposit amount plus zero PnL, so the return should be ~0.
    bills = [bill(5 * DAY, 10000)]
    r = modified_dietz_return(100000, 110000, bills, 0, 10 * DAY)
    assert r == pytest.approx(0.0, abs=1e-9)


def test_modified_dietz_deposit_near_end_barely_weighted():
    # A deposit arriving right at period end passes through the numerator
    # untouched (end - begin - net_cf), so a genuine 5000 gain on top of a
    # 10000 deposit should read as ~5% on the ~100000 base, since the
    # deposit's near-zero weight barely affects the denominator.
    bills = [bill(10 * DAY - 1, 10000)]
    r = modified_dietz_return(100000, 115000, bills, 0, 10 * DAY)
    assert r == pytest.approx(0.05, rel=0.01)


def test_modified_dietz_rejects_non_positive_period():
    with pytest.raises(ValueError):
        modified_dietz_return(100000, 110000, [], 10, 10)


def test_modified_dietz_rejects_non_positive_beginning_value():
    with pytest.raises(ValueError):
        modified_dietz_return(0, 10000, [], 0, DAY)
