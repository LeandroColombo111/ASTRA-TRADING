from dataclasses import dataclass
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class Params:
    fast: int = 20
    slow: int = 100
    breakout: int = 24
    atr_period: int = 14
    stop_atr: float = 2.5
    trail_atr: float = 3.0
    reward: float = 4.0
    min_trend: float = 0.0
    max_hours: int = 240

    def __post_init__(self):
        if not (1 < self.fast < self.slow <= 200 and 2 <= self.breakout <= 200 and self.atr_period >= 2):
            raise ValueError("Invalid indicator windows")
        if min(self.stop_atr, self.trail_atr, self.reward, self.max_hours) <= 0 or self.min_trend < 0:
            raise ValueError("Invalid exit parameters")

def features(bars, p):
    # Index identifies OPEN time. 4h group [00:00,04:00) is available at 04:00.
    anchor = bars.resample("4h", closed="left", label="right").agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"})
    counts = bars.close.resample("4h", closed="left", label="right").count()
    anchor = anchor[counts == 4]
    fast = anchor.close.ewm(span=p.fast, adjust=False, min_periods=p.fast).mean()
    slow = anchor.close.ewm(span=p.slow, adjust=False, min_periods=p.slow).mean()
    strength = (fast-slow) / slow
    anchor_side = pd.Series(np.where(strength > p.min_trend, 1, np.where(strength < -p.min_trend, -1, 0)), index=anchor.index)
    # At hourly close t+1h use only completed anchor candles.
    side = anchor_side.reindex(bars.index + pd.Timedelta(hours=1), method="ffill").fillna(0).to_numpy()
    prev = bars.close.shift(1)
    tr = pd.concat([bars.high-bars.low, (bars.high-prev).abs(), (bars.low-prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/p.atr_period, adjust=False, min_periods=p.atr_period).mean()
    upper = bars.high.shift(1).rolling(p.breakout).max()
    lower = bars.low.shift(1).rolling(p.breakout).min()
    signal = np.where((side == 1) & (bars.close > upper), 1, np.where((side == -1) & (bars.close < lower), -1, 0))
    return pd.DataFrame({"signal":signal, "anchor":side, "atr":atr}, index=bars.index)
