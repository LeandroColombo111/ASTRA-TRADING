"""Small OKX V5 adapter. Explicit SWAP, contracts, read-only checks and demo orders."""
import base64
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import hashlib
import hmac
import json
import os
from pathlib import Path
from urllib.parse import urlencode
import requests
import pandas as pd

INSTRUMENT = 'BTC-USDT-SWAP'
ALLOWED_HOSTS = {'https://openapi.okx.com','https://www.okx.com','https://us.okx.com','https://eea.okx.com'}

class ExchangeError(RuntimeError):
    pass

class AmbiguousOrder(RuntimeError):
    pass


def load_env(path='.env'):
    """Read only known OKX variables, never execute/source shell content."""
    if not Path(path).exists():
        return
    allowed={'OKX_API_KEY','OKX_API_SECRET','OKX_PASSPHRASE','OKX_DEMO','OKX_BASE_URL'}
    for line in Path(path).read_text().splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        key,value=line.split('=',1)
        if key.strip() in allowed:
            os.environ.setdefault(key.strip(),value.strip().strip('\"\''))


def rounded(value, step, up=False):
    v,s=Decimal(str(value)),Decimal(str(step))
    return format((v/s).to_integral_value(rounding=ROUND_UP if up else ROUND_DOWN)*s,'f')


class OKX:
    def __init__(self, demo=True):
        self.demo=demo
        self.base=os.getenv('OKX_BASE_URL','https://openapi.okx.com').rstrip('/')
        if self.base not in ALLOWED_HOSTS:
            raise ValueError('Only official OKX API hosts may receive credentials')
        self.session=requests.Session()

    def request(self, method, path, params=None, body=None, private=False):
        target=path+('?' + urlencode(params) if params else '')
        payload=json.dumps(body,separators=(',',':')) if body is not None else ''
        headers={'Content-Type':'application/json'}
        if self.demo:
            headers['x-simulated-trading']='1'
        if private:
            key,secret,password=(os.getenv(k) for k in ('OKX_API_KEY','OKX_API_SECRET','OKX_PASSPHRASE'))
            if not all([key,secret,password]):
                raise ExchangeError('Missing OKX environment credentials')
            timestamp=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
            signature=base64.b64encode(hmac.new(secret.encode(),(timestamp+method+target+payload).encode(),hashlib.sha256).digest()).decode()
            headers.update({'OK-ACCESS-KEY':key,'OK-ACCESS-SIGN':signature,'OK-ACCESS-PASSPHRASE':password,'OK-ACCESS-TIMESTAMP':timestamp})
        try:
            r=self.session.request(method,self.base+target,data=payload or None,headers=headers,timeout=20,allow_redirects=False)
            if r.status_code!=200:
                raise ExchangeError(f'OKX HTTP {r.status_code} on {path}')
            result=r.json()
        except (requests.RequestException,ValueError):
            # Never include request, response body, headers or credential material.
            error=AmbiguousOrder if method=='POST' else ExchangeError
            raise error(f'OKX transport failure on {path}; reconcile before another order') from None
        if str(result.get('code'))!='0':
            raise ExchangeError(f"OKX code {result.get('code')} on {path}")
        data=result.get('data',[])
        for item in data:
            if isinstance(item,dict) and str(item.get('sCode','0'))!='0':
                raise ExchangeError(f"OKX order code {item.get('sCode')} on {path}")
        return data

    def instrument(self):
        data=self.request('GET','/api/v5/public/instruments',{'instType':'SWAP','instId':INSTRUMENT})
        if len(data)!=1:
            raise ExchangeError('Instrument missing')
        x=data[0]
        if x.get('instType')!='SWAP' or x.get('ctType')!='linear' or x.get('ctValCcy')!='BTC' or x.get('settleCcy')!='USDT' or x.get('state')!='live':
            raise ExchangeError('Unexpected instrument contract specification')
        return x

    def candles(self, after=None):
        params={'instId':INSTRUMENT,'bar':'1H','limit':'100'}
        if after is not None:
            params['after']=str(after)
        data=self.request('GET','/api/v5/market/history-candles',params)
        rows=[x for x in data if x[8]=='1']
        if not rows:
            raise ExchangeError('No completed OKX candles')
        frame=pd.DataFrame([[int(x[0]),*[float(y) for y in x[1:6]]] for x in rows],columns=['time','open','high','low','close','volume'])
        frame.index=pd.to_datetime(frame.pop('time'),unit='ms',utc=True)
        return frame.sort_index()

    def positions(self):
        return [x for x in self.request('GET','/api/v5/account/positions',{'instType':'SWAP'},private=True) if float(x.get('pos',0))!=0]

    def config(self):
        return self.request('GET','/api/v5/account/config',private=True)[0]

    def equity(self):
        account=self.request('GET','/api/v5/account/balance',{'ccy':'USDT'},private=True)[0]
        usdt=next((x for x in account['details'] if x['ccy']=='USDT'),None)
        if usdt is None or float(usdt.get('eq','0'))<=0:
            raise ExchangeError('Positive USDT trading equity required')
        return float(usdt['eq'])

    def pending(self):
        return self.request('GET','/api/v5/trade/orders-pending',{'instType':'SWAP'},private=True)

    def algos(self):
        results=[]
        for kind in ('conditional','oco'):
            results.extend(self.request('GET','/api/v5/trade/orders-algo-pending',{'instType':'SWAP','ordType':kind},private=True))
        return results

    def ticker(self):
        return self.request('GET','/api/v5/market/ticker',{'instId':INSTRUMENT})[0]

    def bills(self, since_ms):
        """Trading-account ledger (fills, transfers, funding) from since_ms
        (inclusive, epoch milliseconds) to now. Paginated via billId."""
        results, after = [], None
        while True:
            params={'instType':'SWAP','begin':str(since_ms),'limit':'100'}
            if after is not None:
                params['after']=after
            page=self.request('GET','/api/v5/account/bills',params,private=True)
            results.extend(page)
            if len(page)<100:
                return results
            after=page[-1]['billId']

    def order(self,client_id):
        return self.request('GET','/api/v5/trade/order',{'instId':INSTRUMENT,'clOrdId':client_id},private=True)[0]

    def place(self,body):
        if not self.demo:
            raise ExchangeError('Real execution disabled: strategy and OKX forward validation are not approved')
        return self.request('POST','/api/v5/trade/order',body=body,private=True)[0]

    def amend_stop(self,algo_id,stop):
        if not self.demo:
            raise ExchangeError('Real execution disabled')
        return self.request('POST','/api/v5/trade/amend-algos',body={'instId':INSTRUMENT,'algoId':algo_id,'newSlTriggerPx':stop,'newSlOrdPx':'-1'},private=True)

    def cancel_algos(self,ids):
        if not self.demo:
            raise ExchangeError('Real execution disabled')
        if ids:
            return self.request('POST','/api/v5/trade/cancel-algos',body=[{'instId':INSTRUMENT,'algoId':x} for x in ids],private=True)


