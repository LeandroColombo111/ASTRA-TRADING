import json
import pandas as pd
import pytest
from astra.legacy_research import search
from astra.engine import Risk


def test_holdout_is_never_used_during_parameter_selection(tmp_path,monkeypatch):
    import astra.legacy_research as research
    index=pd.date_range('2021-01-01','2026-09-01',freq='h',inclusive='left',tz='UTC')
    bars=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':1.,'funding':0.},index=index)
    boundary=pd.Timestamp('2025-03-01',tz='UTC')
    calls=[]
    def fake_backtest(data,p,risk,start,end,prepared=None):
        calls.append((data.index[-1],start,end))
        if prepared is not None:
            assert data.index[-1]<boundary
            assert end<=boundary
            assert not (tmp_path/'holdout.lock').exists()
        else:
            assert (tmp_path/'holdout.lock').exists()
            assert (tmp_path/'selected.json').exists()
            assert start==boundary
        eq=pd.Series(10000.,index=pd.date_range(start+pd.Timedelta(hours=1),end,freq='h'))
        return eq,[],{'halted':False}
    monkeypatch.setattr(research,'backtest',fake_backtest)
    result=search(bars,tmp_path,attempts=1,simulations=100)
    assert len(calls)==5 # three development folds, one final, one cost stress
    assert result['status']=='CRITERIA_NOT_MET'
    assert result['approved_for_live'] is False
    assert len((tmp_path/'attempts.jsonl').read_text().splitlines())==1
    with pytest.raises(ValueError,match='holdout already opened'):
        search(bars,tmp_path,attempts=1,simulations=100)


def test_invalid_budget_cannot_start(tmp_path):
    with pytest.raises(ValueError,match='1..200'):
        search(pd.DataFrame(),tmp_path,attempts=201)
