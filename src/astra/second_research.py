"""Round two: controlled component diagnosis, then a bounded local search.

All known 2025-26 outcomes are explicitly exploratory. No new independent
18-month holdout exists after the first research round.
"""
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
from .data import load
from .engine import Risk, metrics, daily_returns
from .legacy_strategy import Params
from .legacy_research import dump, monte_carlo, deflated_sharpe
from .diagnostics import Intervention, simulate, research_features, attribution


def panel(base,risk):
    yield 'baseline',base,risk,True
    yield 'zero_fees_diagnostic',base,replace(risk,fee_bps=0),False
    yield 'zero_slippage_diagnostic',base,replace(risk,slippage_bps=0),False
    yield 'zero_funding_diagnostic',replace(base,funding_enabled=False),risk,False
    yield 'zero_all_costs_diagnostic',replace(base,funding_enabled=False),replace(risk,fee_bps=0,slippage_bps=0),False
    yield 'double_costs_stress',base,replace(risk,fee_bps=risk.fee_bps*2,slippage_bps=risk.slippage_bps*2),False
    yield 'long_only_diagnostic',replace(base,direction=1),risk,False
    yield 'short_only_diagnostic',replace(base,direction=-1),risk,False
    yield 'risk_3pct_diagnostic',base,replace(risk,fraction=.03),False
    yield 'trailing_off',replace(base,trail_enabled=False),risk,True
    for width in (3,4,6):
        yield f'trailing_width_{width}',replace(base,params=replace(base.params,trail_atr=float(width))),risk,True
    for threshold in (.5,1.,2.):
        yield f'trailing_activation_{threshold}R',replace(base,trail_start_r=threshold),risk,True
    yield 'target_off',replace(base,target_enabled=False),risk,True
    for reward in (3,4):
        yield f'target_{reward}R',replace(base,params=replace(base.params,reward=float(reward))),risk,True
    for stop in (2,3,5):
        yield f'initial_stop_{stop}ATR',replace(base,params=replace(base.params,stop_atr=float(stop))),risk,True
    for adx in (15,20,25):
        yield f'ADX_{adx}',replace(base,adx_min=float(adx)),risk,True
    for hours in (6,12):
        yield f'cooldown_{hours}h',replace(base,cooldown_hours=hours),risk,True
    yield 'pullback_EMA20',replace(base,entry_mode='pullback'),risk,True
    yield 'anchor_EMA20_100',replace(base,params=replace(base.params,fast=20,slow=100)),risk,True
    yield 'breakout_72h',replace(base,params=replace(base.params,breakout=72)),risk,True


def component_changes(base,spec):
    changed=[]
    a,b=asdict(base),asdict(spec)
    for k in a:
        if k!='params' and a[k]!=b[k]:changed.append(k)
    for k in a['params']:
        if a['params'][k]!=b['params'][k]:changed.append('params.'+k)
    return changed


def expanded(base,risk,seed=20260907):
    """Small interventions, not a wholesale rewrite: at most two component groups."""
    rng=np.random.default_rng(seed)
    while True:
        # Baseline EMA8/60, breakout168, ATR14, stop4 and target2R retained
        # unless that specific component is selected as an intervention.
        groups=rng.choice(['trailing','entry','strength','stop','target','cooldown'],size=2,replace=False)
        s=base
        for group in groups:
            if group=='trailing':
                s=replace(s,trail_start_r=float(rng.choice([0,.5,1,1.5,2])),params=replace(s.params,trail_atr=float(rng.choice([2,3,4,5,6]))))
            elif group=='entry':
                if rng.random()<.35:s=replace(s,entry_mode='pullback')
                else:s=replace(s,params=replace(s.params,breakout=int(rng.choice([48,72,96,120,168]))))
            elif group=='strength':s=replace(s,adx_min=float(rng.choice([15,18,20,22,25,30])))
            elif group=='stop':s=replace(s,params=replace(s.params,stop_atr=float(rng.choice([2,2.5,3,3.5,4,5]))))
            elif group=='target':s=replace(s,params=replace(s.params,reward=float(rng.choice([1.5,2,2.5,3,4]))))
            elif group=='cooldown':s=replace(s,cooldown_hours=int(rng.choice([3,6,12,24,48])))
        yield s,risk


def key(spec,risk):
    return json.dumps({'spec':asdict(spec),'risk':asdict(risk)},sort_keys=True)


def score_folds(folds):
    sr=np.array([x['sharpe'] for x in folds])
    eligible=all(x['trades']>=20 and not x['halted'] and x['long_trades']>0 and x['short_trades']>0 for x in folds)
    return bool(eligible),float(np.median(sr)-.25*sr.std())


