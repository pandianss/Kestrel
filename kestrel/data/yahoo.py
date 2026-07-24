"""Yahoo Finance loader for NSE monthly bars — a *development* data source.

⚠️ This is survivorship-biased and licence-incompatible with live use. It
exists to develop and test the engine, not to produce trustworthy results:

  * Survivorship — you can only fetch tickers that still trade. Delisted names
    are unreachable, so any universe built from Yahoo is biased upward (G-43).
  * Licence — the real system's data comes from Kite, whose terms govern
    storage and redistribution (doc 02 §9.7). Yahoo is not a substitute there.

Adjusted close is total-return adjusted (dividends + splits), which happens to
sidestep the G-08 dividend problem *for development* — but do not carry that
convenience into conclusions about the real Kite pipeline.

Data is cached to `data/cache/` so repeated runs are offline and deterministic.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

_CACHE = Path("data/cache")
_UA = {"User-Agent": "Mozilla/5.0"}


def _chart_url(symbol: str, interval: str = "1mo") -> str:
    if symbol.startswith("^"):
        q = symbol.replace("^", "%5E")
        return f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range=max&interval={interval}"
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"
        f"?range=max&interval={interval}&events=div%2Csplit"
    )


def _fetch_one(symbol: str, timeout: int = 20) -> pd.Series:
    req = urllib.request.Request(_chart_url(symbol), headers=_UA)
    d = json.load(urllib.request.urlopen(req, timeout=timeout))
    r = d["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s")
    ind = r["indicators"]
    values = ind["adjclose"][0]["adjclose"] if "adjclose" in ind else ind["quote"][0]["close"]
    return pd.Series(values, index=ts, name=symbol)


def load_daily_ohlc(
    symbol: str,
    *,
    use_cache: bool = True,
    timeout: int = 20,
) -> pd.DataFrame:
    """Daily OHLC bars for one NSE `symbol`, for the execution-plane slice.

    Returns a frame indexed by date with columns open/high/low/close. Split-
    adjusted; the raw OHLC is what the fill model needs (intrabar highs/lows
    drive stop and target evaluation — a close-only series cannot). Same
    development-only caveats as the rest of this module.
    """
    _CACHE.mkdir(parents=True, exist_ok=True)
    key = _CACHE / f"daily_ohlc_{symbol}.pkl"
    if use_cache and key.exists():
        return pd.read_pickle(key)

    req = urllib.request.Request(_chart_url(symbol, interval="1d"), headers=_UA)
    d = json.load(urllib.request.urlopen(req, timeout=timeout))
    r = d["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s").normalize()
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame(
        {"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]},
        index=ts,
    ).dropna()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if use_cache:
        df.to_pickle(key)
    return df


def load_monthly(
    symbols: list[str],
    *,
    use_cache: bool = True,
    pause: float = 0.12,
) -> pd.DataFrame:
    """Monthly adjusted-close panel for `symbols` (NSE), month-end indexed.
    Columns that fail to fetch are dropped (and reported by the caller via the
    returned columns). Cached per run under `data/cache/`."""
    _CACHE.mkdir(parents=True, exist_ok=True)
    key = _CACHE / ("monthly_" + "_".join(sorted(symbols))[:80] + f"_{len(symbols)}.pkl")
    if use_cache and key.exists():
        return pd.read_pickle(key)

    series: dict[str, pd.Series] = {}
    for s in symbols:
        try:
            series[s] = _fetch_one(s)
            time.sleep(pause)
        except Exception:  # noqa: BLE001 — a failed ticker is dropped, not fatal
            continue
    px = pd.DataFrame(series)
    px.index = px.index.to_period("M").to_timestamp("M")
    px = px[~px.index.duplicated(keep="last")].sort_index()
    if use_cache:
        px.to_pickle(key)
    return px
