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
| `data/universe.py` | Point-in-time universe abstraction. `StaticUniverse` is survivorship-biased and says so; `PointInTimeUniverse` is the trustworthy one (needs the G-43 snapshotter). |
| `data/yahoo.py` | **Development-only** NSE loader. Survivorship-biased, licence-incompatible with live — for building the engine, not for conclusions. |
| `strategies/momentum.py` | First documented anomaly (D-17): cross-sectional momentum, a pure function of prices. |
| `backtest/engine.py` | Deterministic, point-in-time, cost-aware monthly rebalance loop. Propagates the survivorship flag so a biased run can't be mistaken for a clean one. |
| `backtest/metrics.py` | CAGR/Sharpe/maxDD **plus t-stat and information ratio** — the honest stats that expose a survivorship-inflated CAGR. |

## Run it

```bash
pip install -e ".[dev]"
python scripts/run_momentum.py      # the first empirical result + its caveat
pytest -q                           # 14 tests: cost traps, determinism, no look-ahead
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
