"""Research-only controlled interventions. Does not change the running bot/config."""
from dataclasses import asdict, dataclass, field
import math
import numpy as np
import pandas as pd
from .engine import Risk, size
from .legacy_strategy import Params, features


@dataclass(frozen=True)
class Intervention:
    params: Params = field(default_factory=Params)
    trail_enabled: bool = True
    trail_start_r: float = 0.
    target_enabled: bool = True
    adx_min: float = 0.
    entry_mode: str = 'breakout'
    cooldown_hours: int = 0
    direction: int = 0  # 0 both, +/-1 diagnostic only
    funding_enabled: bool = True

    def __post_init__(self):
        if self.entry_mode not in ('breakout', 'pullback') or self.direction not in (-1,0,1):
            raise ValueError('Invalid research signal mode')
        if self.trail_start_r < 0 or self.adx_min < 0 or self.cooldown_hours < 0:
            raise ValueError('Invalid research intervention')


def research_features(bars, spec):
    f = features(bars, spec.params)
    anchor = bars.resample('4h', closed='left', label='right').agg({'open':'first','high':'max','low':'min','close':'last'})
    count = bars.close.resample('4h', closed='left', label='right').count()
    anchor = anchor[count == 4]
    tr = pd.concat([anchor.high-anchor.low,(anchor.high-anchor.close.shift()).abs(),(anchor.low-anchor.close.shift()).abs()],axis=1).max(axis=1)
    up, down = anchor.high.diff(), -anchor.low.diff()
    plus = up.where((up > down) & (up > 0), 0.).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    minus = down.where((down > up) & (down > 0), 0.).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    smooth_tr = tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    pdi,mdi = 100*plus/smooth_tr,100*minus/smooth_tr
    dx = 100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    adx = dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    f['adx4h'] = adx.reindex(bars.index+pd.Timedelta(hours=1),method='ffill').to_numpy()
    if spec.entry_mode == 'pullback':
        # Completed 1h close crosses EMA20 after trading on the other side;
        # the 4h direction is unchanged. No discretionary pattern labeling.
        ema = bars.close.ewm(span=20,adjust=False,min_periods=20).mean()
        long = (bars.close > ema) & (bars.close.shift(1) <= ema.shift(1)) & (f.anchor == 1)
        short = (bars.close < ema) & (bars.close.shift(1) >= ema.shift(1)) & (f.anchor == -1)
        f['signal'] = np.where(long,1,np.where(short,-1,0))
    if spec.adx_min:
        f.loc[~(f.adx4h >= spec.adx_min),'signal'] = 0
    if spec.direction:
        f.loc[f.signal != spec.direction,'signal'] = 0
    return f


