from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from astra.legacy_strategy import Params
from astra.legacy_engine import Risk,backtest
from astra.diagnostics import Intervention,research_features,simulate,attribution


def market(n=1600):
    rng=np.random.default_rng(11);c=100*np.exp(np.cumsum(rng.normal(0,.01,n)))
    b=pd.DataFrame({'open':c,'high':c*1.02,'low':c*.98,'close':c,'volume':1.,'funding':np.where(np.arange(n)%8==0,.0001,0.)},index=pd.date_range('2023-01-01',periods=n,freq='h',tz='UTC'))
    return b


def test_baseline_engine_equivalence():
    b=market();p=Params(fast=8,slow=60,breakout=24);r=Risk(max_drawdown=.8)
    a,trades,_=backtest(b,p,r,b.index[300],b.index[-1]+pd.Timedelta(hours=1))
    c,rich,_=simulate(b,Intervention(params=p),r,b.index[300],b.index[-1]+pd.Timedelta(hours=1))
    pd.testing.assert_series_equal(a,c,check_freq=False)
    assert len(trades)==len(rich)>0
    for x,y in zip(trades,rich):
        for k in x:assert x[k]==y[k]
    costs=attribution(rich,r.capital)
    assert costs['totals_usdt']['net_pnl']==pytest.approx(c.iloc[-1]-r.capital)


def test_adx_pullback_are_prefix_invariant():
    b=market();spec=Intervention(entry_mode='pullback',adx_min=20)
    full=research_features(b,spec)
    for cut in [805,807,1001]:
        pd.testing.assert_frame_equal(full.iloc[:cut],research_features(b.iloc[:cut],spec))


def test_delayed_trailing_does_not_tighten_before_profit():
    index=pd.date_range('2023-01-01',periods=5,freq='h',tz='UTC')
    b=pd.DataFrame({'open':[100]*5,'high':[101]*5,'low':[99,99,97,96,99],'close':[100]*5,'volume':1.,'funding':0.},index=index)
    f=pd.DataFrame({'signal':[1,0,0,0,0],'anchor':1,'atr':1.,'adx4h':25.},index=index)
    p=Params(stop_atr=4,trail_atr=2,reward=4)
    r=Risk(fee_bps=0,slippage_bps=0,max_drawdown=.9)
    _,a,_=simulate(b,Intervention(params=p),r,index[1],index[-1]+pd.Timedelta(hours=1),f)
    _,c,_=simulate(b,Intervention(params=p,trail_start_r=1),r,index[1],index[-1]+pd.Timedelta(hours=1),f)
    assert a[0]['exit_detail']=='trailing_stop' and a[0]['exit']==98
    assert c[0]['exit_detail']=='initial_stop' and c[0]['exit']==96
    assert c[0]['trailing_updates']==0


def test_no_cost_counterfactual_still_has_price_losses():
    b=market();p=Params(fast=8,slow=60,breakout=12);r=Risk(fee_bps=0,slippage_bps=0,max_drawdown=.9)
    _,t,_=simulate(b,Intervention(params=p,funding_enabled=False),r,b.index[300],b.index[-1]+pd.Timedelta(hours=1))
    a=attribution(t,r.capital)['totals_usdt']
    assert a['entry_fee']==a['exit_fee']==a['funding_cost']==a['slippage_cost']==0
    assert a['net_pnl']==pytest.approx(a['gross_before_execution_costs'])