def entry_plan(meta,side,price,atr,p,risk,equity,client_id):
    from .engine import size
    if side not in (-1,1) or not atr>0 or not price>0:
        raise ValueError('Invalid signal')
    # Reserve adverse fill/slippage in sizing; round stops toward entry.
    expected=price*(1+side*risk.slippage_bps/10000)
    distance=atr*p.stop_atr
    stop=rounded(expected-side*distance,meta['tickSz'],up=side==1)
    target=rounded(expected+side*distance*p.reward,meta['tickSz'],up=side==-1)
    if float(stop)<=0 or float(target)<=0 or (side==1 and not float(stop)<price<float(target)) or (side==-1 and not float(target)<price<float(stop)):
        raise ValueError('Invalid protection levels')
    base_qty=size(equity,expected,abs(expected-float(stop)),risk)
    multiplier=Decimal(meta['ctVal'])*Decimal(meta.get('ctMult') or '1')
    contracts=rounded(Decimal(str(base_qty))/multiplier,meta['lotSz'])
    if Decimal(contracts)<Decimal(meta['minSz']):
        raise ValueError('Position smaller than OKX minimum')
    return {'instId':INSTRUMENT,'tdMode':'isolated','posSide':'net','clOrdId':client_id,'side':'buy' if side==1 else 'sell','ordType':'market','sz':contracts,'attachAlgoOrds':[{'attachAlgoClOrdId':client_id+'s','slTriggerPx':stop,'slOrdPx':'-1','slTriggerPxType':'last','tpTriggerPx':target,'tpOrdPx':'-1','tpTriggerPxType':'last'}]}
