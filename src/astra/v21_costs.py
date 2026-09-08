"""Actual OKX funding and observed historical L2 spread samples for raw screening."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import pandas as pd
from .v2_data import funding_file, verified_write
from .research import dump

ROOT=Path('data/v21')
OUT=Path('reports/v2.1-sleeve1')


def collect_funding():
    months=json.loads((OUT/'monthly_universes.json').read_text())
    symbols=set(s for m in months for s in m['symbols'])
    days=pd.date_range('2025-02-28','2026-09-01',tz='UTC',freq='D')
    frames=[];sources=[]
    def job(day):return funding_file(day,Path('data/v2'))
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i,(frame,source) in enumerate(pool.map(job,days),1):
            frames.append(frame.loc[frame.instrument_name.isin(symbols),['instrument_name','time','funding_rate']]);sources.append(source)
            if i%40==0:print(f'Funding archive {i}/{len(days)}',flush=True)
    f=pd.concat(frames).drop_duplicates().sort_values(['instrument_name','time'])
    f=f[(f.time>=pd.Timestamp('2025-03-01',tz='UTC'))&(f.time<pd.Timestamp('2026-09-01',tz='UTC'))]
    if f.duplicated(['instrument_name','time']).any():raise ValueError('Conflicting funding events')
    verified_write(ROOT/'funding_events.csv',f.to_csv(index=False).encode())
    dump(OUT/'funding_sources.json',sources)
    print('Funding collected',len(f),flush=True)

if __name__=='__main__':collect_funding()


def sample_book_lines(lines,symbol,seconds=60):
    """Replay snapshot/deltas; sample reconstructed BBO once per elapsed second."""
    import numpy as np
    bids={};asks={};first=None;previous_second=None;observations=[];raw=[]
    for line in lines:
        item=json.loads(line)
        if item.get('instId')!=symbol:raise ValueError('Wrong book symbol')
        stamp=int(item['ts'])
        if first is None:
            if item['action']!='snapshot':raise ValueError('L2 sample must begin with snapshot')
            first=stamp
        if stamp<first:raise ValueError('Book time reversed')
        if stamp>=first+seconds*1000:break
        raw.append(line)
        if item['action']=='snapshot':bids={};asks={}
        elif item['action']!='update':raise ValueError('Unknown L2 action')
        for side,levels in ((bids,item['bids']),(asks,item['asks'])):
            for level in levels:
                price=float(level[0]);quantity=float(level[1])
                if quantity==0:side.pop(price,None)
                else:side[price]=quantity
        second=(stamp-first)//1000
        if second!=previous_second:
            if not bids or not asks:raise ValueError('Empty reconstructed book')
            bid,ask=max(bids),min(asks)
            if bid<=0 or ask<=bid:raise ValueError('Invalid reconstructed BBO')
            observations.append({'ts':stamp,'bid':bid,'ask':ask,'spread_fraction':(ask-bid)/((ask+bid)/2)})
            previous_second=second
    if len(observations)<50:raise ValueError('Insufficient historical sample seconds')
    return {'first_ts':first,'last_ts':observations[-1]['ts'],'samples':len(observations),'half_spread':float(np.median([r['spread_fraction'] for r in observations])/2),'observations':observations},b''.join(raw)


def collect_spreads():
    import gzip,tarfile,requests,time
    from .v2_data import request_cached,verified_read
    months=json.loads((OUT/'monthly_universes.json').read_text())
    jobs=[]
    for m in months[:-1]:
        cut=pd.Timestamp(m['asof']);day=cut-pd.DateOffset(months=1)
        # Include outgoing positions: these may require liquidation on membership change.
        prior=months[max(0,months.index(m)-1)]['symbols']
        symbols=sorted(set(m['symbols'])|set(prior));links={}
        for i in range(0,len(symbols),5):
            batch=symbols[i:i+5]
            data=request_cached(ROOT/'spread_catalog'/f'{cut.date()}-{i}.json','/api/v5/public/market-data-history',{'module':'4','instType':'SWAP','instFamilyList':','.join(s.removesuffix('-SWAP') for s in batch),'dateAggrType':'daily','begin':str(int(day.timestamp()*1000)),'end':str(int(day.timestamp()*1000))},True)
            for g in data:
                for d in g.get('details',[]):
                    for f in d.get('groupDetails',[]):links[f['filename'].split('-L2orderbook')[0]]=f
        for symbol in symbols:jobs.append((str(cut.date()),symbol,links.get(symbol)))
        print('Spread catalog',cut.date(),len(links),flush=True)
    def job(args):
        cut,symbol,link=args
        try:
            if not link:raise ValueError('Historical L2 archive absent')
            path=ROOT/'spread_samples'/cut/(symbol+'.jsonl.gz')
            cached=verified_read(path)
            if cached is not None:
                result,_=sample_book_lines(gzip.decompress(cached).splitlines(keepends=True),symbol)
            else:
                from urllib.parse import urlparse
                if urlparse(link['url']).hostname!='static.okx.com':raise ValueError('Unexpected L2 host')
                for attempt in range(3):
                    try:
                        with requests.get(link['url'],stream=True,timeout=40) as response:
                            response.raise_for_status()
                            with tarfile.open(fileobj=response.raw,mode='r|gz') as archive:
                                member=next(m for m in archive if m.isfile())
                                result,raw=sample_book_lines(archive.extractfile(member),symbol)
                        verified_write(path,gzip.compress(raw,mtime=0));break
                    except (requests.RequestException,tarfile.TarError):
                        if attempt==2:raise
                        time.sleep(2**attempt)
            result.update(month=cut,symbol=symbol,url=link['url'],sample_file=str(path),sample_only=True)
            result.pop('observations')
            return result
        except Exception as e:return {'month':cut,'symbol':symbol,'error':type(e).__name__+': '+str(e)}
    results=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,r in enumerate(pool.map(job,jobs),1):
            results.append(r)
            if i%40==0:print(f'Spread samples {i}/{len(jobs)} errors={sum("error" in x for x in results)}',flush=True)
    dump(OUT/'spread_samples.json',results)
    print('Spreads complete',len(results),'errors',sum('error' in x for x in results),flush=True)
