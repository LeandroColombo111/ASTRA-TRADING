"""Bounded parameter search, chronological validation, sealed final holdout."""
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis
from .legacy_strategy import Params, features
from .legacy_engine import Risk, backtest, metrics, daily_returns


def candidates(seed, count):
    if not 1 <= count <= 200:
        raise ValueError("Search budget must be 1..200")
    rng, seen = np.random.default_rng(seed), set()
    while len(seen) < count:
        p = Params(fast=int(rng.choice([8,12,20,30,40])),slow=int(rng.choice([60,100,150,200])),breakout=int(rng.choice([12,24,48,72,96,168])),atr_period=int(rng.choice([14,21,28])),stop_atr=float(rng.choice([1.5,2,2.5,3,4])),trail_atr=float(rng.choice([2,3,4,5,6])),reward=float(rng.choice([2,3,4,6,10])),min_trend=float(rng.choice([0,.002,.005,.01])),max_hours=int(rng.choice([96,168,240,480])))
        if p not in seen:
            seen.add(p)
            yield p


def monte_carlo(returns, simulations=2000, seed=912, block_days=7):
    """Circular moving-block bootstrap of daily net returns (dependence retained locally)."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 60 or not np.isfinite(r).all() or simulations < 100:
        raise ValueError("Monte Carlo needs >=60 finite daily returns and >=100 paths")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0,len(r),size=(simulations,math.ceil(len(r)/block_days)))
    indices = (starts[:,:,None]+np.arange(block_days)) % len(r)
    samples = r[indices.reshape(simulations,-1)[:,:len(r)]]
    wealth = np.concatenate([np.ones((simulations,1)),np.cumprod(1+samples,axis=1)],axis=1)
    dd = (1-wealth/np.maximum.accumulate(wealth,axis=1)).max(axis=1)
    sd = samples.std(axis=1,ddof=1)
    sharpe = np.divide(samples.mean(axis=1)*np.sqrt(365),sd,out=np.zeros(simulations),where=sd>0)
    return {"simulations":simulations,"block_days":block_days,"seed":seed,"sharpe_p05":float(np.quantile(sharpe,.05)),"sharpe_p50":float(np.median(sharpe)),"sharpe_p95":float(np.quantile(sharpe,.95)),"drawdown_p95":float(np.quantile(dd,.95)),"probability_loss":float(np.mean(wealth[:,-1]<1)),"probability_drawdown_over_25pct":float(np.mean(dd>.25)),"limitation":"Conditional on observed daily returns, not proof against overfitting; paths do not re-execute strategy or drawdown halt."}


def deflated_sharpe(returns, trial_sharpes):
    """Bailey/Lopez de Prado approximation; independent trials conservatively assumed.

    Uses daily Sharpe variance across all searched configurations and nonnormal moments.
    Autocorrelation is NOT corrected here; block bootstrap is reported separately.
    """
    r = np.asarray(returns)
    sd = r.std(ddof=1)
    if sd <= 0 or len(r) < 60:
        return 0.
    sr = r.mean()/sd
    n = len(trial_sharpes)
    spread = np.std(np.asarray(trial_sharpes)/np.sqrt(365),ddof=1) if n>1 else 0.
    gamma = .5772156649
    benchmark = spread*((1-gamma)*norm.ppf(1-1/n)+gamma*norm.ppf(1-1/(n*math.e))) if n>1 else 0.
    denom = 1-skew(r,bias=False)*sr+(kurtosis(r,fisher=False,bias=False)-1)*sr*sr/4
    return float(norm.cdf((sr-benchmark)*np.sqrt(len(r)-1)/np.sqrt(max(denom,1e-12))))


def dump(path, obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")


def search(bars, output, attempts=200, seed=42, risk=None, holdout_months=18, simulations=2000):
    risk = risk or Risk()
    if holdout_months < 18:
        raise ValueError("Final holdout must cover >=18 months")
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    if (output/"holdout.lock").exists():
        raise ValueError("Final holdout already opened. Do not retune using these dates. Use new future data for a fresh independent test.")
    if (output/"protocol.json").exists():
        raise ValueError("Run directory already used; attempts cannot silently restart or exceed their budget")
    if not 1 <= attempts <= 200:
        raise ValueError("Search budget must be 1..200")
    end = bars.index[-1]+pd.Timedelta(hours=1)
    holdout = end-pd.DateOffset(months=holdout_months)
    dev_start = bars.index[0]+pd.DateOffset(months=12)
    if holdout-dev_start < pd.Timedelta(days=730):
        raise ValueError("Need >=12 months warmup +24 months development +18 months holdout")
    # Disjoint chronological development windows; full context computes causal indicators.
    bounds = [dev_start,dev_start+(holdout-dev_start)/3,dev_start+2*(holdout-dev_start)/3,holdout]
    bounds = [b.ceil("h") for b in bounds]
    data_hash = sha256(pd.util.hash_pandas_object(bars,index=True).values.tobytes()).hexdigest()
    dump(output/"protocol.json",{"seed":seed,"attempt_budget":attempts,"holdout_start":str(holdout),"end_exclusive":str(end),"risk":asdict(risk),"data_hash":data_hash,"selection":"Maximum median development-fold Sharpe minus 0.25*fold SD; all folds >=20 trades and no halt preferred; no holdout-based retuning","criteria":{"holdout_sharpe":1.5,"holdout_months":18,"minimum_trades":50,"minimum_each_side":10,"max_drawdown":.25,"bootstrap_sharpe_p05":0,"deflated_sharpe_probability":.95},"research_venue":"Binance USD-M proxy","execution_venue":"OKX BTC-USDT-SWAP"})
    records, choices = [], []
    # No holdout metrics are calculated in the search loop.
    dev = bars.loc[bars.index < holdout]
    for number,p in enumerate(candidates(seed,attempts),1):
        f = features(dev,p)
        folds = []
        for a,b in zip(bounds[:-1],bounds[1:]):
            equity,trades,state = backtest(dev,p,risk,a,b,prepared=f)
            m = metrics(equity,trades,risk.capital)
            m["halted"] = state["halted"]
            folds.append(m)
        sr = [m["sharpe"] for m in folds]
        eligible = all(m["trades"]>=20 and not m["halted"] for m in folds)
        score = float(np.median(sr)-.25*np.std(sr))
        record = {"attempt":number,"params":asdict(p),"folds":folds,"mean_sharpe":float(np.mean(sr)),"score":score,"eligible":eligible}
        records.append(record)
        choices.append((eligible,score,p,number))
        with (output/"attempts.jsonl").open("a") as stream:
            stream.write(json.dumps(record,allow_nan=False)+"\n")
        if number%10 == 0:
            print(f"Attempt {number}/{attempts}: best development score {max(x[1] for x in choices):.3f}",flush=True)
    eligible,score,p,number = max(choices,key=lambda x:(x[0],x[1]))
    dump(output/"selected.json",{"params":asdict(p),"risk":asdict(risk),"attempt":number,"development_eligible":eligible,"execution_venue":"OKX","data_venue":"Binance proxy","approved_for_live":False})
    # Persist the lock BEFORE seeing final outcomes (including across crashes).
    (output/"holdout.lock").write_text(f"Opened once: {holdout} to {end}. Data hash {data_hash}\n")
    equity,trades,state = backtest(bars,p,risk,holdout,end)
    final = metrics(equity,trades,risk.capital)
    returns = daily_returns(equity,risk.capital)
    mc = monte_carlo(returns,simulations,seed+1)
    dsr = deflated_sharpe(returns,[r["mean_sharpe"] for r in records])
    # Stress does not feed selection and is reported even when the objective fails.
    stress_risk = replace(risk,fee_bps=risk.fee_bps*2,slippage_bps=risk.slippage_bps*2)
    stress_equity,stress_trades,_ = backtest(bars,p,stress_risk,holdout,end)
    stress = metrics(stress_equity,stress_trades,risk.capital)
    gates = {"development_eligible":eligible,"sharpe_at_least_1_5":final["sharpe"]>=1.5,"at_least_18_months":holdout+pd.DateOffset(months=18)<=end,"at_least_50_trades":final["trades"]>=50,"both_sides":min(final["long_trades"],final["short_trades"])>=10,"drawdown_under_25pct":final["max_drawdown"]<=.25,"not_halted":not state["halted"],"bootstrap_lower_bound_positive":mc["sharpe_p05"]>0,"dsr_at_least_95pct":dsr>=.95,"double_costs_positive_sharpe":stress["sharpe"]>0}
    report = {"status":"PROXY_CRITERIA_MET" if all(gates.values()) else "CRITERIA_NOT_MET","attempts":attempts,"selected_attempt":number,"holdout_start":str(holdout),"holdout_end_exclusive":str(end),"params":asdict(p),"risk":asdict(risk),"holdout":final,"monte_carlo":mc,"deflated_sharpe_probability_approx":dsr,"double_cost_stress":stress,"gates":gates,"approved_for_live":False,"limitations":["Historical venue is Binance, not OKX. OKX validation remains required.","Fees/slippage are explicit assumptions, not your account fee tier.","Risk is a target at the stop, not a guaranteed maximum loss; gaps and funding can exceed it.","OHLC simulation cannot model exchange outages, queue position, mark-price liquidation or all intrabar paths.","Monte Carlo and approximate DSR cannot guarantee future Sharpe or absence of overfitting."]}
    dump(output/"report.json",report)
    equity.to_csv(output/"holdout_equity.csv",index_label="time")
    pd.DataFrame(trades).to_csv(output/"holdout_trades.csv",index=False)
    text = f"# Resultado de investigación\n\nEstado: **{report['status']}**. {attempts} intentos; seleccionado #{number}.\n\nDatos: futuros Binance BTCUSDT; referencia para OKX, no resultados de OKX.\n\nHoldout: {holdout.date()} a {end.date()} (fin exclusivo), {holdout_months} meses.\n\n| Métrica fuera de muestra | Valor |\n|---|---:|\n| Sharpe anualizado, retornos diarios, RF=0 | {final['sharpe']:.3f} |\n| Retorno neto | {final['return']:.2%} |\n| Máximo drawdown | {final['max_drawdown']:.2%} |\n| Operaciones | {final['trades']} |\n| Long / short | {final['long_trades']} / {final['short_trades']} |\n| Sharpe Monte Carlo p05 / p50 / p95 | {mc['sharpe_p05']:.3f} / {mc['sharpe_p50']:.3f} / {mc['sharpe_p95']:.3f} |\n| DSR aproximado | {dsr:.2%} |\n| Sharpe con costos duplicados | {stress['sharpe']:.3f} |\n\nNo habilitado para capital real.\n\n## Criterios\n\n" + "\n".join(f"- {'PASS' if v else 'FAIL'}: {k}" for k,v in gates.items())+"\n\n## Límites\n\n"+"\n".join("- "+s for s in report["limitations"])+"\n"
    (output/"RESULTADOS.md").write_text(text)
    return report
