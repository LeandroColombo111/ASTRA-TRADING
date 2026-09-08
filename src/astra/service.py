"""Restart-safe demo service; one isolated net SWAP position on a dedicated account."""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import fcntl
import json
import logging
import signal
import sqlite3
import threading
import time
import pandas as pd
from .accounting import deposit_adjusted_equity, modified_dietz_return
from .data import validate
from .engine import Risk
from .directional_strategy import Params, features

STRATEGIES = {'v1': (Params, features)}


def strategy_for(name):
    """Select the research family a config declares. Unknown names are refused
    rather than silently falling back to a different strategy."""
    if name in (None, 'v1'):
        return STRATEGIES['v1']
    if name == 'v4_hourly':
        from .v4_hourly import HourlyParams, features as hourly_features
        return HourlyParams, hourly_features
    raise ValueError('Unknown strategy in config: ' + str(name))


def backtest_for(name):
    """The backtest that matches a family. Every consumer of a config must route
    through this; importing one family's engine while serving another silently
    replays a different strategy than the one configured."""
    if name in (None, 'v1'):
        from .engine import backtest
        return backtest
    if name == 'v4_hourly':
        from .v4_hourly import backtest as hourly_backtest
        return hourly_backtest
    raise ValueError('Unknown strategy in config: ' + str(name))
from .okx import OKX, INSTRUMENT, ExchangeError, entry_plan, rounded

log=logging.getLogger('astra')

