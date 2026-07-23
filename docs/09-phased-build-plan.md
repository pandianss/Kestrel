# 09 — Phased Build Plan

**Last updated:** 2026-07-23
**Status:** proposed; **not started** (awaiting go-ahead).

Each phase has deliverables and **exit criteria** — a phase isn't "done" until its exit criteria pass. Phases are mostly sequential but some overlap is noted.

---

## Phase 0 — Foundations & compliance
**Goal:** scaffolding everything later phases depend on — including the regulatory groundwork, which is now a build-time dependency rather than a pre-live checklist.

- Repo structure (Rust workspace + Python package), config & secret handling.
- Daily login / token-minting helper (handles the 6 AM expiry; see doc 10 §2).
- Instruments-master loader + identity mapping (`exchange:tradingsymbol` ↔ token).
- 🔴 **Dated, immutable daily snapshots** of the instruments master, F&O ban list, and circuit limits — **not overwrites** (G-43). A few MB/day, and **unrecoverable if skipped**: without them every backtest carries survivorship bias and there is no archive to backfill from. Every day the ingester runs without this destroys research data.
- **Redis contract**: versioned event schemas generated for both planes from one source, stream `MAXLEN` caps, consumer groups, DLQ — including a **stubbed news/macro event schema** so those agents slot in later without rework (doc 06 §2.1).
- Observability skeleton (Prometheus + Grafana + structured logging).
- Sandbox connectivity check (API-contract validation harness).
- **⚠️ SEBI/ToS groundwork — moved here from Phase 6** *(revised 2026-07-22; the framework took full effect 1 April 2026, so this can no longer be deferred)*:
  - **Provision and register a static IP** (Elastic IP, ap-south-1) in the Kite developer profile's IP whitelist. Orders from unwhitelisted IPs are rejected outright.
  - ✅ **Resolved — not an algo provider.** Self + immediate family on a single account is exempt from empanelment (doc 02 §9.4). No action needed; recorded here because it was the question that could have reshaped the project.
  - **Obtain the generic Algo ID** and confirm how it attaches — bound server-side to the API key, or passed per order? ⚠️ *Every API order must carry an algo tag; there is no exempt volume (doc 02 §9.3).* Plumb `algo_id` as a required field from the first order the simulator ever sees.
  - ✅ **Client-level OPS limit confirmed: 10** (owner, 2026-07-22). G-39's book sizing stands. Read from config — TOPS is adjustable on exchange notice.
  - ✅ **Local storage for backtesting: proceeding** (owner, 2026-07-22) on the basis that data is never shared, displayed, or redistributed. Recorded as an accepted risk, not an external ruling (G-15). Standing constraints: dashboards on-host behind VPN, alerts carry state not prices, host stays in India.
  - Confirm TOPS scope — the NSE circular says "per exchange" in §B.2 and "per exchange/segment" in §F. Budget per *exchange* (stricter) until answered.
  - Implement the order limiter on the **calendar clock second**, not a rolling window, targeting 8/s (doc 02 §9.5).
  - Record the answers, with dates, in doc 13 (decision log). These are the questions that can invalidate the project, so ask them before writing the ingester, not after.

**Exit criteria:** can authenticate, fetch & store the instruments master, publish/consume a **versioned** test event on Redis through a consumer group, see it on a Grafana panel — **and have written confirmation from Zerodha on the three compliance questions above.**

---

## Phase 1 — Data plane (Python) — *not the first milestone any more*

> ⚠️ **Re-sequenced (D-09 / D-16 / D-02):** the factor backtest and vertical slice come first (see "Recommended starting point"). The data plane is now **Python** (D-02), and under end-of-day cadence it streams only held names — so this is a modest component, not the hardest-scale milestone it once was.
**Goal:** live market data flowing and stored.
- WebSocket ingester (**Python, D-02**): the held-book stream (Full mode) plus daily-bar REST pulls for screening. The 3-connection / tiered-mode machinery is intraday-only and not built for the end-of-day design.
- Binary parser → canonical `Tick` → **tick sanity filter** → Redis cache + Redis Streams + QuestDB.
- Reconnection, gap detection, 403 handling, metrics.
- **Tick capture + deterministic replay harness (doc 07 §4.3)** — every subsequent phase depends on it: fill-fidelity validation (G-09), look-ahead-safe **deterministic-plane** backtests (G-23), risk-engine regression tests, and incident reproduction. ⚠️ It does **not** backtest the agent fleet (G-42). It is built here because this is where its input first exists.

**Exit criteria (rescoped for D-16):** stream the **held book (~10 names) plus a few test instruments** for a full session with **zero silent drops** and verified auto-reconnect; pull daily bars for the screening universe via REST; a captured session **replays byte-identically across the hot plane**. ⚠️ The old "scale toward 9,000, p99 < 5 ms" criterion is **dropped** — an end-of-day system never live-streams the universe (G-03 downgraded 🔴→🟡).

---

## Phase 2 — Historical + research store
**Goal:** data for the static study fleet.
- Resumable, rate-governed (3/s) backfill to QuestDB; per-(instrument,interval) high-water marks.
- DuckDB/Parquet research store; corporate-action adjustment decision (Gap G-08).
- **Reference data resolved as-of the simulation date**, never as-of now (G-43).
- **Backtest spec — scoped to the deterministic plane only** (G-42): pre-registration, hold-out, walk-forward, and a stated multiple-comparison protocol. ⚠️ The cognition plane is **not** backtestable; it is forward-tested in Phase 5.

**Exit criteria:** backfill a representative universe across intervals, resume correctly after a kill, and run a sample analytical query in DuckDB within target time.

---

