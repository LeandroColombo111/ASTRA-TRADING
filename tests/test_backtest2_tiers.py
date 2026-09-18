"""Size-based OKX position tiers (ported from the public okx-perp-backtest repo)."""
import pytest


# --- OKX position tiers: sized in contracts, not dollars -------------------------------------------------

REAL_ROWS = [  # first three BTC-USDT isolated tiers as returned by OKX on 2026-09-18 (maxSz is in contracts)
    {"tier": "2", "minSz": "1000.01", "maxSz": "5000", "mmr": "0.005", "maxLever": "66.66"},
    {"tier": "1", "minSz": "0", "maxSz": "1000", "mmr": "0.004", "maxLever": "100"},
    {"tier": "3", "minSz": "5000.01", "maxSz": "20000", "mmr": "0.0075", "maxLever": "50"},
]


def test_okx_rows_are_converted_from_contracts_to_base_currency_and_sorted():
    from astra.backtest2.friction.liquidation import PositionTiers
    t = PositionTiers.from_okx_rows(REAL_ROWS, ct_val=0.01)
    assert t.rows == ((10.0, 100.0, 0.004), (50.0, 66.66, 0.005), (200.0, 50.0, 0.0075))


def test_tier_lookup_boundaries_and_oversize_is_refused():
    from astra.backtest2.friction.liquidation import PositionTiers
    t = PositionTiers.from_okx_rows(REAL_ROWS, ct_val=0.01)
    assert t.tier_for_size(10.0)[1] == 0.004        # boundary belongs to the lower tier
    assert t.tier_for_size(10.01)[1] == 0.005
    with pytest.raises(ValueError, match="largest tier"):
        t.tier_for_size(201.)


def test_tier_depends_on_size_not_on_price():
    from astra.backtest2.friction.liquidation import LiquidationModel, PositionTiers
    m = LiquidationModel(PositionTiers.from_okx_rows(REAL_ROWS, 0.01), "isolated")
    # same 20 BTC position at two very different prices: same tier, so the liquidation gap scales with price
    low = m.liquidation_price(1000., 1, 20., 20. * 1000. / 10.)
    high = m.liquidation_price(100000., 1, 20., 20. * 100000. / 10.)
    assert high / 100000. == pytest.approx(low / 1000.)


def test_offline_snapshot_is_valid_and_dated():
    from astra.backtest2.friction.liquidation import PositionTiers
    t = PositionTiers()
    assert len(t.rows) > 50 and "fetched" in t.source
    mmrs = [r[2] for r in t.rows]
    assert mmrs == sorted(mmrs), "maintenance margin ratio should not fall as size grows"
    assert t.tier_for_size(1.0) == (100.0, 0.004)


def test_fetch_okx_parses_both_endpoints_without_touching_the_network(monkeypatch):
    from astra.backtest2.friction import liquidation as liq

    def fake(path, params, timeout):
        if "position-tiers" in path:
            return {"code": "0", "data": REAL_ROWS}
        return {"code": "0", "data": [{"ctVal": "0.01"}]}

    monkeypatch.setattr(liq, "_get_json", fake)
    t = liq.PositionTiers.fetch_okx()
    assert t.rows[0] == (10.0, 100.0, 0.004) and t.source == "OKX live BTC-USDT-SWAP"


def test_fetch_okx_refuses_an_error_response(monkeypatch):
    from astra.backtest2.friction import liquidation as liq
    monkeypatch.setattr(liq, "_get_json", lambda *a: {"code": "51001", "data": []})
    with pytest.raises(ValueError):
        liq.PositionTiers.fetch_okx()
