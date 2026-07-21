# Kestrel — Multi-Agent Trading System (Design Documentation)

> **Kestrel** is the project codename. Built on the Zerodha Kite Connect API, it's named for the bird of prey — a cousin of the *kite* — that hovers dead-still to scan a wide field, then stoops on the one target worth striking. That is the system in one image: watch all 9,000 instruments broadly, act selectively through a single execution gateway.

**Status:** Design / pre-implementation (no code written yet)
**Last updated:** 2026-07-21
**Purpose of this repo (for now):** Capture the full architecture and design decisions agreed so far, in a form that can be reviewed by other agents/humans to find gaps *before* any implementation begins.

---

## What Kestrel is

A multi-agent platform built on the [Zerodha Kite Connect v3 API](https://kite.trade/docs/connect/v3/) that:

1. **Ingests** live and historical Indian market data (equities + F&O) at large scale (up to 9,000 streamed instruments).
2. **Studies** the market with a fleet of LLM agents — both *static* (historical/event-driven, offline batch) and *ongoing* (live, streaming-driven).
3. **Decides** via a funnel of agents (screeners → specialists → a single risk/portfolio manager).
4. **Executes** — initially against a **paper-trading simulator** (no real money), designed to flip to live later with the same interfaces.

The three confirmed product decisions driving this design:

| Decision | Choice |
|---|---|
| What it does with decisions | **Paper-trade first** (simulated execution, prove the logic before real money) |
| Hot-path technology | **Rust + Python** (Rust for the latency-sensitive data/execution planes, Python for the agent/cognition layer) |
| Instrument universe | **Max (3,000–9,000 instruments)** — uses all 3 WebSocket connections on one API key |

---

## How to review this documentation (for gap-finding agents)

Each document is self-contained. When reviewing, please look for:

- **Missing constraints** — anything about Kite Connect, market microstructure, or Indian market regulation we failed to account for.
- **Incorrect assumptions** — claims stated as fact that need verification (see `docs/11-open-questions-and-gaps.md` for the ones we already know about).
- **Architectural risks** — single points of failure, race conditions, unhandled failure modes.
- **Undefined behavior** — places where the design says *what* but not *how*, and the *how* is non-trivial.
- **Scope/strategy gaps** — this design is deliberately **strategy-agnostic plumbing**; the actual trading *edge* is not yet defined (flagged in doc 11). Note anywhere this bites.

The single most useful document to challenge is **`docs/11-open-questions-and-gaps.md`** — add to it.

---

## Document index

| # | Document | Covers |
|---|---|---|
| 01 | [Overview, Goals & Scope](docs/01-overview-goals-scope.md) | Vision, goals, non-goals, success criteria |
| 02 | [Kite Connect API Constraints](docs/02-kite-connect-constraints.md) | Every load-bearing API limit and fact |
| 03 | [System Architecture](docs/03-architecture.md) | Two-plane model, components, data flow |
| 04 | [Technology Stack](docs/04-tech-stack.md) | Stack choices + rationale + alternatives |
| 05 | [Agent Architecture](docs/05-agent-architecture.md) | Full agent roster, counts, coordination, the funnel |
| 06 | [Data Plane Spec](docs/06-data-plane.md) | Rust ingester, WebSocket, tiered subscription, parsing, storage |
| 07 | [Execution Plane Spec](docs/07-execution-plane.md) | Paper fill simulator, risk engine, P&L ledger, rate budget |
| 08 | [Cognition Plane Spec](docs/08-cognition-plane.md) | LangGraph orchestration, Claude tiering, static + live fleets, news & macro agents |
| 09 | [Phased Build Plan](docs/09-phased-build-plan.md) | Phases 0–6 with deliverables and exit criteria |
| 10 | [Prerequisites & Operations](docs/10-prerequisites-and-ops.md) | Subscription, daily login, deployment, observability, security |
| 11 | [Open Questions & Known Gaps](docs/11-open-questions-and-gaps.md) | The gap-finding target — assumptions, risks, undecided items |
| 12 | [Glossary](docs/12-glossary.md) | Terms, abbreviations, Kite/Indian-market vocabulary |

---

## Naming & namespaces

The project codename is **Kestrel**. Conventions to apply as code lands:
- **Repo / workspace:** `kestrel`
- **Rust services (hot plane):** `kestrel-ingester`, `kestrel-backfill`, `kestrel-quote`, `kestrel-execution`
- **Python package (cognition plane):** `kestrel`, with modules `kestrel.agents`, `kestrel.orchestrator`, `kestrel.news`, `kestrel.macro`
- **Redis streams / keys:** `kestrel:ticks`, `kestrel:candidates`, `kestrel:assessments`, `kestrel:orders`, `kestrel:news`, `kestrel:macro`
- **Metrics prefix (Prometheus):** `kestrel_*`
- Avoid `kite` / `zerodha` in internal names to prevent confusion with the broker's own product.

---

## Guiding principle (read this first)

> **Agent count is never set by the size of the market.** It is set by (a) Kite's *per-API-key* rate limits, which force the I/O-facing agents down to effectively one of each, and (b) the LLM latency/token budget on the cognition agents, which has sharply diminishing returns past ~30. Information-source agents (news, central banks) are cheap because they don't touch Kite's limits — but each only earns its place if its signal reaches a decision and changes an action.
