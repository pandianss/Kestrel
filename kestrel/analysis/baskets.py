"""Instrument factor scoring and basket grouping engine.

Computes a normalized composite potential score (0.0 to 1.0) per instrument based on:
1. EPS Growth Trajectory (40% weight): slope direction, QoQ, YoY growth
2. Quality / ROE (30% weight): Return on Equity
3. Leverage Safety (30% weight): Debt-to-Equity ratio

Ranks all instruments from most potential to least potential and groups them into
four distinct factor baskets:
- High Conviction / Prime Quality (Score >= 0.70)
- Growth & Momentum (0.45 <= Score < 0.70)
- Value & Defensive (0.20 <= Score < 0.45)
- Underperforming / High Risk (Score < 0.20)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kestrel.analysis.fundamentals_trend import Trend


@dataclass(frozen=True)
class ScoredInstrument:
    symbol: str
    potential_score: float         # 0.0 to 1.0 (higher = more potential)
    basket_name: str               # Basket group name
    basket_badge: str              # Icon / badge tag
    direction: str                 # "improving" | "declining" | "flat" | "insufficient"
    slope: float | None
    latest_eps: float | None
    latest_roe: float | None
    latest_d2e: float | None
    latest_bvps: float | None
    qoq_growth: float | None
    yoy_growth: float | None
    promoter_holding_pct: float | None = None
    promoter_trend_pct: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["potential_pct"] = f"{self.potential_score * 100:.1f}%"
        d["roe_pct"] = f"{self.latest_roe * 100:.1f}%" if self.latest_roe is not None else "—"
        d["d2e_ratio"] = f"{self.latest_d2e:.2f}" if self.latest_d2e is not None else "—"
        d["promoter_pct"] = f"{self.promoter_holding_pct * 100:.1f}%" if self.promoter_holding_pct is not None else "—"
        return d


def score_eps_trajectory(t: Trend) -> float:
    """Score EPS trajectory between 0.0 and 1.0 (35% of potential score)."""
    base = 0.5
    if t.direction == "improving":
        base = 0.85
    elif t.direction == "flat":
        base = 0.50
    elif t.direction == "declining":
        base = 0.10
    elif t.direction == "insufficient":
        base = 0.30

    # Growth acceleration bonuses (up to +0.15)
    bonus = 0.0
    if t.qoq_growth is not None and t.qoq_growth > 0.10:
        bonus += min(0.10, t.qoq_growth * 0.2)
    if t.yoy_growth is not None and t.yoy_growth > 0.15:
        bonus += min(0.05, t.yoy_growth * 0.1)

    return min(1.0, base + bonus)


def score_quality_roe(roe: float | None) -> float:
    """Score Quality / ROE between 0.0 and 1.0 (25% of potential score)."""
    if roe is None:
        return 0.40  # Neutral fallback if ROE is not available
    if roe >= 0.20:
        return 1.0
    if roe >= 0.10:
        return 0.60 + (roe - 0.10) * 4.0
    if roe >= 0.0:
        return roe * 6.0
    return 0.0  # Negative ROE


def score_leverage_d2e(d2e: float | None) -> float:
    """Score Leverage Safety / Debt-to-Equity between 0.0 and 1.0 (25% of potential score)."""
    if d2e is None:
        return 0.50  # Neutral fallback if D/E is not available
    if d2e <= 0.25:
        return 1.0  # Debt-free / negligible leverage
    if d2e <= 1.0:
        return 1.0 - (d2e - 0.25) * 0.60
    if d2e <= 2.0:
        return 0.55 - (d2e - 1.0) * 0.45
    return 0.0  # High leverage (> 2.0 D/E)


def score_promoter_holding(holding_pct: float | None, trend_pct: float | None = None) -> float:
    """Score Promoter Stake & Conviction between 0.0 and 1.0 (15% of potential score)."""
    if holding_pct is None:
        return 0.50  # Neutral fallback if promoter data unavailable
    
    # Base score on skin-in-the-game percentage
    if holding_pct >= 0.60:
        base = 0.90
    elif holding_pct >= 0.45:
        base = 0.70
    elif holding_pct >= 0.30:
        base = 0.50
    else:
        base = 0.30

    # Trend adjustment (promoter buying vs selling)
    adj = 0.0
    if trend_pct is not None:
        if trend_pct > 0.01:
            adj = min(0.10, trend_pct * 2.0)
        elif trend_pct < -0.01:
            adj = max(-0.20, trend_pct * 3.0)

    return max(0.0, min(1.0, base + adj))


def score_valuation(pe: float | None = None, pb: float | None = None) -> float:
    """Score cheapness between 0.0 and 1.0 — higher = cheaper. The backtest showed
    the quality/growth score buys great companies at any price and pays for the
    mean-reversion; this pillar rewards buying them cheap. Loss-making (pe<=0) or
    negative-book (pb<=0) scores low, not free — cheap-for-a-reason."""
    parts = []
    if pe is not None:
        if pe <= 0:
            parts.append(0.15)
        elif pe <= 10:
            parts.append(1.0)
        elif pe >= 40:
            parts.append(0.0)
        else:
            parts.append(1.0 - (pe - 10) / 30.0)
    if pb is not None:
        if pb <= 0:
            parts.append(0.15)
        elif pb <= 1:
            parts.append(1.0)
        elif pb >= 8:
            parts.append(0.0)
        else:
            parts.append(1.0 - (pb - 1) / 7.0)
    return sum(parts) / len(parts) if parts else 0.5


def compute_potential_score(
    t: Trend,
    promoter_holding_pct: float | None = None,
    promoter_trend_pct: float | None = None,
    *,
    pe: float | None = None,
    pb: float | None = None,
) -> float:
    """Composite potential score (0.0 to 1.0).

    Without a valuation input (pe/pb both None — e.g. the dashboard before prices
    are wired), the original 4-pillar weighting is used unchanged. With price, a
    5th *valuation* pillar is added (quality CHEAP, not just quality) and the
    weights are rebalanced: EPS 30 / ROE 20 / D-E 20 / promoter 10 / value 20."""
    eps_s = score_eps_trajectory(t)
    roe_s = score_quality_roe(t.latest_roe)
    d2e_s = score_leverage_d2e(t.latest_debt_to_equity)
    prom_s = score_promoter_holding(promoter_holding_pct, promoter_trend_pct)

    if pe is None and pb is None:
        # 4-Pillar: EPS 35%, ROE 25%, D/E 25%, Promoter 15%
        score = 0.35 * eps_s + 0.25 * roe_s + 0.25 * d2e_s + 0.15 * prom_s
    else:
        val_s = score_valuation(pe, pb)
        # 5-Pillar: EPS 30%, ROE 20%, D/E 20%, Promoter 10%, Valuation 20%
        score = 0.30 * eps_s + 0.20 * roe_s + 0.20 * d2e_s + 0.10 * prom_s + 0.20 * val_s
    return max(0.0, min(1.0, score))


def assign_basket(score: float) -> tuple[str, str]:
    """Assign instrument to a factor basket based on its composite score."""
    if score >= 0.70:
        return "High Conviction / Prime Quality", "🏆 High Conviction"
    if score >= 0.45:
        return "Growth & Momentum", "📈 Growth"
    if score >= 0.20:
        return "Value & Defensive", "🛡️ Value"
    return "Underperforming / High Risk", "⚠️ High Risk"


def rank_and_group_baskets(
    trends: list[Trend],
    relations_store=None
) -> dict[str, list[ScoredInstrument]]:
    """Rank all trends from most potential to least, and group them into baskets."""
    from datetime import date
    scored: list[ScoredInstrument] = []
    
    for t in trends:
        promoter_holding = None
        promoter_trend = None
        
        if relations_store is not None:
            try:
                rels = relations_store.relations_asof(t.symbol, date.today())
                prom_recs = [r for r in rels if r.target_name_or_symbol == "Promoter & Promoter Group"]
                if prom_recs:
                    promoter_holding = prom_recs[-1].holding_pct
                    if len(prom_recs) >= 2:
                        promoter_trend = prom_recs[-1].holding_pct - prom_recs[0].holding_pct
            except Exception:
                pass

        score = compute_potential_score(t, promoter_holding, promoter_trend)
        b_name, b_badge = assign_basket(score)
        scored.append(
            ScoredInstrument(
                symbol=t.symbol,
                potential_score=score,
                basket_name=b_name,
                basket_badge=b_badge,
                direction=t.direction,
                slope=t.slope,
                latest_eps=t.latest_eps,
                latest_roe=t.latest_roe,
                latest_d2e=t.latest_debt_to_equity,
                latest_bvps=t.latest_book_value_per_share,
                qoq_growth=t.qoq_growth,
                yoy_growth=t.yoy_growth,
                promoter_holding_pct=promoter_holding,
                promoter_trend_pct=promoter_trend,
            )
        )

    # Sort descending by potential_score (most potential to least potential)
    scored.sort(key=lambda s: (-s.potential_score, -(s.slope or 0.0)))

    # Group into dictionary
    baskets: dict[str, list[ScoredInstrument]] = {
        "High Conviction / Prime Quality": [],
        "Growth & Momentum": [],
        "Value & Defensive": [],
        "Underperforming / High Risk": [],
    }
    for item in scored:
        baskets.setdefault(item.basket_name, []).append(item)

    return baskets

