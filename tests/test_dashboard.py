"""Regression checks for the dashboard's decision charts."""
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dashboard  # noqa: E402
from kestrel.analysis.fundamentals_trend import QuarterPoint, Trend


def test_slice_outcomes_chart_is_zero_centred_and_annotated():
    chart = dashboard._slice_outcomes_chart({
        "findings": [
            {"symbol": "GAIN", "net_pnl": 12_500},
            {"symbol": "LOSS", "net_pnl": -2_000},
        ]
    })

    assert 'class="chart-zero"' in chart
    assert 'outcome-bar positive' in chart
    assert 'outcome-bar negative' in chart
    assert "GAIN" in chart and "LOSS" in chart
    assert "Net P&amp;L by vertical slice" in chart


def test_eps_small_multiples_label_each_series_and_its_scale():
    trend = Trend(
        "UP",
        (QuarterPoint(date(2024, 3, 31), 10.0), QuarterPoint(date(2024, 6, 30), 12.0)),
        2,
        12.0,
        2.0,
        0.2,
        None,
        1.0,
        "improving",
    )

    chart = dashboard._fundamental_trends_chart({"trends": [trend]})

    assert 'class="trend-chart-grid"' in chart
    assert "UP" in chart
    assert 'trend-line improving' in chart
    assert "Each chart has its own EPS scale" in chart


def test_basket_chart_exposes_rank_and_data_completeness():
    chart = dashboard._basket_rank_chart({
        "baskets": {
            "Growth": [
                {"symbol": "TOP", "potential_score": 0.75, "direction": "improving",
                 "latest_roe": 0.2, "latest_d2e": 0.3},
                {"symbol": "BOTTOM", "potential_score": 0.25, "direction": "flat",
                 "latest_roe": None, "latest_d2e": None},
            ]
        }
    })

    assert 'class="rank-list"' in chart
    assert chart.index("TOP") < chart.index("BOTTOM")
    assert 'aria-valuenow="75.0"' in chart
    assert "ROE available for 1/2" in chart
