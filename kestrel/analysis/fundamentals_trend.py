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
    latest_roe: float | None = None
    latest_debt_to_equity: float | None = None
    latest_book_value_per_share: float | None = None


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


def _calculate_balance_sheet_metrics(records: list[FundamentalRecord], asof: date | None, latest_eps: float | None) -> tuple[float | None, float | None, float | None]:
    public_recs = sorted(
        [r for r in records if (asof is None or r.publish_date <= asof)],
        key=lambda r: r.publish_date
    )
    if not public_recs:
        return None, None, None

    # 1. Latest Book Value per Share
    latest_bvps = None
    for r in reversed(public_recs):
        if r.book_value_per_share > 0:
            latest_bvps = r.book_value_per_share
            break

    # 2. Latest Net Worth and Total Debt
    latest_net_worth = None
    latest_total_debt = None
    for r in reversed(public_recs):
        if r.net_worth is not None:
            latest_net_worth = r.net_worth
            break
    for r in reversed(public_recs):
        if r.total_debt is not None:
            latest_total_debt = r.total_debt
            break

    # 3. Compute Debt to Equity
    latest_d2e = None
    if latest_total_debt is not None and latest_net_worth is not None and latest_net_worth > 0:
        latest_d2e = latest_total_debt / latest_net_worth

    # 4. Compute ROE
    latest_roe = None
    pe_recs = {}
    for r in public_recs:
        pe_recs[r.period_end] = r
    sorted_pe_recs = [pe_recs[pe] for pe in sorted(pe_recs)]

    if len(sorted_pe_recs) >= 4:
        last_4 = sorted_pe_recs[-4:]
        span_days = (last_4[-1].period_end - last_4[0].period_end).days
        if 270 <= span_days <= 370 and all(r.net_profit is not None for r in last_4):
            ttm_profit = sum(r.net_profit for r in last_4)
            if latest_net_worth is not None and latest_net_worth > 0:
                latest_roe = ttm_profit / latest_net_worth

    # ROE is reported ONLY from real TTM profit over real net worth (above).
    # We deliberately do NOT fall back to EPS / book_value: when the balance
    # sheet is missing (as it is for most results-only filings) BVPS is often a
    # placeholder, and EPS/BVPS then produces absurd "ROE" (e.g. 2128, or simply
    # EPS itself when BVPS≈1) that the scorer read as world-class quality. Better
    # to return None (scored as neutral) than to invent a number.
    # Sanity clamp: a real ROE outside [-100%, +150%] is a data error, not a
    # genuine return — discard it rather than let it saturate the quality pillar.
    if latest_roe is not None and not (-1.0 <= latest_roe <= 1.5):
        latest_roe = None

    return latest_roe, latest_d2e, latest_bvps


def analyse(symbol: str, records: list[FundamentalRecord], *,
            asof: date | None = None, flat_band: float = 0.02,
            min_quarters: int = 4) -> Trend:
    pts = build_series(records, asof=asof)
    latest_roe, latest_d2e, latest_bvps = _calculate_balance_sheet_metrics(records, asof, pts[-1].eps if pts else None)

    # Confidence gate: a direction from 2–3 quarters is a single delta, not a
    # trend — indistinguishable from a microcap's earnings bouncing around. We
    # need at least a year of quarters (default 4) before we'll call a company
    # "improving"/"declining". Below that it is honestly "insufficient", and we
    # suppress slope/QoQ/YoY so nothing downstream scores it as a real trajectory.
    if len(pts) < min_quarters:
        return Trend(symbol, tuple(pts), len(pts), pts[-1].eps if pts else None,
                     None, None, None, None, "insufficient",
                     latest_roe, latest_d2e, latest_bvps)

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
                 _yoy_growth(pts), slope, direction,
                 latest_roe, latest_d2e, latest_bvps)


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
