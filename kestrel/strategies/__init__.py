"""Documented-anomaly strategies (D-17): cross-sectional momentum, low-vol.

Each is a pure function of a price panel exposing the same contract —
`<factor>_scores(prices, cfg)` and `target_holdings(scores_row, tradeable, cfg)`
with higher score = better — so the backtest engine treats them identically.
"""