def simulate(bars, spec, risk, start, end, prepared=None):
    """Equivalent to v1 for baseline, with richer cost/exit records.

    Closed-bar maximum favorable move is causal and excludes any unobserved
    intrabar sequence. No claim is made to reconstruct intrabar MFE/MAE.
    """
    f = research_features(bars,spec) if prepared is None else prepared
    mask = (bars.index >= pd.Timestamp(start)) & (bars.index < pd.Timestamp(end))
    indices = np.flatnonzero(mask)
    if len(indices) == 0: raise ValueError('Empty evaluation interval')
    prices = bars[['open','high','low','close','funding']].to_numpy()
    fv = f[['signal','anchor','atr','adx4h']].to_numpy()
    fee,slip = risk.fee_bps/10000,risk.slippage_bps/10000
    cash = peak = equity = risk.capital
    qty=entry=stop=target=initial_distance=entry_reference=entry_equity=0.
    entry_fee=funding_paid=0.
    age=trail_updates=0
    peak_close_r=-math.inf
    first_trail_r=None
    last_exit=-100000
    opened=None
    halted=False
    curve=[];trades=[]
    p=spec.params

    def close(raw_price, reason, i, detail=None):
        nonlocal cash,qty,entry_fee,funding_paid,last_exit
        direction = 1 if qty>0 else -1
        fill = raw_price*(1-direction*slip)
        exit_fee = abs(qty)*fill*fee
        gross = qty*(fill-entry)
        net = gross-exit_fee-entry_fee-funding_paid
        gross_reference = qty*(raw_price-entry_reference)
        trades.append({'entry_time':str(opened),'exit_time':str(bars.index[i]),'side':direction,'quantity':abs(qty),'entry':entry,'exit':fill,'net_pnl':net,'reason':reason,'exit_detail':detail or reason,'gross_before_execution_costs':gross_reference,'slippage_cost':gross_reference-gross,'entry_fee':entry_fee,'exit_fee':exit_fee,'funding_cost':funding_paid,'initial_risk_usdt':abs(qty)*initial_distance,'initial_risk_fraction':abs(qty)*initial_distance/entry_equity,'initial_distance':initial_distance,'entry_equity':entry_equity,'peak_completed_close_r':None if peak_close_r == -math.inf else peak_close_r,'first_trailing_update_r':first_trail_r,'trailing_updates':trail_updates,'hours':(bars.index[i]-opened).total_seconds()/3600})
        cash += gross-exit_fee
        qty=0.;entry_fee=funding_paid=0.;last_exit=i

    for n,i in enumerate(indices):
        o,h,l,c,funding=prices[i]
        if not spec.funding_enabled:funding=0.
        previous=fv[i-1] if i>0 else (0,0,np.nan,np.nan)
        signal,anchor,atr_prev,_=previous
        had_position=bool(qty)
        force_close=n==len(indices)-1
        if qty:
            payment=qty*o*funding;cash-=payment;funding_paid+=payment
        if qty and (int(anchor)!=np.sign(qty) or age>=p.max_hours):
            close(o,'anchor_or_timeout',i,'anchor' if int(anchor)!=np.sign(qty) else 'timeout')
        if not qty and not had_position and not halted and not force_close and i-last_exit>spec.cooldown_hours:
            if signal and np.isfinite(atr_prev) and atr_prev>0:
                direction=int(signal);entry=o*(1+direction*slip);initial_distance=atr_prev*p.stop_atr
                if initial_distance<entry:
                    q=size(cash,entry,initial_distance,risk)
                    if q:
                        qty=q*direction;entry_reference=o;entry_equity=cash
                        stop=entry-direction*initial_distance;target=entry+direction*initial_distance*p.reward
                        age=0;opened=bars.index[i];entry_fee=q*entry*fee;cash-=entry_fee
                        funding_paid=0.;trail_updates=0;first_trail_r=None;peak_close_r=-math.inf
        if qty:
            direction=1 if qty>0 else -1
            floor=peak*(1-risk.max_drawdown)
            kill_price=entry+(floor-cash)/qty
            active_stop=max(stop,kill_price) if direction==1 else min(stop,kill_price)
            stopped=l<=active_stop if direction==1 else h>=active_stop
            reached=(h>=target if direction==1 else l<=target) and spec.target_enabled
            if stopped:
                kill=active_stop==kill_price
                detail='drawdown' if kill else ('trailing_stop' if trail_updates else 'initial_stop')
                close(min(o,active_stop) if direction==1 else max(o,active_stop),'drawdown' if kill else 'stop',i,detail)
                if kill:halted=True
            elif reached:close(target,'target',i)
            elif force_close:close(c,'end_of_period',i)
            else:
                current_r=direction*(c-entry)/initial_distance
                peak_close_r=max(peak_close_r,current_r)
                atr=fv[i,2]
                # Preserve v1 unconditional trailing when threshold == 0.
                activate = spec.trail_start_r == 0 or peak_close_r >= spec.trail_start_r
                if spec.trail_enabled and activate and np.isfinite(atr):
                    trail=c-direction*atr*p.trail_atr
                    new_stop=max(stop,trail) if direction==1 else min(stop,trail)
                    if new_stop!=stop:
                        trail_updates+=1
                        if first_trail_r is None:first_trail_r=current_r
                    stop=new_stop
                age+=1
        equity=cash+qty*(c-entry);peak=max(peak,equity)
        if equity<=peak*(1-risk.max_drawdown):halted=True
        if equity<=0:
            if qty:close(c,'insolvent',i)
            cash=equity=0.;halted=True
        curve.append(equity)
    return pd.Series(curve,index=bars.index[indices]+pd.Timedelta(hours=1),name='equity'),trades,{'cash':cash,'equity':equity,'halted':halted,'trades':len(trades)}


def attribution(trades, capital):
    t=pd.DataFrame(trades)
    if t.empty:return {'trades':0}
    totals={k:float(t[k].sum()) for k in ['net_pnl','gross_before_execution_costs','slippage_cost','entry_fee','exit_fee','funding_cost']}
    assert abs(totals['gross_before_execution_costs']-totals['slippage_cost']-totals['entry_fee']-totals['exit_fee']-totals['funding_cost']-totals['net_pnl'])<1e-6
    groups={}
    for field in ['side','exit_detail']:
        groups[field]={str(k):{'trades':len(g),'net_pnl':float(g.net_pnl.sum()),'win_rate':float((g.net_pnl>0).mean()),'mean_hours':float(g.hours.mean())} for k,g in t.groupby(field)}
    x=t.first_trailing_update_r.dropna()
    wins=t.loc[t.net_pnl>0,'net_pnl'];losses=t.loc[t.net_pnl<0,'net_pnl']
    return {'trades':len(t),'totals_usdt':totals,'percentage_points_of_initial_capital':{k:v/capital*100 for k,v in totals.items()},'groups':groups,'trades_with_trailing_updates':int((t.trailing_updates>0).sum()),'first_trail_at_loss_count':int((x<0).sum()),'median_first_trail_r':float(x.median()) if len(x) else None,'average_nominal_risk_fraction':float(t.initial_risk_fraction.mean()),'median_nominal_risk_fraction':float(t.initial_risk_fraction.median()),'profit_factor':float(wins.sum()/-losses.sum()) if len(losses) else None,'average_win':float(wins.mean()) if len(wins) else 0.,'average_loss':float(losses.mean()) if len(losses) else 0.}