class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.lock=open(str(path)+'.lock','a')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, time TEXT, kind TEXT, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS candles (time TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def get(self,key,default=None):
        row=self.db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def save(self,key,value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',(key,json.dumps(value,allow_nan=False)))

    def event(self,kind,payload):
        with self.db:
            self.db.execute('INSERT INTO events(time,kind,payload) VALUES (?,?,?)',(str(pd.Timestamp.now(tz='UTC')),kind,json.dumps(payload,allow_nan=False)))

    def add_candles(self,frame):
        with self.db:
            self.db.executemany('INSERT OR IGNORE INTO candles VALUES (?,?)',[(str(t),json.dumps(row)) for t,row in frame.to_dict('index').items()])

    def candles(self):
        rows=self.db.execute('SELECT time,payload FROM candles ORDER BY time').fetchall()
        return pd.DataFrame([json.loads(v) for _,v in rows],index=pd.to_datetime([t for t,_ in rows],utc=True))

    def close(self):
        self.db.close();fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close()


class Service:
    def __init__(self,client,store,p,risk,mode='observe',features_fn=None):
        self.features=features_fn or features
        if mode not in ('observe','demo'):
            raise ValueError('Service supports observe or demo; live is not approved')
        if mode=='demo' and not client.demo:
            raise ValueError('Demo service requires simulated OKX endpoint')
        self.x,self.s,self.p,self.r,self.mode=client,store,p,risk,mode
        fingerprint=sha256(json.dumps({'params':asdict(p),'risk':asdict(risk),'mode':mode,'host':client.base},sort_keys=True).encode()).hexdigest()
        if store.get('fingerprint',fingerprint)!=fingerprint:
            raise ValueError('State belongs to different config/mode; use separate state file')
        store.save('fingerprint',fingerprint)
        self.meta=client.instrument()
        if mode=='demo':
            config=client.config()
            if config.get('posMode')!='net_mode' or config.get('acctLv')!='2':
                raise ExchangeError('Use Futures account mode with net positions on a dedicated demo account')
            # Read leverage; do not silently alter account settings.
            leverage=client.request('GET','/api/v5/account/leverage-info',{'instId':INSTRUMENT,'mgnMode':'isolated'},private=True)
            if not leverage or any(float(x['lever'])>2 for x in leverage):
                raise ExchangeError('Configure isolated leverage at 1x or 2x before running')

    def market(self):
        self.s.add_candles(self.x.candles())
        b=self.s.candles()
        # Warmup must cover the slowest anchor EMA and the breakout lookback.
        minimum=max(1200,self.p.slow*4+400,getattr(self.p,'breakout',0)+400)
        while len(b)<minimum:
            older=self.x.candles(int(b.index[0].timestamp()*1000))
            self.s.add_candles(older)
            updated=self.s.candles()
            if len(updated)<=len(b):
                raise ExchangeError('Insufficient historical warmup')
            b=updated
            time.sleep(.15)
        # Backfill downtime without executing stale signals.
        try:
            b['funding']=0.;validate(b)
        except ValueError:
            raise ExchangeError('Gap in OKX candle cache; halt and repair data before entries') from None
        return b,self.features(b,self.p)

    def reconcile_intent(self):
        intent=self.s.get('intent')
        if not intent:
            return
        # An uncertain POST is never blindly resubmitted. Not found also blocks.
        order=self.x.order(intent['clOrdId'])
        status=order['state']
        if status in ('live','partially_filled'):
            self.s.save('halted',True)
            raise ExchangeError('Order incomplete: manual reconciliation required; no new entries')
        if status not in ('filled','canceled','mmp_canceled'):
            raise ExchangeError('Unknown order state')
        self.s.event('order_reconciled',{'client_id':intent['clOrdId'],'state':status,'filled_contracts':order.get('accFillSz'),'avg_price':order.get('avgPx'),'fee':order.get('fee'),'fee_currency':order.get('feeCcy')})
        if intent['kind']=='entry' and float(order.get('accFillSz') or 0)>0:
            self.s.save('position',{'client_id':intent['clOrdId'],'opened':intent['time'],'stop':intent['stop'],'target':intent['target'],'entry':float(order['avgPx']),'initial_distance':abs(float(order['avgPx'])-float(intent['stop'])),'peak_favorable_r':0.})
        self.s.save('intent',None)

    def submit(self,body,kind,when):
        intent={'clOrdId':body['clOrdId'],'kind':kind,'time':str(when)}
        if kind=='entry':
            intent.update(stop=body['attachAlgoOrds'][0]['slTriggerPx'],target=body['attachAlgoOrds'][0]['tpTriggerPx'])
        self.s.save('intent',intent) # fsync/commit BEFORE network write.
        self.s.event('order_intent',body)
        self.x.place(body)
        self.reconcile_intent()

    def close_position(self,pos,reason,when):
        cid='ast'+sha256((str(when)+reason+pos['posId']).encode()).hexdigest()[:24]
        self.submit({'instId':INSTRUMENT,'tdMode':'isolated','posSide':'net','side':'sell' if float(pos['pos'])>0 else 'buy','ordType':'market','sz':str(abs(float(pos['pos']))),'reduceOnly':True,'clOrdId':cid},'exit',when)
        self.s.event('exit_reason',{'reason':reason})
        # Keep exchange protection in place until position is confirmed flat.

    def tick(self):
        if self.mode=='demo':
            self.reconcile_intent()
        bars,f=self.market()
        now=pd.Timestamp.now(tz='UTC');closed=bars.index[-1]+pd.Timedelta(hours=1)
        last=self.s.get('last_closed')
        new=last is not None and pd.Timestamp(last)<closed
        recent=pd.Timedelta(0)<=now-closed<=pd.Timedelta(minutes=2)
        cur=f.iloc[-1]
        if self.mode=='observe':
            if new:
                self.s.event('signal',{'time':str(closed),'side':int(cur.signal),'atr':float(cur.atr),'anchor':int(cur.anchor)})
                log.info('Completed candle %s: signal=%s anchor=%s',closed,int(cur.signal),int(cur.anchor))
            self.s.save('last_closed',str(closed));self.s.save('heartbeat',str(now));return
        # Consume the candle before any external write; a crash cannot re-enter it.
        self.s.save('last_closed',str(closed))
        positions=self.x.positions()
        if any(x['instId']!=INSTRUMENT or x.get('posSide')!='net' or x.get('mgnMode')!='isolated' for x in positions) or len(positions)>1:
            raise ExchangeError('Unexpected position; dedicated account reconciliation required')
        equity=self.x.equity()
        inception_ms=self.s.get('inception_ms')
        if inception_ms is None:
            inception_ms=int(now.timestamp()*1000)
            self.s.save('inception_ms',inception_ms)
            self.s.save('inception_equity',equity)
        bills=self.x.bills(inception_ms)
        adjusted=deposit_adjusted_equity(equity,bills)
        peak=max(self.s.get('peak',adjusted),adjusted);self.s.save('peak',peak)
        halted=self.s.get('halted',False) or adjusted<=peak*(1-self.r.max_drawdown)
        self.s.save('halted',halted)
        owned=self.s.get('position')
        pending=self.x.pending()
        algos=self.x.algos()
        if any(not x.get('clOrdId','').startswith('ast') for x in pending):
            raise ExchangeError('External open order found; do not share account with another bot')
        if positions:
            if not owned:
                raise ExchangeError('Unowned position found: reconcile manually before running')
            pos=positions[0];side=1 if float(pos['pos'])>0 else -1
            protection=[a for a in algos if a['instId']==INSTRUMENT and a.get('algoClOrdId')==owned['client_id']+'s']
            if not protection or any(not a.get('slTriggerPx') for a in protection):
                self.s.save('halted',True)
                self.close_position(pos,'missing_protection',now)
                raise ExchangeError('Missing confirmed protection: close requested, service halted')
            age=(closed-pd.Timestamp(owned['opened'])).total_seconds()/3600
            if halted or (new and (int(cur.anchor)!=side or age>=self.p.max_hours)):
                self.close_position(pos,'drawdown' if halted else 'anchor_or_timeout',closed)
            elif new:
                ticker=self.x.ticker();price=float(ticker['last'])
                if not owned.get('initial_distance') or not owned.get('entry'):
                    raise ExchangeError('Legacy position lacks effective risk basis; reconcile before trailing')
                owned['peak_favorable_r']=max(owned.get('peak_favorable_r',0.),side*(float(bars.close.iloc[-1])-owned['entry'])/owned['initial_distance'])
                self.s.save('position',owned)
                trail=(float(bars.close.iloc[-1])-side*float(cur.atr)*self.p.trail_atr) if owned['peak_favorable_r']>=self.p.trail_start_r else float(owned['stop'])
                stop=max(float(owned['stop']),trail) if side==1 else min(float(owned['stop']),trail)
                if (side==1 and price<=stop) or (side==-1 and price>=stop):
                    self.close_position(pos,'trailing_stop',closed)
                elif stop!=float(owned['stop']):
                    newstop=rounded(stop,self.meta['tickSz'],up=side==1)
                    for a in protection:self.x.amend_stop(a['algoId'],newstop)
                    owned['stop']=newstop;self.s.save('position',owned)
        else:
            if owned:
                # Confirm flat, then cancel only this bot's remaining protection.
                self.x.cancel_algos([a['algoId'] for a in algos if a.get('algoClOrdId')==owned['client_id']+'s'])
                fills=self.x.request('GET','/api/v5/trade/fills',{'instType':'SWAP','instId':INSTRUMENT,'limit':'100'},private=True)
                self.s.event('flat_confirmed',{'client_id':owned['client_id'],'recent_fills':fills})
                self.s.save('position',None)
                # No reentry in same cycle as observed closure.
            elif algos or pending:
                raise ExchangeError('Unreconciled pending orders block entries')
            elif new and recent and not halted and int(cur.signal):
                ticker=self.x.ticker()
                if now-pd.to_datetime(int(ticker['ts']),unit='ms',utc=True)>pd.Timedelta(seconds=30):
                    raise ExchangeError('Stale OKX quote')
                side=int(cur.signal);price=float(ticker['askPx'] if side==1 else ticker['bidPx'])
                if abs(price/float(bars.close.iloc[-1])-1)>.005:
                    self.s.event('skipped_gap',{'time':str(closed)})
                else:
                    cid='ast'+sha256(str(closed).encode()).hexdigest()[:24]
                    plan=entry_plan(self.meta,side,price,float(cur.atr),self.p,self.r,equity,cid)
                    self.submit(plan,'entry',closed)
        self.s.save('last_closed',str(closed));self.s.save('heartbeat',str(now))


def run(selected,state,mode='observe',once=False):
    cfg=json.loads(Path(selected).read_text())
    params_class,features_fn=strategy_for(cfg.get('strategy'))
    p=params_class(**cfg['params']);risk=Risk(**cfg['risk'])
    log.info('Serving strategy %s from %s',cfg.get('strategy','v1'),selected)
    store=Store(state);stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    try:
        svc=Service(OKX(demo=True),store,p,risk,mode,features_fn)
        failures=0
        while not stop.is_set():
            try:
                svc.tick();failures=0
            except Exception as exc:
                failures+=1
                log.error('Service cycle failed (%s); entries blocked for this cycle',type(exc).__name__)
                if once or failures>=3:raise
            if once:break
            stop.wait(10)
    finally:
        store.close()
