import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import sqlite3
import sys
import pandas as pd
from .data import download,load
from .engine import Risk,backtest,metrics
from .directional_strategy import Params
from .okx import OKX,load_env
from .research import dump,require_precheck,status


def main():
    parser=argparse.ArgumentParser(description='ASTRA futures research and OKX demo service')
    parser.add_argument('--env-file',default='.env')
    sub=parser.add_subparsers(dest='command',required=True)
    d=sub.add_parser('download');d.add_argument('--start',default='2023-03-01');d.add_argument('--end',default='2026-09-01');d.add_argument('--directory',default='data/v2');d.add_argument('--symbol',default='BTC-USDT-SWAP')
    r=sub.add_parser('research');r.add_argument('--output',default='reports/v2.1-sleeve1');r.add_argument('--attempts',type=int,default=60)
    b=sub.add_parser('replay');b.add_argument('--data',required=True);b.add_argument('--selected',default='configs/selected.json');b.add_argument('--output',default='reports/replay');b.add_argument('--start');b.add_argument('--end')
    s=sub.add_parser('serve');s.add_argument('--selected',default='configs/selected.json');s.add_argument('--state',default='state/observe.db');s.add_argument('--mode',choices=['observe','demo'],default='observe');s.add_argument('--once',action='store_true')
    sub.add_parser('doctor')
    v2=sub.add_parser('v2-status');v2.add_argument('--output',default='reports/v2.1-sleeve1')
    sub.add_parser('precheck')
    dg=sub.add_parser('diagnostics');dg.add_argument('--repetitions',type=int,default=400)
    h=sub.add_parser('health');h.add_argument('--state',default='state/observe.db')
    v=sub.add_parser('review');v.add_argument('--trades',default='reports/run-001/holdout_trades.csv')
    pf=sub.add_parser('performance');pf.add_argument('--selected',default='configs/selected.json');pf.add_argument('--state',default='state/observe.db')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    load_env(args.env_file)
    try:
        if args.command=='download':print(download(args.start,args.end,args.directory,args.symbol))
        elif args.command=='research':
            require_precheck(args.output,args.attempts)
            raise RuntimeError('Portfolio research is a later conditional stage; no optimizer started')
        elif args.command=='v2-status':
            print(json.dumps(status(args.output),indent=2))
        elif args.command=='precheck':
            from .v21_precheck import run_precheck
            print(json.dumps(run_precheck(),indent=2))
        elif args.command=='diagnostics':
            # Read-only over saved artifacts. Uses no optimization attempt and
            # changes no gate; it cannot revive or alter an archived run.
            from .v21_diagnostics import run_all
            report=run_all(args.repetitions)
            print(json.dumps({k:report[k]['verdict'] for k in ('d1_control_audit','d2_weighting_decomposition') },indent=2))
        elif args.command=='replay':
            from .service import strategy_for,backtest_for
            cfg=json.loads(Path(args.selected).read_text());risk=Risk(**cfg['risk'])
            params_class,_=strategy_for(cfg.get('strategy'))
            replay_backtest=backtest_for(cfg.get('strategy'))
            e,t,_=replay_backtest(load(args.data),params_class(**cfg['params']),risk,args.start,args.end)
            out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
            dump(out/'metrics.json',metrics(e,t,risk.capital));e.to_csv(out/'equity.csv',index_label='time');pd.DataFrame(t).to_csv(out/'trades.csv',index=False)
            print('Replay saved using corrected trailing activation; not a reproduction of pre-v2 fills or independent validation.')
        elif args.command=='serve':
            from .service import run
            run(args.selected,args.state,args.mode,args.once)
        elif args.command=='doctor':
            x=OKX(demo=True);meta=x.instrument();cfg=x.config();positions=x.positions()
            checks={'demo_authentication':'ok','instrument':meta['instId'],'contract_value_btc':meta['ctVal'],'lot_contracts':meta['lotSz'],'position_mode':cfg['posMode'],'account_level':cfg['acctLv'],'open_swap_positions':len(positions),'ready_account_mode':cfg['acctLv']=='2' and cfg['posMode']=='net_mode','orders_sent':0,'live_enabled':False}
            print(json.dumps(checks,indent=2))
            if not checks['ready_account_mode']:print('Set dedicated OKX DEMO account to Futures mode, net position mode, isolated leverage 1x or 2x. No setting was changed.')
        elif args.command=='health':
            with sqlite3.connect(f'file:{Path(args.state).resolve()}?mode=ro',uri=True) as db:
                row=db.execute("SELECT value FROM kv WHERE key='heartbeat'").fetchone()
            if not row or pd.Timestamp.now(tz='UTC')-pd.Timestamp(json.loads(row[0]))>pd.Timedelta(minutes=3):
                raise RuntimeError('Stale or missing heartbeat')
            print('healthy')
        elif args.command=='performance':
            from .accounting import deposit_adjusted_equity, modified_dietz_return
            cfg=json.loads(Path(args.selected).read_text());risk=Risk(**cfg['risk'])
            with sqlite3.connect(f'file:{Path(args.state).resolve()}?mode=ro',uri=True) as db:
                kv=dict(db.execute('SELECT key,value FROM kv').fetchall())
            inception_ms=json.loads(kv['inception_ms']) if 'inception_ms' in kv else None
            inception_equity=json.loads(kv['inception_equity']) if 'inception_equity' in kv else None
            peak=json.loads(kv['peak']) if 'peak' in kv else None
            halted=json.loads(kv['halted']) if 'halted' in kv else False
            if inception_ms is None or peak is None:
                print(json.dumps({'note':'No performance data yet; service has not completed a demo tick.'},indent=2));return
            x=OKX(demo=True);equity=x.equity();bills=x.bills(inception_ms)
            from .accounting import net_transfers
            transfers=net_transfers(bills)
            adjusted=deposit_adjusted_equity(equity,bills)
            drawdown_pct=max(0.,(peak-adjusted)/peak*100) if peak>0 else 0.
            now_ms=int(pd.Timestamp.now(tz='UTC').timestamp()*1000)
            period_days=(now_ms-inception_ms)/86400000
            try:
                twr_pct=modified_dietz_return(inception_equity,equity,bills,inception_ms,now_ms)*100
            except ValueError:
                twr_pct=None
            print(json.dumps({
                'equity':equity,'adjusted_equity':adjusted,'peak':peak,
                'drawdown_pct':drawdown_pct,'max_drawdown_pct':risk.max_drawdown*100,
                'distance_to_halt_pct':max(0.,risk.max_drawdown*100-drawdown_pct),
                'halted':halted,'net_transfers':transfers,
                'inception_equity':inception_equity,'period_days':period_days,
                'time_weighted_return_pct':twr_pct,
                'note':'time_weighted_return_pct is a Modified Dietz approximation, not a true daily-linked TWR; paper PnL only, not a validation of the strategy.'
            },indent=2))
        elif args.command=='review':
            t=pd.read_csv(args.trades)
            if t.empty:print('No completed trades.');return
            pnl=t.net_pnl
            print(json.dumps({'trades':len(t),'net_pnl':float(pnl.sum()),'last_20_mean_pnl':float(pnl.tail(20).mean()),'last_20_win_rate':float((pnl.tail(20)>0).mean()),'note':'Monitoring only. Parameters do not retune after each trade; any new search requires fresh independent validation.'},indent=2))
    except Exception as exc:
        # Do not emit arbitrary exception payloads (may include third party secrets).
        if isinstance(exc,(ValueError,RuntimeError)):
            print(f'{type(exc).__name__}: {exc}',file=sys.stderr)
        else:print(f'{type(exc).__name__}: operation failed',file=sys.stderr)
        raise SystemExit(1) from None

if __name__=='__main__':main()
