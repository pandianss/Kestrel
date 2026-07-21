# 01 — Overview, Goals & Scope

**Last updated:** 2026-07-21

---

## 1. Vision

Build a multi-agent system that continuously studies the Indian equity and derivatives market through the Zerodha Kite Connect API, forms trading decisions via a layered set of LLM agents, and executes those decisions — first on paper, later (if proven) live. The system should behave like a small automated trading desk: a **macro desk**, a **single-stock desk**, and a **market-microstructure desk**, all feeding a **single risk/portfolio manager** that is the sole authority to place (paper) orders.

## 2. Primary goals

1. **Breadth.** Watch a very large universe (up to 9,000 instruments) that no human desk could monitor, and surface the handful that matter *right now*.
2. **Speed where it counts.** Parse the live tick stream and react internally in low single-digit milliseconds; never waste the shared Kite rate budget. (Note: this is *not* HFT — see §5.)
3. **Sound multi-agent decision-making.** A funnel that turns broad, cheap screening into narrow, expensive judgement, with exactly one component authorized to act.
4. **Provable correctness before risk.** Paper-trade with a realistic fill simulator and a P&L ledger, so the logic can be validated with zero financial exposure before any live capital.
5. **Clean live-migration path.** Paper and live share the same interfaces, rate budgets, and risk controls, so flipping to live is a configuration change plus a go/no-go review, not a rewrite.

## 3. Secondary goals

- **Cost control** on LLM usage via model tiering (cheap models for high-frequency work, strong models for rare, high-stakes judgement).
- **Observability** sufficient to trust an autonomous system (dashboards, P&L ledger, fill-quality metrics, alerting).
- **Reproducibility** of research (static study runs and backtests must be re-runnable and free of look-ahead bias).

## 4. Scope

### In scope (this design)
- Live market-data ingestion (WebSocket) and historical backfill.
- A tiered subscription manager to fit 9,000 instruments across 3 WebSocket connections.
- A paper-execution engine (fill simulator + risk engine + P&L ledger).
- The agent fleet: static study agents, live screeners/specialists, a risk/portfolio manager, and information-source agents (news, central banks/macro).
- Supporting storage, event bus, deployment, observability, and security posture.

### Explicitly out of scope (for now)
- **Live real-money trading.** Deferred behind a go/no-go review (see doc 09, Phase 6).
- **The trading strategy / alpha itself.** This design is *plumbing*: it can carry any strategy. The specific edge is **not defined here** and is flagged as the biggest open gap (doc 11, Gap G-01).
- **Options pricing/greeks engine, portfolio optimizer, and tax/accounting** — may come later; not in the initial build.
- **A user-facing UI** beyond operational dashboards.
- **Multiple brokers.** Kite/Zerodha only.

## 5. Explicit non-goals (calibration)

- **This is not HFT.** Kite is a throttled retail feed; its tick cadence and REST rate limits set the latency floor, not our code. We do not co-locate at the exchange, and we will not out-race professional low-latency desks on marquee events. Our edge is **breadth + synthesis**, not microsecond speed.
- **News/central-bank agents are not headline-racing bots.** Their value is watching more sources than a human can and reasoning about second-order effects — not beating algos to a wire in the first milliseconds.

## 6. Success criteria (proposed — needs confirmation)

The following are proposed measures for "is the paper system working?" They are deliberately about *system quality*, not profitability (which depends on the undefined strategy):

| Criterion | Target (draft) |
|---|---|
| Tick-to-internal-state latency (p99) | < 5 ms from packet receipt to normalized state |
| Data completeness | 0 silently dropped ticks; all gaps logged and backfilled |
| Fill-simulator fidelity | Paper fills reconcile against replayed ticks within a defined slippage band |
| Rate-budget safety | Zero `429` responses in normal operation; every Kite call passes through a governed budget |
| Decision auditability | Every paper order traceable to the agent chain + data that produced it |
| Uptime during market hours | Data plane reconnects automatically; no manual intervention intraday |

> **Open:** profitability targets and risk-adjusted return metrics (Sharpe, max drawdown) cannot be set until a strategy exists. See doc 11.

## 7. Users / operators

- **Operator (you):** performs the daily login (regulatory requirement, doc 02 §2), monitors dashboards, approves the eventual go/no-go to live.
- **The agents:** autonomous during market hours within the risk manager's guardrails.
- **Reviewers (now):** other agents/humans reading this doc set to find gaps.
