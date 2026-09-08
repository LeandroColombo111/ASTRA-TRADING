from dataclasses import asdict
from itertools import islice
import json
from pathlib import Path
import pandas as pd
import pytest
from astra.legacy_strategy import Params
from astra.engine import Risk
from astra.diagnostics import Intervention
from astra.second_research import panel,expanded,key,run_round_two,score_folds


def test_panel_budget_and_controls_not_deployable():
    base=Intervention(params=Params(fast=8,slow=60,breakout=168,stop_atr=4,trail_atr=2,reward=2))
    cases=list(panel(base,Risk()))
    assert len(cases)==30
    assert len({key(s,r) for _,s,r,_ in cases})==30
    for name,s,r,selectable in cases:
        if s.direction or not s.funding_enabled or r.fee_bps!=6 or r.slippage_bps!=3 or r.fraction!=.02:
            assert not selectable
        if selectable:assert s.direction==0 and s.funding_enabled and r.fraction==.02


def test_local_search_keeps_user_constraints():
    base=Intervention(params=Params(fast=8,slow=60,breakout=168,stop_atr=4,trail_atr=2,reward=2))
    for s,r in islice(expanded(base,Risk()),500):
        assert s.params.fast==8 and s.params.slow==60 and s.params.atr_period==14
        assert s.direction==0 and s.funding_enabled and r==Risk()
        groups=sum([s.params.trail_atr!=2 or s.trail_start_r!=0,s.params.breakout!=168 or s.entry_mode!='breakout',s.adx_min!=0,s.params.stop_atr!=4,s.params.reward!=2,s.cooldown_hours!=0])
        assert groups<=2


def test_round_two_will_not_overwrite_existing_protocol(tmp_path):
    (tmp_path/'protocol.json').write_text('{}')
    with pytest.raises(ValueError,match='already started'):
        run_round_two(output=tmp_path)
    with pytest.raises(ValueError,match='30..200'):
        run_round_two(output=tmp_path,budget=201)


def test_fold_gate_rejects_dropping_one_direction():
    folds=[{'sharpe':2.,'trades':50,'long_trades':50,'short_trades':0,'halted':False}]*3
    assert score_folds(folds)[0] is False