## Phase 3 — Paper execution engine (Rust safety core — D-02)
**Goal:** a trustworthy paper broker.
- `OrderIntent`/`OrderAck` interface (including `market_protection`, `intent_kind`, and the mandatory `exit_plan`); fill simulator (slippage/latency/partials) vs. live ticks.
- Deterministic risk engine + kill-switch; **margin model** (doc 07 §3.1); P&L ledger with the dated Indian cost model **including the auto-square-off charge**.
- **Position Manager** — stops, targets, time-exits, MIS square-off, feed-loss policy. The exit path must work with the entire cognition plane stopped.
- **Event-window de-risk rule wired in early** (from the macro calendar), even before the LLM macro agent exists.

**Exit criteria:** submit scripted intents, get realistic fills, see correct P&L net of modelled costs, trip the kill-switch on a simulated daily-loss breach, and reconcile position state with zero drift over a session.

**Additional exit criteria for the exit path — all must pass with Python stopped:**
- A stop-loss fires and fills with every cognition-plane process killed.
- *(If MIS is ever used)* an MIS position auto-squares before the broker's cut-off with the ₹50 + GST charge in the ledger. ⚠️ Under D-16 the default is **CNC/NRML**, so the primary exit-path test is a **stop firing on the held book with the cognition plane killed**, and overnight-gap handling (G-18).
- A simulated feed outage triggers the configured `on_data_loss` behaviour per product.
- An exit is accepted while the account is over its exposure cap and while the kill-switch is tripped (risk checks must not block risk reduction).
- A margin breach trips the kill-switch.

---

## Phase 4 — Static study fleet (cognition)
**Goal:** the offline "study the market" capability.
- LangGraph batch fleet over cached data → ranked watchlist + regime priors. ⚠️ *No "Full-mode promotion list" under D-16* — there is no live tiering to promote into; the watchlist feeds the **next-morning decision**, and only *held* names are streamed.
- Reproducible, look-ahead-safe runs. **This fleet is an overlay on the documented factor (D-17), not the primary signal.**

**Exit criteria:** a nightly run produces a stable, explainable watchlist + regime priors that measurably improve on the factor-alone baseline (else it does not earn its token cost — G-44).

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

⚠️ **Phase 5 is not a rehearsal — it is the only validation the cognition plane will ever get** (G-42). LLM judgement cannot be backtested: the model has seen the historical period, a full-year replay would cost ~$28k per run, and responses are non-deterministic. **Decide in advance what forward-test evidence would be sufficient** — before anyone is looking at a P&L curve they like. Per-decision agent-chain attribution is the only way to tell whether the agents added anything over the deterministic spine.

---

## Phase 6 — Hardening & go/no-go
**Goal:** make it trustworthy; decide about live.
- Failure injection (WS drop, Redis blip, token expiry mid-session, source outage, **cognition-plane death with open positions**, **Redis memory pressure**).
- **Adversarial prompt-injection testing** against the news pipeline (G-24) — a crafted item that tries to hijack the loop must fail to change an action.
- Reconciliation, alerting, dashboards, runbooks.
- **Final regulatory confirmation** — the *groundwork* moved to Phase 0; what remains here is confirming nothing changed in the interim, and closing out ToS questions (G-05, G-12).
- Paper-performance review vs. success criteria (doc 01 §6).

**Exit criteria (to even *consider* live):** N sessions of stable paper operation, validated fill fidelity, all failure modes handled gracefully, regulatory/ToS questions resolved, and an explicit human go/no-go. **Live is out of scope until this passes.**

---

## Recommended starting point — revised 2026-07-23 for D-16 / D-17

The original "Phase 0 + Phase 1: build the 9,000-instrument ingester first" is **no longer the right start.** D-16 (end-of-day positional) removes the 9,000-instrument live-ingest problem that Phase 1 existed to de-risk, and D-17 (documented factor) gives a concrete, deterministic strategy to build *before* any of it. D-09 is now settled: **strategy-first.**

The strategy-first sequence:

1. **Phase 0 essentials** — repo, config, secrets, the Redis contract, **and the point-in-time snapshotter** (G-43, losing data every day it doesn't exist). No static IP needed yet; the compliance answers are in.
2. **The factor backtest** — pick a documented anomaly (D-17), pull point-in-time daily bars, model Indian costs (doc 07 §5.1), and answer *"does this edge survive here?"* **before any live wiring.** Deterministic, cheap, and it is where a real edge is either found or ruled out. This is the highest-information, lowest-cost work in the project.
3. **The vertical slice** — one instrument, the factor rule, the real fill simulator and Position Manager, no LLMs. Exercises the exit path, margin, and cost model end-to-end. Now runs a *researched* strategy, so its paper results mean something.
4. **The end-of-day live plane** — daily screen, pre-open decide, live-stream only held names. Small, because D-16 made it small.
5. **The LLM overlay — last, and only if it earns its cost** (G-44): does factor + agents beat factor alone, net of tokens?

⚠️ **The two 🔴 gaps this review found** — no exit path (G-28), no margin model (G-29) — were invisible in documents and surface on the first real position. Steps 2–3 hit them early and cheaply, which is the whole point of going strategy-first.

⚠️ **A Python-only build is now viable** (D-02 re-opened): with no 9,000-instrument ingest, the Rust case shrinks to a small safety core. Decide D-02 before committing to two toolchains — it may be one.

## Dependencies at a glance
```
0 ─► 1 ─► 2 ─► 4 ─► 4.5 ─► 5 ─► 6
      └──────► 3 ──────────► 5
(3 depends on 1 for live ticks and the replay harness; 5 depends on 2,3,4; 4.5 before/with 5)
```
