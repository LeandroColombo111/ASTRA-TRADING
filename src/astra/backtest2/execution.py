"""Orchestrates one closed bar at a time: funding -> liquidation -> strategy exit -> entry -> stop/target.

Same discipline as engine.step(): only bars[i-1] and earlier feed decisions
for bar i, never a future bar. Liquidation is checked before the strategy's
own stop because an exchange-forced close preempts it when both are touched
in the same bar.

Deliberate simplifications vs engine.py, documented rather than hidden:
- No portfolio drawdown kill-stop / entry_effective_stop bookkeeping. Only
  the strategy's ATR stop/target/trailing and the exchange liquidation are
  modeled as exit paths, plus a simple equity-drawdown halt on new entries.
- Risk.fee_bps/slippage_bps (from engine.Risk) are used ONLY to estimate
  unit risk for position sizing before a fill is known -- a chicken-and-egg
  every real trading system has. Actual cash flows always come from
  fee_model/slippage_model, never from those flat estimates.
"""
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from ..engine import Account, Risk, size
from .friction.funding import FundingModel
from .friction.slippage import SlippageModel
from .friction.fees import FeeModel
from .friction.liquidation import LiquidationModel


@dataclass
class Position:
    """Reference shape only; ExecutionSimulator operates on engine.Account so its output is directly comparable to engine.backtest()."""
    side: int = 0
    quantity: float = 0.
    entry: float = 0.
    entry_time: str = ""
    margin: float = 0.


