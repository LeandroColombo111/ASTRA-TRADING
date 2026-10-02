"""Tercera prueba en vivo (docs/FORWARD_TEST_HIGHER_RISK.md): la MISMA estrategia v4_hourly congelada, con mas riesgo por operacion (3 % en vez de
2 %) y freno de caida del 40 % en vez de 25 %. Replay del motor de backtest sobre archivos de Binance USD-M (BTCUSDT), igual que la segunda prueba
(src/astra/forward_smart_money.py, de donde reusa la descarga con checksum, la deteccion de huecos y el funding).

Cada corrida tambien calcula un CONTROL: la configuracion actual (2 %, freno 25 %) sobre exactamente los mismos datos, para comparar sin depender
del mercado. El resultado se REESCRIBE en <out-dir>/state.json; no se commitea nada.
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from .backtest2.research import WARMUP, build_sim, max_dd, sharpe_from_equity
from .engine import Risk
from .forward_smart_money import Archive, HOUR, _write_atomic, load_bars, load_funding
from .v4_hourly import HourlyParams, features

PRE_REG_START = pd.Timestamp('2026-10-02 06:00', tz='UTC')
RISK_FRACTION = 0.03
MAX_DRAWDOWN = 0.40


def _replay(sim, bars, params, risk, start, end):
    if end <= start:
        return pd.Series([risk.capital], index=[start]), [], {'qty': 0.}
    return sim.run(bars, features(bars, params), params, risk, start=start, end=end)


def _summary(eq, trades, state, risk):
    return {
        'equity_now': float(eq.iloc[-1]),
        'return_pct': float(eq.iloc[-1] / risk.capital - 1) * 100,
        'sharpe': sharpe_from_equity(eq, risk.capital) if len(eq) > 1 else 0.,
        'max_drawdown_pct': max_dd(eq, risk.capital) * 100,
        'trades': len(trades),
        'open_position': bool(state.get('qty', 0.)),
    }


def run(out_dir, pre_reg_start=PRE_REG_START, config='configs/selected.json', archive=None, now=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    archive = archive or Archive(out / 'cache')
    now = now or pd.Timestamp.now(tz='UTC')
    today = now.date()
    cfg = json.loads(Path(config).read_text())
    params = HourlyParams(**cfg['params'])
    control_risk = Risk(**cfg['risk'])
    risk = Risk(**{**cfg['risk'], 'fraction': RISK_FRACTION, 'max_drawdown': MAX_DRAWDOWN})
    sim_main, sim_control = build_sim(risk), build_sim(control_risk)

    yesterday = today - timedelta(days=1)
    bars = load_bars(archive, (pre_reg_start - WARMUP).date(), yesterday, today)
    bars['funding'] = load_funding(archive, bars, today)
    start = max(bars.index[0] + WARMUP, pre_reg_start)
    end = bars.index[-1] + HOUR

    eq, trades, state = _replay(sim_main, bars, params, risk, start, end)
    ceq, ctrades, cstate = _replay(sim_control, bars, params, control_risk, start, end)
    daily = eq.resample('1D').last().dropna()
    result = {
        'generated_at_utc': now.isoformat(),
        'pre_registration_start': str(pre_reg_start),
        'risk_fraction': risk.fraction,
        'max_drawdown_limit': risk.max_drawdown,
        'data_through': str(bars.index[-1] + HOUR),
        'forward_days': round(max((end - pre_reg_start) / pd.Timedelta(days=1), 0.), 2),
        **_summary(eq, trades, state, risk),
        'control_2pct_dd25': _summary(ceq, ctrades, cstate, control_risk),
        'trade_list': trades,
        'equity_daily': {str(k.date()): round(float(v), 2) for k, v in daily.items()},
    }
    _write_atomic(out / 'state.json', json.dumps(result, indent=2, default=str))
    log = out / 'log.csv'
    if not log.exists():
        log.write_text('generated_at_utc,data_through,forward_days,equity_now,return_pct,sharpe,max_drawdown_pct,trades,control_equity_now,control_trades\n')
    with open(log, 'a') as f:
        f.write(f"{result['generated_at_utc']},{result['data_through']},{result['forward_days']},{result['equity_now']:.2f},"
                f"{result['return_pct']:.3f},{result['sharpe']:.3f},{result['max_drawdown_pct']:.3f},{result['trades']},"
                f"{result['control_2pct_dd25']['equity_now']:.2f},{result['control_2pct_dd25']['trades']}\n")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out-dir', required=True, help='where state.json, log.csv and the download cache live (never committed)')
    ap.add_argument('--config', default='configs/selected.json')
    ap.add_argument('--pre-reg-start', default=None, help='TESTING ONLY; the VM wrapper never passes it (the frozen value is in the code)')
    args = ap.parse_args(argv)
    start = pd.Timestamp(args.pre_reg_start, tz='UTC') if args.pre_reg_start else PRE_REG_START
    result = run(args.out_dir, pre_reg_start=start, config=args.config)
    print(json.dumps({k: v for k, v in result.items() if k not in ('trade_list', 'equity_daily')}, indent=2, default=str))


if __name__ == '__main__':
    main()
