# `kestrel/` — the deterministic plane (Python)

First code. This is the **deterministic plane** — data, research, and the
backtest engine. The execution safety core is separate Rust (doc 13, D-02) and
is not built yet. Per D-09 the strategy comes first, so this is where the
project starts: prove a documented factor (D-17) on real data before wiring
anything live.

## Layout

| Path | What |
|---|---|
| `costs.py` | Indian transaction-cost model — dated, sourced (doc 07 §5.1, archived rates). The money-losing-if-wrong number, tested. |
| `data/universe.py` | Point-in-time universe abstraction. `StaticUniverse` is survivorship-biased and says so; `PointInTimeUniverse` is the trustworthy one, now fed by the snapshotter. |
| `data/snapshot.py` | **The G-43 / D-15 keystone.** Immutable, dated reference snapshots. A second write with different content *raises* — never overwrites. `asof()` gives point-in-time retrieval. sha256 manifests. |
| `data/reference.py` | Swappable reference sources: `KiteInstrumentsSource` (real, inert until auth) and `StaticListSource` (dev, runnable today). |
| `data/pit.py` | Bridge: archived snapshots → `PointInTimeUniverse`. Closes the loop snapshots → PIT universe → backtest. |
| `data/yahoo.py` | **Development-only** NSE loader. Survivorship-biased, licence-incompatible with live — for building the engine, not for conclusions. |
| `data/kite_history.py` | **Real** Kite daily-bar loader: resolves symbol→token from the instruments snapshot, paginates + paces, injectable HTTP. Real prices — but survivorship (G-43) and dividend gaps (G-08) still apply; for calibration, not a clean verdict. |
| `kite/auth.py` | Daily login (doc 10 §2): checksum + `request_token`→`access_token` exchange, 06:00-IST expiry math. Operator-in-the-loop; never automates the browser (G-12). Pure core, injectable HTTP. |
| `kite/tokenstore.py` | Where the day's token lives so services can read it. 0600 file behind a `TokenStore` protocol (Redis later). `load_valid(now)` fails safe past expiry. |
| `execution/exits.py` | Deterministic exit rules (doc 07 §2.1): stop/target/time/data-loss on daily bars. Gap-through modelled honestly, favourable gaps not banked, stop wins ties. The heart of D-07. |
| `execution/book.py` | Positions, cash, and the round-trip P&L ledger. Cash can never go where it can't (G-29). |
| `execution/sizing.py` | Position sizing (G-18): equal-weight, fixed-fractional, **risk-based** (ties size to the stop), vol-target. Integer shares, floors, never overspends. |
| `execution/risk.py` | Deterministic pre-trade checks. Gates entries only — **never blocks an exit** (doc 07 §3). |
| `execution/manager.py` | The Position Manager (doc 07 §4): owns positions, fires exits from code, carries the conservative end-of-day fill model. Deterministic, no LLM in the loss path. |
| `strategies/momentum.py` | First documented anomaly (D-17): cross-sectional momentum, a pure function of prices. |
| `strategies/low_volatility.py` | Second documented anomaly (D-17): low-volatility, same contract as momentum. Built so the eventual point-in-time test can compare factors, not just measure one. |
| `strategies/value.py` | Third documented anomaly (D-17): value (earnings/book yield), same contract. Needs point-in-time fundamentals; runs on a dev source today, real feed deferred (an owner data decision). |
| `strategies/quality.py` | Fourth documented anomaly (D-17): quality/profitability (ROE), same contract. Reads fundamentals point-in-time. |
| `data/fundamentals.py` | Point-in-time fundamentals schema: dated, reporting-lagged records; `asof()` returns only what was **public** by the query date — the value/quality look-ahead guard. |
| `data/fundamentals_store.py` | Where filed results accumulate immutably (JSONL/symbol). Keeps original + restatements by publish_date; `asof()` picks what was public then. Implements `FundamentalsSource`. |
| `data/filings.py` | The results feed: `parse_xbrl_facts` (solid), `extract_financials` (heuristic, needs calibration), `NSEFilingsSource` (structured, inert until on-host tuning), `StaticFilings` (dev). |
| `backtest/engine.py` | Deterministic, point-in-time, cost-aware monthly rebalance loop. Propagates the survivorship flag so a biased run can't be mistaken for a clean one. |
| `backtest/metrics.py` | CAGR/Sharpe/maxDD **plus t-stat and information ratio** — the honest stats that expose a survivorship-inflated CAGR. |

## Run it

```bash
pip install -e ".[dev]"
python scripts/run_momentum.py           # the first empirical result + its caveat
python scripts/run_factor_comparison.py  # momentum vs low-vol, head to head, honest controls
python scripts/run_slice.py              # the vertical slice: one instrument through the exit path
python scripts/kite_login.py             # daily: mint the access_token (operator-in-the-loop)
python scripts/snapshot_reference.py --require-live  # daily: archive today's universe (scheduled via deploy/scheduler/)
python scripts/pull_history.py SYMBOL    # (after login) real Kite daily bars, cached
python scripts/snapshot_constituents.py  # daily: snapshot NIFTY 500 -> clean point-in-time stock universe
python scripts/harvest_fundamentals.py   # ingest NSE results filings (current-quarter EPS) into the store
python scripts/dashboard.py              # local on-host dashboard -> dashboard.html (open in a browser)
pytest -q                                # 133 tests: costs, determinism, factors, exits, filings, constituents, dividends
```

## The first result, and why it matters (2026-07-23)

Momentum on today's NSE large caps shows ~30% CAGR net of costs — and it is
**mostly survivorship bias**. Holding the same survivors returns ~28%; NIFTY
(which includes the delisted) returns ~8%. Momentum's edge over the survivor
control is IR ~0.14, and the clean long-short spread is statistically
insignificant. See doc 11, G-01 and G-43.

**The engine is trustworthy; the *data* is not.** A real verdict on the factor
needs a broad, point-in-time universe (delisted names included), which requires
Kite + the snapshotter. That is the next dependency, and this result is exactly
why it is non-negotiable — the bias is worth ~18 points of fake return.
