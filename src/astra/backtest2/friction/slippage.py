"""Liquidity-aware fill price: walk the real order book when covered, else a square-root impact proxy.

OKX historical L2 book coverage has gaps (2023-02-24->2024-07-19 and
2026-05-21->present). Every fill records which regime produced it so the
final report can show what fraction of trades relied on real book data.
"""
from dataclasses import dataclass
from typing import Literal
import math
import pandas as pd

Side = Literal[1, -1]


class InsufficientLiquidity(Exception):
    """Raised when an order is larger than all visible book depth; never invents liquidity that wasn't there."""


@dataclass(frozen=True)
class FillResult:
    price: float
    source: Literal["real_book", "proxy"]


class LiquidityBook:
    """Historical OKX L2 snapshots, when available for the requested timestamp.

    This base class always reports no coverage, so SlippageModel falls back
    to the proxy model everywhere until a real book data source (e.g. an
    OKXHistoricalBook backed by downloaded L2 snapshots) is plugged in.
    """

    def has_real_book(self, timestamp: pd.Timestamp) -> bool:
        raise NotImplementedError

    def levels_at(self, timestamp: pd.Timestamp, side: Side) -> list[tuple[float, float]]:
        """[(price, quantity_available), ...] ordered from best price outward. Only called when has_real_book is True."""
        raise NotImplementedError


class NullLiquidityBook(LiquidityBook):
    """No book data wired up yet -- SlippageModel always uses the volume/ATR proxy."""

    def has_real_book(self, timestamp: pd.Timestamp) -> bool:
        return False

    def levels_at(self, timestamp: pd.Timestamp, side: Side) -> list[tuple[float, float]]:
        raise RuntimeError("NullLiquidityBook has no real book; has_real_book() should have been checked first")


@dataclass(frozen=True)
class SlippageModel:
    liquidity_book: LiquidityBook
    impact_k: float  # calibrated from live paper-trading fill logs, not assumed

    def __post_init__(self):
        if self.impact_k < 0:
            raise ValueError("impact_k cannot be negative")

    def fill_price(self, timestamp: pd.Timestamp, mid_price: float, side: Side,
                    order_notional: float, bar_volume_notional: float, atr: float) -> FillResult:
        """Average fill price for order_notional, using the best available liquidity source."""
        if mid_price <= 0 or order_notional <= 0:
            raise ValueError("mid_price and order_notional must be positive")
        if side not in (1, -1):
            raise ValueError("side must be 1 (buying pressure) or -1 (selling pressure)")
        if self.liquidity_book.has_real_book(timestamp):
            levels = self.liquidity_book.levels_at(timestamp, side)
            order_qty = order_notional / mid_price
            price = self._walk_book(levels, order_qty)
            return FillResult(price=price, source="real_book")
        price = self._proxy_impact(mid_price, side, order_notional, bar_volume_notional, atr)
        return FillResult(price=price, source="proxy")

    def _walk_book(self, levels: list[tuple[float, float]], order_qty: float) -> float:
        """Average price to fill order_qty consuming levels in order; raises if levels are insufficient."""
        remaining = order_qty
        cost = 0.
        for price, qty_available in levels:
            if price <= 0 or qty_available < 0:
                raise ValueError("Invalid book level")
            take = min(remaining, qty_available)
            cost += take * price
            remaining -= take
            if remaining <= 1e-12:
                break
        if remaining > 1e-12:
            raise InsufficientLiquidity("Order size exceeds all visible book depth")
        return cost / order_qty

    def _proxy_impact(self, mid_price: float, side: Side, order_notional: float,
                       bar_volume_notional: float, atr: float) -> float:
        """impact = impact_k * (atr/mid) * sqrt(order_notional / bar_volume_notional), applied against side."""
        if bar_volume_notional <= 0:
            raise ValueError("bar_volume_notional must be positive to estimate liquidity")
        if atr < 0 or not math.isfinite(atr):
            raise ValueError("atr must be a finite, non-negative number")
        relative_volatility = atr / mid_price
        impact = self.impact_k * relative_volatility * math.sqrt(order_notional / bar_volume_notional)
        return mid_price * (1 + side * impact)
