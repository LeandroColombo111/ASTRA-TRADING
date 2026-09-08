from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from astra.directional_strategy import Params, features
from astra.engine import Risk, Account, size, step, backtest
from astra.data import validate
from astra.legacy_research import candidates, monte_carlo


def bars(n=1500):
    rng=np.random.default_rng(3)
    c=100*np.exp(np.cumsum(rng.normal(0,.006,n)))
    return pd.DataFrame({'open':c,'high':c*1.01,'low':c*.99,'close':c,'volume':1.,'funding':0.},index=pd.date_range('2023-01-01',periods=n,freq='h',tz='UTC'))


def test_indicators_have_no_future_information():
    b=bars();p=Params();f=features(b,p)
    for cut in [803,804,805,1001,1234]:
        pd.testing.assert_frame_equal(f.iloc[:cut],features(b.iloc[:cut],p))
    modified=b.copy();modified.iloc[1001:,:4]*=10
    pd.testing.assert_frame_equal(f.iloc[:1001],features(modified,p).iloc[:1001])


def test_risk_budget_and_exposure():
    r=Risk()
    for distance in [100,1000,5000]:
        q=size(10000,50000,distance,r)
        assert q*(distance+50000*(2*r.fee_bps+r.slippage_bps)/10000)<=200+1e-8
        assert q*50000<=10000
    with pytest.raises(ValueError):Risk(fraction=.04)


def test_stop_first_and_accounting():
    r=Risk(fee_bps=0,slippage_bps=0,max_drawdown=.9)
    s=Account.new(r);p=Params(stop_atr=2,reward=2)
    b=dict(open=100,high=110,low=90,close=100,funding=0)
    f=dict(signal=1,atr=2,anchor=1)
    t=step(s,'now',b,f,f,p,r)
    assert len(t)==1 and t[0]['reason']=='stop'
    assert t[0]['exit']==96 and s.cash==10000+t[0]['net_pnl']


def test_short_pnl_and_funding_sign():
    r=Risk(fee_bps=0,slippage_bps=0,max_drawdown=.9)
    s=Account(10000,10000,10000,qty=-10,entry=100,stop=110,target=80)
    f=dict(signal=0,atr=2,anchor=-1)
    t=step(s,'now',dict(open=100,high=101,low=79,close=80,funding=.01),f,f,Params(),r)
    assert s.cash==10210
    assert t[0]['net_pnl']==210


def test_gap_stop_and_no_same_bar_reentry():
    r=Risk(fee_bps=0,slippage_bps=0,max_drawdown=.9)
    s=Account(10000,10000,10000,qty=10,entry=100,stop=95,target=120)
    f=dict(signal=1,atr=2,anchor=1)
    t=step(s,'now',dict(open=90,high=100,low=89,close=99,funding=0),f,f,Params(),r)
    assert t[0]['exit']==90 and s.qty==0


def test_halt_survives_and_blocks_entries():
    r=Risk();s=Account.new(r);s.halted=True
    f=dict(signal=1,atr=2,anchor=1)
    assert step(s,'now',dict(open=100,high=101,low=99,close=100,funding=0),f,f,Params(),r)==[]
    assert s.qty==0


def test_entry_uses_previous_signal_and_costs_reconcile():
    b=bars(200);p=Params(fast=2,slow=3,breakout=2);r=Risk(max_drawdown=.9)
    f=features(b,p);f['signal']=0;f['anchor']=1;f['atr']=1
    f.iloc[50,f.columns.get_loc('signal')]=1
    eq,trades,s=backtest(b,p,r,prepared=f)
    assert pd.Timestamp(trades[0]['entry_time'])==b.index[51]
    assert eq.iloc[-1]-r.capital==pytest.approx(sum(t['net_pnl'] for t in trades))


def test_missing_bar_rejected():
    with pytest.raises(ValueError,match='Missing'):
        validate(bars().drop(bars().index[50]))


def test_search_budget_unique_reproducible():
    assert len(set(candidates(42,200)))==200
    assert list(candidates(42,3))==list(candidates(42,3))
    with pytest.raises(ValueError):list(candidates(42,201))


def test_bootstrap_reproducible_and_initial_loss_drawdown():
    r=np.full(100,-.01)
    a=monte_carlo(r,100)
    assert a==monte_carlo(r,100)
    assert a['probability_loss']==1 and a['drawdown_p95']>.63
