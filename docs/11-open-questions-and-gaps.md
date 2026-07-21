# 11 — Open Questions & Known Gaps

**Last updated:** 2026-07-21

> **This is the gap-finding target.** These are the things we already know are undecided, unverified, or risky. Reviewing agents/humans should (a) challenge these, (b) add ones we missed, and (c) flag anywhere the rest of the design contradicts itself. Each gap has an ID, severity, and a proposed direction — the proposed direction is *not* a decision.

**Severity key:** 🔴 blocker (must resolve before/at that phase) · 🟠 significant · 🟡 to firm up.

---

## A. Strategy & product

### G-01 🔴 — There is no trading strategy yet
The entire design is **strategy-agnostic plumbing**. It can carry *a* strategy but defines *none*. What actually constitutes an edge — entry/exit logic, the signals that matter, holding periods, instruments, long/short, cash vs. F&O — is undefined.
*Why it matters:* everything downstream (which specialists, which risk limits, success metrics, even universe selection) depends on it. A perfect pipeline with no edge loses money (minus costs) live.
*Proposed direction:* treat the first strategy as a **pluggable module** the risk manager consumes; define at least one concrete, testable strategy before Phase 5. Reviewer question: *is it sound to build all this plumbing before proving a single strategy on simpler infrastructure?*

### G-13 🟠 — Universe selection criteria (which 9,000?)
"Max universe" is a capacity, not a selection. Which instruments fill the 9,000 (all F&O? NIFTY 500 + all their options? liquidity filter?) is undefined and interacts with tiering and cost.

### G-14 🟡 — Success metrics beyond system quality
Profitability/risk-adjusted targets (Sharpe, max DD) can't be set without G-01. Doc 01 §6 only defines system-quality metrics.

---

## B. Regulatory & ToS (India-specific — do not skip)

### G-02 🔴 — SEBI retail algo-trading framework
India (SEBI) has a regulatory framework for retail algorithmic trading via broker APIs (tagging/registration of algos, broker controls, thresholds). ⚠️ **Unverified here.** Live auto-execution may require registered/approved algos, a unique algo ID, static IP registration, and broker-side controls.
*Why it matters:* it can block or reshape live trading, and possibly affects order tagging even in development.
*Proposed direction:* full regulatory review in Phase 6 **before any live consideration**; confirm current SEBI rules and Zerodha's specific algo-approval process. Reviewer: verify the current (2026) rules — they have evolved.

### G-05 🟠 — Multiple API keys / subscriptions to raise the ceiling
We claim additional keys multiply the WS/rate budget. ⚠️ Verify this is permitted by Zerodha ToS and not considered abuse.

### G-12 🟠 — Automated daily login (TOTP)
Automating the 6 AM token mint via headless browser + TOTP is a **ToS gray area**. Default to operator-in-the-loop until confirmed.

### G-15 🟡 — Data redistribution / storage terms
Storing and deriving from Kite market data — confirm license terms permit our storage/retention and that we don't redistribute.

---

## C. Data plane

### G-03 🔴 — QuestDB ingest throughput at 9,000-instrument tick volume
Assumed, not measured. Full-depth ticks across 9,000 instruments is a large sustained write load.
*Proposed direction:* measure in Phase 1 before committing to QuestDB; have TimescaleDB/ClickHouse as fallbacks.

### G-04 🟠 — Storage sizing & retention
Disk growth per trading day (tick + depth) and a retention policy are unquantified. Drives cost (doc 10 §5).

### G-06 🟠 — Tiered subscription promotion/demotion policy
The *mechanism* is defined; the *policy* (thresholds, hysteresis to avoid flapping, max Full-tier size, how promotion requests from study/news/intraday-heuristics are arbitrated) is not.

### G-08 🟠 — Corporate-action adjustment of historical data
How Kite returns split/bonus-adjusted candles must be verified; if unadjusted, we need an adjustment layer or backtests will be wrong.

### G-16 🟡 — Bandwidth budget for full streaming
Even tiered, confirm sustained bandwidth (esp. Full mode) fits the host/network; define the max Full-tier count that stays within budget.

