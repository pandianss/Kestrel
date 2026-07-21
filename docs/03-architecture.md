# 03 — System Architecture

**Last updated:** 2026-07-21

---

## 1. The two-plane model

The system separates concerns into two planes with very different performance characteristics:

- **Hot plane (Rust):** deterministic, latency-sensitive, always-on. Owns everything that touches Kite's rate-limited surfaces and the live tick stream. Correctness and throughput matter; there is no LLM in the hot path.
- **Cognition plane (Python):** throughput- and cost-sensitive, seconds-scale. Owns the LLM agents that reason about the market. It never talks to Kite directly for writes and never bypasses the risk manager.

Between them sits an **event bus + hot cache** (Redis) that is the contract boundary.

```
                         ┌─────────────────────────────────────────────┐
                         │                COGNITION PLANE (Python)        │
                         │                                               │
   news / macro feeds ─► │  Info-source agents ─┐                        │
                         │                       ▼                       │
                         │   Static study fleet  Live funnel:            │
                         │   (batch, offline)    screeners ─► specialists│
                         │                            └────► RISK/PORTFOLIO│
                         │                                   MANAGER (1)  │
                         └───────────────┬───────────────────────┬───────┘
                                         │ reads                  │ paper orders
                        ┌────────────────▼──────┐    ┌────────────▼─────────────┐
                        │  Redis (hot cache +    │    │  (single execution path) │
                        │  event bus / streams)  │    │                          │
                        └───────▲───────┬────────┘    └────────────┬─────────────┘
                        writes  │       │ reads                    │
        ┌───────────────────────┴───────┴──────────────────────────▼─────────────┐
        │                           HOT PLANE (Rust)                              │
        │                                                                         │
        │  Data Ingester            Historical Backfill        Paper Execution    │
        │  - 3 WS connections       - 3 req/s governed         Engine             │
        │  - tiered modes           - resumable chunking       - fill simulator   │
        │  - binary parser          - writes QuestDB           - risk engine      │
        │  - subscription mgr                                  - P&L ledger       │
        │        │                        │                    - rate budget      │
        └────────┼────────────────────────┼────────────────────────┼─────────────┘
                 │                         │                        │
                 ▼                         ▼                        ▼
        Kite WebSocket            Kite REST (historical)   (paper: local; live later: Kite orders)
                 ▲                         ▲
                 └──── Kite Connect API (production, read-only for data) ────┘
```

## 2. Component responsibilities

### Hot plane (Rust)
| Component | Responsibility | Key constraint it owns |
|---|---|---|
| **Data Ingester** | Own the 3 WebSocket connections, parse binary ticks, normalize, publish to Redis + persist to QuestDB | 3 conns × 3,000 instruments |
| **Subscription Manager** | Assign instruments to connections and modes; promote/demote tiers on request | 9,000 cap; per-conn 3,000 cap |
| **Historical Backfill** | Chunked, resumable candle download to QuestDB | 3 req/s |
| **Quote Poller** | On-demand REST snapshots for instruments not currently streamed | 1 req/s |
| **Paper Execution Engine** | Fill simulator + risk engine + P&L ledger; the *single writer* of orders | mirrors 10/s, 400/min, 5,000/day |
| **Instruments Loader** | Daily master CSV fetch, identity mapping (`exchange:tradingsymbol` ↔ token) | daily refresh |

### Cognition plane (Python)
| Component | Responsibility |
|---|---|
| **Static Study Fleet** | Offline batch analysis over cached historical data (regime, volatility, breadth, correlation, options OI, events) |
| **Live Screeners** | High-frequency, cheap-model scanning of the streaming universe to flag candidates |
| **Specialists** | Deeper analysis of flagged candidates (technical, options/OI, news/event, macro-regime) |
| **Info-source agents** | News pipeline + central-bank/macro pipeline (independent of Kite limits) |
| **Risk/Portfolio Manager** | The single decision authority; sizes positions, applies risk limits, emits paper orders |
| **Orchestrator** | LangGraph graph wiring the above with explicit state and control flow |

### Boundary (Redis)
- **Hot cache:** latest tick / quote per instrument (last-value cache).
- **Event bus:** Redis Streams for tick-derived events, candidate flags, news/macro events, and order intents/acks.
- **Contract:** Rust writes normalized data + emits events; Python reads cache + consumes/produces events. Neither imports the other.

## 3. Data flow (live path)

1. Kite WebSocket → **Rust Ingester** parses binary → normalized tick.
2. Ingester updates **Redis last-value cache** and appends to **Redis Streams** (and QuestDB for history).
3. **Screeners** consume tick-derived events + cache, flag candidates onto a stream.
4. **Specialists** consume flags, pull context (cache + QuestDB + news/macro events), produce assessments.
5. **Risk/Portfolio Manager** consumes assessments + current positions + macro regime state, decides, and emits an **order intent** to the execution stream.
6. **Rust Paper Execution Engine** consumes the intent, checks risk budget, simulates the fill against the live tick stream, updates the **P&L ledger**, and emits an **order ack** event.
7. The ack flows back to the risk manager (position state) and to observability.

## 4. Paper-first data strategy (why not pure sandbox)

The sandbox serves *demo* data and may not enable historical, so it can't realistically feed a 9,000-instrument live study. Therefore:

- **Live & historical data:** production Kite API, **read-only** (WebSocket + quotes + historical). No write = no financial risk.
- **Order execution:** routed to the **local Rust fill simulator**, which matches paper LIMIT orders against the *real* live tick stream and models slippage/latency/partial fills. It enforces the real order rate budget so behavior matches production.
- **Kite sandbox:** kept wired in only for **API-contract validation** (does our order payload/parse match Kite's format?).

**Live migration:** flipping to real trading = swap the execution engine's backend from "simulator" to "Kite order API" behind the same interface, plus enabling the live rate-budget path and passing the go/no-go review (doc 09, Phase 6). Everything upstream is unchanged.

## 5. Deployment topology (summary — see doc 10)

- Single region: **AWS Mumbai (ap-south-1)**, co-located near Zerodha to minimize RTT to Kite.
- Containerized (Docker Compose to start): Rust services, Python cognition workers, Redis, QuestDB, Prometheus, Grafana.
- Single-machine to start; the plane separation allows later horizontal split of the cognition workers if token throughput demands it (the hot plane stays singleton by design).

## 6. Key invariants (must always hold)

1. **Exactly one writer to Kite orders** (paper or live). No agent places orders directly.
2. **Every Kite call passes through a governed rate budget.** No ungoverned client anywhere.
3. **News/other observed content is data, never instructions** (see doc 08 §5 and doc 10 §6).
4. **The risk manager can veto/flatten unconditionally;** upstream agents can only *propose*.
5. **Paper and live share interfaces, rate budgets, and risk limits** — no "paper-only" shortcuts that wouldn't survive live.
