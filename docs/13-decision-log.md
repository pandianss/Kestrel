# 13 — Decision Log

**Last updated:** 2026-07-23

The README says this repo exists to capture design decisions. Until now those decisions were embedded as prose rationale scattered across seven documents, which makes them hard to challenge one at a time — a reviewer who wants to argue against Rust has to reconstruct the argument for it from three places first.

This log records each significant decision once: what was decided, what else was considered, why, and **how expensive it would be to reverse**. That last column is the one that matters when deciding how hard to argue.

**Status:** `FIRM` (decided, revisit only with new information) · `PROVISIONAL` (decided to unblock work, expected to be revisited) · `OPEN` (recorded because it *should* be a decision but isn't yet)

**Reversibility:** `CHEAP` (config or a day's work) · `MODERATE` (a component rewrite) · `EXPENSIVE` (re-architecture)

---

| ID | Decision | Status | Reversibility |
|---|---|---|---|
| [D-01](#d-01) | Paper-trade before live | FIRM | CHEAP |
| [D-02](#d-02) | **Python default + small Rust safety core** (execution plane) | FIRM | CHEAP toward Python-only |
| [D-03](#d-03) | Max universe (9,000) on one API key | PROVISIONAL | CHEAP |
| [D-04](#d-04) | Redis as the inter-plane contract | FIRM | MODERATE |
| [D-05](#d-05) | QuestDB for time-series capture | PROVISIONAL | MODERATE |
| [D-06](#d-06) | Single LLM risk manager as sole entry authority | FIRM | MODERATE |
| [D-07](#d-07) | Exits are deterministic, never LLM-dependent | FIRM | MODERATE |
| [D-08](#d-08) | Production data read-only + local simulator | FIRM | MODERATE |
| [D-09](#d-09) | Build order: **strategy-first vertical slice** (resolved by D-16/D-17) | FIRM | — |
| [D-10](#d-10) | Claude model tiering across the funnel | PROVISIONAL | CHEAP |
| [D-11](#d-11) | Single-host Docker Compose to start | PROVISIONAL | MODERATE |
| [D-12](#d-12) | Manager arbitrates by formula, not judgement | PROVISIONAL | CHEAP |
| [D-13](#d-13) | **Single-user application** (self + immediate family) | FIRM | CHEAP in code, EXPENSIVE in regulation |
| [D-14](#d-14) | Mathematical formalisation of execution physics, margin & aggregation | FIRM | CHEAP |
| [D-15](#d-15) | **No destruction of data** — append, tier, never delete | FIRM | Impossible retroactively |
| [D-16](#d-16) | **Positional / end-of-day**, not intraday | FIRM | MODERATE |
| [D-17](#d-17) | **First strategy is a documented anomaly**, not invented | FIRM (approach) | CHEAP |

---

<a id="d-01"></a>

## D-01 — Paper-trade first

**Decided:** validate the entire system against a local fill simulator before risking any capital. Live is gated behind a Phase 6 go/no-go review.

**Alternatives:** small live capital from the start (real fills, real slippage, real feedback — and real losses while the plumbing is still wrong); pure backtesting (cheap and fast, but no live-path validation at all).

**Why:** the failure modes of a new autonomous trading system are overwhelmingly mechanical rather than strategic — wrong position state, mis-parsed ticks, a stop that never fires. Paper trading catches those at zero cost. The 2026-07-22 review is direct evidence: it found a missing exit path and a missing margin model, either of which would have cost real money on day one.

**Cost:** paper fills are modelled, not observed, so simulator fidelity becomes a load-bearing assumption (G-09).

**Status:** FIRM · **Reversibility:** CHEAP — flipping the execution backend is a config change by design.

---

<a id="d-02"></a>

## D-02 — Python everywhere, with a small Rust safety core

**Resolved 2026-07-23.** *(Superseding the original "Rust hot plane + Python cognition plane." D-16 removed the throughput rationale for a large Rust plane; this replaces it.)*

**Decided:** **Python is the default language for the whole system.** A **small Rust core** implements only the components where a bug directly causes an uncontrolled loss or a compliance breach — chosen for **compile-time correctness, not speed.**

### The boundary — and it is deliberately narrow

| Rust safety core | Python (everything else) |
|---|---|
| **Execution Gateway** — single writer to the broker, `algo_id` tagging, the calendar-second rate limiter | Data ingester (now ~10 live names — trivial) |
| **Risk engine** — pre-trade checks, margin, kill-switch | Historical backfill, instruments loader + snapshotter |
| **Position Manager** — stops, targets, time-exits, feed-loss policy | Tick sanity filter, fill simulator *(paper-only; can be Python)* |
| | The **entire cognition plane** — screeners, specialists, manager, factor backtest, research |

The line is exactly **doc 07's execution plane.** Everything in doc 06 (data) and doc 08 (cognition) is Python. That is a crisp, defensible boundary — not "the fast stuff," which sprawls, but "the stuff that must not be wrong about money or compliance," which is bounded and small (order of ~1,000–2,000 lines).

**Alternatives considered and rejected:**
- **Python-only** — viable, and genuinely close. Rejected only because the exit path and risk engine are the code where a silent bug is most expensive, and Rust's type system + absence of GC pauses buy real confidence there. If the operator later judges that confidence not worth a second toolchain, collapsing to Python-only is CHEAP (see reversibility).
- **The original large Rust hot plane** (ingester, backfill, quote poller all in Rust) — its justification was 9,000-instrument throughput, which D-16 deleted. Keeping it would pay the two-toolchain tax for speed nobody can observe (10 ticks/sec has ~2,000× headroom in Python).

### Why — correctness, explicitly not speed

At this cadence and scale, **speed is not a differentiator**: 10 ticks/sec against a 100,000 µs/tick budget is 99.95% idle in Python, and Kite's ~1 tick/sec feed means a stop that fires 30 ms "late" fills on the same tick regardless (doc 01 §5 — "not HFT, the latency floor is Kite's"). The Rust core is justified on a different axis entirely:

- **The exit path is the money-losing-if-wrong code** (D-07). Rust's type system catches whole classes of bug — null/None, unhandled variants, integer overflow, use-after-move — at compile time rather than at 2 p.m. with an open position.
- **No GC pause to reason about** in the one loop (stop evaluation) where an unbounded pause is theoretically undesirable — even though at this cadence it wouldn't matter, it removes the question entirely.
- **Compliance surface** (single-writer, tagging, rate limit) is small, changes rarely, and is exactly the kind of code worth freezing behind a strict compiler.

### Cost

- **Two toolchains** — but only one of them is large. The Rust surface is ~1–2k lines that change rarely; the Python surface is where all iteration happens.
- **A Redis boundary** between the Python manager and the Rust execution core — but this already existed as the inter-plane contract (D-04), just at a different line. The manager emits `OrderIntent` onto a stream; the Rust core consumes it. No new mechanism.
- **The `.pyd`/FFI question is avoided** — the two sides talk over Redis, not in-process, so there is no PyO3 binding to maintain unless profiling ever demands one (it won't, at this scale).

**Status:** FIRM · **Reversibility:** **CHEAP toward Python-only** (delete the Rust core, reimplement ~1.5k lines behind the same Redis contract — a known, bounded job); EXPENSIVE to re-expand Rust, but D-16 means there is no reason to.

---

*Original decision preserved below for the record:*

**Originally decided:** Rust for ingestion, execution, and position management; Python for LLM agents. Redis between them.

**Alternatives:** Python throughout (fastest to build, GC pauses and parse cost at 9,000 instruments); Rust throughout (uniform, but the agent ecosystem lives in Python); Go or C++ (middle grounds with worse ecosystem fit for one or the other half).

**Why:** the two halves have genuinely different requirements. Tick parsing and stop evaluation want predictable latency and no GC pauses; agent logic wants iteration speed and the Anthropic/LangGraph ecosystem. The split lets each half be written in the language that fits it.

**Cost:** two toolchains, two test setups, a serialization boundary, and a smaller pool of people who can work across the whole system. This is the single most expensive decision in the project.

**⚠️ The honest counter-argument** *(previously filed only as a meta-question for reviewers in doc 11 §G.2, which is backwards for a decision the README lists as confirmed)*: at the paper stage the Rust plane may not earn its cost. A Python-only paper MVP would validate the concept faster, and doc 06 §6 shows bandwidth is trivial — it is the ~9,000 writes/sec that is demanding, and only at full scale. A defensible alternative: Python end-to-end for a small universe, port to Rust when measurements show it is needed.

**Why we are keeping it anyway:** the hot plane is also where the *safety* code lives — the Position Manager, the risk engine, the kill-switch. Those benefit from predictable latency and strict typing regardless of universe size, and rewriting them later means rewriting the parts it is most dangerous to get wrong. Related: D-09.

**⚠️ Re-opened by D-16 (2026-07-23).** The throughput half of this decision's rationale — *"~9,000 writes/sec is demanding"* — **no longer holds.** An end-of-day positional system screens on daily bars and streams only the ~10 held names, so the parse/ingest load is trivial. The Rust case now rests **only** on safety-critical determinism (Position Manager + risk engine), which is a small, well-bounded surface — not the full hot plane. A **Python-only build is now a serious contender**, with a narrow Rust core (or none) for the exit path. Downgraded from FIRM to **PROVISIONAL** pending that reassessment; it is the most consequential open decision after G-01.

**Status:** ~~FIRM~~ **PROVISIONAL** *(D-16 removed its main pillar)* · **Reversibility:** EXPENSIVE if built, CHEAP to reconsider before building.

---

<a id="d-03"></a>

## D-03 — Max universe (9,000 instruments) on one API key

**Decided:** use all 3 WebSocket connections × 3,000 instruments on a single API key, with tiered modes (Full / Quote / LTP).

**Alternatives:** a focused universe of a few hundred (far simpler, and adequate for most strategies); multiple API keys for more (**now largely foreclosed** — G-05).

**Why:** the stated edge is breadth plus synthesis rather than speed (doc 01 §5). That thesis needs breadth to be real.

**Cost:** it is the source of most of the system's engineering difficulty — tiering, ingest throughput, storage, and screener token spend all scale with it. **And it is not yet justified by any strategy** (G-01), because we do not know whether the edge needs 9,000 names or 200.

**⚠️ Marked PROVISIONAL deliberately.** Doc 09 Phase 1 starts at a few hundred instruments and scales up. If the eventual strategy needs 300 names, this decision quietly disappears and takes most of the complexity with it. Nothing should be built that *requires* 9,000.

**⚠️ Further weakened by D-16 (2026-07-23).** Under an end-of-day cadence, "universe" means *screened on daily candles*, not *live-streamed*. Screening 9,000 daily bars is cheap and needs no WebSocket capacity at all — only the ~10 held names are streamed live. The 3-connection / 9,000-instrument live-streaming architecture is now **almost entirely unused** by a positional system. Keep the *breadth of screening*; drop the *breadth of streaming*.

**Status:** PROVISIONAL · **Reversibility:** CHEAP downward (subscribe to fewer), expensive upward. D-16 makes downward the likely direction.

---

<a id="d-04"></a>

## D-04 — Redis as the inter-plane contract

**Decided:** Redis Streams plus a last-value cache as the boundary between planes; start here and optimize only if profiling demands it.

**Alternatives:** Kafka / NATS JetStream (durable and scalable, heavier for a single host); PyO3 in-process binding (fastest, couples the planes tightly); shared-memory ring buffer (fastest possible, most complex).

**Why:** language-agnostic, inspectable while debugging, one system for both cache and messaging, and it keeps the planes genuinely independent. The explicit rule is *do not pre-optimize the boundary* (doc 04 §2).

**Cost:** serialization on every hop, in-memory storage that must be bounded (G-31), and no durability guarantee — hence the rule that **no stream is the system of record**.

**Status:** FIRM · **Reversibility:** MODERATE — a versioned schema (doc 06 §2.1) means the transport can be swapped without rewriting producers and consumers.

---

<a id="d-05"></a>

## D-05 — QuestDB for time-series capture

**Decided:** QuestDB for tick and candle storage; DuckDB + Parquet for research.

**Alternatives:** TimescaleDB (Postgres tooling, relational plus time-series, lower ingest ceiling); ClickHouse (excellent analytics, more ops weight); Parquet files only (no ingest path).

**Why:** purpose-built for high-ingest market data, SQL interface, fast time-range queries.

**⚠️ Unvalidated at our write rate** (G-03, 🔴). ~9,000 writes/sec sustained is the requirement, and it is assumed rather than measured. Fallbacks named.

**Status:** PROVISIONAL until Phase 1 measurement · **Reversibility:** MODERATE — writes go through one ingestion path, so the store is swappable if that path stays abstract. **Keep it abstract until D-05 is confirmed.**

---

<a id="d-06"></a>

## D-06 — A single LLM risk manager as sole entry authority

**Decided:** exactly one agent may open a position. It holds the whole book, applies deterministic limits, and arbitrates conflicting specialist opinions.

**Alternatives:** multiple agents placing orders in parallel (races, no coherent portfolio view, no global risk); a purely deterministic sizer (no cross-signal judgement, which is the point of the fleet).

**Why:** coherence. Portfolio-level risk cannot be applied by components that each see only their own slice.

**Cost:** a throughput bottleneck on entries and a dependency on one model's availability — **bounded by D-07**, which ensures the failure mode is "stop opening positions," not "stop managing risk."

**Status:** FIRM · **Reversibility:** MODERATE.

---

<a id="d-07"></a>

## D-07 — Exits are deterministic and never depend on an LLM

**Decided:** a Rust Position Manager owns every open position and emits exits on its own. The LLM manager may tighten or trail a stop but is never required for an exit to happen. Risk checks may block entries, never exits.

*(Added 2026-07-22 in response to G-28.)*

**Alternatives:** the risk manager emits all orders (the original design — puts LLM latency in the loss path); broker-side stop orders only (real, but no trailing logic, no time-exits, and no behaviour on feed loss); a hybrid with broker stops as a backstop beneath our own — **worth revisiting for live**.

**Why:** entries and exits have opposite failure modes. A late entry costs an opportunity; a late exit costs money without bound. The deciding component should differ accordingly.

**Cost:** a second order-emitting component, so "single writer" becomes "single *gateway*, two intent sources." The gateway remains the only thing that talks to the broker, so the invariant holds where it matters.

**Status:** FIRM · **Reversibility:** MODERATE.

---

<a id="d-08"></a>

## D-08 — Production data (read-only) + local fill simulator, not the sandbox

**Decided:** take live and historical data from the production API read-only, route orders to a local simulator, and keep the sandbox for API-contract validation only.

**Alternatives:** sandbox for everything (demo data, historical often unavailable, cannot feed a 9,000-instrument study); recorded data only (no live-path validation).

**Why:** the sandbox cannot supply realistic data at this scale, and read-only production access carries no financial risk.

**Cost:** the order *payload* path is only validated against the sandbox, not exercised end-to-end for real. Live migration therefore carries genuine first-run risk — which is what the Phase 6 go/no-go exists to contain. Margin APIs in particular cannot be validated at all before live (G-29).

**Status:** FIRM · **Reversibility:** MODERATE.

---

<a id="d-09"></a>

## D-09 — Build order: strategy-first vertical slice

**Status: FIRM** *(resolved 2026-07-23 by D-16 + D-17).* This sat OPEN because the project had been making it by default. D-16 (positional) and D-17 (documented factor) settle it: there is now a concrete strategy to build *first*, and it is deterministic.

**Decided:** build the **deterministic factor spine first**, prove it on historical data, then add the live plane and (only if it earns its cost) the LLM overlay. Not "infrastructure then strategy" — **strategy then the infrastructure it actually needs.**

The sequence that falls out:

1. **The documented factor as a backtest** (D-17) — deterministic, over point-in-time historical bars (G-43). Answers "does this edge survive Indian costs?" before any live wiring. First real deliverable.
2. **The vertical slice** — one instrument, the factor rule, real simulator, real Position Manager, no LLMs. Exercises the risk spine end-to-end.
3. **The end-of-day live plane** — daily screen, pre-open decide, live-stream only held names (D-16). Much smaller than the original 9,000-instrument design.
4. **The LLM overlay, last and optional** — added only where it can be shown to beat the factor net of its cost (G-44).

**Why this is now obvious rather than a judgement call:** the two 🔴 gaps this review found (no exit path G-28, no margin model G-29) were invisible in documents and appear on the first real position — argument for a slice. D-17 adds that the slice now has a *researched* strategy to run rather than a hard-coded placeholder, so its results mean something. And D-16 removes the "but the slice doesn't de-risk 9,000-instrument ingest" objection — under end-of-day, that ingest problem **no longer exists** (G-03).

**Status:** FIRM · **Reversibility:** the ordering is cheap to hold to; deviating (building the fleet before the factor is proven) is the expensive mistake it exists to prevent.

---

<a id="d-10"></a>

## D-10 — Claude model tiering across the funnel

**Decided:** Haiku for screeners, Sonnet for specialists and study agents, Fable for the risk manager and high-salience macro analysis.

**Alternatives:** one model everywhere (simpler, either too expensive at screener volume or too weak at the top); fine-tuned small models (premature without training data).

**Why:** the funnel narrows volume as it climbs stakes, so model strength should climb with it. Thousands of cheap judgements at the bottom, one expensive judgement at the top.

**Cost:** three sets of prompts and evaluation criteria; tier boundaries are guesses until measured (G-11).

**Status:** PROVISIONAL — pin exact model IDs at build time · **Reversibility:** CHEAP.

---

<a id="d-11"></a>

## D-11 — Single-host Docker Compose to start

**Decided:** all services on one ap-south-1 host, containerized, scaling out only if measurements demand it.

**Alternatives:** Kubernetes from day one (operational weight with no current payoff); managed services (less control, higher cost, latency further from Kite).

**Why:** the workload genuinely fits one machine (doc 06 §6), and single-host removes distributed-systems problems the project does not need — notably distributed rate limiting (G-07).

**Cost:** a single point of failure (G-27), accepted while no real money is at risk.

**⚠️ Constrained since 2026-07-22:** the static-IP requirement (doc 02 §9) pins the order path to one registered address regardless, so any future multi-host topology must keep the Execution Gateway on the whitelisted host. Horizontal scaling is available for the cognition plane only.

**Status:** PROVISIONAL · **Reversibility:** MODERATE for the cognition plane; the order path is constrained by regulation, not by us.

---

<a id="d-14"></a>

## D-14 — Mathematical formalization of execution physics, margin & evidence aggregation

**Decided:** replace qualitative/draft rules in data, execution, and cognition specifications with explicit mathematical models (Almgren-Chriss market impact, SPAN 16-scenario grid valuation, Bayesian Log-Likelihood ratio evidence fusion, and EWMA/MAD tick sanity jump filters).

**Alternatives:** maintain high-level qualitative descriptions (simpler to read for non-quantitative stakeholders, but leaves microstructural fill physics, margin constraints, and multi-agent consensus ambiguous during build phase).

**Why:** ambiguity in market simulation or margin modeling leads to false confidence during paper trading. Precise mathematical specifications ensure paper execution fidelity matches exchange dynamics.

**Cost:** increased specification complexity; requires quantitative calibration during Phase 1 tick replay.

**⚠️ Three calibration caveats established after this decision was taken** — the formalisation is sound, the constants were not:

1. **Impact coefficients are borrowed, not fitted.** $\gamma pprox 0.5$ comes from developed-market large caps; Indian mid-caps and illiquid strikes run materially higher. Starting values now sit *above* the literature figure by design (doc 07 §4.1, G-09).
2. **SPAN is not locally computable.** Scan ranges come from the exchange's daily risk file, and a scenario grid omits short-option minimum, calendar-spread, and delivery margins. The formalisation is now explicitly labelled *reference for interpreting the API's answer*, not an implementation spec (doc 07 §3.1, G-29).
3. **Summed LLRs assume specialist independence, which is false.** Corrected with an effective-sample-size discount plus corroboration and veto gates (doc 08 §3.1.1, G-21).

**The pattern worth keeping:** precise notation made these assumptions *harder* to see, not easier — a formula reads as settled in a way prose does not. The decision stands; every asserted constant now carries a ⚠️ and a calibration owner.

**Status:** FIRM · **Reversibility:** CHEAP.

---

<a id="d-12"></a>

## D-12 — The risk manager arbitrates by formula, not by judgement

**Status: PROVISIONAL.** *(Added 2026-07-22, recording a change that arrived as formalism in doc 08 §3.1 rather than as an explicit decision.)*

**Decided (provisionally):** specialist assessments are combined into a directional call by a **correlation-discounted Bayesian LLR** with corroboration and veto gates, rather than by the LLM manager weighing them in prose.

**Alternatives:**
- **LLM judgement within deterministic guardrails** — the original design (doc 05 §4). Handles novel situations and cross-signal nuance; not reproducible, hard to audit, and its reasoning cannot be regression-tested.
- **Formula only** — auditable, reproducible, backtestable, cheap. Blind to anything not encoded in the specialist scores.
- **Formula for the routine case, LLM for the exceptions** — formula decides when specialists broadly agree; LLM adjudicates genuine conflict. More machinery, but plays to each one's strength.

**Why the formula:** determinism at the decision point is worth a great deal here. A formula can be replayed (doc 07 §4.3), regression-tested, and attributed after a loss. "The model felt bearish" cannot be any of those, and this is the component that authorizes risk.

**What it costs — and this is the part that needs deliberate acceptance:**

1. **It changes what the manager is.** Doc 05 §4 describes an agent that "resolves conflicting specialist opinions." Under D-12 it computes a number and checks gates. That is a real narrowing of the design's ambition, whatever its merits.
2. **It weakens the case for Fable at the top of the funnel** (D-10). If the manager is largely arithmetic, paying frontier-model rates for it is hard to justify — which also moves the G-11 token-spend estimate. **This should be re-examined once §3.1 stabilises.**
3. **It is unrunnable cold** (doc 08 §3.2). $w_k$, $\rho_k$, and $\Sigma$ all need a track record that does not exist at Phase 5.
4. **It does not close G-21.** Aggregation is not arbitration. The genuinely hard question — what happens when technical and macro disagree — is answered by gates bolted on top, and those gates are the actual policy.

**Why PROVISIONAL:** option 3 (hybrid) has not been properly evaluated, and the cost implication for D-10 is unresolved. Revisit once there is enough paper history to measure whether the formula's calls differ meaningfully from an LLM's on the same inputs — that comparison is cheap to run and would settle this.

**Status:** PROVISIONAL · **Reversibility:** CHEAP — the aggregation step is one component behind a stable interface, and both alternatives consume the same specialist outputs.

---

<a id="d-17"></a>

## D-17 — The first strategy is a documented, published anomaly — not an invented edge

**Status: FIRM (as an approach).** *(Owner directive: "research-backed intervention," 2026-07-23.)* The specific factor is still to be chosen (G-01 stays open), but **how** the first edge is chosen is now decided.

**Decided:** the first strategy Kestrel trades will be a **well-documented, peer-reviewed market anomaly with decades of published out-of-sample evidence** — not a novel edge invented for this system, and not an LLM-discovered pattern.

**Alternatives:** invent a strategy (what the docs implied — the highest-risk path, no prior evidence); let the LLM fleet *find* an edge (G-42 makes this unvalidatable — you cannot backtest it, and the model has seen the history); buy a signal from a vendor (recurring cost, black box, and empanelment questions).

### Why this is the right first move — and why it fits everything else

**It is the only path with evidence that predates our own trading.** G-42 established the hard constraint: the LLM plane cannot be backtested — the model has seen the test period, and forward-testing takes years. A **published anomaly sidesteps this entirely**, because the evidence already exists, was generated out-of-sample across decades and markets, and does not depend on us re-running anything through an LLM. It is the one kind of edge you can have real confidence in *before* committing capital.

**It is deterministic, which four other decisions already want.** A documented factor — momentum, low-volatility, value, quality, size — is a **rule over historical bars.** It lives in the deterministic plane, where:
- it **can** be backtested conventionally (G-42);
- it is **white-box describable** if registration is ever needed (G-41);
- it is the **cheapest** part to run (G-11 — no per-decision LLM cost);
- it is the **only rigorously validatable** part (G-42 again).

**It gives the LLM fleet a job it can actually be measured against.** Instead of the agents *being* the strategy (unvalidatable), the documented factor is the baseline and the agents are an **overlay that must beat it** — better entry timing, regime filtering, avoiding value traps. Now "do the LLMs add anything?" has a concrete answer: *do they beat the factor alone, net of their cost?* That is a forward test with a control, which is worth far more than a forward test without one.

### Candidate anomalies (all documented, all positional — fit D-16)

| Anomaly | Evidence base | Why it fits |
|---|---|---|
| **Cross-sectional momentum** | Jegadeesh–Titman 1993 and ~30 yrs of replication across markets incl. India | Positional (3–12 month holds), rule-based, works on daily bars |
| **Low-volatility** | Extensively documented; the "low-vol anomaly" | Lower drawdown, suits a single operator with no on-call (D-13) |
| **Value (P/B, P/E)** | Fama–French and successors | Slow, positional, deterministic to compute |
| **Quality (profitability, low accruals)** | Novy-Marx and others | Combines well with value; fundamental data, low turnover |

⚠️ **All of these are documented in *developed* markets primarily.** Indian-market persistence must be checked — some factors travel, some don't, and transaction costs here (doc 07 §5.1) are higher. That check is itself a deterministic backtest, and it is the **first concrete Phase 2 deliverable** now that a strategy shape exists.

### What it costs / limits

- **Documented factors are crowded.** Their published Sharpe is lower now than at discovery — decades of capital have chased them. The realistic expectation is a **modest, positive, well-evidenced edge**, not a large one. This is a feature: it is honest, and it is what the risk envelope (G-18) should be sized against. Anyone expecting outsized returns from a known factor has misunderstood what "documented" means.
- **It does not resolve G-01, only shapes it.** The specific factor, the universe it applies to, rebalance frequency, and long-only vs long/short are still choices. But they are now choices *within a researched frame*, not invention from nothing.
- **The factor may not survive Indian costs and liquidity.** If the Phase 2 backtest shows it doesn't, that is a real and useful negative result — far better learned on historical data than with capital.

**Status:** FIRM as an approach · **Reversibility:** CHEAP — the strategy is a pluggable module by design (G-01's original direction); swapping or adding factors is expected.

---

<a id="d-16"></a>

## D-16 — Positional, end-of-day system — not intraday

**Status: FIRM.** *(Owner decision, 2026-07-23.)*

**Decided:** Kestrel is a **positional (swing) system on an end-of-day cadence.** It screens on completed daily bars after close, decides pre-open, and holds positions for **days to weeks**. It is explicitly **not** intraday.

- **Screening:** once per day, post-close, on the day's settled bars.
- **Decision:** once per day, pre-open, on the resulting candidates.
- **Position Manager:** runs live all session, but **only on held positions** (~10, per G-39) — evaluating stops, targets, and time-exits against the live feed.

**Alternatives:** intraday MIS (the original implied design — 30-second screening, ~100 decisions/session); higher-frequency swing (hourly screening); pure buy-and-hold (no active exits).

### Why — four independent pressures, all pointing here

This is the same convergence that G-11, G-41, G-42 and G-44 kept surfacing, now made explicit:

1. **Cost.** Screening every 30 s costs ~$27,750/yr; end-of-day costs ~$2,200/yr — **13× cheaper** (G-11 model). The agent funnel alone drops to ~$350/yr.
2. **Unit economics (G-44).** The fleet's break-even capital falls from **₹6.1 cr to ₹0.48 cr** — from "needs a fund" to "works on a retail account."
3. **The LLM does what it is good at.** Considered analysis on settled data, overnight, with no latency pressure — not reflex judgement in a 30-second loop. This is the single biggest lever on decision *quality*, separate from cost.
4. **It removes most of the 🔴 engineering risk** (see the cascade below).

### What it changes — the cascade

| Area | Intraday assumption | Under D-16 |
|---|---|---|
| **Data plane (G-03 🔴)** | Stream 9,000 instruments at ~9,000 writes/s into QuestDB | **Screen 9,000 on daily candles** (historical API); **stream only the ~10 held**. The hardest scale gap largely dissolves |
| **Universe (D-03)** | 9,000 live-streamed | 9,000 *screened* on daily bars; a few hundred is plenty. D-03's live-streaming justification weakens further |
| **Hot-plane throughput (D-02)** | Rust justified by 9,000-instrument parse load | ⚠️ **That justification evaporates.** The Rust case now rests only on safety-critical determinism (Position Manager, risk engine) — a much smaller surface. **D-02 must be revisited** |
| **Storage / tiering (G-04, G-31)** | ~5 GB/day of ticks | Orders of magnitude less — daily bars for the universe, ticks only for held names |
| **Products (G-18, G-30)** | MIS intraday | **CNC delivery / NRML carry.** No 3:25 square-off, no ₹50 charge — but **overnight gap risk that stops cannot protect against**. G-18's envelope needs rewriting for gaps |
| **News pipeline (doc 08 §4)** | Real-time catalyst reaction | Largely lost — an 11 a.m. catalyst is seen at close. ⚠️ It is now the **largest single LLM line** (~$1,250/yr of a ~$2,200 total); **question whether it earns its place** |

### What it costs

**1. Overnight gap risk becomes the dominant danger.** An intraday stop is a floor you can act on; a gap through it overnight is not. The G-18 envelope must size for gaps, not for intraday stop distance — smaller positions, or explicit gap-risk budgeting. This is the real price of leaving intraday.

**2. Evidence accumulates slowly (G-42).** At ~250 decisions/year instead of 25,000, forward validation — the *only* validation the LLM plane can have — takes **years, not months** to separate skill from luck. Phase 6's "N stable sessions" is now measured in years. This is inherent to trading less often, not a flaw, but it must be planned for.

**Status:** FIRM · **Reversibility:** MODERATE — cadence is config, but it interacts with product choice (CNC vs MIS) and the whole data-plane sizing, so a later reversal to intraday reopens G-03 and D-02.

---

<a id="d-15"></a>

## D-15 — No destruction of data

**Status: FIRM.** *(Owner directive, 2026-07-22.)*

**Decided:** **data is never destroyed.** It is added to, tiered to cheaper storage, or — only where an external obligation requires it — deleted with a recorded reason. Nothing in the system silently drops, samples away, overwrites, or ages out data.

**Alternatives:** conventional retention windows (delete after N months — the industry default); sampling for high-volume paths (keep 1-in-N rejects, rotate logs); overwrite-in-place for reference data (what the design originally did with the instruments master).

### Why this is affordable, which is what makes it a rule rather than an aspiration

| Approach | Storage cost/yr |
|---|---|
| Uncompressed, S3 Standard | ~$359 |
| Parquet+zstd (~8×), S3 Standard | ~$45 |
| **Parquet+zstd (~8×), S3 Standard-IA** | **~$24** |
| Parquet+zstd (~8×), Glacier Instant | ~$8 |

**Keeping everything forever costs roughly $24/year** — about a third of the Kite subscription, and **0.3% of even the lean LLM line.** Retention policies exist to control cost; here there is no cost worth controlling. Deleting data to save $24 while spending $9,000 on tokens would be incoherent.

### What it changes concretely

| Was | Now |
|---|---|
| Rejected ticks *"sampled into a quarantine log"* | **Every** rejected tick persisted with its reject reason |
| *"Retention policy — how long to keep full depth"* | **Tiering** policy — hot → warm → cold. Nothing expires |
| Instruments master overwritten daily | Dated immutable snapshots (G-43) |
| Redis `MAXLEN` trimming | Permitted **only** where a durable copy provably landed first — and the ordering is enforced, not assumed |
| Ledger "persisted, crash-safe" | **Append-only.** Corrections are new entries, never in-place edits |

### The subtle one: defending against *third-party* destruction

Kite adjusts historical candles **in place** on a corporate-action ex-date (doc 02 §5.1). The unadjusted series is destroyed from our view, permanently, by someone else. Under D-15 that is not something to accept — the backfill must **capture the as-of series before adjustments land** and record the adjustment event, so both the pre- and post-adjustment views survive.

This is the same shape as G-43: *free to capture now, impossible to reconstruct later.*

### The one exception, and it is not ours to choose

Kite ToS §9(b) requires deleting stored content on termination of the agreement (doc 02 §9.7, G-15). **This is an externally imposed obligation that overrides D-15.** It is recorded here rather than hidden, and it is the reason the research corpus is a leasehold rather than an asset.

**No other exception is permitted.** If a future change appears to require deleting data, it needs a decision entry of its own explaining why — not a retention config.

### What it costs

Storage grows monotonically, so the tiering path must actually be built rather than assumed. Query performance on the hot tier must not degrade as cold data accumulates — that is a partitioning requirement, not a reason to delete. And the quarantine/reject store will contain a lot of genuinely worthless data; it stays anyway, because *deciding what is worthless is exactly the judgement that turns out to be wrong later.*

**Status:** FIRM · **Reversibility:** CHEAP to relax, **IMPOSSIBLE to apply retroactively** — data destroyed under a laxer rule is gone. This is why it is being set now rather than at Phase 2.

---

<a id="d-13"></a>

## D-13 — Single-user application

**Status: FIRM.** *(Confirmed by the owner 2026-07-22.)*

**Decided:** Kestrel serves **one operator trading their own account** (extendable to immediate family under the same regulatory carve-out — doc 02 §9.4). It is not a product, a service, or a platform for others.

**Alternatives:** a multi-tenant service (would make us an **algo provider** requiring exchange empanelment — doc 02 §9.4, a different regulatory regime and a different company); an open-sourced tool others self-host (no empanelment issue, but a support and liability surface).

**Why:** it is what the operator actually wants, and it keeps the project inside the retail carve-out where the regulatory burden is a generic Algo ID rather than empanelment plus per-strategy registration.

### What this buys — things we now do *not* build

| Not building | Because |
|---|---|
| User accounts, auth, RBAC, session management | One operator. VPN/SSH is the access control |
| Multi-tenancy, per-user isolation, `user_id` anywhere in the schema | One book, one ledger, one set of positions |
| Per-user rate budgets or quota accounting | One Kite client ID, one 10 OPS budget |
| A public API, SDK, or webhook surface for third parties | Nobody else integrates |
| Onboarding, billing, support tooling, SLAs | No customers |
| Horizontal scaling for *user* load | Scaling is only ever about throughput (doc 10 §3) |

**This is a large simplification and it should be taken.** Every item above is a component that would otherwise need designing, testing, securing, and maintaining. Resist adding any of them "in case we productise later" — D-13 can be revisited, and revisiting it deliberately is cheaper than carrying unused multi-tenancy through the whole build.

### What this does *not* change

Single-user does not soften a single correctness requirement. One person's money is still money:

- **Exits still must be deterministic** (D-07, G-28). Arguably *more* so — see below.
- **Compliance is identical.** Tagging, static IP, TOPS, market protection all apply the same way.
- **The exchange kill switch** (G-40) is no less likely.
- **Backtest validity** (G-42) is unchanged.

### What it makes *harder*, and these are the interesting ones

**1. 🔴 The unit economics become severe (G-44).** LLM cost is fixed; profit scales with capital. A single retail account may not clear the ~₹24 lakh/year hurdle the full agent fleet imposes — it breaks even only around ₹1.2 crore. **This is the most consequential consequence of D-13 and it may reshape what gets built.**

**2. There is no on-call rotation.** One operator means the daily token mint, kill-switch response, and exchange-halt runbook all depend on one person being reachable. Travel, illness, or sleep are not edge cases — they are Tuesdays.

> **This makes D-07 (deterministic exits) load-bearing rather than merely prudent.** With a team you could argue a human would notice a stuck position. With one operator there is no such backstop, so **safe unattended operation is a hard requirement**: the system must be able to run a full session, and exit every position correctly, with nobody watching. It already can — that is what D-07 bought — but D-13 is the reason it had to.

**3. Bus factor is one.** The documentation set *is* the mitigation, which retroactively justifies its weight. If the operator steps away for six months, doc 11 and doc 13 are what make the project resumable.

**Status:** FIRM · **Reversibility:** CHEAP *away* from single-user in the code (nothing built assumes multi-tenancy), EXPENSIVE in regulation — serving anyone else triggers algo-provider empanelment (doc 02 §9.4).

---

## How to add a decision

When a choice is made that a future reviewer might reasonably question, add a row and a section. Record the alternatives **as they were actually considered** — a decision log that lists only strawman alternatives is worse than none, because it manufactures false confidence. If a decision is being made by default rather than deliberately, record it as `OPEN` (see D-09) rather than leaving it invisible.
