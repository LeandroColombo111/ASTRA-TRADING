from decimal import Decimal
import hashlib
import hmac
import base64
import json
import pytest
import requests
from astra.okx import OKX,ExchangeError,AmbiguousOrder,entry_plan,load_env
from astra.directional_strategy import Params
from astra.engine import Risk
from astra.service import Store

META={'ctVal':'0.01','ctMult':'1','lotSz':'0.01','minSz':'0.01','tickSz':'0.1'}

@pytest.mark.parametrize('side',[-1,1])
def test_contract_units_and_protection(side):
    body=entry_plan(META,side,60000,300,Params(),Risk(),10000,'astabc')
    assert body['instId']=='BTC-USDT-SWAP' and body['tdMode']=='isolated'
    assert body['posSide']=='net' and body['side']==('buy' if side==1 else 'sell')
    btc=float(body['sz'])*.01
    assert btc*60000<=10000
    assert Decimal(body['sz']) % Decimal(META['lotSz'])==0
    a=body['attachAlgoOrds'][0]
    assert a['slOrdPx']==a['tpOrdPx']=='-1'
    assert (float(a['slTriggerPx'])<60000<float(a['tpTriggerPx'])) if side==1 else (float(a['tpTriggerPx'])<60000<float(a['slTriggerPx']))


def test_signing_and_demo_header(monkeypatch):
    for k,v in [('OKX_API_KEY','fakekey'),('OKX_API_SECRET','fakesecret'),('OKX_PASSPHRASE','fakepass')]:monkeypatch.setenv(k,v)
    x=OKX()
    def request(method,url,**kw):
        assert kw['allow_redirects'] is False
        h=kw['headers'];assert h['x-simulated-trading']=='1'
        path=url.removeprefix(x.base)
        expected=base64.b64encode(hmac.new(b'fakesecret',(h['OK-ACCESS-TIMESTAMP']+method+path).encode(),hashlib.sha256).digest()).decode()
        assert expected==h['OK-ACCESS-SIGN']
        return type('Response',(),{'status_code':200,'json':lambda self:{'code':'0','data':[]}})()
    monkeypatch.setattr(x.session,'request',request)
    assert x.request('GET','/api/v5/account/positions',{'instType':'SWAP'},private=True)==[]


def test_live_writes_disabled():
    with pytest.raises(ExchangeError,match='Real execution disabled'):OKX(demo=False).place({})


def test_credentials_not_sent_to_arbitrary_host(monkeypatch):
    monkeypatch.setenv('OKX_BASE_URL','https://example.com')
    with pytest.raises(ValueError):OKX()


def test_env_parser_does_not_execute_or_override(tmp_path,monkeypatch):
    f=tmp_path/'env';f.write_text('OKX_API_KEY="abc"\nOTHER=secret\nOKX_API_SECRET=$(echo unsafe)\n')
    monkeypatch.setenv('OKX_API_KEY','existing');monkeypatch.delenv('OKX_API_SECRET',raising=False)
    load_env(f)
    import os
    assert os.environ['OKX_API_KEY']=='existing'
    assert os.environ['OKX_API_SECRET']=='$(echo unsafe)'


def test_network_failure_is_ambiguous_and_no_retry(monkeypatch):
    x=OKX();calls=[]
    def fail(*a,**k):calls.append(1);raise requests.Timeout('private secret')
    monkeypatch.setattr(x.session,'request',fail)
    with pytest.raises(AmbiguousOrder) as exc:x.request('POST','/api/v5/trade/order',body={})
    assert len(calls)==1 and 'private secret' not in str(exc.value)


def test_order_level_errors_checked(monkeypatch):
    x=OKX()
    response=type('R',(),{'status_code':200,'json':lambda self:{'code':'0','data':[{'sCode':'51000','sMsg':'secret'}]}})()
    monkeypatch.setattr(x.session,'request',lambda *a,**k:response)
    with pytest.raises(ExchangeError,match='51000') as exc:x.request('POST','/order')
    assert 'secret' not in str(exc.value)


def test_journal_persists_and_excludes_second_process(tmp_path):
    path=tmp_path/'state.db';s=Store(path)
    s.save('intent',{'clOrdId':'astabc'});s.save('halted',True)
    with pytest.raises(BlockingIOError):Store(path)
    s.close();s=Store(path)
    assert s.get('intent')['clOrdId']=='astabc' and s.get('halted') is True
    s.close()


def test_uncertain_order_never_resubmitted(tmp_path):
    from astra.service import Service
    s=Store(tmp_path/'x.db');s.save('intent',{'clOrdId':'astabc','kind':'entry','time':'2026-01-01'})
    class Exchange:
        def order(self,cid):raise ExchangeError('not found')
        def place(self,body):pytest.fail('Must not retry uncertain order')
    svc=object.__new__(Service);svc.x=Exchange();svc.s=s
    with pytest.raises(ExchangeError):svc.reconcile_intent()
    assert s.get('intent') is not None
    s.close()
