"""Exchange-forced closure when margin falls below maintenance, distinct from the strategy's own stop.

Maintenance margin ratio is tiered by position notional (OKX
/api/v5/public/position-tiers), not a single constant, so liquidation_price
resolves the tier iteratively against the notional it implies.

Simplification, documented rather than hidden: fees already paid on entry
are not subtracted from available_margin before solving for the
liquidation price. That makes the estimate very slightly optimistic
(liquidation looks marginally farther away than it truly is). Fold the
entry fee into available_margin here if that precision starts to matter.
"""
from dataclasses import dataclass
from typing import Literal

MarginMode = Literal["isolated", "cross"]


@dataclass(frozen=True)
class PositionTiers:
    """Ascending (notional_ceiling, max_leverage, maintenance_margin_ratio) rows, as published by OKX.

    The rows below are a placeholder shape for BTC-USDT-SWAP, not a live
    fetch -- OKX revises these periodically. Refresh via
    /api/v5/public/position-tiers before trusting liquidation distances in
    a real decision; wire that refresh with from_okx_rows() below rather
    than editing the numbers here by hand.
    """
    rows: tuple = (
        (50_000., 75., .004),
        (200_000., 50., .006),
        (1_000_000., 30., .01),
        (5_000_000., 20., .02),
        (float("inf"), 10., .05),
    )

    def __post_init__(self):
        ceilings = [r[0] for r in self.rows]
        if ceilings != sorted(ceilings):
            raise ValueError("Tier rows must be sorted by ascending notional_ceiling")
        if any(mmr <= 0 or leverage <= 0 for _, leverage, mmr in self.rows):
            raise ValueError("Invalid tier leverage or maintenance margin ratio")

    @classmethod
    def from_okx_rows(cls, raw: list[dict]) -> "PositionTiers":
        """Builds a table from OKX's /api/v5/public/position-tiers response rows."""
        rows = tuple(sorted(
            (float(r["maxSz"]) * float(r.get("uly_px", r.get("last", 1.))), float(r["maxLever"]), float(r["mmr"]))
            for r in raw
        ))
        return cls(rows)

    def tier_for_notional(self, notional: float) -> tuple[float, float]:
        """(max_leverage, mmr) of the first tier whose ceiling covers this notional."""
        if notional < 0:
            raise ValueError("Notional cannot be negative")
        for ceiling, max_leverage, mmr in self.rows:
            if notional <= ceiling:
                return max_leverage, mmr
        return self.rows[-1][1], self.rows[-1][2]


@dataclass(frozen=True)
class LiquidationModel:
    tier_table: PositionTiers
    margin_mode: MarginMode

    def __post_init__(self):
        if self.margin_mode == "cross":
            raise NotImplementedError("Cross margin needs a multi-position Account; only isolated is supported today")

    def maintenance_margin_ratio(self, notional: float) -> float:
        """mmr for the tier matching this notional."""
        return self.tier_table.tier_for_notional(notional)[1]

    def liquidation_price(self, entry: float, side: int, qty: float, available_margin: float) -> float:
        """Solves margin_balance(P) = maintenance_margin(P) for isolated margin, iterating because mmr depends on notional(P)."""
        if side not in (1, -1):
            raise ValueError("side must be 1 (long) or -1 (short)")
        if entry <= 0 or qty <= 0 or available_margin <= 0:
            raise ValueError("entry, qty and available_margin must be positive")
        notional_guess = qty * entry
        price = entry
        for _ in range(5):
            mmr = self.maintenance_margin_ratio(notional_guess)
            denominator = qty * (mmr - side)
            if denominator == 0:
                raise ValueError("Degenerate maintenance margin ratio for this side")
            price = (available_margin - side * qty * entry) / denominator
            if price <= 0:
                # Fully collateralized (leverage <= 1x on a long): liquidation is unreachable at a positive price.
                return 0. if side == 1 else float("inf")
            new_notional = qty * price
            if abs(new_notional - notional_guess) < 1e-6 * max(notional_guess, 1.):
                break
            notional_guess = new_notional
        return price

    def check(self, bar_low: float, bar_high: float, side: int, liq_price: float) -> bool:
        """Pessimistic intrabar touch, same convention as the stop check in engine.py."""
        if side not in (1, -1):
            raise ValueError("side must be 1 (long) or -1 (short)")
        return bar_low <= liq_price if side == 1 else bar_high >= liq_price
