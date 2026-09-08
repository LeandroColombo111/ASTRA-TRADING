"""Linear perpetual, single position, next-bar entry, conservative OHLC fills."""
from dataclasses import dataclass, asdict
import math
import numpy as np
import pandas as pd
from .legacy_strategy import features

@dataclass(frozen=True)
class Risk:
    capital: float = 10000.
    fraction: float = .02
    fee_bps: float = 6.
    slippage_bps: float = 3.
    max_exposure: float = 1.
    max_drawdown: float = .25
    quantity_step: float = .001
    minimum_notional: float = 10.

    def __post_init__(self):
        if not .02 <= self.fraction <= .03:
            raise ValueError("Risk fraction must be 2% to 3%")
        if not (self.capital > 0 and 0 < self.max_exposure <= 1 and 0 < self.max_drawdown < 1):
            raise ValueError("Invalid capital, exposure or drawdown limit")
        if min(self.fee_bps, self.slippage_bps, self.minimum_notional) < 0 or self.quantity_step <= 0:
            raise ValueError("Invalid costs or quantity step")

@dataclass
class Account:
    cash: float
    peak: float
    equity: float
    qty: float = 0.
    entry: float = 0.
    stop: float = 0.
    target: float = 0.
    age: int = 0
    entry_time: str = ""
    trade_cost: float = 0.
    halted: bool = False
    trades: int = 0

    @classmethod
    def new(cls, risk):
        return cls(risk.capital, risk.capital, risk.capital)

def size(equity, entry, distance, risk):
    unit_risk = distance + entry * (2*risk.fee_bps + risk.slippage_bps)/10000
    q = min(equity*risk.fraction/unit_risk, equity*risk.max_exposure/entry)
    q = math.floor(q/risk.quantity_step)*risk.quantity_step
    return q if q*entry >= risk.minimum_notional else 0.

def step(s, timestamp, bar, previous, current, p, risk, force_close=False):
    """Consume one closed hourly candle; no future bars or indicators accessed."""
    o,h,l,c,funding = (float(bar[x]) for x in ("open","high","low","close","funding"))
    fee, slip = risk.fee_bps/10000, risk.slippage_bps/10000
    events = []
    had_position = bool(s.qty)
    # Funding timestamp at candle open: charge prior position, before exits/entries.
    if s.qty:
        payment = s.qty*o*funding
        s.cash -= payment
        s.trade_cost += payment
    def close(price, reason):
        side = np.sign(s.qty)
        fill = price*(1-side*slip)
        commission = abs(s.qty)*fill*fee
        pnl = s.qty*(fill-s.entry)-commission-s.trade_cost
        s.cash += s.qty*(fill-s.entry)-commission
        events.append({"entry_time":s.entry_time,"exit_time":str(timestamp),"side":int(side),"quantity":abs(s.qty),"entry":s.entry,"exit":fill,"net_pnl":pnl,"reason":reason})
        s.trades += 1
        s.qty = 0.
        s.trade_cost = 0.
    # Exit on the previous completed anchor changing direction, or timeout.
    if s.qty and (int(previous["anchor"]) != np.sign(s.qty) or s.age >= p.max_hours):
        close(o, "anchor_or_timeout")
    if not s.qty and not had_position and not s.halted and not force_close:
        direction, atr = int(previous["signal"]), float(previous["atr"])
        if direction and np.isfinite(atr) and atr > 0:
            entry = o*(1+direction*slip)
            distance = atr*p.stop_atr
            if distance < entry:
                quantity = size(s.cash, entry, distance, risk)
                if quantity:
                    s.qty, s.entry = quantity*direction, entry
                    s.stop = entry-direction*distance
                    s.target = entry+direction*distance*p.reward
                    s.age, s.entry_time = 0, str(timestamp)
                    s.trade_cost = quantity*entry*fee
                    s.cash -= s.trade_cost
    if s.qty:
        side = int(np.sign(s.qty))
        # Portfolio drawdown stop is evaluated intrabar. Gaps can exceed the limit.
        floor = s.peak*(1-risk.max_drawdown)
        kill_price = s.entry+(floor-s.cash)/s.qty
        active_stop = max(s.stop, kill_price) if side == 1 else min(s.stop, kill_price)
        stopped = l <= active_stop if side == 1 else h >= active_stop
        reached = h >= s.target if side == 1 else l <= s.target
        if stopped:  # When both touch, pessimistically stop first.
            kill = active_stop == kill_price
            close(min(o, active_stop) if side == 1 else max(o, active_stop), "drawdown" if kill else "stop")
            if kill:
                s.halted = True
        elif reached:
            close(s.target, "target")
        elif force_close:
            close(c, "end_of_period")
        else:
            # Update trailing stop at close, effective only on the NEXT candle.
            atr = float(current["atr"])
            if np.isfinite(atr):
                trail = c-side*atr*p.trail_atr
                s.stop = max(s.stop, trail) if side == 1 else min(s.stop, trail)
            s.age += 1
    s.equity = s.cash+s.qty*(c-s.entry)
    s.peak = max(s.peak,s.equity)
    if s.equity <= s.peak*(1-risk.max_drawdown):
        s.halted = True
    if s.equity <= 0:
        if s.qty:
            close(c, "insolvent")
        s.cash = s.equity = 0.
        s.halted = True
    return events

def backtest(bars, p, risk, start=None, end=None, prepared=None):
    f = features(bars,p) if prepared is None else prepared
    positions = np.flatnonzero((bars.index >= (pd.Timestamp(start) if start is not None else bars.index[0])) & (bars.index < (pd.Timestamp(end) if end is not None else bars.index[-1]+pd.Timedelta(hours=1))))
    s = Account.new(risk)
    curve, trades, dates = [], [], []
    bvals, fvals = bars.to_dict("records"), f.to_dict("records")
    for n,i in enumerate(positions):
        if i == 0:
            previous = {"signal":0,"anchor":0,"atr":float("nan")}
        else:
            previous = fvals[i-1]
        trades.extend(step(s,bars.index[i],bvals[i],previous,fvals[i],p,risk,force_close=n == len(positions)-1))
        curve.append(s.equity)
        dates.append(bars.index[i]+pd.Timedelta(hours=1))
    equity = pd.Series(curve,index=pd.DatetimeIndex(dates),name="equity")
    return equity, trades, asdict(s)

def daily_returns(equity, capital):
    # Close timestamps on midnight belong to the preceding trading day.
    e = equity.copy()
    e.index = e.index-pd.Timedelta(nanoseconds=1)
    daily = e.resample("1D").last()
    return daily.pct_change().fillna(daily.iloc[0]/capital-1)

def metrics(equity, trades, capital):
    r = daily_returns(equity,capital)
    sd = float(r.std(ddof=1))
    wealth = np.r_[capital, equity.to_numpy()]
    dd = 1-wealth/np.maximum.accumulate(wealth)
    return {"sharpe":float(np.sqrt(365)*r.mean()/sd) if sd > 0 else 0.,"return":float(equity.iloc[-1]/capital-1),"max_drawdown":float(dd.max()),"trades":len(trades),"long_trades":sum(t["side"]==1 for t in trades),"short_trades":sum(t["side"]==-1 for t in trades),"win_rate":sum(t["net_pnl"]>0 for t in trades)/max(1,len(trades)),"days":len(r)}
