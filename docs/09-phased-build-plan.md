# 09 — Phased Build Plan

**Last updated:** 2026-07-21
**Status:** proposed; **not started** (awaiting go-ahead).

Each phase has deliverables and **exit criteria** — a phase isn't "done" until its exit criteria pass. Phases are mostly sequential but some overlap is noted.

---

## Phase 0 — Foundations
**Goal:** scaffolding everything later phases depend on.
- Repo structure (Rust workspace + Python package), config & secret handling.
- Daily login / token-minting helper (handles the 6 AM expiry; see doc 10 §2).
- Instruments-master loader + identity mapping (`exchange:tradingsymbol` ↔ token).
- **Redis contract stubs** for the event bus — including a **stubbed news/macro event schema** so those agents slot in later without rework.
- Observability skeleton (Prometheus + Grafana + structured logging).
- Sandbox connectivity check (API-contract validation harness).

**Exit criteria:** can authenticate, fetch & store the instruments master, publish/consume a test event on Redis, and see it on a Grafana panel.

---

## Phase 1 — Data plane (Rust ingester) — *first real milestone*
**Goal:** live market data flowing and stored.
- WebSocket ingester: 3 connections, subscription manager, tiered modes.
- Binary parser → canonical `Tick` → Redis cache + Redis Streams + QuestDB.
- Reconnection, gap detection, 403 handling, metrics.

**Exit criteria:** stream a few hundred instruments in mixed modes for a full session with **zero silent drops**, auto-reconnect verified, tick-to-cache p99 < 5 ms, and QuestDB ingest keeping up. Then scale toward the 9,000 target and **measure** ingest throughput/disk growth (validates doc 11, Gap G-03/G-04).

---

## Phase 2 — Historical + research store
**Goal:** data for the static study fleet.
- Resumable, rate-governed (3/s) backfill to QuestDB; per-(instrument,interval) high-water marks.
- DuckDB/Parquet research store; corporate-action adjustment decision (Gap G-08).

**Exit criteria:** backfill a representative universe across intervals, resume correctly after a kill, and run a sample analytical query in DuckDB within target time.

---

## Phase 3 — Paper execution engine (Rust)
**Goal:** a trustworthy paper broker.
- `OrderIntent`/`OrderAck` interface; fill simulator (slippage/latency/partials) vs. live ticks.
- Deterministic risk engine + kill-switch; P&L ledger with Indian cost model.
- **Event-window de-risk rule wired in early** (from the macro calendar), even before the LLM macro agent exists.

**Exit criteria:** submit scripted intents, get realistic fills, see correct P&L, trip the kill-switch on a simulated daily-loss breach, and reconcile position state with zero drift over a session.

---

## Phase 4 — Static study fleet (cognition)
**Goal:** the offline "study the market" capability.
- LangGraph batch fleet (8–24 agents) over cached data → ranked watchlist + regime priors + **Full-mode promotion list** consumed by the subscription manager.
- Reproducible, look-ahead-safe runs.

**Exit criteria:** a nightly run produces a stable, explainable watchlist + promotion list; promoting those instruments to Full mode the next morning works end-to-end.

---

## Phase 4.5 — News sub-pipeline
**Goal:** catalyst awareness. (Built after the baseline so its P&L contribution is measurable.)
- Ingest+dedupe+entity-resolve → structured classify/sentiment → impact analyst (high-salience).
- Feeds screeners, risk manager, and the promotion list; enforces the instruction-source boundary (doc 08 §6).

**Exit criteria:** a live corporate announcement is fetched, deduped, correctly resolved to the right instrument token, and produces a catalyst flag + Full-mode promotion — with raw text never entering downstream reasoning.

---

## Phase 5 — Live cognition funnel (+ macro agent)
**Goal:** the operating heart.
- Screeners → specialists → risk/portfolio manager → paper execution.
- Macro/central-bank agent: regime state + event scheduler feeding the manager.
- Backpressure, structured I/O, audit trail per order.

**Exit criteria:** run a full paper session where flags → assessments → sized intents → simulated fills, every order traceable to its agent chain + data, within risk limits, with the manager as sole writer.

---

## Phase 6 — Hardening & go/no-go
**Goal:** make it trustworthy; decide about live.
- Failure injection (WS drop, Redis blip, token expiry mid-session, source outage).
- Reconciliation, alerting, dashboards, runbooks.
- **Regulatory review** (SEBI algo framework — Gap G-02) and **ToS review** (multi-key, automated login — Gaps G-05, G-12).
- Paper-performance review vs. success criteria (doc 01 §6).

**Exit criteria (to even *consider* live):** N sessions of stable paper operation, validated fill fidelity, all failure modes handled gracefully, regulatory/ToS questions resolved, and an explicit human go/no-go. **Live is out of scope until this passes.**

---

## Recommended starting point
**Phase 0 + Phase 1** — foundations plus the Rust data-plane ingester (with the news/macro event schema stubbed into Phase 0). This is the milestone that de-risks the hardest scale question (9,000-instrument ingest) earliest.

## Dependencies at a glance
```
0 ─► 1 ─► 2 ─► 4 ─► 4.5 ─► 5 ─► 6
      └──────► 3 ──────────► 5
(3 depends on 1 for live ticks; 5 depends on 2,3,4; 4.5 before/with 5)
```
