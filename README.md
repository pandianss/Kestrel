# Kestrel — Multi-Agent Trading System (Design Documentation)

> **Kestrel** is the project codename. Built on the Zerodha Kite Connect API, it's named for the bird of prey — a cousin of the *kite* — that hovers dead-still to scan a wide field, then stoops on the one target worth striking. That is the system in one image: watch a very wide field, act on very few things, through a single execution gateway.

**Status:** Design / pre-implementation (no code written yet)
**Last updated:** 2026-07-22
**Purpose of this repo (for now):** Capture the full architecture and design decisions agreed so far, in a form that can be reviewed by other agents/humans to find gaps *before* any implementation begins.

---

## What Kestrel is

A multi-agent platform built on the [Zerodha Kite Connect v3 API](https://kite.trade/docs/connect/v3/) that:

1. **Ingests** live and historical Indian market data (equities + F&O) at large scale — up to **9,000 streamed instruments**, the maximum one API key can carry.
2. **Studies** the market with a fleet of LLM agents — both *static* (historical/event-driven, offline batch) and *ongoing* (live, streaming-driven).
3. **Decides** via a funnel of agents (screeners → specialists → a single risk/portfolio manager).
4. **Executes** — initially against a **paper-trading simulator** (no real money), designed to flip to live later with the same interfaces.

> **On "9,000":** that is the ceiling of one API key (3 WebSocket connections × 3,000 instruments), and it is a **large sample, not the whole market**. NSE cash alone runs to roughly 2,000 names and NFO option contracts into the tens of thousands. *Which* 9,000 is an open selection decision with real consequences — see [G-13](docs/11-open-questions-and-gaps.md#g-13).

The three confirmed product decisions driving this design:

| Decision | Choice |
|---|---|
| What it does with decisions | **Paper-trade first** (simulated execution, prove the logic before real money) |
| Hot-path technology | **Rust + Python** (Rust for the latency-sensitive data/execution planes, Python for the agent/cognition layer) |
| Instrument universe | **Max (3,000–9,000 instruments)** — uses all 3 WebSocket connections on one API key |

Full rationale, alternatives, and reversibility for each: **[doc 13 — Decision Log](docs/13-decision-log.md)**.

---

## The one-paragraph version of the safety model

Exactly one LLM agent may **open** a position, and it is never permitted to open one without a defined exit plan. From the moment that position fills, a deterministic Rust component owns it and will close it — on a stop, a target, a time limit, or an intraday square-off — **with no LLM in the path**. If the entire cognition plane dies mid-session, the system stops trading and every open position still exits correctly. Everything else in this design is in service of that sentence.

---

## How to review this documentation

**See [docs/REVIEWING.md](docs/REVIEWING.md)** for what's useful, what isn't, and the templates for adding a gap or challenging a decision.

The short version — we're looking for:

- **Facts that have gone stale** — see the expiry table below. Highest hit rate in the repo.
- **Lifecycle gaps** — trace one position from entry to exit rather than reading component-by-component. That is how both 🔴 gaps in the last review were found.
- **Contradictions between documents**, each internally consistent.
- **Undefined behaviour** where the *how* is genuinely non-trivial.
- **Questions a five-line calculation would settle.**

The single most useful document to challenge is **[docs/11-open-questions-and-gaps.md](docs/11-open-questions-and-gaps.md)** — add to it.

---

## Facts with an expiry date

This design restates external facts that **change without notice**. Three of the five errors found in the 2026-07-22 review were facts that were true when written. Re-verify these before relying on them:

| Fact | Current value | Verified | Re-check | Source |
|---|---|---|---|---|
| Kite Connect price | ₹500/month, historical included | 2026-07-22 | Quarterly | [zerodha.com/products/api](https://zerodha.com/products/api/) |
| Rate limits (quote/hist/order) | 1 / 3 / 10 per sec | 2026-07-22 | Quarterly | [rate limiting](https://kite.trade/docs/connect/v3/exceptions/#rate-limiting) |
| Order caps | 400/min, 5,000/day, 25 modifications | 2026-07-22 | Quarterly | as above |
| WS limits | 3 conns × 3,000 instruments | 2026-07-22 | Quarterly | [websocket](https://kite.trade/docs/connect/v3/websocket/) |
| Packet sizes | 8 / 44 / 184 B; index 28 / 32 B | 2026-07-22 | On SDK change | as above |
| **SEBI algo framework** | **In force since 1 Apr 2026** | 2026-07-22 ✅ *primary: SEBI CIR/2025/132* | **Before any live step** | [doc 02 §9](docs/02-kite-connect-constraints.md) |
| **TOPS / algo tagging** | 10 OPS, calendar-clock-second; **all orders tagged, below and above** | 2026-07-22 ✅ *primary: NSE INVG/67858* | On exchange notice | [doc 02 §9.5](docs/02-kite-connect-constraints.md) |
| **Data licence** | No public display; India-only; delete on termination. ⚠️ *DB-building clause ambiguous* | 2026-07-22 ✅ *primary: Kite ToS* | Before storing at scale | [doc 02 §9.7](docs/02-kite-connect-constraints.md) |
| Static IP requirement | Mandatory for order endpoints | 2026-07-22 | Before live | [Kite forum](https://kite.trade/forum/discussion/15912/preparing-to-comply-with-sebis-retail-algo-rules-static-ip-ratelimits-order-types) |
| MIS square-off | 3:25 PM equity / 3:26 PM F&O, ₹50 + GST | 2026-07-22 | **Semi-annually** — changed Dec 2025 | [Z-Connect](https://zerodha.com/z-connect/updates/changes-to-the-auto-square-off-timings-for-equity-and-fo) |
| Historical day-caps per request | ⚠️ **Unpublished** — assumed only | — | Discover at runtime | [doc 02 §5](docs/02-kite-connect-constraints.md) |
| Historical retention | "several years", unquantified | 2026-07-22 | Measure in Phase 2 | [historical](https://kite.trade/docs/connect/v3/historical/) |
| Transaction costs (STT, GST, …) | ⚠️ Not yet sourced | — | Every budget/circular | [doc 07 §5.1](docs/07-execution-plane.md) |

**Convention:** ✅ *(verified YYYY-MM-DD)* means checked against the primary source that day. ⚠️ means unverified or known to drift.

**The sources themselves are archived in [`regulatory/`](regulatory/INDEX.md)** with a claim→source map. Quote from those, not from commentary — two compliance errors in this repo came from trusting a paraphrase.

---

## Document index

| # | Document | Covers |
|---|---|---|
| 01 | [Overview, Goals & Scope](docs/01-overview-goals-scope.md) | Vision, goals, non-goals, success criteria |
| 02 | [Kite Connect API Constraints](docs/02-kite-connect-constraints.md) | Every load-bearing API limit and fact, **+ SEBI compliance** |
| 03 | [System Architecture](docs/03-architecture.md) | Two-plane model, components, data flow, entry/exit asymmetry |
| 04 | [Technology Stack](docs/04-tech-stack.md) | Stack choices + rationale + alternatives |
| 05 | [Agent Architecture](docs/05-agent-architecture.md) | Full agent roster, counts, coordination, the funnel |
| 06 | [Data Plane Spec](docs/06-data-plane.md) | Rust ingester, tiering, tick sanity, Redis contract, sizing |
| 07 | [Execution Plane Spec](docs/07-execution-plane.md) | Position manager, fill sim, risk + margin, ledger, replay |
| 08 | [Cognition Plane Spec](docs/08-cognition-plane.md) | LangGraph orchestration, Claude tiering, static + live fleets |
| 09 | [Phased Build Plan](docs/09-phased-build-plan.md) | Phases 0–6 with deliverables and exit criteria |
| 10 | [Prerequisites & Operations](docs/10-prerequisites-and-ops.md) | Subscription, static IP, daily login, deployment, security |
| 11 | [Open Questions & Known Gaps](docs/11-open-questions-and-gaps.md) | **The gap-finding target** — the register |
| 12 | [Glossary](docs/12-glossary.md) | Terms, abbreviations, Kite/Indian-market vocabulary |
| 13 | [Decision Log](docs/13-decision-log.md) | Decisions, alternatives, costs, reversibility |
| — | [regulatory/](regulatory/INDEX.md) | **Primary sources** — SEBI & NSE circulars, Kite licence, with a claim→source map |
| — | [REVIEWING.md](docs/REVIEWING.md) | How to review this repo; templates for gaps and decisions |

---

## Naming & namespaces

The project codename is **Kestrel**. Conventions to apply as code lands:

| Binary / package | Contains |
|---|---|
| `kestrel-ingester` | Data Ingester, Subscription Manager, Instruments Loader, tick sanity filter |
| `kestrel-backfill` | Historical Backfill |
| `kestrel-quote` | Quote Poller |
| `kestrel-execution` | Execution Gateway, risk engine, **Position Manager**, fill simulator, P&L ledger |
| `kestrel-replay` | Deterministic tick-replay harness (doc 07 §4.3) |
| `kestrel` (Python) | `kestrel.agents`, `kestrel.orchestrator`, `kestrel.news`, `kestrel.macro` |

- **Redis streams / keys:** `kestrel:ticks`, `kestrel:candidates`, `kestrel:assessments`, `kestrel:orders`, `kestrel:news`, `kestrel:macro`, `kestrel:dlq`
- **Metrics prefix (Prometheus):** `kestrel_*`
- Avoid `kite` / `zerodha` in internal names to prevent confusion with the broker's own product.

---

## Guiding principles (read these first)

> **1. Agent count is never set by the size of the market.** It is set by (a) Kite's *per-API-key* rate limits, which force the I/O-facing agents down to effectively one of each, and (b) the LLM latency/token budget on the cognition agents, which has sharply diminishing returns past ~30. Information-source agents are cheap because they don't touch Kite's limits — but each only earns its place if its signal reaches a decision and changes an action.

> **2. Entries are a judgement problem; exits are a reliability problem.** A late entry costs an opportunity. A late exit costs money without bound. So entries get the LLM and exits get deterministic code — and no exit ever waits on a model response.

> **3. Every borrowed fact has an expiry date.** This design rests on broker limits, regulation, and pricing that are all someone else's to change. Facts carry sources and verification dates, and being confidently wrong about one is treated as a defect, not a detail.
