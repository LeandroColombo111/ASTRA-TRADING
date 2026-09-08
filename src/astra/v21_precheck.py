"""Locked v2.1 raw-signal screen. No optimization or historical holdout claim."""
from pathlib import Path
from io import BytesIO
import json
import numpy as np
import pandas as pd
from .v2_data import admit_month, verified_read
from .research import dump

OUT=Path('reports/v2.1-sleeve1')
ROOT=Path('data/v2')


def read_histories():
    manifest=json.loads(Path('reports/v2-sleeve1/data_manifest.json').read_text())
    histories={}
    for s in manifest['rows_by_symbol']:
        f=pd.read_csv(BytesIO(verified_read(ROOT/'daily'/f'{s}.csv')),index_col='time',parse_dates=True)
        f.index=pd.to_datetime(f.index,utc=True);histories[s]=f
    return histories


def ensure_open():
    if (OUT/"run.closed").exists():raise RuntimeError("v2.1 archived; no threshold changes or repeated search")


def universe():
    ensure_open()
    protocol=json.loads((OUT/'protocol.json').read_text())
    assert protocol['fixed_operational_constraints']['median_quote_volume_90d_min']==5_000_000
    original=json.loads(Path('reports/v2-sleeve1/historical_inventories.json').read_text())
    histories=read_histories()
    results=[admit_month(pd.Timestamp(cut),symbols,histories,5_000_000) for cut,symbols in original['inventories'].items()]
    dump(OUT/'monthly_universes.json',results)
    pd.DataFrame([{'month':m['asof'][:10],'eligible_before_cap':sum(r['admitted'] or r['reason']=='outside_top50_prior_liquidity' for r in m['rows']),'selected':m['count'],'gate_pass':m['pass']} for m in results]).to_csv(OUT/'universe_summary.csv',index=False)
    gate={'status':'UNIVERSE_GATE_PASSED' if all(m['pass'] for m in results) else 'UNIVERSE_GATE_FAILED','minimum_universe_count':min(m['count'] for m in results),'maximum_universe_count':max(m['count'] for m in results),'optimization_attempts':0,'approved_for_live':False}
    dump(OUT/'universe_gate.json',gate)
    print(json.dumps(gate),flush=True)
    return results,histories




def hac_mean_t(values,lag):
    x=np.asarray(values,dtype=float);x=x[np.isfinite(x)];n=len(x)
    if n<3:return None
    z=x-x.mean();longvar=float(z@z/n)
    for k in range(1,min(lag,n-1)+1):longvar+=2*(1-k/(lag+1))*float(z[k:]@z[:-k]/n)
    return float(x.mean()/np.sqrt(longvar/n)) if longvar>0 else None


def annual_sharpe(values):
    x=np.asarray(values,dtype=float)
    return float(np.sqrt(365)*x.mean()/x.std(ddof=1)) if len(x)>1 and x.std(ddof=1)>0 else None


def prepare_signals():
    from .strategy import rank_ensemble,btc_beta,neutral_weights
    months=json.loads((OUT/'monthly_universes.json').read_text());histories=read_histories()
    names=sorted(set(s for m in months for s in m['symbols']))
    closes=pd.DataFrame({s:histories[s].close for s in names})
    opens=pd.DataFrame({s:histories[s].open for s in names})
    returns=closes.pct_change(fill_method=None)
    beta=btc_beta(returns,returns['BTC-USDT-SWAP'])
    dates=pd.date_range('2025-03-01','2026-08-31',tz='UTC',freq='D')
    scores=pd.DataFrame(np.nan,index=dates,columns=names);weights=pd.DataFrame(0.,index=dates,columns=names);diagnostics=[]
    for m in months[:-1]:
        cut=pd.Timestamp(m['asof']);end=cut+pd.DateOffset(months=1);selected=m['symbols']
        rank,vol=rank_ensemble(closes,selected)
        for date in dates[(dates>=cut)&(dates<end)]:
            prev=date-pd.Timedelta(days=1)
            covariance=returns.loc[:prev,selected].tail(60).cov(min_periods=60)*365
            w,d=neutral_weights(rank.loc[prev],vol.loc[prev],beta.loc[prev,selected],covariance)
            scores.loc[date,selected]=rank.loc[prev];weights.loc[date,selected]=w
            d['date']=str(date.date());diagnostics.append(d)
        print('Signal weights prepared',cut.date(),flush=True)
    scores.to_csv(OUT/'raw_scores.csv',index_label='time')
    weights.to_csv(OUT/'raw_weights.csv',index_label='time')
    dump(OUT/'weight_diagnostics.json',diagnostics)
    return scores,weights,opens