def evaluate_development(bars,spec,risk,bounds,prepared):
    folds=[]
    for start,end in zip(bounds[:-1],bounds[1:]):
        e,t,s=simulate(bars,spec,risk,start,end,prepared)
        m=metrics(e,t,risk.capital);m['halted']=s['halted'];folds.append(m)
    return folds


def run_round_two(data='data/BTCUSDT-1h.csv',output='reports/run-002',baseline='configs/selected.json',budget=200,seed=20260907):
    if not 30 <= budget <= 200:raise ValueError('Round two budget must be 30..200 including diagnostic configurations')
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/'protocol.json').exists():raise ValueError('Round two already started; do not overwrite or reset its budget')
    cfg=json.loads(Path(baseline).read_text());risk=Risk(**cfg['risk']);base=Intervention(params=Params(**cfg['params']))
    bars=load(data)
    audit_start=pd.Timestamp('2025-03-01',tz='UTC');end=pd.Timestamp('2026-09-01',tz='UTC')
    start=pd.Timestamp('2022-01-01',tz='UTC')
    bounds=[start,start+(audit_start-start)/3,start+2*(audit_start-start)/3,audit_start]
    bounds=[x.ceil('h') for x in bounds]
    if bars.index[0]>pd.Timestamp('2021-01-01',tz='UTC') or bars.index[-1]<end-pd.Timedelta(hours=1):raise ValueError('Required research dates not covered')
    dump(out/'protocol.json',{'round':2,'budget_including_diagnostics':budget,'previous_round_attempts':200,'seed':seed,'data_sha256':sha256(Path(data).read_bytes()).hexdigest(),'fixed_constraints':{'venue':'OKX SWAP target; Binance for controlled comparison','asset':'BTC','signal':'1h','anchor':'4h','directions':'long and short','risk_fraction':risk.fraction,'maximum_risk_fraction':.03,'target_sharpe':1.5,'minimum_evaluation_months':18},'development_bounds':[str(x) for x in bounds],'known_audit_start':str(audit_start),'known_audit_end_exclusive':str(end),'known_audit_is_independent':False,'selection':'Development median fold Sharpe minus 0.25*SD; require >=20 trades and both sides/no halt in every fold. Diagnostic-only cost/side/risk changes are not selectable. Select before evaluating non-panel candidates on known audit.','panel_count':30,'search':'170 additional unique configurations; at most two component groups changed relative to baseline. Original anchor EMA8/60, timeframe, asset, costs and risk retained.','holdout_rule':'No new independent 18-month validation is claimed. Previous observed prices and diagnosis contaminate reuse even when computational features are causal.','stopping_rule':'Stop at 200 total round-two configurations; apparent improvement does not establish the independent target.','new_experiment_costs':'Base 6bps fees and 3bps slippage per side; funding historical. Zero-cost cases are diagnostic only.'})
    dev=bars.loc[bars.index<audit_start]
    records=[];seen=set();lookup={};feature_cache={}
    def get_features(data,spec):
        # Cost/exit-only interventions share indicators; save computation.
        fkey=(len(data),spec.params.fast,spec.params.slow,spec.params.breakout,spec.params.atr_period,spec.params.min_trend,spec.adx_min,spec.entry_mode,spec.direction)
        if fkey not in feature_cache:feature_cache[fkey]=research_features(data,spec)
        return feature_cache[fkey]
    def trial(label,spec,risk,selectable,phase):
        ident=len(records)+1
        k=key(spec,risk)
        if k in seen:return
        seen.add(k);lookup[ident]=(spec,risk)
        folds=evaluate_development(dev,spec,risk,bounds,get_features(dev,spec))
        eligible,score=score_folds(folds)
        record={'attempt':ident,'phase':phase,'label':label,'changes':component_changes(base,spec),'spec':asdict(spec),'risk':asdict(risk),'selectable':selectable,'eligible':bool(eligible and selectable),'development_score':score,'development_mean_sharpe':float(np.mean([f['sharpe'] for f in folds])),'folds':folds}
        if phase=='one_component_diagnosis':
            e,t,s=simulate(bars,spec,risk,audit_start,end,get_features(bars,spec))
            record['known_audit']=metrics(e,t,risk.capital)
            record['known_audit']['halted']=s['halted']
            record['known_audit_attribution']=attribution(t,risk.capital)
            if ident==1:
                e.to_csv(out/'baseline_equity.csv',index_label='time');pd.DataFrame(t).to_csv(out/'baseline_trades_detailed.csv',index=False)
                dump(out/'baseline_attribution.json',record['known_audit_attribution'])
        records.append(record)
        with (out/'attempts.jsonl').open('a') as stream:stream.write(json.dumps(record,allow_nan=False)+'\n')
        if phase=='one_component_diagnosis':print(f"{ident:03d}/{budget} {label}: dev {score:.3f}; known audit Sharpe {record['known_audit']['sharpe']:.3f}",flush=True)
        elif ident%10==0:print(f"{ident:03d}/{budget} targeted search; best eligible dev score {max((r['development_score'] for r in records if r['eligible']),default=0):.3f}",flush=True)
    for label,spec,risk_i,selectable in panel(base,risk):trial(label,spec,risk_i,selectable,'one_component_diagnosis')
    dump(out/'component_diagnosis.json',records.copy())
    for spec,risk_i in expanded(base,risk,seed):
        if len(records)>=budget:break
        trial('targeted_'+str(len(records)+1),spec,risk_i,True,'targeted_search')
    eligible=[r for r in records if r['eligible']]
    selected=max(eligible or [r for r in records if r['selectable']],key=lambda r:r['development_score'])
    spec,risk_i=lookup[selected['attempt']]
    dump(out/'selected_research.json',{'attempt':selected['attempt'],'spec':asdict(spec),'risk':asdict(risk_i),'changes':component_changes(base,spec),'selected_on':'development only; informed by previous research','approved_for_live':False,'approved_for_independent_target':False,'research_only':True})
    e,t,state=simulate(bars,spec,risk_i,audit_start,end,get_features(bars,spec))
    final=metrics(e,t,risk_i.capital)
    e.to_csv(out/'selected_equity.csv',index_label='time');pd.DataFrame(t).to_csv(out/'selected_trades_detailed.csv',index=False)
    r=daily_returns(e,risk_i.capital)
    mc={str(block):monte_carlo(r,2000,seed+block,block_days=block) for block in [3,7,14]}
    # Include all configurations from both rounds in the trial-count diagnostic.
    old=[json.loads(x)['mean_sharpe'] for x in Path('reports/run-001/attempts.jsonl').read_text().splitlines()]
    dsr=deflated_sharpe(r,old+[x['development_mean_sharpe'] for x in records])
    stressrisk=replace(risk_i,fee_bps=risk_i.fee_bps*2,slippage_bps=risk_i.slippage_bps*2)
    se,st,_=simulate(bars,spec,stressrisk,audit_start,end,get_features(bars,spec))
    stress=metrics(se,st,risk_i.capital)
    comparisons=[]
    for a,b in zip(pd.date_range(audit_start,end,freq='6MS')[:-1],pd.date_range(audit_start,end,freq='6MS')[1:]):
        row={'start':str(a),'end_exclusive':str(b)}
        for name,sp in [('baseline',base),('selected',spec)]:
            ce,ct,_=simulate(bars,sp,risk_i,a,b,get_features(bars,sp));row[name]=metrics(ce,ct,risk_i.capital)
        comparisons.append(row)
    report={'status':'SECOND_RESEARCH_COMPLETE_NOT_INDEPENDENTLY_VALIDATED','attempts_this_round':len(records),'cumulative_attempts':200+len(records),'selected_attempt':selected['attempt'],'selected_changes':component_changes(base,spec),'baseline_known_audit':records[0]['known_audit'],'selected_known_audit':final,'apparent_sharpe_target_met':final['sharpe']>=1.5,'independent_18month_target_met':False,'development_score':selected['development_score'],'development_folds':selected['folds'],'development_eligible':selected['eligible'],'selected_attribution':attribution(t,risk_i.capital),'monte_carlo_by_block_days':mc,'deflated_sharpe_approx_cumulative':dsr,'double_cost_stress':stress,'six_month_stability':comparisons,'approved_for_live':False,'known_audit_period':{'start':str(audit_start),'end_exclusive':str(end),'months':18,'independent':False},'limitations':['Diagnostic ablations are conditional simulated counterfactuals; they do not identify universal market causes.','Both rounds and diagnosis informed this research. Reused audit data and another venue for BTC are not independent time samples.','Monte Carlo paths are conditional resampled returns, not proof of no overfitting.','Current 1x exposure cap can lower nominal risk below 2%; risk budget and exposure cap are different.','OKX venue comparison, if available, is transportability evidence only, not independent validation.']}
    dump(out/'report.json',report)
    pd.DataFrame([{'attempt':x['attempt'],'label':x['label'],'selectable':x['selectable'],'eligible':x['eligible'],'development_score':x['development_score'],'audit_sharpe':x.get('known_audit',{}).get('sharpe'),'audit_return':x.get('known_audit',{}).get('return'),'audit_trades':x.get('known_audit',{}).get('trades')} for x in records]).to_csv(out/'comparison.csv',index=False)
    print(json.dumps({'status':report['status'],'selected_attempt':selected['attempt'],'changes':report['selected_changes'],'known_audit':final},indent=2),flush=True)
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--data',default='data/BTCUSDT-1h.csv');p.add_argument('--output',default='reports/run-002');p.add_argument('--budget',type=int,default=200)
    a=p.parse_args();run_round_two(data=a.data,output=a.output,budget=a.budget)
