# 05 — Agent Architecture

**Last updated:** 2026-07-22

> **Core principle (repeated because it governs everything here):** agent count is *not* set by the size of the market. It is set by (a) Kite's per-key rate limits — which force the I/O-facing agents to be effectively one of each — and (b) the LLM latency/token budget on the cognition agents — which has sharply diminishing returns past ~30. Information-source agents (news, macro) are cheap because they never touch Kite's limits, but each earns its place only if its signal reaches a decision and changes an action.

---

## 1. Three categories of "agent"

Not everything here is an LLM. We distinguish:

- **I/O services** (Rust) — talk to Kite. Bounded by rate limits → **singletons**.
- **Cognition agents** (Python/LLM) — reason over cached/streamed data. Bounded by compute/token budget → **scale wider, with diminishing returns**.
- **Information-source agents** (Python/LLM + fetchers) — bring in external signal (news, central banks). Independent of Kite limits.

---

## 2. I/O services — bounded by rate limits → singletons

| Service | Count | Why not more |
|---|---|---|
| Data Ingester (owns 3 WS connections) | **1** (with up to 3 connection workers) | 3-connection hard cap per key; more copies can't add connections |
| Quote Poller | **1** | Shares the 1 req/s quote budget; parallel pollers just queue |
| Historical Backfill | **1** (worker pool sharing a 3/s token bucket) | 3 req/s is the ceiling regardless of worker count |
| Position Manager | **1** | Must hold every open position coherently; two would race on the same stop |
| Paper Execution Gateway | **1** | Must be the single writer; parallel writers = race + budget violation |

**Raising this ceiling with additional API keys is largely not available** ⚠️ *(revised 2026-07-22)*. The earlier version of this document assumed extra keys/subscriptions would multiply the budget. Two facts undercut that:

1. **The 10 orders/second limit is scoped to the Kite client ID, not the app** — it applies regardless of how many apps sit under one developer profile. Extra apps buy no extra order throughput.
2. **The SEBI framework pushes toward unique credentials per client and one static IP per developer profile** (doc 02 §9), so a fan of keys under one operator is exactly the pattern the rules are designed to discourage.

Additional *WebSocket* capacity via a second key may still be technically possible, but plan capacity on **one key, one budget** and treat anything more as a question for Zerodha rather than an assumption (doc 11, G-05).

---

## 3. Static / historical study fleet — bounded by compute/tokens

**Purpose:** offline, batch "study the market" over cached historical data — pre-market and overnight. Because it reads from local storage (QuestDB/DuckDB), it is **decoupled from Kite's rate limits entirely** (data is pre-cached by the backfill service).

**Sizing method:** `analysis dimension × market bucket`.

Dimensions (~7–10):
1. Trend / regime
2. Volatility structure
3. Volume / liquidity
4. Correlation / sector rotation
5. Options OI / flow (F&O)
6. Market breadth
7. Event / earnings / corporate-actions
8. (optional) Seasonality / calendar effects
9. (optional) Relative strength / momentum ranking

Buckets: NSE sectors / indices (~11) or custom groupings.

**Recommended fleet size:** **8–24 parallel agents** for a nightly/pre-market batch. Past ~30, added agents produce redundant opinions, not new signal.

**Output:** a ranked watchlist + regime priors + the day's **Full-mode promotion list** (which instruments deserve full-depth streaming today), consumed by the live plane and the subscription manager.

---

## 4. Live / ongoing decision funnel — the operating heart

A funnel that turns broad-cheap into narrow-expensive, with exactly one authority to act.

```
   streaming universe (up to 9,000)
            │
            ▼
   ┌───────────────────┐  8–12 workers, Claude Haiku
   │  SCREENERS        │  scan cache/tick events, flag candidates
   └─────────┬─────────┘
             │ candidate flags (stream)
             ▼
   ┌───────────────────┐  3–5 workers, Claude Sonnet
   │  SPECIALISTS      │  technical / options-OI / news-event / macro-regime
   └─────────┬─────────┘
             │ assessments (stream)
             ▼
   ┌───────────────────┐  1, Claude Fable
   │  RISK / PORTFOLIO │  sizes, applies risk limits, arbitrates,
   │  MANAGER          │  SOLE authority to OPEN a position
   └─────────┬─────────┘
             │ entry intent (+ mandatory exit plan)
             ▼
   ┌───────────────────┐  1 (Rust)
   │  EXECUTION GATEWAY│  risk + margin check → fill sim → ledger → ack
   └─────────┬─────────┘
             │ on fill, hands the position to ↓
             ▼
   ┌───────────────────┐  1 (Rust) — NO LLM
   │  POSITION MANAGER │  stops · targets · time-exits · square-off
   └─────────┬─────────┘  emits exit intents deterministically
             └──────────────► back to EXECUTION GATEWAY
```