@dataclass(frozen=True)
class ExecutionSimulator:
    funding_model: FundingModel
    slippage_model: SlippageModel
    fee_model: FeeModel
    liquidation_model: LiquidationModel
    leverage: float  # derived from Risk.max_exposure to match the existing sizing model, not a free parameter
    target_exposure: float | None = None  # fixed notional/equity per entry; None keeps risk-based sizing

    def __post_init__(self):
        if self.leverage <= 0:
            raise ValueError("leverage must be positive")

    def _quantity(self, cash, price, distance, risk, previous):
        """Risk-based by default. A signal row may carry its own 'exposure' (fraction of equity, e.g. vol-targeted);
        otherwise target_exposure applies. Always capped by risk.max_exposure and the exchange lot rules."""
        exposure = previous.get("exposure", self.target_exposure)
        if exposure is None or not np.isfinite(exposure):
            return size(cash, price, distance, risk)
        exposure = min(float(exposure), risk.max_exposure)
        q = np.floor(cash * exposure / price / risk.quantity_step) * risk.quantity_step
        return float(q) if q * price >= risk.minimum_notional else 0.

    def step(self, s: Account, timestamp: pd.Timestamp, bar: dict, previous: dict, current: dict,
              p, risk: Risk, force_close: bool = False) -> list[dict]:
        """Consumes one closed hourly candle; mutates s in place and returns any trade events closed this bar."""
        o, h, l, c = (float(bar[x]) for x in ("open", "high", "low", "close"))
        funding_rate = float(bar["funding"])
        bar_volume_notional = max(float(bar.get("volume", 0.)) * o, 1e-9)
        atr_current = float(current["atr"])
        events = []
        had_position = bool(s.qty)

        if s.qty and self.funding_model.is_funding_instant(timestamp):
            side0 = int(np.sign(s.qty))
            payment = self.funding_model.settle(side0, abs(s.qty), funding_rate, o)
            s.cash -= payment
            s.trade_cost += payment

        def close(price_hint: float, reason: str):
            side = int(np.sign(s.qty))
            quantity = abs(s.qty)
            exit_side = -side  # closing a long sells (pressure -1); closing a short buys (pressure +1)
            fill = self.slippage_model.fill_price(
                timestamp, price_hint, exit_side, quantity * price_hint, bar_volume_notional, atr_current
            ).price
            if reason == "liquidated":
                commission = self.fee_model.liquidation_fee(quantity * fill)
            else:
                order_type = "maker" if reason == "target" else "taker"
                commission = self.fee_model.fee(quantity * fill, order_type)
            pnl = s.qty * (fill - s.entry) - commission - s.trade_cost
            s.cash += s.qty * (fill - s.entry) - commission
            events.append({
                "entry_time": s.entry_time, "exit_time": str(timestamp), "side": side,
                "quantity": quantity, "entry": s.entry, "exit": fill, "net_pnl": pnl, "reason": reason,
                "equity_before": getattr(s, "entry_equity", risk.capital),
            })
            s.trades += 1
            s.qty = 0.
            s.trade_cost = 0.

        # Liquidation preempts the strategy's own stop if price gaps through both in the same bar.
        if s.qty:
            side = int(np.sign(s.qty))
            margin = abs(s.qty) * s.entry / self.leverage
            liq_price = self.liquidation_model.liquidation_price(s.entry, side, abs(s.qty), margin)
            if self.liquidation_model.check(l, h, side, liq_price):
                close(liq_price, "liquidated")

        if s.qty and (int(previous["anchor"]) != np.sign(s.qty) or s.age >= p.max_hours):
            close(o, "anchor_or_timeout")

        if not s.qty and not had_position and not s.halted and not force_close:
            direction, atr_prev = int(previous["signal"]), float(previous["atr"])
            if direction and np.isfinite(atr_prev) and atr_prev > 0:
                distance = atr_prev * p.stop_atr
                if distance < o:
                    quantity = self._quantity(s.cash, o, distance, risk, previous)
                    if quantity:
                        s.entry_equity = s.cash  # flat here, so cash == equity: the "before this trade" baseline for Monte Carlo
                        fill = self.slippage_model.fill_price(
                            timestamp, o, direction, quantity * o, bar_volume_notional, atr_prev
                        ).price
                        commission = self.fee_model.fee(quantity * fill, "taker")
                        s.qty, s.entry = quantity * direction, fill
                        s.stop = fill - direction * distance
                        s.target = fill + direction * distance * p.reward
                        s.initial_distance = distance
                        s.peak_favorable_r = 0.
                        s.age, s.entry_time = 0, str(timestamp)
                        s.trade_cost = commission
                        s.cash -= commission

        if s.qty:
            side = int(np.sign(s.qty))
            stopped = l <= s.stop if side == 1 else h >= s.stop
            reached = h >= s.target if side == 1 else l <= s.target
            if stopped:
                close(s.stop, "stop")
            elif reached:
                close(s.target, "target")
            elif force_close:
                close(c, "end_of_period")
            else:
                s.peak_favorable_r = max(s.peak_favorable_r, side * (c - s.entry) / s.initial_distance) if s.initial_distance > 0 else 0.
                if np.isfinite(atr_current) and s.peak_favorable_r >= p.trail_start_r:
                    trail = c - side * atr_current * p.trail_atr
                    s.stop = max(s.stop, trail) if side == 1 else min(s.stop, trail)
                s.age += 1

        s.equity = s.cash + s.qty * (c - s.entry)
        s.peak = max(s.peak, s.equity)
        if s.equity <= s.peak * (1 - risk.max_drawdown):
            s.halted = True
        if s.equity <= 0:
            if s.qty:
                close(c, "insolvent")
            s.cash = s.equity = 0.
            s.halted = True
        return events

    def run(self, bars: pd.DataFrame, signal: pd.DataFrame, p, risk: Risk,
            start=None, end=None) -> tuple[pd.Series, list[dict], dict]:
        """Same output shape as engine.backtest(): equity curve, trade list, final account state."""
        positions = np.flatnonzero(
            (bars.index >= (pd.Timestamp(start) if start is not None else bars.index[0]))
            & (bars.index < (pd.Timestamp(end) if end is not None else bars.index[-1] + pd.Timedelta(hours=1)))
        )
        if len(positions) == 0:
            raise ValueError("Requested range has no bars")
        s = Account.new(risk)
        curve, trades, dates = [], [], []
        bvals, fvals = bars.to_dict("records"), signal.to_dict("records")
        for n, i in enumerate(positions):
            previous = {"signal": 0, "anchor": 0, "atr": float("nan")} if i == 0 else fvals[i - 1]
            trades.extend(self.step(s, bars.index[i], bvals[i], previous, fvals[i], p, risk,
                                      force_close=n == len(positions) - 1))
            curve.append(s.equity)
            dates.append(bars.index[i] + pd.Timedelta(hours=1))
        equity = pd.Series(curve, index=pd.DatetimeIndex(dates), name="equity")
        return equity, trades, asdict(s)
