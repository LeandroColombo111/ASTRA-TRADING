"""8h funding settlement, decoupled from the 1h bar grid.

OKX settles perpetual funding at fixed UTC instants (00:00, 08:00, 16:00),
not continuously per candle. A position only pays/receives when it is open
exactly at one of those instants.
"""
from dataclasses import dataclass
import pandas as pd

FUNDING_HOURS_UTC = (0, 8, 16)


@dataclass(frozen=True)
class FundingModel:

    def is_funding_instant(self, timestamp: pd.Timestamp) -> bool:
        """True only at an exact UTC funding hour; False for every other bar.

        Defensive check, independent of any upstream pre-zeroing of the
        funding column (see okx_history.py), so a different data source
        cannot silently break this model's timing.
        """
        if timestamp.tzinfo is None:
            raise ValueError("Funding timestamps must be timezone-aware")
        utc = timestamp.tz_convert("UTC")
        return utc.hour in FUNDING_HOURS_UTC and utc.minute == 0 and utc.second == 0

    def settle(self, side: int, quantity: float, funding_rate: float, mark_price: float) -> float:
        """Cash flow of one funding payment. Longs pay when funding_rate > 0, shorts receive, and vice versa.

        Positive result is a cost (subtract from cash); negative is income.
        Matches engine.py's existing convention (payment = qty*price*funding
        with qty already signed), so the two engines agree on sign.
        """
        if side not in (1, -1):
            raise ValueError("side must be 1 (long) or -1 (short)")
        return side * quantity * mark_price * funding_rate