**Note the loop.** The funnel above is the *entry* path and it is LLM-shaped. The exit path is a closed deterministic loop between the Position Manager and the Execution Gateway, with no Python in it (doc 03 §2.1, doc 07 §4). That asymmetry is deliberate: a slow entry costs an opportunity, a slow exit costs money.

**Recommended concurrent live agent range: ~15–25.** Beyond ~30 you pay for conflicting opinions and latency, not edge.

| Layer | Count | Model | Notes |
|---|---|---|---|
| Screeners | 8–12 | Haiku | Partition the universe; rolling scan; cheap & fast |
| Specialists | 3–5 | Sonnet | One per lens: technical, options/OI, news/event, macro-regime |
| Risk/Portfolio Manager | **1** | Fable | Singleton by design — the safety throttle, not a bottleneck to remove |
| Position Manager | **1** | — (Rust) | Deterministic exits; never waits on an LLM |
| Execution Gateway | **1** | — (Rust) | Single writer |

**Why the singleton manager is a feature, not a flaw:** multiple LLM agents placing orders in parallel is a race condition with real money and no coherent portfolio view. One manager holds the whole book, applies global risk limits, and resolves conflicting specialist opinions.

**And why the singleton manager is no longer a single point of *failure*:** because it is only on the entry path. If it stalls, hangs, or its model provider has an outage, the system stops opening positions — and every position already open continues to be managed by deterministic Rust. The worst case degrades to "we stop trading," not "we stop managing risk."

---

## 5. Information-source agents (detail in doc 08 §4–5)

- **News sub-pipeline:** ingest+dedupe+entity-resolve → classify/sentiment (cheap) → impact analyst (strong, high-salience only). Feeds screeners (as catalyst flags) and the manager (as veto/context). **Also drives the Full-mode promotion list.**
- **Macro / central-bank agent:** calendar-driven + a daily regime-state refresh (RBI, US Fed, ECB, BoJ, PBoC + DXY, US 10Y, crude, USD/INR, India VIX, FII/DII flows). Consumer is the **risk manager** (regime prior + position sizing + event-window de-risk), *not* the stock screeners.

**Altitude matters:** news maps to a *single instrument*; macro shifts the *whole book*. Different consumers, different jobs.

---

## 6. Coordination & control

- **Orchestration:** LangGraph graph with explicit shared state (regime, positions, active candidates, risk budget). Each edge is a defined hand-off; no implicit global mutation.
- **Communication:** via Redis Streams (durable, replayable) — screeners → specialists → manager → execution, plus news/macro event streams.
- **Backpressure:** if specialists lag, screeners throttle candidate emission; if the manager lags, it always has the option to open nothing.
  - ⚠️ **Corrected 2026-07-22:** an earlier version of this line read "the manager can always do nothing (safe default)." That is true for *entries* and false for *exits* — doing nothing while holding a losing position is not a safe default, it is an unbounded one. Doing nothing is safe only because the Position Manager (doc 07 §4) is separately guaranteed to act.
- **Determinism where possible:** risk limits, position sizing bounds, **exits**, and kill-switch triggers are *deterministic code*, not LLM judgement — the LLM proposes within hard-coded guardrails.

---

## 7. The "don't let the roster sprawl" rule

Every proposed new agent must declare:
1. **Consumer** — screener-level (stock-specific) or manager-level (portfolio/regime)?
2. **Altitude** — single instrument vs. whole book?
3. **Measurable contribution** — does it demonstrably improve paper P&L / decision quality?

If a proposed agent doesn't fit the **macro desk / single-stock desk / microstructure desk → one risk manager** structure, that's the signal to push back rather than add it.

---

## 8. Summary table — recommended counts

| Group | Recommended | Hard ceiling | Bounded by |
|---|---|---|---|
| Data Ingester | 1 (≤3 conn workers) | 3 connections | Kite WS limit |
| Quote Poller | 1 | 1 effective | Kite 1 req/s |
| Backfill | 1 (pooled) | 3 req/s effective | Kite historical limit |
| Position Manager | 1 | 1 (must be) | Coherent ownership of open positions |
| Execution Gateway | 1 | 1 (must be) | Single-writer safety |
| Static study fleet | 8–24 | ~30 useful | Tokens / redundancy |
| Live screeners | 8–12 | universe/latency | Tokens / latency |
| Live specialists | 3–5 | ~7 | Tokens / redundancy |
| Risk/Portfolio Manager | 1 | 1 (must be) | Coherence + safety |
| News pipeline | 2–3 stages | — | Source cost / tokens |
| Macro/central-bank | 1 (+calendar jobs) | — | Event cadence |
| **Live concurrent total** | **~15–25** | **~30** | Tokens / latency / conflict risk |
