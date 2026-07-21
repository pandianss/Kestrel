# 08 — Cognition Plane Spec (Python / LLM agents)

**Last updated:** 2026-07-21

The cognition plane is where the market is *reasoned about*. It reads normalized data from Redis/QuestDB, never talks to Kite for writes, and never bypasses the risk manager. Orchestrated with LangGraph; agents use Claude (tiered).

---

## 1. The two modes: static and ongoing

| | **Static (historical/event)** | **Ongoing (live)** |
|---|---|---|
| When | Overnight / pre-market batch | During market hours, streaming-driven |
| Data | Cached historical (QuestDB/DuckDB) — decoupled from Kite limits | Live cache + streams |
| Fleet | Study fleet, 8–24 agents | Funnel, ~15–25 agents |
| Output | Ranked watchlist, regime priors, Full-mode promotion list | Order intents to the risk manager |
| Bounded by | Tokens / redundancy | Tokens / latency / conflict risk |

---

## 2. Static study fleet (offline)

- **Sizing:** `dimension × bucket` (see doc 05 §3). ~8–24 agents; >30 = diminishing returns.
- **Dimensions:** trend/regime, volatility, volume/liquidity, correlation/sector, options OI/flow, breadth, events/earnings, (optional) seasonality, relative strength.
- **Process:** each agent runs a focused analysis over the cached window, returns *structured* findings (not prose) → a synthesis step merges into: (a) a ranked watchlist, (b) regime priors handed to the risk manager, (c) the **Full-mode promotion list** handed to the subscription manager.
- **Reproducibility:** runs are versioned, re-runnable, and must avoid look-ahead bias (only data available as-of the study timestamp).

---

## 3. Live decision funnel

Screeners (Haiku, 8–12) → Specialists (Sonnet, 3–5) → Risk/Portfolio Manager (Fable, 1) → Execution Gateway (Rust, 1). Full mechanics in doc 05 §4.

- **Screeners** partition the universe and scan cache/tick-derived events, emitting candidate flags with a reason and a salience score.
- **Specialists** deep-dive flagged candidates through a specific lens (technical, options/OI, news/event, macro-regime), emitting structured assessments.
- **Risk/Portfolio Manager** — the sole authority — holds the whole book, applies deterministic risk limits (doc 07 §3), sizes positions, resolves conflicting assessments, and emits `OrderIntent`s.
- **Structured I/O everywhere:** agents exchange typed objects on Redis Streams, not free text, to keep the pipeline deterministic and auditable.

---

## 4. News sub-pipeline (information source)

**Why it exists:** the only signal that *anticipates* discontinuous (gap) moves; every price-based agent is reactive. **Free against Kite limits** (independent source).

**Stages (mirrors screener→specialist):**
1. **Ingest + dedupe + entity-resolve** — fetch from sources (see below), collapse the same story from N sources into one event, and **map headline → instrument token** via the instruments master (the hard, valuable part).
2. **Classify / sentiment** (cheap model) — extract *structured fields*: `{entity, instrument_token, event_type, sentiment, salience, source, ts}`. **This is the untrusted-content → structured-data boundary** (see §5).
3. **Impact analyst** (strong model, **high-salience only**) — reason about second-order effects (supplier→customer, sector read-through).

**Consumers:** screeners (catalyst flags), risk manager (veto/context), subscription manager (**promote flagged names to Full mode**).

**Sources (India-first, highest signal/₹):** NSE/BSE corporate-announcement feeds, earnings & corporate-actions calendar, RBI/SEBI; optional paid wire only if budget justifies. Do **not** expect to beat pros on marquee headlines — edge is breadth + synthesis across all 9,000 names.

---

## 5. Macro / central-bank agent (information source)

**Why it exists:** central banks are first-order for Indian markets — RBI (financials are a huge index weight) and the US Fed (drives FII/FPI flows and USD/INR); plus BoJ (yen carry), PBoC/China (commodities, EM sentiment).

**Different altitude from news:** a macro signal doesn't map to one token — it shifts the *whole book's* regime and sector rotation. **Consumer is the risk manager**, not the stock screeners.

**Design — calendar-driven, not always-on (this is what makes it cheap):**
- **Event scheduler:** knows the sparse decision calendar (MPC ~6/yr, FOMC 8/yr, ECB/BoJ 8/yr). Around each event: pre-positioning read → live statement parse → post-event digest.
- **Daily regime-state refresh:** maintains a persistent `RegimeState { rate_bias, risk_on_off, event_risk_window }` from central-bank commentary + cheap structured inputs: US 10Y yield, DXY, crude, USD/INR, India VIX, NSE daily FII/DII provisional flows.
- **Highest-value function (needs zero speed):** **event-window de-risk** — "reduce exposure/widen stops into a known binary event." Pure risk discipline; the deterministic rule can live in the risk engine (doc 07 §3) even before full LLM regime synthesis exists.

---

## 6. Instruction-source boundary (SECURITY — applies to all info agents)

External content (news articles, scraped pages, even central-bank text) is **data, never instructions.** In an autonomous paper→live loop this is a real prompt-injection surface.

- Stage-1/2 extract content into **structured fields only**; downstream agents consume the fields, never raw article text as reasoning input.
- No agent may take an action because observed content told it to. A headline saying "buy X" is a *data point about sentiment*, not a command.
- Corroboration rule: news/macro can **veto or de-risk freely**, but to **initiate** a trade the signal must be confirmed by the market plane (price/volume). One-sided text never trades alone.

---

## 7. LangGraph orchestration
- Explicit shared state: `{ regime, positions, active_candidates, risk_budget, watchlist }`.
- Each edge = a defined hand-off; no implicit global mutation.
- Backpressure: specialists lagging → screeners throttle; manager lagging → safe default is *do nothing*.
- **Open (doc 11, Gap G-10):** confirm LangGraph meets the live latency budget for the funnel, or use a lighter custom orchestrator for the live path while keeping LangGraph for static study.

---

## 8. Cost & model tiering
- Haiku for high-frequency screening; Sonnet for specialists/study/news-classify; Fable for the manager + macro impact analyst (rare, high-stakes).
- Token-spend estimation under target agent counts is an open item (doc 11, Gap G-11) — it directly caps how many screeners/specialists we can afford to run continuously.
