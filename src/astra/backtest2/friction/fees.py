"""Real OKX maker/taker fee schedule, keyed by simulated order type, not a single flat rate."""
from dataclasses import dataclass
from typing import Literal

OrderType = Literal["maker", "taker"]

# Regular (non-VIP) tier for USDT-margined perpetual swaps, per OKX's public
# fee schedule. OKX charges liquidations at the account's current taker rate,
# not a separate higher rate (unlike some other exchanges) -- so
# liquidation_bps defaults to taker_bps here, not a bigger constant.
REGULAR_TIER_MAKER_BPS = 2.
REGULAR_TIER_TAKER_BPS = 5.


@dataclass(frozen=True)
class FeeModel:
    maker_bps: float
    taker_bps: float
    liquidation_bps: float

    def __post_init__(self):
        if min(self.maker_bps, self.taker_bps, self.liquidation_bps) < 0:
            raise ValueError("Fee rates cannot be negative")

    @classmethod
    def regular_tier(cls) -> "FeeModel":
        """OKX's public non-VIP fee schedule; liquidation billed at the taker rate."""
        return cls(REGULAR_TIER_MAKER_BPS, REGULAR_TIER_TAKER_BPS, REGULAR_TIER_TAKER_BPS)

    def fee(self, notional: float, order_type: OrderType) -> float:
        """Commission owed for one fill of this notional."""
        rate = self.maker_bps if order_type == "maker" else self.taker_bps
        return notional * rate / 10000

    def liquidation_fee(self, notional: float) -> float:
        """Commission owed when the position is force-closed by the exchange, not by the strategy."""
        return notional * self.liquidation_bps / 10000
