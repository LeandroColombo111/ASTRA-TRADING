"""Exchange-forced closure when margin falls below maintenance, distinct from the strategy's own stop.

OKX tiers the maintenance margin ratio by POSITION SIZE (in contracts), not
by notional in dollars. A position's size does not change as price moves, so
its tier is fixed for the life of the trade and the liquidation price has a
closed form.

Simplification, documented rather than hidden: fees already paid on entry
are not subtracted from available_margin before solving for the
liquidation price. That makes the estimate very slightly optimistic
(liquidation looks marginally farther away than it is). Fold the entry fee
into available_margin here if that precision starts to matter.
"""
from dataclasses import dataclass
import json
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .okx_tiers_snapshot import ROWS as SNAPSHOT_ROWS, SOURCE as SNAPSHOT_SOURCE

MarginMode = Literal["isolated", "cross"]
OKX_BASE = "https://www.okx.com"


def _get_json(path: str, params: dict, timeout: float) -> dict:
    request = Request(OKX_BASE + path + "?" + urlencode(params), headers={"User-Agent": "okx-perp-backtest"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


@dataclass(frozen=True)
class PositionTiers:
    """Ascending (max_size, max_leverage, maintenance_margin_ratio) rows.

    max_size is in the BASE currency (BTC for BTC-USDT-SWAP), already converted
    from OKX's contract counts. The default is a dated offline snapshot of
    BTC-USDT; use fetch_okx() for a fresh table or another instrument.
    """
    rows: tuple = SNAPSHOT_ROWS
    source: str = SNAPSHOT_SOURCE

    def __post_init__(self):
        if not self.rows:
            raise ValueError("Tier table cannot be empty")
        sizes = [r[0] for r in self.rows]
        if sizes != sorted(sizes):
            raise ValueError("Tier rows must be sorted by ascending max_size")
        if any(size <= 0 or leverage <= 0 or mmr <= 0 for size, leverage, mmr in self.rows):
            raise ValueError("Invalid tier size, leverage or maintenance margin ratio")

    @classmethod
    def from_okx_rows(cls, raw: list, ct_val: float, source: str = "okx") -> "PositionTiers":
        """Parse /api/v5/public/position-tiers rows. maxSz is in contracts; ct_val is base units per contract."""
        if ct_val <= 0:
            raise ValueError("ct_val must be positive")
        ordered = sorted(raw, key=lambda r: int(r["tier"]))
        rows = tuple((round(float(r["maxSz"]) * ct_val, 8), float(r["maxLever"]), float(r["mmr"])) for r in ordered)
        return cls(rows, source)

    @classmethod
    def fetch_okx(cls, inst_id: str = "BTC-USDT-SWAP", inst_family: str = "BTC-USDT",
                  timeout: float = 10.) -> "PositionTiers":
        """Live isolated-margin tiers from OKX's public endpoints (no credentials needed)."""
        tiers = _get_json("/api/v5/public/position-tiers",
                          {"instType": "SWAP", "tdMode": "isolated", "instFamily": inst_family}, timeout)
        spec = _get_json("/api/v5/public/instruments", {"instType": "SWAP", "instId": inst_id}, timeout)
        if tiers.get("code") != "0" or spec.get("code") != "0" or not tiers["data"] or not spec["data"]:
            raise ValueError("OKX returned no tiers or instrument data for %s" % inst_id)
        return cls.from_okx_rows(tiers["data"], float(spec["data"][0]["ctVal"]), "OKX live " + inst_id)

    def tier_for_size(self, size: float) -> tuple:
        """(max_leverage, mmr) of the first tier whose max_size covers this position size."""
        if size < 0:
            raise ValueError("Position size cannot be negative")
        for max_size, max_leverage, mmr in self.rows:
            if size <= max_size:
                return max_leverage, mmr
        raise ValueError("Position size %s exceeds OKX's largest tier (%s); such a position could not be opened"
                         % (size, self.rows[-1][0]))


@dataclass(frozen=True)
class LiquidationModel:
    tier_table: PositionTiers
    margin_mode: MarginMode

    def __post_init__(self):
        if self.margin_mode == "cross":
            raise NotImplementedError("Cross margin needs a multi-position Account; only isolated is supported today")

    def maintenance_margin_ratio(self, size: float) -> float:
        """mmr for the tier covering this position size (in base currency)."""
        return self.tier_table.tier_for_size(size)[1]

    def liquidation_price(self, entry: float, side: int, qty: float, available_margin: float) -> float:
        """Solves margin_balance(P) = maintenance_margin(P) for isolated margin; qty is in base currency."""
        if side not in (1, -1):
            raise ValueError("side must be 1 (long) or -1 (short)")
        if entry <= 0 or qty <= 0 or available_margin <= 0:
            raise ValueError("entry, qty and available_margin must be positive")
        mmr = self.maintenance_margin_ratio(qty)
        price = (available_margin - side * qty * entry) / (qty * (mmr - side))
        if price <= 0:
            # Fully collateralized (leverage <= 1x on a long): liquidation is unreachable at a positive price.
            return 0. if side == 1 else float("inf")
        return price

    def check(self, bar_low: float, bar_high: float, side: int, liq_price: float) -> bool:
        """Pessimistic intrabar touch, same convention as a stop check."""
        if side not in (1, -1):
            raise ValueError("side must be 1 (long) or -1 (short)")
        return bar_low <= liq_price if side == 1 else bar_high >= liq_price
