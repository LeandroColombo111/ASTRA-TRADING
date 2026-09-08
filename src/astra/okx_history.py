"""Download public OKX SWAP candles and official monthly funding archives."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile
import json
import time
import requests
import pandas as pd
from .okx import OKX,INSTRUMENT,ExchangeError
from .data import validate


def candle_month(month,root):
    path=root/f'candles-{month.strftime("%Y-%m")}.json'
    end=month+pd.DateOffset(months=1)
    if path.exists():return json.loads(path.read_text())
    x=OKX(demo=False);cursor=int(end.timestamp()*1000);rows=[]
    for page in range(10):
        for attempt in range(4):
            try:
                data=x.request('GET','/api/v5/market/history-candles',{'instId':INSTRUMENT,'bar':'1H','limit':'100','after':str(cursor)})
                break
            except ExchangeError:
                if attempt==3:raise
                time.sleep(2**attempt)
        if not data:raise ValueError('Incomplete OKX historical candles')
        minimum=min(int(row[0]) for row in data)
        if minimum>=cursor:raise ValueError('OKX history pagination did not advance')
        rows.extend(row for row in data if row[8]=='1' and int(month.timestamp()*1000)<=int(row[0])<int(end.timestamp()*1000))
        cursor=minimum
        if cursor<=int(month.timestamp()*1000):break
        time.sleep(.15)
    path.write_text(json.dumps(rows))
    return rows


def download_okx(start='2025-01-01',end='2026-09-01',directory='data/okx'):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    begin,finish=pd.Timestamp(start,tz='UTC'),pd.Timestamp(end,tz='UTC')
    if begin.day!=1 or finish.day!=1 or begin>=finish:raise ValueError('Use increasing full-month boundaries')
    months=list(pd.date_range(begin,finish,freq='MS',inclusive='left'))
    x=OKX(demo=False);links=[]
    for offset in range(0,len(months),9):
        a=months[offset];b=min(a+pd.DateOffset(months=9),finish)-pd.Timedelta(milliseconds=1)
        listing_path=root/f'funding-list-{a.strftime("%Y-%m")}.json'
        if listing_path.exists():data=json.loads(listing_path.read_text())
        else:
            data=x.request('GET','/api/v5/public/market-data-history',{'module':'3','instType':'SWAP','instFamilyList':'BTC-USDT','dateAggrType':'monthly','begin':str(int(a.timestamp()*1000)),'end':str(int(b.timestamp()*1000))})
            listing_path.write_text(json.dumps(data,indent=2));time.sleep(.45)
        for group in data:
            for detail in group.get('details',[]):
                for file in detail.get('groupDetails',[]):
                    if file['filename'].startswith(INSTRUMENT+'-fundingrates-'):links.append(file)
    links={x['filename']:x for x in links}
    expected={f'{INSTRUMENT}-fundingrates-{m.strftime("%Y-%m")}.zip' for m in months}
    if not expected.issubset(links):raise ValueError('Missing official monthly funding archives: '+str(expected-set(links)))
    funding=[];manifest=[]
    for name in sorted(expected):
        item=links[name];url=item['url']
        if urlparse(url).scheme!='https' or urlparse(url).hostname!='static.okx.com':raise ValueError('Unexpected archive host')
        path=root/name
        if not path.exists():
            r=requests.get(url,timeout=40);r.raise_for_status();path.write_bytes(r.content)
        with ZipFile(BytesIO(path.read_bytes())) as z:
            frame=pd.read_csv(z.open(z.namelist()[0]))
        funding.append(frame)
        manifest.append({'url':url,'sha256':sha256(path.read_bytes()).hexdigest(),'type':'funding_archive'})
    # Parsing uses the documented/observed English field suffixes, allowing
    # bilingual legacy column labels as documented by OKX.
    funds=pd.concat(funding,ignore_index=True)
    columns={str(c).lower():c for c in funds.columns}
    rate_col=next((v for k,v in columns.items() if 'fundingrate' in k.replace('_','').replace(' ','')),None)
    time_col=next((v for k,v in columns.items() if any(w in k.replace('_','').replace(' ','') for w in ['fundingtime','timestamp'])),None)
    if rate_col is None or time_col is None:raise ValueError('Unrecognized funding schema: '+str(list(funds.columns)))
    rawtime=funds[time_col]
    numeric=pd.to_numeric(rawtime,errors='coerce')
    timestamp=pd.to_datetime(numeric,unit='ms',utc=True) if numeric.notna().all() else pd.to_datetime(rawtime,utc=True)
    rates=pd.Series(pd.to_numeric(funds[rate_col],errors='raise').to_numpy(),index=pd.DatetimeIndex(timestamp)).sort_index()
    rates=rates[(rates.index>=begin)&(rates.index<finish)]
    # OKX monthly archive boundaries are UTC+8. The final UTC funding event
    # can belong to the following archive; supplement it from public history.
    if not rates.empty and rates.index[-1] < finish-pd.Timedelta(hours=8):
        tail_path=root/f'funding-boundary-{finish.strftime("%Y-%m")}.json'
        if tail_path.exists():tail=json.loads(tail_path.read_text())
        else:
            tail=x.request('GET','/api/v5/public/funding-rate-history',{'instId':INSTRUMENT,'limit':'100','after':str(int(finish.timestamp()*1000)+1)})
            tail_path.write_text(json.dumps(tail,indent=2))
        extra=pd.Series({pd.to_datetime(int(row['fundingTime']),unit='ms',utc=True):float(row.get('realizedRate') or row['fundingRate']) for row in tail},dtype=float)
        extra=extra[(extra.index>=begin)&(extra.index<finish)]
        overlap=rates.index.intersection(extra.index)
        if len(overlap) and ((rates.loc[overlap]-extra.loc[overlap]).abs()>1e-10).any():raise ValueError('Funding REST/archive discrepancy')
        rates=pd.concat([rates,extra.loc[~extra.index.isin(rates.index)]]).sort_index()
        manifest.append({'endpoint':'https://openapi.okx.com/api/v5/public/funding-rate-history','role':'UTC boundary supplement; monthly archives use UTC+8','sha256':sha256(tail_path.read_bytes()).hexdigest()})
    if rates.empty or rates.index.has_duplicates or (rates.index.to_series().diff().dropna()>pd.Timedelta(hours=8,minutes=1)).any():raise ValueError('Missing or duplicate funding events')
    if rates.index[0]>begin+pd.Timedelta(hours=8) or rates.index[-1]<finish-pd.Timedelta(hours=8):raise ValueError('Funding boundary coverage failed')
    with ThreadPoolExecutor(max_workers=4) as pool:
        monthly=list(pool.map(lambda m:candle_month(m,root),months))
    rows=[row for part in monthly for row in part]
    bars=pd.DataFrame([[int(row[0]),*[float(x) for x in row[1:6]]] for row in rows],columns=['time','open','high','low','close','volume'])
    bars.index=pd.to_datetime(bars.pop('time'),unit='ms',utc=True);bars=bars.sort_index()
    bars['funding']=rates.groupby(rates.index.floor('h')).sum().reindex(bars.index,fill_value=0.)
    validate(bars)
    if len(bars)!=int((finish-begin).total_seconds()/3600):raise ValueError('Candle date coverage failed')
    dest=root/'BTC-USDT-SWAP-1h.csv';bars.to_csv(dest,index_label='time')
    for month in months:
        path=root/f'candles-{month.strftime("%Y-%m")}.json'
        manifest.append({'endpoint':'https://openapi.okx.com/api/v5/market/history-candles','month':month.strftime('%Y-%m'),'sha256':sha256(path.read_bytes()).hexdigest(),'type':'hourly_candles'})
    (root/'manifest.json').write_text(json.dumps({'venue':'OKX','instrument':INSTRUMENT,'start':str(begin),'end_exclusive':str(finish),'rows':len(bars),'funding_events':len(rates),'csv_sha256':sha256(dest.read_bytes()).hexdigest(),'archives':manifest,'checksum_note':'Locally computed hashes for reproducibility; OKX did not supply independent archive checksums.','validation_role':'Cross-venue comparison on known BTC dates, not independent temporal validation'},indent=2))
    print(f'OKX complete: {len(bars)} hourly candles; {len(rates)} funding events',flush=True)
    return dest

if __name__=='__main__':download_okx()
