"""Tests for the live dashboard (reworked): fast render from precomputed state."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dashboard  # noqa: E402


def _state() -> dict:
    return {
        "generated": "2026-08-07 12:00:00", "generated_epoch": 1.0,
        "ranking": [
            {"symbol": "AAA", "potential_score": 0.9, "latest_roe": 0.25, "latest_d2e": 0.10, "direction": "improving"},
            {"symbol": "BBB", "potential_score": 0.5, "latest_roe": None, "latest_d2e": None, "direction": "declining"},
        ],
        "ranking_counts": (2, 100), "ranking_at": None,
        "book": {"rows": [{"symbol": "AAA", "qty": 10, "entry_price": 100.0,
                           "entry_notional": 1000.0, "now_px": 110.0, "value": 1100.0, "pnl": 100.0}],
                 "equity": 1100.0, "cash": 0.0, "inception": 1000.0, "ret": 0.10,
                 "rebalances": 1, "created": "x"},
        "backtest": {"config": "c", "window": "w", "months": 94, "generated": "2026-08-07T00:00",
                     "dates": ["2019-01", "2019-02", "2020-01"],
                     "strategy_equity": [1.0, 1.1, 2.0], "benchmark_equity": [1.0, 1.05, 1.5],
                     "stats": {"strategy": {"cagr": 0.27, "sharpe": 1.17, "maxdd": -0.3, "total": 5.0},
                               "benchmark": {"cagr": 0.23, "sharpe": 0.99, "maxdd": -0.35, "total": 4.0},
                               "active": 0.035, "ir": 0.49, "turnover": 0.2}, "caveat": "c"},
        "fund_latest_q": "2026-06-30", "price_latest": "2026-08-07",
        "worker_alive": True, "token_valid": True,
    }


def test_render_live_is_complete_and_clean():
    h = dashboard.render_live(_state())
    assert "<!doctype html>" in h.lower()
    assert "if isinstance" not in h                     # no leaked f-string conditionals
    for pane in ("p-pipeline", "p-leaderboard", "p-paper", "p-backtest"):
        assert pane in h
    assert "AAA" in h and "line-strat" in h and "auto-refresh" in h


def test_leaderboard_handles_missing_roe_de():
    h = dashboard._leaderboard(_state())
    assert "AAA" in h and "BBB" in h and "—" in h        # BBB has no ROE/D-E


def test_backtest_svg_plots_both_series():
    svg = dashboard._svg_equity(_state()["backtest"])
    assert "line-strat" in svg and "line-bench" in svg and svg.count("polyline") == 2


def test_gather_live_tolerates_missing_artifacts(tmp_path, monkeypatch):
    for attr in ("RANKING", "PORTFOLIO", "BACKTEST"):
        monkeypatch.setattr(dashboard, attr, tmp_path / f"{attr}.json")
    monkeypatch.setattr(dashboard, "KITE_CACHE", tmp_path / "kc")
    monkeypatch.setattr(dashboard, "FUND_DIR", tmp_path / "f")
    monkeypatch.setattr(dashboard, "PID_FILE", tmp_path / "pid")
    st = dashboard.gather_live()
    assert st["ranking"] == [] and st["book"] is None and st["backtest"] is None
    assert "<!doctype html>" in dashboard.render_live(st).lower()   # still renders
