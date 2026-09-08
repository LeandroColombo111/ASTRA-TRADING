"""Causal OKX universe admission. No Binance substitution or silent gap fill."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Lock
from zipfile import ZipFile
from urllib.parse import urlparse
import json
import re
import time
import requests
import numpy as np
import pandas as pd
from .okx import OKX, ExchangeError
from .research import dump

STABLES={'USDT','USDC','DAI','TUSD','FDUSD','USDE','USDS','USD1','PYUSD','FRAX','UST','USTC','BUSD','USDD'}
DUPLICATES={'WBTC':'BTC','WETH':'ETH','STETH':'ETH','BETH':'ETH','ETHW':'ETHW'}

class RateLimiter:
    def __init__(self,seconds=.14):self.seconds=seconds;self.lock=Lock();self.last=0.
    def wait(self):
        with self.lock:
            delay=max(0.,self.last+self.seconds-time.monotonic())
            time.sleep(delay);self.last=time.monotonic()

LIMIT=RateLimiter()
CATALOG_LIMIT=RateLimiter(.43)


def verified_read(path):
    path=Path(path);check=Path(str(path)+'.sha256')
    if not path.exists():return None
    if not check.exists() or sha256(path.read_bytes()).hexdigest()!=check.read_text().strip():
        raise ValueError(f'Cached content checksum mismatch: {path.name}')
    return path.read_bytes()


def verified_write(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(str(path)+'.tmp');temp.write_bytes(payload);temp.replace(path)
    Path(str(path)+'.sha256').write_text(sha256(payload).hexdigest())


def request_cached(path,endpoint,params,catalog=False):
    old=verified_read(path)
    if old is not None:return json.loads(old)
    client=OKX(demo=False)
    for attempt in range(4):
        (CATALOG_LIMIT if catalog else LIMIT).wait()
        try:
            response=client.request('GET',endpoint,params)
            verified_write(path,json.dumps(response).encode());return response
        except ExchangeError:
            if attempt==3:raise
            time.sleep(2**attempt)


def funding_file(day,root):
    key=day.strftime('%Y-%m-%d');stamp=int(day.timestamp()*1000)
    catalog=request_cached(root/'catalog'/f'{key}.json','/api/v5/public/market-data-history',{'module':'3','instType':'SWAP','instFamilyList':'ANY','dateAggrType':'daily','begin':str(stamp),'end':str(stamp)},True)
    files=[f for group in catalog for detail in group.get('details',[]) for f in detail.get('groupDetails',[]) if f['filename']==f'allswap-fundingrates-{key}.zip']
    if len(files)!=1:raise ValueError(f'No unique historical inventory for {key}')
    file=files[0];url=file['url']
    if urlparse(url).scheme!='https' or urlparse(url).hostname!='static.okx.com':raise ValueError('Unexpected archive source')
    dest=root/'funding_inventory'/file['filename'];raw=verified_read(dest)
    if raw is None:
        for attempt in range(4):
            try:
                response=requests.get(url,timeout=40);response.raise_for_status();raw=response.content;break
            except requests.RequestException:
                if attempt==3:raise
                time.sleep(2**attempt)
        with ZipFile(BytesIO(raw)) as z:
            if z.testzip() is not None:raise ValueError('Archive CRC failed')
        verified_write(dest,raw)
    with ZipFile(BytesIO(raw)) as z:frame=pd.read_csv(z.open(z.namelist()[0]))
    normalize={c:re.sub('[^a-z_]','',str(c).lower()) for c in frame.columns};frame=frame.rename(columns=normalize)
    required={'instrument_name','funding_rate','funding_time'}
    if not required.issubset(frame.columns):raise ValueError('Unknown funding inventory schema')
    frame['time']=pd.to_datetime(frame.funding_time,unit='ms',utc=True)
    return frame,{'url':url,'sha256':sha256(raw).hexdigest(),'date':key}


def inventory_at(cut,root):
    # UTC+8 archives straddle UTC. Filter rows by event time BEFORE cut.
    frames=[];sources=[]
    for day in (cut-pd.Timedelta(days=1),cut):
        frame,source=funding_file(day,root);frames.append(frame);sources.append(source)
    frame=pd.concat(frames)
    causal=frame[(frame.time>=cut-pd.Timedelta(days=1))&(frame.time<cut)]
    symbols=sorted(s for s in causal.instrument_name.unique() if re.fullmatch(r'[A-Z0-9]+-USDT-SWAP',str(s)))
    if not symbols:raise ValueError('Empty historical instrument inventory')
    return symbols,sources


def validate_daily(frame):
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:raise ValueError('Invalid daily candle index')
    if not np.isfinite(frame.to_numpy()).all():raise ValueError('Nonfinite daily candle data')
    if (frame[['open','high','low','close']]<=0).any().any() or (frame.quote_volume<0).any():raise ValueError('Invalid prices/quote volume')
    if ((frame.high<frame[['open','close','low']].max(axis=1))|(frame.low>frame[['open','close']].min(axis=1))).any():raise ValueError('Invalid daily OHLC')
    # Gaps are recorded by the admission window validator, never filled.


def daily_history(symbol,start,end,root):
    rows=[];cursor=int(end.timestamp()*1000);floor=int(start.timestamp()*1000)
    for n in range(30):
        path=root/'daily_pages'/symbol/f'{cursor}.json'
        result=request_cached(path,'/api/v5/market/history-candles',{'instId':symbol,'bar':'1Dutc','limit':'100','after':str(cursor)})
        if not result:break
        earliest=min(int(r[0]) for r in result)
        if earliest>=cursor:raise ValueError('Pagination did not advance')
        rows.extend(r for r in result if r[8]=='1' and floor<=int(r[0])<int(end.timestamp()*1000))
        if earliest<=floor:break
        cursor=earliest
    if not rows:return None
    frame=pd.DataFrame([[int(r[0]),*[float(v) for v in r[1:5]],float(r[7])] for r in rows],columns=['time','open','high','low','close','quote_volume'])
    frame.index=pd.to_datetime(frame.pop('time'),unit='ms',utc=True);frame=frame.sort_index();validate_daily(frame)
    dest=root/'daily'/f'{symbol}.csv';verified_write(dest,frame.to_csv(index_label='time').encode())
    return frame


def underlying(symbol):
    asset=symbol.removesuffix('-USDT-SWAP')
    for prefix in ('1000000','1000'):
        if asset.startswith(prefix):asset=asset[len(prefix):]
    return DUPLICATES.get(asset,asset)


def symbol_exclusion(symbol):
    asset=symbol.removesuffix('-USDT-SWAP')
    if underlying(symbol) in STABLES:return 'stablecoin'
    if re.search(r'[235](L|S)$',asset) or asset in {'BTCUP','BTCDOWN','ETHUP','ETHDOWN'}:return 'leveraged_token'
    return None


def admit_month(cut,symbols,histories,minimum_quote_volume=20_000_000):
    begin=cut-pd.DateOffset(months=24)
    expected=pd.date_range(begin,cut,freq='1D',inclusive='left')
    recent=pd.date_range(cut-pd.Timedelta(days=90),cut,freq='1D',inclusive='left')
    records=[]
    for symbol in sorted(symbols):
        why=symbol_exclusion(symbol);f=histories.get(symbol)
        row={'symbol':symbol,'underlying':underlying(symbol),'median_daily_quote_volume_90d':None,'expected_history_days':len(expected),'observed_history_days':0}
        if why is None:
            if f is None:why='missing_okx_history'
            else:
                past=f.loc[(f.index>=begin)&(f.index<cut)]
                row['observed_history_days']=len(past)
                if not past.index.equals(expected):why='less_than_24_continuous_months_or_gap'
                else:
                    volume=float(past.loc[recent,'quote_volume'].median());row['median_daily_quote_volume_90d']=volume
                    if volume<minimum_quote_volume:why=f'median_quote_volume_below_{minimum_quote_volume/1_000_000:g}m'
        row['reason']=why;row['admitted']=why is None;records.append(row)
    # Keep at most one instrument per underlying, based on prior liquidity.
    keep={}
    for row in sorted((r for r in records if r['admitted']),key=lambda r:(-r['median_daily_quote_volume_90d'],r['symbol'])):
        if row['underlying'] in keep:row.update(admitted=False,reason='duplicate_underlying')
        else:keep[row['underlying']]=row
    ordered=sorted((r for r in records if r['admitted']),key=lambda r:(-r['median_daily_quote_volume_90d'],r['symbol']))
    for row in ordered[50:]:row.update(admitted=False,reason='outside_top50_prior_liquidity')
    chosen=[r['symbol'] for r in ordered[:50]]
    return {'asof':str(cut),'symbols':chosen,'count':len(chosen),'pass':len(chosen)>=25,'rows':records,'lookahead':False}


def prepare_universe(root='data/v2',output='reports/v2-sleeve1'):
    root=Path(root);out=Path(output);root.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    months=pd.date_range('2025-03-01','2026-09-01',freq='MS',tz='UTC')
    inventories={};sources=[]
    for cut in months:
        symbols,source=inventory_at(cut,root);inventories[str(cut)]=symbols;sources.extend(source)
        print('Historical inventory',cut.date(),len(symbols),flush=True)
    dump(out/'historical_inventories.json',{'inventories':inventories,'sources':sources,'method':'Membership from actual prior-day funding records; current instrument list is not used to reconstruct historical membership.'})
    symbols=sorted(set().union(*[set(s) for s in inventories.values()]))
    meta=json.loads(verified_read(root/'current_instruments.json'))
    listings={r['instId']:pd.to_datetime(int(r['listTime']),unit='ms',utc=True) for r in meta if r.get('listTime')}
    # Relistings can reset current listTime. Never use it to drop a symbol
    # that has an earlier recorded historical membership.
    first_seen={s:min(pd.Timestamp(k) for k,v in inventories.items() if s in v) for s in symbols}
    excluded={s:'listed_less_than_24_months_before_latest_admission' for s in symbols if s in listings and listings[s]>months[-1]-pd.DateOffset(months=24) and first_seen[s]>=listings[s]}
    dump(out/'listing_date_conflicts.json',{s:{'current_listing_time':str(listings[s]),'earlier_historical_membership':str(first_seen[s])} for s in symbols if s in listings and first_seen[s]<listings[s]})
    fetch=[s for s in symbols if s not in excluded and symbol_exclusion(s) is None]
    dump(out/'symbol_fetch_plan.json',{'count':len(fetch),'symbols':fetch,'excluded_by_known_listing_date':excluded,'note':'All unknown or delisted historical instruments are requested from OKX. No survivor-only universe or Binance fallback.'})
    histories={};errors={}
    def job(symbol):
        try:return symbol,daily_history(symbol,months[0]-pd.DateOffset(months=24),months[-1],root),None
        except (ValueError,ExchangeError) as exc:return symbol,None,str(exc)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,(symbol,frame,error) in enumerate(pool.map(job,fetch),1):
            histories[symbol]=frame
            if error:errors[symbol]=error
            if i%10==0 or i==len(fetch):print(f'Daily history {i}/{len(fetch)}; unavailable={len(errors)}',flush=True)
    dump(out/'unavailable_history.json',errors)
    results=[admit_month(cut,inventories[str(cut)],histories) for cut in months]
    dump(out/'monthly_universes.json',results)
    pd.DataFrame([{'month':x['asof'][:10],'eligible_symbols':x['count'],'gate_pass':x['pass']} for x in results]).to_csv(out/'universe_summary.csv',index=False)
    manifest={'venue':'OKX','rows_by_symbol':{s:len(f) for s,f in histories.items() if f is not None},'unavailable':errors,'files':{str(p.relative_to(root)):p.read_text().strip() for p in root.rglob('*.sha256')},'integrity':'ZIP CRC + locally pinned SHA256 verified on every cache read. OKX does not publish separate signed/source checksums; do not claim publisher checksum verification.'}
    dump(out/'data_manifest.json',manifest)
    failing=[x for x in results if not x['pass']]
    status={'status':'UNIVERSE_GATE_FAILED' if failing else 'UNIVERSE_GATE_PASSED','minimum_universe_count':min(x['count'] for x in results),'maximum_universe_count':max(x['count'] for x in results),'failing_months':[{'month':x['asof'][:10],'count':x['count']} for x in failing],'optimization_attempts':0,'precheck_signal_status':'NOT_RUN_UNIVERSE_GATE' if failing else 'READY_FOR_COST_DATA_AND_SIGNAL_PRECHECK','approved_for_live':False}
    dump(out/'universe_gate.json',status);print(json.dumps(status,indent=2),flush=True)
    return status

if __name__=='__main__':prepare_universe()