def evaluate():
    ensure_open()
    from io import BytesIO
    scores,weights,opens=prepare_signals()
    # The final close of Aug 31 is the observable terminal mark at Sep 1.
    # Fetch exact next open separately if absent; never silently substitute.
    names=list(weights.columns)
    terminal=pd.Timestamp('2026-09-01',tz='UTC')
    if terminal not in opens.index or opens.loc[terminal,names].isna().any():
        from .v2_data import daily_history
        for s in names:
            f=daily_history(s,terminal,terminal+pd.Timedelta(days=1),Path('data/v21/terminal'))
            if f is None or terminal not in f.index:raise ValueError('Missing terminal OKX open: '+s)
            opens.loc[terminal,s]=f.loc[terminal,'open']
    events=pd.read_csv(BytesIO(verified_read(Path('data/v21/funding_events.csv'))))
    events['time']=pd.to_datetime(events.time,utc=True)
    events['day']=events.time.dt.floor('D')
    funding=events.pivot_table(index='day',columns='instrument_name',values='funding_rate',aggfunc='sum').reindex(index=weights.index,columns=names)
    counts=events.pivot_table(index='day',columns='instrument_name',values='funding_rate',aggfunc='count').reindex(index=weights.index,columns=names)
    midnight=events.loc[events.time==events.day].pivot_table(index='day',columns='instrument_name',values='funding_rate',aggfunc='sum').reindex(index=weights.index,columns=names).fillna(0.)
    spread_records=json.loads((OUT/'spread_samples.json').read_text())
    spread_lookup={(r['month'],r['symbol']):r['half_spread'] for r in spread_records if 'error' not in r}
    fee_meta=json.loads((OUT/'account_fee.json').read_text())['values']
    fee=abs(float(fee_meta.get('takerU') or fee_meta['taker']))
    horizons=json.loads((OUT/'protocol.json').read_text())['precheck']['diagnostic_rebalance_days']
    outputs=[];ic_rows=[];curves={}
    for horizon in horizons:
        ic=[]
        for date in scores.index:
            future=date+pd.Timedelta(days=horizon)
            if future>terminal:continue
            score=scores.loc[date].dropna();forward=opens.loc[future,score.index]/opens.loc[date,score.index]-1
            valid=pd.concat([score.rename('score'),forward.rename('forward')],axis=1).dropna()
            if len(valid)<25:raise ValueError('Incomplete forward IC cross-section')
            value=valid.score.corr(valid.forward,method='spearman');ic.append(value)
            ic_rows.append({'date':date,'horizon':horizon,'ic':value,'symbols':len(valid)})
        frame,diag=simulate_raw(weights,opens,funding,counts,spread_lookup,fee,horizon,midnight)
        frame.to_csv(OUT/f'raw_daily_h{horizon}.csv',index_label='time')
        curves[horizon]=frame
        outputs.append({'horizon_days':horizon,'ic_mean':float(np.nanmean(ic)),'ic_hac_t':hac_mean_t(ic,max(horizon-1,7)),'ic_days':len(ic),'gross_sharpe':annual_sharpe(frame.gross_return),'net_sharpe':annual_sharpe(frame.net_return) if diag['cost_coverage_complete'] else None,**diag})
        print('Raw precheck horizon',horizon,outputs[-1],flush=True)
    pd.DataFrame(ic_rows).to_csv(OUT/'ic_series.csv',index=False)
    pd.DataFrame(outputs).to_csv(OUT/'precheck_table.csv',index=False)
    primary=outputs[0]
    result={'status':'NOT_EVALUABLE_COST_DATA' if primary['net_sharpe'] is None else ('SIGNAL_PRECHECK_PASSED' if primary['net_sharpe']>.3 else 'SIGNAL_PRECHECK_FAILED'),'primary_daily_net_sharpe':primary['net_sharpe'],'historical_spread_costs_verified':primary['spread_coverage_complete'],'funding_verified':primary['funding_coverage_complete'],'optimization_attempts':0,'approved_for_live':False,'horizons':outputs,'net_model':'Actual daily summed funding rates applied to opening marked notional; current authenticated fee scenario and causal prior-month L2 sampled half-spread. Funding intraday mark approximation disclosed; not final execution engine validation.'}
    result['benchmarks']=benchmarks(weights,opens,funding,counts,midnight,spread_lookup,fee)
    dump(OUT/'signal_precheck.json',result)
    return result


