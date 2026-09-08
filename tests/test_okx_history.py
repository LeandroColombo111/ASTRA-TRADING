from pathlib import Path
from zipfile import ZipFile
import json
import pandas as pd
from astra.okx_history import download_okx


def test_utc8_archives_supplement_final_utc_event(tmp_path,monkeypatch):
    import astra.okx_history as history
    start=pd.Timestamp('2026-07-01',tz='UTC');end=pd.Timestamp('2026-09-01',tz='UTC')
    months=pd.date_range(start,end,freq='MS',inclusive='left')
    groups=[]
    for month in months:
        following=month+pd.DateOffset(months=1)
        name=f'BTC-USDT-SWAP-fundingrates-{month.strftime("%Y-%m")}.zip'
        times=pd.date_range(month-pd.Timedelta(hours=8),following-pd.Timedelta(hours=8),freq='8h',inclusive='left')
        frame=pd.DataFrame({'instrument_name':'BTC-USDT-SWAP','funding_rate':.0001,'funding_time':[int(t.timestamp()*1000) for t in times]})
        with ZipFile(tmp_path/name,'w') as z:z.writestr(name.replace('.zip','.csv'),frame.to_csv(index=False))
        groups.append({'filename':name,'url':'https://static.okx.com/'+name})
        candles=[[str(int(t.timestamp()*1000)),'100','101','99','100','1','1','100','1'] for t in pd.date_range(month,following,freq='h',inclusive='left')]
        (tmp_path/f'candles-{month.strftime("%Y-%m")}.json').write_text(json.dumps(candles))
    class Public:
        def __init__(self,demo):assert demo is False
        def request(self,method,path,params):
            assert method=='GET'
            if path.endswith('market-data-history'):return [{'details':[{'groupDetails':groups}]}]
            if path.endswith('funding-rate-history'):
                return [{'fundingTime':str(int((end-pd.Timedelta(hours=8)).timestamp()*1000)),'realizedRate':'.0001','fundingRate':'.0001'}]
            raise AssertionError('Unexpected network endpoint')
    monkeypatch.setattr(history,'OKX',Public);monkeypatch.setattr(history.time,'sleep',lambda _:None)
    path=download_okx('2026-07-01','2026-09-01',tmp_path)
    bars=pd.read_csv(path,index_col='time',parse_dates=True)
    assert len(bars)==62*24
    assert (bars.funding!=0).sum()==62*3
    assert bars.loc[end-pd.Timedelta(hours=8),'funding']==.0001
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    assert manifest['funding_events']==186
    assert any(x.get('role','').startswith('UTC boundary') for x in manifest['archives'])
