"""Consultor de setups: datos de mercado en tiempo real + validación R/R.

Módulo independiente del bot (src/astra). Solo lee APIs públicas, nunca opera.

Subcomandos:
  analyze TICKER   Snapshot completo (1d/4h/1h, indicadores, niveles, noticias, macro).
  scan             Resumen de la watchlist con setups mecánicos candidatos.
  rr               Valida un setup (lados, R/R, distancia del SL vs ATR).
  log              Registra un setup en advisor/journal.csv.

Uso: .venv/bin/python advisor/advisor.py analyze SOL
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
WATCHLIST = ROOT / "watchlist.json"
JOURNAL = ROOT / "journal.csv"
SNAPSHOTS = ROOT / "snapshots"

MIN_RR = 2.0
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36"}
TIMEOUT = 15

MACRO = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "^VIX": "VIX", "DX-Y.NYB": "DXY", "^TNX": "US10Y"}


# ---------------------------------------------------------------- datos


def _binance(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    r = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(rows).iloc[:, :6]
    df.columns = ["ts", "open", "high", "low", "close", "volume"]
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts").astype(float)


def _okx(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    bar = {"1d": "1Dutc", "4h": "4H", "1h": "1H"}[interval]
    inst = symbol.replace("USDT", "-USDT")
    r = requests.get(
        "https://www.okx.com/api/v5/market/candles",
        params={"instId": inst, "bar": bar, "limit": min(limit, 300)},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    rows = r.json().get("data") or []
    if not rows:
        raise ValueError(f"OKX sin datos para {inst}")
    df = pd.DataFrame([x[:6] for x in rows], columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
    return df.set_index("ts").astype(float).sort_index()


def _crypto(symbol: str, interval: str, limit: int) -> tuple[pd.DataFrame, str]:
    try:
        return _binance(symbol, interval, limit), "binance"
    except Exception:
        return _okx(symbol, interval, limit), "okx"


def _yahoo(ticker: str, interval: str, rng: str) -> tuple[pd.DataFrame, dict]:
    r = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quote_plus(ticker)}",
        params={"interval": interval, "range": rng, "includePrePost": "false"},
        headers=UA,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    res = r.json()["chart"]["result"]
    if not res:
        raise ValueError(f"Yahoo sin datos para {ticker}")
    res = res[0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {k: q[k] for k in ("open", "high", "low", "close", "volume")},
        index=pd.to_datetime(res["timestamp"], unit="s", utc=True),
    ).dropna(subset=["close"])
    df.index.name = "ts"
    return df.astype(float), res["meta"]


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return df.resample(rule, origin="start_day").agg(agg).dropna(subset=["close"])


def fetch(ticker: str, kind: str) -> dict:
    """Devuelve velas 1d/4h/1h, precio actual y metadatos para un activo."""
    if kind == "crypto":
        sym = ticker.upper().replace("/", "").replace("-", "")
        if not sym.endswith("USDT"):
            sym += "USDT"
        d1, src = _crypto(sym, "1d", 500)
        h4, _ = _crypto(sym, "4h", 500)
        h1, _ = _crypto(sym, "1h", 500)
        price = float(h1["close"].iloc[-1])
        return {"symbol": sym, "source": src, "1d": d1, "4h": h4, "1h": h1, "price": price,
                "market_state": "24/7"}
    d1, meta = _yahoo(ticker, "1d", "2y")
    h1, _ = _yahoo(ticker, "60m", "180d")
    h4 = _resample(h1, "4h")
    price = float(meta.get("regularMarketPrice") or h1["close"].iloc[-1])
    last = datetime.fromtimestamp(meta.get("regularMarketTime", 0), tz=timezone.utc)
    stale = datetime.now(timezone.utc) - last > timedelta(minutes=30)
    return {"symbol": ticker.upper(), "source": "yahoo", "1d": d1, "4h": h4, "1h": h1, "price": price,
            "market_state": "cerrado (último precio: " + last.isoformat(timespec="minutes") + ")" if stale else "abierto"}


def resolve_kind(ticker: str, wl: dict) -> str:
    t = ticker.upper()
    if t in (x.upper() for x in wl.get("crypto", [])):
        return "crypto"
    if t in (x.upper() for x in wl.get("stocks", [])):
        return "stock"
    if t.endswith("USDT"):
        return "crypto"
    try:
        _binance(t + "USDT", "1d", 1)
        return "crypto"
    except Exception:
        return "stock"


# ---------------------------------------------------------------- indicadores


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    out = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    return out.where(dn > 0, 100.0)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def swings(df: pd.DataFrame, k: int = 3) -> tuple[list[float], list[float]]:
    """Fractales: máximos/mínimos con k velas más bajas/altas a cada lado."""
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    highs, lows = [], []
    for i in range(k, len(df) - k):
        if h[i] == h[i - k:i + k + 1].max():
            highs.append(float(h[i]))
        if l[i] == l[i - k:i + k + 1].min():
            lows.append(float(l[i]))
    return highs, lows


def volume_profile(df: pd.DataFrame, bins: int = 40) -> dict:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    hist, edges = np.histogram(tp, bins=bins, weights=df["volume"])
    mids = (edges[:-1] + edges[1:]) / 2
    order = np.argsort(hist)[::-1]
    total, acc, area = hist.sum(), 0.0, []
    for i in order:
        acc += hist[i]
        area.append(i)
        if acc >= 0.7 * total:
            break
    return {"poc": float(mids[order[0]]), "vah": float(edges[max(area) + 1]), "val": float(edges[min(area)])}


def cluster(levels: list[float], tol: float) -> list[float]:
    out: list[list[float]] = []
    for x in sorted(levels):
        if out and x - out[-1][-1] <= tol:
            out[-1].append(x)
        else:
            out.append([x])
    return [float(np.mean(c)) for c in out]


def trend(df: pd.DataFrame) -> str:
    c = df["close"]
    e50, e200 = ema(c, 50), ema(c, 200)
    slope = e50.iloc[-1] - e50.iloc[-6]
    if c.iloc[-1] > e50.iloc[-1] > e200.iloc[-1] and slope > 0:
        return "alcista"
    if c.iloc[-1] < e50.iloc[-1] < e200.iloc[-1] and slope < 0:
        return "bajista"
    return "rango"


def tf_summary(df: pd.DataFrame, price: float) -> dict:
    c = df["close"]
    a = atr(df)
    out = {
        "trend": trend(df),
        "ema": {n: round(float(ema(c, n).iloc[-1]), 6) for n in (20, 50, 100, 200)},
        "rsi14": round(float(rsi(c).iloc[-1]), 1),
        "atr14": round(float(a.iloc[-1]), 6),
        "atr_pct": round(float(a.iloc[-1] / price * 100), 2),
        "atr_percentile_100": round(float((a.tail(100) < a.iloc[-1]).mean() * 100), 0),
        "last_bar": df.index[-1].isoformat(),
    }
    win = df.tail(60)
    hi, lo = float(win["high"].max()), float(win["low"].min())
    out["range_60"] = {"high": hi, "low": lo, "position_pct": round((price - lo) / (hi - lo) * 100, 1) if hi > lo else 50.0}
    return out


def levels(frames: dict, price: float) -> dict:
    tol = 0.5 * float(atr(frames["4h"]).iloc[-1])
    hs, ls = [], []
    for tf, k in (("1d", 3), ("4h", 3)):
        h, l = swings(frames[tf].tail(250), k)
        hs += h
        ls += l
    allv = cluster(hs + ls, tol)
    d1 = frames["1d"]
    return {
        "resistances": [round(x, 6) for x in allv if x > price][:5],
        "supports": [round(x, 6) for x in allv if x < price][::-1][:5],
        "volume_profile_4h_120": {k: round(v, 6) for k, v in volume_profile(frames["4h"].tail(120)).items()},
        "prev_day": {"high": float(d1["high"].iloc[-2]), "low": float(d1["low"].iloc[-2])},
        "high_52w": float(d1["high"].tail(365).max()),
        "low_52w": float(d1["low"].tail(365).min()),
    }


# ---------------------------------------------------------------- R/R


def rr_check(side: str, entry: float, sl: float, tp1: float, tp2: float | None = None,
             atr4h: float | None = None, split: float = 0.5) -> dict:
    side = side.lower()
    sign = 1 if side == "long" else -1
    errors = []
    risk = (entry - sl) * sign
    if risk <= 0:
        errors.append("SL del lado equivocado de la entrada")
    for name, tp in (("tp1", tp1), ("tp2", tp2)):
        if tp is not None and (tp - entry) * sign <= 0:
            errors.append(f"{name.upper()} del lado equivocado de la entrada")
    if errors:
        return {"valid": False, "errors": errors}
    rr1 = (tp1 - entry) * sign / risk
    rr2 = (tp2 - entry) * sign / risk if tp2 is not None else None
    blended = rr1 * split + rr2 * (1 - split) if rr2 is not None else rr1
    out = {
        "valid": True,
        "risk_pct": round(risk / entry * 100, 2),
        "rr_tp1": round(rr1, 2),
        "rr_tp2": round(rr2, 2) if rr2 is not None else None,
        "rr_blended": round(blended, 2),
        "blended_split": f"{int(split * 100)}% en TP1 / {int((1 - split) * 100)}% en TP2",
        "approved": blended >= MIN_RR,
        "rule": f"R/R ponderado >= 1:{MIN_RR:g}",
        "warnings": [],
    }
    if atr4h:
        out["sl_distance_atr4h"] = round(risk / atr4h, 2)
        if risk < atr4h:
            out["warnings"].append("SL a menos de 1 ATR(4h): riesgo alto de barrido por mecha")
    return out


def build_setup(side: str, lv: dict, price: float, tfs: dict) -> dict | None:
    a = tfs["4h"]["atr14"]
    sign = 1 if side == "long" else -1
    stops = lv["supports"] if side == "long" else lv["resistances"]
    targets = lv["resistances"] if side == "long" else lv["supports"]
    stop_lvl = next((s for s in stops if abs(price - s) >= 0.5 * a), None)
    if stop_lvl is None:
        return None
    sl = stop_lvl - sign * 0.5 * a
    # TP1 = primer obstáculo real (no se saltea niveles cercanos: eso inflaría el R/R).
    tps = [t for t in targets if abs(t - price) >= 0.25 * a]
    tp1 = tps[0] - sign * 0.1 * a if tps else price + sign * 3 * tfs["1d"]["atr14"]
    tp2 = tps[1] - sign * 0.1 * a if len(tps) > 1 else tp1 + sign * 2 * tfs["1d"]["atr14"]
    chk = rr_check(side, price, sl, tp1, tp2, a)
    return {"side": side, "entry": round(price, 6), "sl": round(sl, 6), "tp1": round(tp1, 6),
            "tp2": round(tp2, 6), "no_level_beyond": not tps, **{k: chk.get(k) for k in
            ("rr_tp1", "rr_tp2", "rr_blended", "approved", "risk_pct", "sl_distance_atr4h", "warnings")}}


def mechanical_setups(lv: dict, price: float, tfs: dict) -> list[dict]:
    """Candidatos mecánicos en ambas direcciones, para rankear la watchlist. Claude los revisa.

    - a favor de tendencia: la tendencia 1d manda y el 4h no la contradice.
    - rango: solo en los extremos del rango de 60 velas de 4h.
    - contra-tendencia: solo en el extremo opuesto del rango (ej. short contra resistencia
      en tendencia alcista). Siempre riesgo Alto.
    """
    t_d, t_4 = tfs["1d"]["trend"], tfs["4h"]["trend"]
    pos = tfs["4h"]["range_60"]["position_pct"]
    ctx = {}
    for side, trend_dir, other, edge in (("long", "alcista", "bajista", pos < 20), ("short", "bajista", "alcista", pos > 80)):
        if t_d == trend_dir and t_4 != other:
            ctx[side] = ("a_favor_de_tendencia", "Medio")
        elif t_d == "rango" and edge:
            ctx[side] = ("rango_extremo", "Medio")
        elif t_d == other and edge:
            ctx[side] = ("contra_tendencia", "Alto")
    out = []
    for side, (context, risk) in ctx.items():
        s = build_setup(side, lv, price, tfs)
        if s:
            out.append({"context": context, "risk_level": risk, **s})
    out.sort(key=lambda s: (s["approved"], s["context"] != "contra_tendencia", s["rr_blended"]), reverse=True)
    return out


# ---------------------------------------------------------------- noticias y macro


def news(query: str, hours: int = 4, limit: int = 12) -> dict:
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}+when:1d&hl=en-US&gl=US&ceid=US:en"
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        items = ET.fromstring(r.content).findall(".//item")
    except Exception as e:
        return {"query": query, "error": str(e), "items": []}
    now = datetime.now(timezone.utc)
    rows = []
    for it in items:
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            continue
        src = it.find("source")
        rows.append({"age_h": round((now - ts).total_seconds() / 3600, 1), "title": it.findtext("title"),
                     "source": src.text if src is not None else None})
    rows.sort(key=lambda x: x["age_h"])
    recent = [x for x in rows if x["age_h"] <= hours]
    return {"query": query, "window_h": hours, "count_in_window": len(recent),
            "items": (recent or rows)[:limit], "fallback_24h": not recent}


def macro() -> dict:
    out = {}

    def one(t):
        try:
            df, _ = _yahoo(t, "1d", "1mo")
            c = df["close"]
            return t, {"name": MACRO[t], "last": round(float(c.iloc[-1]), 2),
                       "chg_1d_pct": round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                       "chg_5d_pct": round(float(c.iloc[-1] / c.iloc[-6] - 1) * 100, 2)}
        except Exception as e:
            return t, {"error": str(e)}

    with ThreadPoolExecutor(5) as ex:
        out.update(dict(ex.map(one, MACRO)))
    try:
        d, _ = _crypto("BTCUSDT", "1d", 7)
        c = d["close"]
        out["BTC"] = {"name": "Bitcoin", "last": round(float(c.iloc[-1]), 2),
                      "chg_1d_pct": round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                      "chg_5d_pct": round(float(c.iloc[-1] / c.iloc[-6] - 1) * 100, 2)}
    except Exception as e:
        out["BTC"] = {"error": str(e)}
    return out


# ---------------------------------------------------------------- comandos


def load_watchlist() -> dict:
    return json.loads(WATCHLIST.read_text())


def news_query(ticker: str, kind: str) -> str:
    name = load_watchlist().get("names", {}).get(ticker.upper())
    if kind == "crypto":
        return f"{name or ticker} crypto"
    return f"{name} stock" if name else f"{ticker} stock"


def analyze_one(ticker: str, kind: str, with_news: bool = True, hours: int = 4) -> dict:
    f = fetch(ticker, kind)
    price = f["price"]
    tfs = {tf: tf_summary(f[tf], price) for tf in ("1d", "4h", "1h")}
    lv = levels(f, price)
    out = {
        "ticker": ticker.upper(), "kind": kind, "symbol": f["symbol"], "source": f["source"],
        "price": price, "market_state": f["market_state"], "timeframes": tfs, "levels": lv,
        "mechanical_setups": mechanical_setups(lv, price, tfs),
    }
    if with_news:
        out["news"] = news(news_query(ticker, kind), hours)
    return out


def cmd_analyze(a) -> dict:
    wl = load_watchlist()
    kind = a.kind or resolve_kind(a.ticker, wl)
    with ThreadPoolExecutor(3) as ex:
        fa = ex.submit(analyze_one, a.ticker, kind, True, a.hours)
        fm = ex.submit(macro)
        fn = ex.submit(news, "Federal Reserve OR inflation OR stock market OR crypto market", a.hours, 10)
        out = fa.result()
        out["macro"] = fm.result()
        out["macro_news"] = fn.result()
    return out


def cmd_scan(a) -> dict:
    wl = load_watchlist()
    assets = [(t, "crypto") for t in wl.get("crypto", [])] + [(t, "stock") for t in wl.get("stocks", [])]
    exclude = {x.upper() for x in (a.exclude or [])}
    assets = [x for x in assets if x[0].upper() not in exclude]

    def one(x):
        t, k = x
        try:
            r = analyze_one(t, k, with_news=False)
            s = next(iter(r["mechanical_setups"]), None)
            return {"ticker": t, "kind": k, "price": r["price"], "trend_1d": r["timeframes"]["1d"]["trend"],
                    "trend_4h": r["timeframes"]["4h"]["trend"], "rsi_4h": r["timeframes"]["4h"]["rsi14"],
                    "atr_pct_4h": r["timeframes"]["4h"]["atr_pct"],
                    "range_pos_4h": r["timeframes"]["4h"]["range_60"]["position_pct"], "setup": s}
        except Exception as e:
            return {"ticker": t, "kind": k, "error": str(e)}

    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(one, assets))
    ok = [r for r in rows if r.get("setup") and r["setup"].get("approved")]
    ok.sort(key=lambda r: r["setup"]["rr_blended"], reverse=True)
    return {"min_rr": MIN_RR, "scanned": len(rows), "approved_count": len(ok),
            "top": ok[: a.top], "errors": [r for r in rows if "error" in r],
            "all": rows if a.all else None}


def cmd_rr(a) -> dict:
    return rr_check(a.side, a.entry, a.sl, a.tp1, a.tp2, a.atr, a.split)


def cmd_log(a) -> dict:
    chk = rr_check(a.side, a.entry, a.sl, a.tp1, a.tp2)
    new = not JOURNAL.exists()
    row = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ticker": a.ticker.upper(),
           "side": a.side, "entry": a.entry, "sl": a.sl, "tp1": a.tp1, "tp2": a.tp2 or "",
           "rr_blended": chk.get("rr_blended", ""), "verdict": a.verdict, "note": a.note or "",
           "outcome": "", "exit_price": "", "closed_at": ""}
    with JOURNAL.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    return {"logged": row, "file": str(JOURNAL)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("analyze")
    s.add_argument("ticker")
    s.add_argument("--kind", choices=["crypto", "stock"])
    s.add_argument("--hours", type=int, default=4, help="ventana de noticias")
    s.add_argument("--save", action="store_true", help="guarda el JSON en advisor/snapshots/")

    s = sub.add_parser("scan")
    s.add_argument("--top", type=int, default=5)
    s.add_argument("--exclude", nargs="*")
    s.add_argument("--all", action="store_true", help="incluye todos los activos, no solo aprobados")
    s.add_argument("--save", action="store_true")

    s = sub.add_parser("rr")
    for x in ("side",):
        s.add_argument(f"--{x}", required=True, choices=["long", "short"])
    for x in ("entry", "sl", "tp1"):
        s.add_argument(f"--{x}", type=float, required=True)
    s.add_argument("--tp2", type=float)
    s.add_argument("--atr", type=float, help="ATR(4h) para chequear barridos")
    s.add_argument("--split", type=float, default=0.5, help="fracción que sale en TP1")

    s = sub.add_parser("log")
    s.add_argument("ticker")
    s.add_argument("--side", required=True, choices=["long", "short"])
    for x in ("entry", "sl", "tp1"):
        s.add_argument(f"--{x}", type=float, required=True)
    s.add_argument("--tp2", type=float)
    s.add_argument("--verdict", required=True, choices=["aprobado", "rechazado", "alternativa"])
    s.add_argument("--note")

    a = p.parse_args(argv)
    out = {"analyze": cmd_analyze, "scan": cmd_scan, "rr": cmd_rr, "log": cmd_log}[a.cmd](a)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **out}
    text = json.dumps(out, indent=2, ensure_ascii=False, default=str)
    if getattr(a, "save", False):
        SNAPSHOTS.mkdir(exist_ok=True)
        name = f"{a.cmd}-{getattr(a, 'ticker', 'watchlist')}-{datetime.now():%Y%m%d-%H%M%S}.json"
        (SNAPSHOTS / name).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
