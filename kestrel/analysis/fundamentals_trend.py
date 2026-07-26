"""Fundamental trend analysis — is a company's performance improving or declining?

Given the accumulated point-in-time fundamentals (per-quarter EPS from filed
results), this measures the trajectory of each company and compares companies to
each other. It answers the plain question: *over this window, are earnings
trending up or down, and by how much?*

Design choices that keep it honest:

  * **Point-in-time optional.** Pass `asof` to see only what was public by a
    date (per period_end, the latest restatement public by then); omit it to use
    the full reported history.
  * **Robust to negative EPS.** Direction comes from the least-squares slope of
    the EPS series (well-defined even when EPS crosses zero); percentage growth
    (YoY/QoQ) is reported only when the base is positive, else left as `None`.
  * **A dead-band, so noise isn't a trend.** A slope within ±`flat_band` of the
    series' scale reads as *flat*, not a spurious improve/decline.

⚠️ **Per-share EPS is not bonus/split-adjusted (G-49).** A bonus or split changes
per-share EPS mechanically, so QoQ/YoY across that boundary is distorted (the
fundamentals analog of the G-08 dividend problem). The multi-quarter *slope* is
fairly robust to a one-off step; single QoQ/YoY around a corporate action are
not. The robust fix is to trend on **net profit (PAT)**, which is share-count-
invariant — a follow-up that needs PAT stored alongside EPS.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kestrel.data.fundamentals import FundamentalRecord


@dataclass(frozen=True)
class QuarterPoint:
    period_end: date
    eps: float


@dataclass(frozen=True)
class Trend:
    symbol: str
    points: tuple[QuarterPoint, ...]     # by period_end ascending
    n: int
    latest_eps: float | None
    qoq_change: float | None             # latest − previous quarter (absolute)
    qoq_growth: float | None             # %, None if prior ≤ 0
    yoy_growth: float | None             # % vs ~4 quarters earlier, None if base ≤ 0
    slope: float | None                  # EPS change per quarter (least squares)
    direction: str                       # "improving" | "declining" | "flat" | "insufficient"


def build_series(records: list[FundamentalRecord], *, asof: date | None = None) -> list[QuarterPoint]:
    """One EPS per period_end (latest restatement wins), sorted by period_end.
    With `asof`, only records public on/before that date are considered."""
    by_pe: dict[date, FundamentalRecord] = {}
    for r in records:
        if asof is not None and r.publish_date > asof:
            continue
        cur = by_pe.get(r.period_end)
        if cur is None or r.publish_date > cur.publish_date:
            by_pe[r.period_end] = r
    return [QuarterPoint(pe, by_pe[pe].eps_ttm) for pe in sorted(by_pe)]


def _slope(ys: list[float]) -> float:
    """Least-squares slope of ys against index 0..n-1 (EPS change per step)."""
    n = len(ys)
    xbar = (n - 1) / 2.0
    ybar = sum(ys) / n
    num = sum((i - xbar) * (y - ybar) for i, y in enumerate(ys))
    den = sum((i - xbar) ** 2 for i in range(n))
    return num / den if den else 0.0


def _yoy_growth(points: list[QuarterPoint]) -> float | None:
    """Latest vs the point ~1 year earlier (closest period_end within 45 days)."""
    if len(points) < 2:
        return None
    latest = points[-1]
    target = latest.period_end.replace(year=latest.period_end.year - 1) \
        if _valid_prev_year(latest.period_end) else None
    if target is None:
        return None
    best = min(points[:-1], key=lambda p: abs((p.period_end - target).days))
    if abs((best.period_end - target).days) > 45 or best.eps <= 0:
        return None
    return latest.eps / best.eps - 1.0


def _valid_prev_year(d: date) -> bool:
    try:
        d.replace(year=d.year - 1)
        return True
    except ValueError:      # 29 Feb
        return False


def analyse(symbol: str, records: list[FundamentalRecord], *,
            asof: date | None = None, flat_band: float = 0.02) -> Trend:
    pts = build_series(records, asof=asof)
    if len(pts) < 2:
        return Trend(symbol, tuple(pts), len(pts), pts[-1].eps if pts else None,
                     None, None, None, None, "insufficient")

    ys = [p.eps for p in pts]
    slope = _slope(ys)
    scale = sum(abs(y) for y in ys) / len(ys) or 1.0
    band = flat_band * scale
    direction = ("improving" if slope > band else
                 "declining" if slope < -band else "flat")

    prev, latest = pts[-2].eps, pts[-1].eps
    qoq_change = latest - prev
    qoq_growth = (latest / prev - 1.0) if prev > 0 else None
    return Trend(symbol, tuple(pts), len(pts), latest, qoq_change, qoq_growth,
                 _yoy_growth(pts), slope, direction)


def company_trend(store, symbol: str, *, asof: date | None = None,
                  flat_band: float = 0.02) -> Trend:
    """Trend for one symbol from a store exposing `records(symbol)`."""
    return analyse(symbol, store.records(symbol), asof=asof, flat_band=flat_band)


def compare(store, symbols: list[str] | None = None, *, asof: date | None = None,
            flat_band: float = 0.02) -> list[Trend]:
    """Trends for many symbols, ranked by slope (improving first). `symbols`
    defaults to everything in the store."""
    syms = symbols if symbols is not None else store.symbols()
    trends = [company_trend(store, s, asof=asof, flat_band=flat_band) for s in syms]
    # rank: measurable trends by slope desc; 'insufficient' last
    return sorted(trends, key=lambda t: (t.slope is None, -(t.slope or 0.0)))
