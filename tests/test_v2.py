import json
import numpy as np
import pandas as pd
import pytest
from astra.directional_strategy import Params
from astra.engine import Account, Risk, step
from astra.strategy import rank_ensemble, neutral_weights
from astra.v2_data import admit_month, verified_write, verified_read
from astra.research import require_precheck, ResearchGateError, cost_gate


def test_trailing_configuration_guard():
    with pytest.raises(ValueError):
        Params(stop_atr=4, trail_atr=2, trail_start_r=0)
    Params(stop_atr=4, trail_atr=4, trail_start_r=0)
    Params(stop_atr=4, trail_atr=2, trail_start_r=1)


@pytest.mark.parametrize('side', [1, -1])
def test_trailing_waits_for_one_r_and_activates_next_bar(side):
    risk = Risk(fee_bps=0, slippage_bps=0, max_drawdown=.9)
    p = Params(stop_atr=4, trail_atr=2, trail_start_r=1, reward=10)
    account = Account.new(risk)
    f = dict(signal=side, anchor=side, atr=1)
    first = dict(open=100, high=101, low=99, close=100-side, funding=0)
    assert step(account, 'first', first, f, f, p, risk) == []
    assert account.stop == 100-side*4
    assert account.entry_effective_risk_fraction == pytest.approx(.02)
    # This bar crosses the NEW trail, but it was not active intrabar.
    second = dict(open=100, high=105 if side==1 else 101,
                  low=99 if side==1 else 95, close=100+side*4, funding=0)
    assert step(account, 'second', second, f, f, p, risk) == []
    assert account.stop == 100+side*2
    third = dict(open=100+side*4, high=105, low=95, close=100, funding=0)
    trade = step(account, 'third', third, f, f, p, risk)[0]
    assert trade['exit'] == 100+side*2


def test_effective_entry_risk_includes_costs_and_active_drawdown_stop():
    risk=Risk(fee_bps=6, slippage_bps=3)
    account=Account(7600,10000,7600)
    f=dict(signal=1, anchor=1, atr=1)
    step(account,'entry',dict(open=100,high=101,low=100,close=100.5,funding=0),f,f,
         Params(stop_atr=4,trail_atr=2,trail_start_r=1),risk)
    assert account.entry_effective_stop > account.entry-4
    expected=abs(account.qty)*(abs(account.entry-account.entry_effective_stop)+account.entry*.0015)/7600
    assert account.entry_effective_risk_fraction == pytest.approx(expected)
    assert 0 < expected <= risk.fraction


def history(cut, volume=21_000_000):
    index=pd.date_range(cut-pd.DateOffset(months=24),cut+pd.Timedelta(days=5),freq='D')
    return pd.DataFrame({'quote_volume':volume},index=index)


def test_universe_causal_volume_continuity_and_minimum():
    cut=pd.Timestamp('2026-09-01',tz='UTC')
    symbols=[f'A{i}-USDT-SWAP' for i in range(25)]
    histories={s:history(cut) for s in symbols}
    initial=admit_month(cut,symbols,histories)
    assert initial['pass'] and initial['count']==25
    for f in histories.values():f.loc[cut:,'quote_volume']=0
    assert admit_month(cut,symbols,histories)==initial
    histories[symbols[0]]=histories[symbols[0]].drop(cut-pd.Timedelta(days=4))
    failed=admit_month(cut,symbols,histories)
    assert not failed['pass'] and failed['count']==24
    histories[symbols[1]].loc[:cut-pd.Timedelta(days=1),'quote_volume']=19_999_999
    assert admit_month(cut,symbols,histories)['count']==23


def test_universe_stables_and_duplicate_underlying():
    cut=pd.Timestamp('2026-09-01',tz='UTC')
    symbols=['BTC-USDT-SWAP','WBTC-USDT-SWAP','USDC-USDT-SWAP','ETH3L-USDT-SWAP']
    result=admit_month(cut,symbols,{s:history(cut) for s in symbols})
    assert result['symbols']==['BTC-USDT-SWAP']
    assert {r['reason'] for r in result['rows']}=={None,'duplicate_underlying','stablecoin','leveraged_token'}


def test_cache_detects_tampering(tmp_path):
    path=tmp_path/'raw.json'
    verified_write(path,b'original')
    assert verified_read(path)==b'original'
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):verified_read(path)


def test_rank_and_neutrality_without_future_data():
    rng=np.random.default_rng(2)
    names=[f'A{i}' for i in range(30)]
    closes=pd.DataFrame(np.exp(np.cumsum(rng.normal(0,.02,(100,30)),axis=0)),columns=names)
    score,vol=rank_ensemble(closes,names)
    short_score,short_vol=rank_ensemble(closes.iloc[:75],names)
    pd.testing.assert_frame_equal(score.iloc[:75],short_score)
    pd.testing.assert_frame_equal(vol.iloc[:75],short_vol)
    weights,stats=neutral_weights(score.iloc[-1],vol.iloc[-1],pd.Series(1.,index=names),pd.DataFrame(np.eye(30)*.25,index=names,columns=names))
    assert abs(weights.sum())<1e-7
    assert abs(stats['btc_beta_exposure'])<=.1
    assert stats['ex_ante_annual_volatility']==pytest.approx(.15)
    assert (weights>0).sum()>=10 and (weights<0).sum()>=10
    assert weights.ne(0).sum()==30


def test_research_gates_and_budget(tmp_path):
    (tmp_path/'protocol.json').write_text(json.dumps({'parameter_count':5}))
    (tmp_path/'universe_gate.json').write_text(json.dumps({'status':'UNIVERSE_GATE_FAILED'}))
    with pytest.raises(ResearchGateError,match='Hard'):require_precheck(tmp_path,61)
    with pytest.raises(ResearchGateError,match='Universe'):require_precheck(tmp_path,60)
    (tmp_path/'run.closed').write_text('closed')
    with pytest.raises(ResearchGateError,match='archived'):require_precheck(tmp_path)
    assert not cost_gate(-100,10)['passed']
    assert not cost_gate(100,31)['passed']
    assert cost_gate(100,30)['passed']