### G-17 🟡 — Market hours, holidays, sessions
Handling of pre-open, market close, holidays, muhurat/special sessions, and F&O expiry-day behavior is unspecified.

---

## D. Execution & risk

### G-09 🔴 — Fill-simulator fidelity
An over-optimistic simulator invalidates the whole paper exercise. Fill rules, slippage/latency models, partial fills, and (optionally) queue position need explicit, conservative, **validated** assumptions.
*Proposed direction:* validate by replay; default to conservative (no instant fills, model slippage, respect available depth).

### G-18 🔴 — Risk limits are placeholders
Doc 07 §3 lists *draft* limits. Real values (per-order cap, exposure caps, daily-loss kill-switch level, position sizing method) need an owner decision — they are the core safety envelope.

### G-19 🟠 — Indian cost model accuracy
STT, brokerage, exchange transaction charges, GST, stamp duty, SEBI turnover fees — the P&L ledger must model these accurately or paper P&L misleads.

### G-20 🟡 — LIMIT-only constraint effects
Sandbox/simulator support LIMIT only (no MARKET). Strategies needing market orders can't be paper-tested faithfully until live; note which strategies this rules out in the paper phase.

---

## E. Cognition & agents

### G-10 🟠 — LangGraph vs. custom orchestrator for the live latency budget
Confirm LangGraph meets live-path latency; consider a lighter custom orchestrator for live while keeping LangGraph for static study.

### G-11 🟠 — LLM token-spend estimate
Continuous screeners dominate cost. Without an estimate we can't size the live fleet responsibly. Directly caps affordable concurrency.

### G-21 🟠 — Conflicting-signal resolution logic
"The manager arbitrates" — but the actual arbitration policy (how to weigh a bullish technical vs. bearish macro vs. neutral news) is undefined and is where a lot of decision quality lives.

### G-22 🟡 — Entity resolution accuracy (news → token)
Mapping headlines to the correct instrument (name changes, ambiguous names, subsidiaries, ADRs) is error-prone; a wrong mapping can trigger the wrong trade. Needs a confidence threshold + human-review path for low confidence.

### G-23 🟡 — Look-ahead bias in static study & backtests
Must enforce as-of-timestamp discipline rigorously; easy to leak future data and get fake edge.

---

## F. Cross-cutting / ops

### G-07 🟠 — Distributed rate limiting if the system ever splits hosts
Token buckets are single-process now. If services split across hosts, the per-key limit must be enforced by a shared limiter or we risk 429s / bans.

### G-24 🟠 — Prompt-injection defense validation
The instruction-source boundary (doc 08 §6) is stated as policy; it needs to be *tested* with adversarial inputs (a news item crafted to hijack the loop) before live.

### G-25 🟡 — Time synchronization
NTP discipline, exchange-vs-receive timestamp handling, and skew alerting need to be concrete.

### G-26 🟡 — Crash/state recovery completeness
Recovery is described per-service; an end-to-end recovery test (mid-session crash of each component) is needed in Phase 6.

### G-27 🟡 — Disaster/failover for a single-host start
Single Docker-Compose host is a single point of failure. Acceptable for paper; define the plan before live.

---

## G. Meta / process questions for reviewers

1. **Sequencing sanity:** is building full 9,000-instrument infrastructure *before* proving any strategy (G-01) the right order, or should a thin vertical slice (small universe + one strategy) come first to de-risk the *idea* before the *scale*?
2. **Complexity vs. payoff:** does the Rust hot plane earn its cost at the *paper* stage, or could a Python-only paper MVP validate the concept faster, with Rust deferred to the scale/live phase?
3. **Agent-count realism:** are ~15–25 live agents actually affordable per the token estimate (G-11), or does cost force a smaller fleet?
4. **Redundancy:** anywhere two agents/components do effectively the same job?
5. **Unhandled failure modes:** what breaks that we haven't listed?

---

## Change log for this document
- 2026-07-21 — initial gap register (G-01 … G-27).