def simulate_raw(weights,opens,funding,counts,spreads,fee,horizon,funding_at_open=None):
    """Daily futures units held between rebalances, marked open-to-open.

    Costs use the same gross-sized positions for additive attribution. They do
    not change future positions in this raw screen. Net NAV accumulates P&L.
    """
    names=list(weights.columns);q=np.zeros(len(names));gross_nav=10000.;net_nav=10000.;rows=[]
    previous_month=None;missing_spread=set();missing_funding=set();max_notional=0.;turnover=[]
    totalfees=totalslip=totalfunding=grosspnl=0.
    for i,date in enumerate(weights.index):
        nextdate=date+pd.Timedelta(days=1);month=str(date.date().replace(day=1))
        price=opens.loc[date,names].to_numpy();nextprice=opens.loc[nextdate,names].to_numpy()
        target=weights.loc[date].to_numpy();active=(q!=0)|(target!=0)
        if not np.isfinite(price[active]).all() or not np.isfinite(nextprice[active]).all():raise ValueError('Missing held price; no synthetic delisting fill')
        before=gross_nav;net_before=net_nav;prior_q=q.copy()
        trade=np.zeros(len(names))
        if i%horizon==0 or month!=previous_month:
            newq=np.divide(gross_nav*target,price,out=np.zeros(len(names)),where=target!=0)
            trade=abs(newq-q)*np.nan_to_num(price);q=newq
        previous_month=month
        # Terminal liquidation is explicitly charged at the final open.
        terminal_trade=abs(q)*np.nan_to_num(nextprice) if i==len(weights)-1 else np.zeros(len(names))
        traded=trade+terminal_trade
        tc=float(traded.sum()*fee);sc=0.
        for j in np.flatnonzero(traded):
            half=spreads.get((month,names[j]))
            if half is None:missing_spread.add((month,names[j]))
            else:sc+=traded[j]*half
        held=q!=0;dailyfund=funding.loc[date].to_numpy();count=counts.loc[date].to_numpy()
        for j in np.flatnonzero(held & (~np.isfinite(dailyfund)|(count<3))):missing_funding.add((str(date.date()),names[j]))
        openfund=funding_at_open.loc[date].to_numpy() if funding_at_open is not None else np.zeros(len(names))
        fc=float(np.sum(q[held]*price[held]*np.nan_to_num(dailyfund[held]-openfund[held])))
        prior_held=prior_q!=0
        fc+=float(np.sum(prior_q[prior_held]*price[prior_held]*openfund[prior_held]))
        gp=float(np.sum(q[held]*(nextprice[held]-price[held])))
        gross_nav+=gp;net_nav+=gp-tc-sc-fc
        if gross_nav<=0 or net_nav<=0:raise ValueError('Raw portfolio insolvent')
        max_notional=max(max_notional,float(np.max(abs(q[held]*price[held]))) if held.any() else 0.)
        turnover.append(float(trade.sum()/before));totalfees+=tc;totalslip+=sc;totalfunding+=fc;grosspnl+=gp
        rows.append({'gross_return':gp/before,'net_return':(gp-tc-sc-fc)/net_before,'gross_nav':gross_nav,'net_nav':net_nav,'price_pnl':gp,'fee':tc,'sampled_spread_cost':sc,'funding_cost':fc,'turnover':turnover[-1]})
    return pd.DataFrame(rows,index=weights.index),{'cost_coverage_complete':not missing_spread and not missing_funding,'spread_coverage_complete':not missing_spread,'funding_coverage_complete':not missing_funding,'missing_spread_pairs':len(missing_spread),'missing_funding_days_symbols':len(missing_funding),'mean_daily_turnover_equity':float(np.mean(turnover)),'max_position_notional_usdt':max_notional,'gross_pnl_usdt':grosspnl,'fees_usdt':totalfees,'sampled_spread_usdt':totalslip,'funding_usdt':totalfunding,'net_return':net_nav/10000-1 if not missing_spread and not missing_funding else None}


