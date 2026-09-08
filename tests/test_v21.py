import json
import numpy as np
import pandas as pd
import pytest
from astra.v2_data import admit_month
from astra.v21_costs import sample_book_lines
from astra.v21_precheck import hac_mean_t,simulate_raw
from astra.strategy import neutral_weights
from test_v2 import history


def test_patch_changes_only_liquidity_with_existing_cap():
    cut=pd.Timestamp('2026-09-01',tz='UTC');symbols=[f'X{i}-USDT-SWAP' for i in range(64)]
    histories={s:history(cut,6_000_000) for s in symbols}
    assert admit_month(cut,symbols,histories)['count']==0
    result=admit_month(cut,symbols,histories,5_000_000)
    assert result['count']==50 and result['pass']
    histories[symbols[0]]=histories[symbols[0]].iloc[2:]
    assert next(r for r in admit_month(cut,symbols,histories,5_000_000)['rows'] if r['symbol']==symbols[0])['admitted']==False


def test_continuous_weights_preserve_rank_sign_and_neutrality():
    names=list(range(30));scores=pd.Series(np.arange(30),index=names,dtype=float)
    vol=pd.Series(1.,index=names);beta=pd.Series(1.,index=names)
    w,d=neutral_weights(scores,vol,beta,pd.DataFrame(np.eye(30),index=names,columns=names))
    assert (np.sign(w)==np.sign(scores-scores.mean())).all()
    assert abs(w.sum())<1e-10
    assert w.loc[29]/w.loc[28]==pytest.approx(14.5/13.5)
    assert d['ex_ante_annual_volatility']==pytest.approx(.15)


def test_l2_updates_delete_best_level_before_spread_measurement():
    lines=[]
    for second in range(61):
        r={'instId':'X','ts':str(second*1000),'action':'snapshot' if second==0 else 'update','asks':[['102','1']],'bids':[['100','1'],['99','1']] if second==0 else [['100','0']]}
        lines.append((json.dumps(r)+'\n').encode())
    sample,raw=sample_book_lines(lines,'X')
    assert sample['samples']==60 and sample['last_ts']==59000
    assert sample['half_spread']==pytest.approx(3/100.5/2)
    assert len(raw.splitlines())==60


def test_raw_accounting_drift_funding_costs_and_missing_gate():
    dates=pd.date_range('2025-03-01',periods=2,tz='UTC');names=['A','B']
    w=pd.DataFrame([[.5,-.5],[.5,-.5]],index=dates,columns=names)
    prices=pd.DataFrame([[100,100],[110,90],[110,90]],index=pd.date_range('2025-03-01',periods=3,tz='UTC'),columns=names)
    funding=pd.DataFrame(0.,index=dates,columns=names);funding['A']=.001
    counts=pd.DataFrame(3.,index=dates,columns=names)
    spreads={('2025-03-01',s):.0001 for s in names}
    frame,d=simulate_raw(w,prices,funding,counts,spreads,.0005,7)
    assert d['gross_pnl_usdt']==pytest.approx(1000)
    assert d['funding_usdt']==pytest.approx(10.5)
    assert d['fees_usdt']==pytest.approx(10)
    assert d['sampled_spread_usdt']==pytest.approx(2)
    assert frame.net_nav.iloc[-1]==pytest.approx(10977.5)
    assert d['cost_coverage_complete']
    _,bad=simulate_raw(w,prices,funding,counts,{},.0005,7)
    assert bad['net_return'] is None and not bad['spread_coverage_complete']


def test_hac_positive_serial_correlation_reduces_t():
    x=np.repeat([-.1,.2,.3,.4],50)
    assert abs(hac_mean_t(x,7))<abs(hac_mean_t(x,0))


def test_midnight_funding_belongs_to_prior_position():
    dates=pd.date_range('2025-03-01',periods=2,tz='UTC');names=['A']
    weights=pd.DataFrame([[1.],[0.]],index=dates,columns=names)
    prices=pd.DataFrame(100.,index=pd.date_range('2025-03-01',periods=3,tz='UTC'),columns=names)
    funding=pd.DataFrame(.01,index=dates,columns=names)
    counts=pd.DataFrame(3.,index=dates,columns=names)
    frame,d=simulate_raw(weights,prices,funding,counts,{('2025-03-01','A'):0.},0.,1,funding)
    assert frame.funding_cost.tolist()==pytest.approx([0.,100.])
    assert d['funding_usdt']==pytest.approx(100.)


def test_random_control_accounting_matches_unpermuted_daily_cohorts(tmp_path,monkeypatch):
    import astra.v21_precheck as module
    monkeypatch.setattr(module,'OUT',tmp_path)
    dates=pd.date_range('2025-03-31',periods=2,tz='UTC');names=['A','B']
    weights=pd.DataFrame([[.5,-.5],[.4,-.4]],index=dates,columns=names)
    prices=pd.DataFrame([[100,100],[110,95],[115,96]],index=pd.date_range('2025-03-31',periods=3,tz='UTC'),columns=names)
    funding=pd.DataFrame(.001,index=dates,columns=names);midnight=funding/3
    counts=pd.DataFrame(3.,index=dates,columns=names)
    spreads={(m,s):.0001 for m in ['2025-03-01','2025-04-01'] for s in names}
    frame,_=simulate_raw(weights,prices,funding,counts,spreads,.0005,1,midnight)
    control=module.random_cohort_control(weights,prices,funding,midnight,spreads,.0005,repetitions=1)
    assert control['median_net_sharpe']==pytest.approx(module.annual_sharpe(frame.net_return))
