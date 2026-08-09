"""Tests for factor scoring, instrument potential ranking, and basket grouping."""
from datetime import date

import pytest

from kestrel.analysis.baskets import (
    assign_basket,
    compute_potential_score,
    rank_and_group_baskets,
    score_eps_trajectory,
    score_leverage_d2e,
    score_quality_roe,
)
from kestrel.analysis.fundamentals_trend import Trend


def test_eps_trajectory_scoring():
    t_up = Trend("UP", (), 4, 10.0, 1.0, 0.20, 0.30, 0.50, "improving")
    t_fl = Trend("FL", (), 4, 5.0, 0.0, 0.0, 0.0, 0.0, "flat")
    t_dn = Trend("DN", (), 4, 2.0, -1.0, None, None, -0.50, "declining")

    s_up = score_eps_trajectory(t_up)
    s_fl = score_eps_trajectory(t_fl)
    s_dn = score_eps_trajectory(t_dn)

    assert s_up > s_fl > s_dn
    assert s_up > 0.85  # Base 0.85 + growth bonuses


def test_quality_roe_scoring():
    assert score_quality_roe(0.25) == 1.0
    assert score_quality_roe(0.15) == pytest.approx(0.80)
    assert score_quality_roe(None) == 0.40  # Neutral fallback
    assert score_quality_roe(-0.05) == 0.0  # Negative ROE penalty


def test_leverage_d2e_scoring():
    assert score_leverage_d2e(0.10) == 1.0   # Low debt
    assert score_leverage_d2e(None) == 0.50  # Neutral fallback
    assert score_leverage_d2e(2.50) == 0.0   # High leverage penalty


def test_basket_assignment():
    assert assign_basket(0.85)[0] == "High Conviction / Prime Quality"
    assert assign_basket(0.55)[0] == "Growth & Momentum"
    assert assign_basket(0.35)[0] == "Value & Defensive"
    assert assign_basket(0.10)[0] == "Underperforming / High Risk"


def test_rank_and_group_baskets_sorts_descending():
    t_high = Trend("HIGH", (), 4, 10.0, 1.0, 0.20, 0.30, 0.50, "improving", latest_roe=0.25, latest_debt_to_equity=0.10)
    t_low = Trend("LOW", (), 4, 2.0, -1.0, None, None, -0.50, "declining", latest_roe=-0.10, latest_debt_to_equity=3.0)

    baskets = rank_and_group_baskets([t_low, t_high])

    # HIGH should be at the top of High Conviction basket
    high_items = baskets["High Conviction / Prime Quality"]
    assert len(high_items) == 1
    assert high_items[0].symbol == "HIGH"
    assert high_items[0].potential_score > 0.80

    # LOW should be in Underperforming / High Risk basket
    low_items = baskets["Underperforming / High Risk"]
    assert len(low_items) == 1
    assert low_items[0].symbol == "LOW"
    assert low_items[0].potential_score < 0.20


def test_sector_relative_valuation_ranks_within_industry():
    from kestrel.analysis.baskets import sector_relative_valuation
    # Within IT, A is cheaper (higher yields) than B; C is a lone-industry name.
    yields = {"A": (0.10, 0.20), "B": (0.02, 0.05), "C": (0.08, None)}
    industry = {"A": "IT", "B": "IT", "C": "BANK"}
    vs = sector_relative_valuation(yields, industry)
    assert vs["A"] > vs["B"]                 # cheaper within its sector scores higher
    assert 0.0 <= vs["C"] <= 1.0
    # a name with no industry is omitted entirely (no valuation pillar)
    assert sector_relative_valuation({"Z": (0.1, 0.1)}, {}) == {}
