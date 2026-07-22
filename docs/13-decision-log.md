# 13 — Decision Log

**Last updated:** 2026-07-22

The README says this repo exists to capture design decisions. Until now those decisions were embedded as prose rationale scattered across seven documents, which makes them hard to challenge one at a time — a reviewer who wants to argue against Rust has to reconstruct the argument for it from three places first.

This log records each significant decision once: what was decided, what else was considered, why, and **how expensive it would be to reverse**. That last column is the one that matters when deciding how hard to argue.

**Status:** `FIRM` (decided, revisit only with new information) · `PROVISIONAL` (decided to unblock work, expected to be revisited) · `OPEN` (recorded because it *should* be a decision but isn't yet)

**Reversibility:** `CHEAP` (config or a day's work) · `MODERATE` (a component rewrite) · `EXPENSIVE` (re-architecture)

---

| ID | Decision | Status | Reversibility |
|---|---|---|---|
| [D-01](#d-01) | Paper-trade before live | FIRM | CHEAP |
| [D-02](#d-02) | Rust hot plane + Python cognition plane | FIRM | EXPENSIVE |
| [D-03](#d-03) | Max universe (9,000) on one API key | PROVISIONAL | CHEAP |
| [D-04](#d-04) | Redis as the inter-plane contract | FIRM | MODERATE |
| [D-05](#d-05) | QuestDB for time-series capture | PROVISIONAL | MODERATE |
| [D-06](#d-06) | Single LLM risk manager as sole entry authority | FIRM | MODERATE |
| [D-07](#d-07) | Exits are deterministic, never LLM-dependent | FIRM | MODERATE |
| [D-08](#d-08) | Production data read-only + local simulator | FIRM | MODERATE |
| [D-09](#d-09) | Build order: infrastructure before strategy | **OPEN** | EXPENSIVE later |
| [D-10](#d-10) | Claude model tiering across the funnel | PROVISIONAL | CHEAP |
| [D-11](#d-11) | Single-host Docker Compose to start | PROVISIONAL | MODERATE |
| [D-12](#d-12) | Manager arbitrates by formula, not judgement | PROVISIONAL | CHEAP |
| [D-13](#d-13) | **Single-user application** (self + immediate family) | FIRM | CHEAP in code, EXPENSIVE in regulation |
| [D-14](#d-14) | Mathematical formalisation of execution physics, margin & aggregation | FIRM | CHEAP |

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

## D-02 — Rust hot plane + Python cognition plane

**Decided:** Rust for ingestion, execution, and position management; Python for LLM agents. Redis between them.

**Alternatives:** Python throughout (fastest to build, GC pauses and parse cost at 9,000 instruments); Rust throughout (uniform, but the agent ecosystem lives in Python); Go or C++ (middle grounds with worse ecosystem fit for one or the other half).

**Why:** the two halves have genuinely different requirements. Tick parsing and stop evaluation want predictable latency and no GC pauses; agent logic wants iteration speed and the Anthropic/LangGraph ecosystem. The split lets each half be written in the language that fits it.

**Cost:** two toolchains, two test setups, a serialization boundary, and a smaller pool of people who can work across the whole system. This is the single most expensive decision in the project.

**⚠️ The honest counter-argument** *(previously filed only as a meta-question for reviewers in doc 11 §G.2, which is backwards for a decision the README lists as confirmed)*: at the paper stage the Rust plane may not earn its cost. A Python-only paper MVP would validate the concept faster, and doc 06 §6 shows bandwidth is trivial — it is the ~9,000 writes/sec that is demanding, and only at full scale. A defensible alternative: Python end-to-end for a small universe, port to Rust when measurements show it is needed.

**Why we are keeping it anyway:** the hot plane is also where the *safety* code lives — the Position Manager, the risk engine, the kill-switch. Those benefit from predictable latency and strict typing regardless of universe size, and rewriting them later means rewriting the parts it is most dangerous to get wrong. Related: D-09.

**Status:** FIRM · **Reversibility:** EXPENSIVE.

---

<a id="d-03"></a>

## D-03 — Max universe (9,000 instruments) on one API key

**Decided:** use all 3 WebSocket connections × 3,000 instruments on a single API key, with tiered modes (Full / Quote / LTP).

**Alternatives:** a focused universe of a few hundred (far simpler, and adequate for most strategies); multiple API keys for more (**now largely foreclosed** — G-05).

**Why:** the stated edge is breadth plus synthesis rather than speed (doc 01 §5). That thesis needs breadth to be real.

**Cost:** it is the source of most of the system's engineering difficulty — tiering, ingest throughput, storage, and screener token spend all scale with it. **And it is not yet justified by any strategy** (G-01), because we do not know whether the edge needs 9,000 names or 200.

**⚠️ Marked PROVISIONAL deliberately.** Doc 09 Phase 1 starts at a few hundred instruments and scales up. If the eventual strategy needs 300 names, this decision quietly disappears and takes most of the complexity with it. Nothing should be built that *requires* 9,000.

**Status:** PROVISIONAL · **Reversibility:** CHEAP downward (subscribe to fewer), expensive upward.

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

## D-09 — Build order: full infrastructure before a strategy

**Status: OPEN.** Recorded because it *is* a decision the project has been making by default, without having been made explicitly.

**Currently implied:** build the full 9,000-instrument data plane, execution engine, and agent fleet, then define a strategy (G-01) before Phase 5.

**Alternative:** a thin vertical slice first — one instrument, one hard-coded strategy, real ticks, real simulator, real Position Manager, no LLMs — then scale.

**Evidence for the slice** *(2026-07-22)*: the review found **two 🔴 gaps that were invisible at the architecture level** — no exit path (G-28) and no margin model (G-29). Both would have surfaced within a day of carrying one real position end-to-end. Both would have invalidated paper results produced by the full build. Scale is a known engineering problem; lifecycle correctness is not, and it is not discoverable by reading documents — which is exactly what this review demonstrated.

**Evidence against:** the slice does not de-risk the hardest *engineering* question (ingest at 9,000), and some of its work is throwaway.

**Recommendation:** insert a Phase 0.5 vertical slice. Days, not weeks, and it exercises the entire risk spine. **Owner decision — this is the single highest-leverage sequencing choice remaining.**

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
