"""Brief v2: fixed cross-sectional momentum ensemble, OKX USDT perps only.

No directional BTC strategy or horizon optimization lives in this module.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize

@dataclass(frozen=True)
class CrossSectionalParams:
    momentum_ensemble_days: tuple = (7,14,30)
    rank_weighting: str = "continuous"
    portfolio_vol_target: float = .15
    no_trade_relative_band: float = .20
    effective_stop_vol_multiplier: float = 3.

    def __post_init__(self):
        if tuple(self.momentum_ensemble_days)!=(7,14,30):raise ValueError('Ensemble horizons are fixed, not optimized')
        if self.rank_weighting!="continuous" or self.portfolio_vol_target!=.15 or self.no_trade_relative_band!=.20:raise ValueError('Brief v2 fixed portfolio definitions cannot be silently changed')
        if self.effective_stop_vol_multiplier<=0:raise ValueError('Stop distance must be positive')


def rank_ensemble(closes,symbols,params=None):
    """Ranks at each CLOSED bar. Execution must consume row i-1 at open i."""
    params=params or CrossSectionalParams()
    if len(symbols)<25:raise ValueError('Universe admission requires at least 25 symbols')
    prices=closes.loc[:,symbols]
    returns=prices.pct_change(fill_method=None)
    vol=returns.rolling(30,min_periods=30).std(ddof=1)
    ranks=[]
    for k in params.momentum_ensemble_days:
        momentum=prices.pct_change(k,fill_method=None)/vol.replace(0,np.nan)
        ranks.append(momentum.rank(axis=1,pct=True,method='average'))
    score=sum(ranks)/len(ranks)
    return score,vol


def btc_beta(returns,btc_returns):
    """60 completed daily observations; no centered windows or future data."""
    variance=btc_returns.rolling(60,min_periods=60).var(ddof=1)
    return returns.rolling(60,min_periods=60).cov(btc_returns).div(variance.replace(0,np.nan),axis=0)


def neutral_weights(score,vol,beta,annual_cov,params=None):
    """Closest inverse-vol rank allocation under dollar/beta constraints.

    Explicitly fails if continuous ranks cannot support neutrality and vol target;
    never inserts a discretionary BTC hedge outside the admitted universe.
    """
    params=params or CrossSectionalParams()
    inputs=pd.concat([score.rename('score'),vol.rename('vol'),beta.rename('beta')],axis=1)
    if len(inputs)<25 or not np.isfinite(inputs.to_numpy()).all() or (inputs.vol<=0).any():raise ValueError('Insufficient finite cross-sectional inputs')
    centered=inputs.score-inputs.score.mean()
    longs=list(centered[centered>0].index);shorts=list(centered[centered<0].index)
    if not longs or not shorts:raise ValueError('No cross-sectional dispersion')
    names=longs+shorts;n=len(longs)
    signs=np.r_[np.ones(n),-np.ones(len(shorts))]
    strength=(centered.abs()/inputs.vol).loc[names].to_numpy()
    initial=np.r_[.5*strength[:n]/strength[:n].sum(),.5*strength[n:]/strength[n:].sum()]
    betas=beta.loc[names].to_numpy();cov=annual_cov.loc[names,names].to_numpy()
    if not np.isfinite(cov).all():raise ValueError('Covariance matrix not available')
    def scaled(z):
        w=z*signs;variance=float(w@cov@w)
        if variance<=0:return w*0.,0.
        scale=params.portfolio_vol_target/np.sqrt(variance)
        return w*scale,scale
    constraints=[{'type':'eq','fun':lambda z:z[:n].sum()-.5},{'type':'eq','fun':lambda z:z[n:].sum()-.5},
                 {'type':'ineq','fun':lambda z:.1-float(scaled(z)[0]@betas)},
                 {'type':'ineq','fun':lambda z:.1+float(scaled(z)[0]@betas)}]
    initial_weights,initial_scale=scaled(initial)
    if initial_scale>0 and abs(initial_weights@betas)<=.1:
        from types import SimpleNamespace
        result=SimpleNamespace(x=initial,success=True)
    else:
        result=minimize(lambda z:float(np.square(z-initial).sum()),initial,method='SLSQP',bounds=[(0,1)]*len(names),constraints=constraints,options={'maxiter':300,'ftol':1e-12})
    w,scale=scaled(result.x)
    if not result.success or abs(w.sum())>1e-7 or abs(w@betas)>.100001:raise ValueError('Continuous ranks cannot satisfy beta/dollar neutrality')
    if scale<=0 or float(np.sqrt(w@cov@w))>.200001:raise ValueError('Invalid portfolio volatility')
    full=pd.Series(0.,index=inputs.index);full.loc[names]=w
    return full,{'net_exposure':float(w.sum()),'btc_beta_exposure':float(w@betas),'gross_exposure':float(abs(w).sum()),'ex_ante_annual_volatility':float(np.sqrt(w@cov@w))}