def random_cohort_control(weights,opens,funding,midnight,spreads,fee,repetitions=1000,seed=2101):
    """Randomize dates of 1-day allocation cohorts within causal membership month.

    Preserves cohort duration, symbols, number, side mix and weight distribution.
    It is a raw signal control, not final-engine trade-spell randomization.
    """
    rng=np.random.default_rng(seed);dates=weights.index;names=list(weights.columns)
    w=weights.to_numpy();price=opens.reindex(dates).loc[:,names].to_numpy()
    nextprice=opens.reindex(dates+pd.Timedelta(days=1)).loc[:,names].to_numpy()
    returns=np.nan_to_num(nextprice/price-1)
    funds=np.nan_to_num(funding.to_numpy());openfund=midnight.to_numpy()
    halves=np.array([[spreads.get((str(d.date().replace(day=1)),s),np.nan) for s in names] for d in dates])
    months=dates.strftime('%Y-%m');groups=[np.flatnonzero(months==m) for m in sorted(set(months))]
    sharpes=[]
    for trial in range(repetitions):
        p=w.copy()
        for idx in groups:p[idx]=w[rng.permutation(idx)]
        grossret=np.sum(p*returns,axis=1)
        grossbefore=np.r_[10000.,10000*np.cumprod(1+grossret)[:-1]]
        drift=np.zeros_like(p);drift[1:]=p[:-1]*(1+returns[:-1])/(1+grossret[:-1,None])
        trade=abs(p-drift);trade[-1]+=abs(p[-1])*(1+returns[-1])
        if ((trade>1e-12)&~np.isfinite(halves)).any():return {'status':'NOT_EVALUABLE_MISSING_SPREAD','repetitions':0}
        costs=np.sum(trade*(fee+np.nan_to_num(halves)),axis=1)
        fundingcost=np.sum(p*(funds-openfund)+drift*openfund,axis=1)
        pnl=grossbefore*(grossret-costs-fundingcost)
        netnav=10000+np.cumsum(pnl);before=np.r_[10000.,netnav[:-1]]
        sharpes.append(annual_sharpe(pnl/before) if (netnav>0).all() else -100.)
    pd.DataFrame({'net_sharpe':sharpes}).to_csv(OUT/'random_control_1000.csv',index=False)
    return {'status':'MEASURED_RAW_COHORT_CONTROL','repetitions':repetitions,'seed':seed,'median_net_sharpe':float(np.median(sharpes)),'p95_net_sharpe':float(np.quantile(sharpes,.95)),'scope':'One-day raw allocation cohorts permuted within monthly universe; final-engine position-duration benchmark remains a later stage.'}


def benchmarks(weights,opens,funding,counts,midnight,spreads,fee):
    months=json.loads((OUT/'monthly_universes.json').read_text())
    equal=weights*0
    for m in months[:-1]:
        begin=pd.Timestamp(m['asof']);end=begin+pd.DateOffset(months=1)
        equal.loc[(equal.index>=begin)&(equal.index<end),m['symbols']]=1/len(m['symbols'])
    btc=weights*0;btc['BTC-USDT-SWAP']=1.
    results={}
    for name,w,h in [('btc_perpetual_passive_long',btc,10**6),('equal_weight_perpetual_basket',equal,10**6)]:
        frame,diag=simulate_raw(w,opens,funding,counts,spreads,fee,h,midnight)
        frame.to_csv(OUT/f'benchmark_{name}.csv',index_label='time')
        results[name]={'gross_sharpe':annual_sharpe(frame.gross_return),'net_sharpe':annual_sharpe(frame.net_return) if diag['cost_coverage_complete'] else None,**diag}
    results['random_cohorts']=random_cohort_control(weights,opens,funding,midnight,spreads,fee)
    return results


def run_precheck():
    ensure_open()
    from .v21_costs import collect_funding,collect_spreads
    months,_=universe()
    if not all(m['pass'] for m in months):raise RuntimeError('Universe failed; precheck prohibited')
    collect_funding();collect_spreads()
    return evaluate()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['universe','precheck'],default='precheck',nargs='?')
    args=parser.parse_args()
    universe() if args.stage=='universe' else run_precheck()
