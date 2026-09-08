"""Verified public USD-M futures archives. Never silently fill missing candles."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import time
import requests
import numpy as np
import pandas as pd

BASE = "https://data.binance.vision/data/futures/um/monthly"

def get(url):
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=40)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)

def archive(kind, month, cache, symbol="BTCUSDT"):
    stem = f"{symbol}-1h-{month}" if kind == "klines" else f"{symbol}-fundingRate-{month}"
    url = f"{BASE}/{kind}/{symbol}/" + ("1h/" if kind == "klines" else "") + stem + ".zip"
    path = cache / (stem + ".zip")
    check = cache / (stem + ".zip.CHECKSUM")
    if not check.exists():
        check.write_bytes(get(url + ".CHECKSUM"))
    expected = check.read_text().split()[0]
    if not path.exists() or sha256(path.read_bytes()).hexdigest() != expected:
        payload = get(url)
        if sha256(payload).hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {url}")
        path.write_bytes(payload)
    with ZipFile(BytesIO(path.read_bytes())) as z:
        frame = pd.read_csv(z.open(z.namelist()[0]), header=None if kind == "klines" else 0)
    return frame, {"url": url, "sha256": expected}

def validate(frame):
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Empty, duplicate or unsorted candles")
    if not (frame.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all():
        raise ValueError("Missing hourly candles")
    x = frame[["open", "high", "low", "close", "volume", "funding"]]
    if not np.isfinite(x.to_numpy()).all():
        raise ValueError("Nonfinite market data")
    if (x[["open", "high", "low", "close"]] <= 0).any().any() or (x.volume < 0).any():
        raise ValueError("Invalid price/volume")
    if ((x.high < x[["open", "close", "low"]].max(axis=1)) | (x.low > x[["open", "close"]].min(axis=1))).any():
        raise ValueError("Invalid OHLC")

def download(start, end, directory):
    """Dates must be month boundaries; end is exclusive, all months complete."""
    start, end = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    if start.day != 1 or end.day != 1 or start >= end or end > pd.Timestamp.now(tz="UTC").normalize().replace(day=1):
        raise ValueError("Use complete months, start < end, day 1")
    directory = Path(directory)
    cache = directory / "raw"
    cache.mkdir(parents=True, exist_ok=True)
    months = pd.date_range(start, end, freq="MS", inclusive="left").strftime("%Y-%m")
    jobs = [(k, m) for m in months for k in ("klines", "fundingRate")]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda km: archive(*km, cache), jobs))
    bars, funds, manifest = [], [], []
    for (kind, month), (df, meta) in zip(jobs, results):
        manifest.append(meta)
        if kind == "klines":
            df = df[pd.to_numeric(df[0], errors="coerce").notna()].copy()
            df = df.iloc[:, :6].astype(float)
            df.columns = ["time", "open", "high", "low", "close", "volume"]
            df.index = pd.to_datetime(df.pop("time"), unit="ms", utc=True)
            bars.append(df)
        else:
            df.index = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
            funds.append(df["last_funding_rate"].astype(float))
    frame = pd.concat(bars).sort_index()
    funding = pd.concat(funds).sort_index()
    if funding.index.has_duplicates or funding.empty:
        raise ValueError("Invalid funding history")
    if funding.index[0] > start + pd.Timedelta(hours=8) or funding.index[-1] < end - pd.Timedelta(hours=8):
        raise ValueError("Funding history does not cover requested range")
    if (funding.index.floor("h").to_series().diff().dropna() > pd.Timedelta(hours=8)).any():
        raise ValueError("Gap in funding history")
    frame["funding"] = funding.groupby(funding.index.floor("h")).sum().reindex(frame.index, fill_value=0.)
    frame = frame.loc[(frame.index >= start) & (frame.index < end)]
    validate(frame)
    if len(frame) != int((end-start).total_seconds()/3600):
        raise ValueError("Archive did not cover requested dates")
    path = directory / "BTCUSDT-1h.csv"
    frame.to_csv(path, index_label="time")
    (directory / "manifest.json").write_text(json.dumps({"source": "Binance USD-M futures, proxy for OKX; NOT OKX data", "start": str(start), "end_exclusive": str(end), "rows": len(frame), "csv_sha256": sha256(path.read_bytes()).hexdigest(), "archives": manifest}, indent=2))
    return path

def load(path):
    frame = pd.read_csv(path, index_col="time", parse_dates=True)
    frame.index = pd.to_datetime(frame.index, utc=True)
    validate(frame)
    return frame
