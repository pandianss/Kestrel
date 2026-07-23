# 08 — Cognition Plane Spec (Python / LLM agents)

**Last updated:** 2026-07-22

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

### 3.1 Evidence aggregation — the arbitration model

> ⚠️ **This is a proposal, not a settled design.** It is recorded here so it can be attacked. It partially addresses G-21, and does **not** close it — see §3.3. The architectural consequence of adopting it (the manager becomes a calculator rather than a judge) is recorded as **doc 13, D-12**.

For candidate instrument $i$, let directional stance $S_i \in \{-1, 0, +1\}$ denote short, neutral, or long. Each specialist $k \in \{1 \dots K\}$ evaluates evidence $E_{i,k}$ and outputs a directional score $d_{i,k} \in [-1, 1]$ with confidence $c_{i,k} \in [0, 1]$.

The naive aggregate Log-Likelihood Ratio is a weighted sum of per-specialist evidence:

$$\text{LLR}_{\text{naive}}(S_i = +1) = \text{LLR}_{\text{prior}} + \sum_{k=1}^K w_k \cdot c_{i,k} \cdot \ln \left( \frac{1 + d_{i,k} \cdot \rho_k}{1 - d_{i,k} \cdot \rho_k} \right)$$

where $\text{LLR}_{\text{prior}}$ is the macro regime prior log-odds $\ln \frac{P(S_i = +1)}{P(S_i = -1)}$, $w_k$ is a precision weight, and $\rho_k \in (0,1)$ is specialist $k$'s historical accuracy.

#### 3.1.1 ⚠️ Why the naive sum is wrong, and the correction

**Summing LLRs assumes the specialists are conditionally independent given $S_i$. They are not.** Technical, options-OI, news-event, and macro-regime specialists all read overlapping data about the same instrument in the same moment. A large price move drives *all four* at once.

The consequence is not a small bias. **Correlated evidence summed as independent overstates confidence, and overstates it most when every specialist agrees** — which is exactly the situation where the model would size up hardest. The failure mode is structural: maximum overconfidence at maximum conviction.

Two corrections, both required:

**1. Discount by an effective sample size.** Estimate the specialist correlation matrix $\Sigma$ (from historical score co-movement) and replace the raw count $K$ with

$$K_{\text{eff}} = \frac{K}{1 + (K-1)\bar{\rho}_{\text{corr}}}, \qquad \bar{\rho}_{\text{corr}} = \frac{2}{K(K-1)}\sum_{j<k}\Sigma_{jk}$$

$$\text{LLR}_{\text{posterior}} = \text{LLR}_{\text{prior}} + \frac{K_{\text{eff}}}{K}\left(\text{LLR}_{\text{naive}} - \text{LLR}_{\text{prior}}\right)$$

With four specialists at $\bar{\rho}_{\text{corr}} = 0.6$, $K_{\text{eff}} \approx 1.8$ — the evidence term is discounted by well over half. That is the honest number, and it should feel uncomfortable.

**2. Cap the per-instrument evidence term.** Independent of correlation, bound $|\text{LLR}_{\text{posterior}} - \text{LLR}_{\text{prior}}| \le \Lambda_{\max}$ so no unanimous chorus can manufacture unbounded conviction from a single underlying observation.

⚠️ $\Sigma$ requires history that does not exist yet (§3.2). **Until it is measured, set $\bar{\rho}_{\text{corr}} = 0.7$ by assumption** — deliberately pessimistic, in keeping with the doc 07 §4.2 rule that unmeasured parameters default against us.

#### 3.1.2 Decision rule — gated, not summed

An `OrderIntent` is emitted if and only if **all** of the following hold:

1. $|\text{LLR}_{\text{posterior}}| \ge \theta_{\text{threshold}}$
2. **Corroboration gate (§6):** for an *entry*, at least one **market-plane** specialist (technical or options-OI) agrees in sign with $\text{LLR}_{\text{posterior}}$. News and macro alone can never open a position, however strong their scores.
3. **Veto gate:** no specialist holding veto authority is opposed above its veto strength. Macro regime and news risk are **vetoes, not summands** (§3.3).
4. All deterministic risk-engine constraints pass (doc 07 §3).

Gates 2 and 3 exist because a pure sum silently violates the instruction-source boundary in §6 — a sufficiently strong news score alone would cross $\theta$ and initiate a trade on text. That is the exact failure §6 was written to prevent, and no threshold value fixes it. **It has to be a gate.**

Exits are unaffected by all of the above. Nothing here can block an exit (doc 07 §3).

#### 3.2 ⚠️ Cold start — this model is not runnable at Phase 5

$w_k$, $\rho_k$, and $\Sigma$ are all **empirical** — they require a track record of specialist calls scored against outcomes. With no strategy (G-01) and no paper history, none exists.

Staged introduction:

| Stage | $w_k$ | $\rho_k$ | $\bar{\rho}_{\text{corr}}$ | Behaviour |
|---|---|---|---|---|
| Cold (Phase 5 start) | Equal | Fixed low (0.55) | 0.7 assumed | Near-prior; trades only on strong unanimous signals |
| Warming (≥ 200 scored calls/specialist) | Equal | Measured | Measured | Weights still equal — too little data to differentiate |
| Warm (≥ 1,000 scored calls) | Measured | Measured | Measured | Full model |

**Never let a specialist's weight be set by its own claimed confidence.** $c_{i,k}$ is self-reported and an LLM will happily report high confidence on noise; $w_k$ and $\rho_k$ must come from realized outcomes only.

#### 3.3 What this does *not* solve (G-21 stays open)

This is an **aggregation mechanism**, not an arbitration **policy**. It answers "how do we combine scores," not the question G-21 actually asks: *what should happen when the technical specialist says +0.8 and macro says −0.9?*

A sum answers "roughly zero, stand down." That is often wrong — a macro regime veto should **dominate** rather than net out against a chart pattern, which is why §3.1.2 makes it a gate. The remaining open questions:

- Which specialists hold veto authority, at what strength, over which horizons?
- How are genuine disagreements *between market-plane* specialists resolved (technical bullish, options-OI bearish)?
- Does $\theta_{\text{threshold}}$ vary by regime, instrument liquidity, or time of day?

Those are decision-quality questions, and they remain **G-21, OPEN**.

---

## 4. News sub-pipeline (information source)

**Why it exists:** the only signal that *anticipates* discontinuous (gap) moves; every price-based agent is reactive. **Free against Kite limits** (independent source).

⚠️ **2026-07-23 — reconsider under D-16.** An end-of-day system cannot react to an intraday headline: an 11 a.m. catalyst is seen at close or the next morning. That removes most of this pipeline's *timing* value. Two things it still does under a positional cadence:
- **Overnight event awareness** — flagging results/earnings/corporate-action dates on held names *feeds the gap-risk de-risk* (G-18), which is now the dominant danger. This is arguably more valuable than before, just for a different reason.
- **Slow catalyst context** for the next-morning decision.
But at ~$1,250/yr it is now the **largest single LLM line** in a ~$2,200 total (G-11). **It must justify that cost against its narrowed role** — quite possibly reduced to a cheap calendar-driven event flag rather than a full ingest+classify+impact pipeline. Decide before Phase 4.5.

**Stages (mirrors screener→specialist):**
1. **Ingest + dedupe + entity-resolve** — fetch from sources (see below), collapse the same story from N sources into one event, and **map headline → instrument token** via the instruments master.

#### Entity resolution — a cascade, with string distance last

**Resolution is tried in strict order. String similarity is the final fallback, never the first tool.**

**Tier 0 — the symbol is already in the feed (covers most of our volume).**
NSE and BSE corporate-announcement feeds — our primary sources — **carry the scrip symbol or code in the payload.** For these, resolution is a dictionary lookup against the instruments master with confidence 1.0. No fuzzy matching, no ambiguity, no LLM. Any design that runs string similarity over an announcement that already told us the symbol is introducing error for free.

**Tier 1 — curated alias dictionary.** A maintained map of `alias → exchange:tradingsymbol`, seeded from the instruments master `name` field and extended by hand as misses appear: common short forms ("Infy", "RIL", "HDFC Bank"), former names, and post-merger renames. Exact or normalized-exact match only. Confidence 1.0.

**Tier 2 — context disambiguation.** When Tier 1 yields **multiple** candidates, disambiguate on co-occurring evidence in the article — sector, exchange, ISIN, registered office, named executives, prior stories about the same entity — rather than on which name is more similar.

**Tier 3 — string similarity, quarantine only.** Only if all of the above fail:

$$\text{Score}(H, T_j) = \alpha \cdot \text{JaroWinkler}(H, T_j) + (1-\alpha) \cdot \left[ 1 - \frac{\text{LevenshteinDistance}(H, T_j)}{\max(|H|, |T_j|)} \right], \quad \alpha = 0.6$$

**A Tier 3 match never auto-binds.** It produces a *candidate* that goes to quarantine for contextual validation. Below 0.65, discard as unmapped.

#### ⚠️ Why string distance must not auto-bind

The previous version of this section auto-bound any score ≥ 0.85. **String distance is maximally confident precisely where a wrong answer is most expensive — sibling entities within one corporate group:**

| Pair | Similarity | Reality |
|---|---|---|
| Bajaj Finance / Bajaj Finserv | very high | Different companies, different businesses, both listed |
| Bajaj Finance / Bajaj Auto | high | Unrelated businesses, same promoter group |
| HDFC Bank / HDFC Ltd | very high | Distinct listings, distinct histories |
| Tata Motors / Tata Motors DVR | near-identical | Different instruments, different prices |
| Motherson / Motherson Sumi Wiring | high | Separate listed entities post-demerger |

Each of these would auto-bind under a 0.85 threshold, and **every one of them resolves trivially at Tier 0 or Tier 1.** This is the exact failure mode G-22 names: a wrong mapping triggering the wrong trade, with the pipeline reporting high confidence while doing it.

**The general rule:** in a market where corporate groups share a name prefix across many listed entities, orthographic similarity is close to *anti*-correlated with referential identity. The more similar two Indian tradingsymbols look, the more likely they are to be different companies that a naive matcher will confuse.

#### Guardrails

- **Corroboration still applies.** Even a confidence-1.0 Tier 0 match cannot initiate a trade alone — §6 and §3.1.2 require market-plane confirmation. Entity resolution errors can therefore cause a missed or spurious *flag*, but not by themselves a wrong *position*.
- **Measure it.** Maintain a labelled test set of headline→symbol pairs, including deliberate sibling-entity traps, and track precision per tier. ⚠️ Thresholds are asserted starting points, not derived — they must be fitted against that set (G-22).
- **Mis-resolutions are logged with the tier that produced them**, so tier-level precision is visible rather than aggregate.

2. **Classify / sentiment** (cheap model) — extract *structured fields*: `{entity, instrument_token, event_type, sentiment, salience, source, ts}`. **This is the untrusted-content → structured-data boundary** (see §5).
3. **Impact analyst** (strong model, **high-salience only**) — reason about second-order effects (supplier→customer, sector read-through).

**Consumers:** screeners (catalyst flags), risk manager (veto/context), subscription manager (**promote flagged names to Full mode**).

**Sources (India-first, highest signal/₹):** NSE/BSE corporate-announcement feeds, earnings & corporate-actions calendar, RBI/SEBI; optional paid wire only if budget justifies. Do **not** expect to beat pros on marquee headlines — edge is breadth + synthesis across the full watched universe, including the long tail nobody is covering.

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
- Backpressure: specialists lagging → screeners throttle; manager lagging → **open nothing new**.
- **`positions` is read-only here.** The cognition plane observes position state; it does not own it. The Position Manager (doc 07 §4) is the owner, and it acts on its own schedule regardless of what this graph is doing.
- **Open (doc 11, Gap G-10):** confirm LangGraph meets the live latency budget for the funnel, or use a lighter custom orchestrator for the live path while keeping LangGraph for static study.
  - *2026-07-22 note:* materially less risky since exits became deterministic. Orchestrator latency now delays only **entries** — a missed opportunity, not an unmanaged position. This graph being slow is a performance problem, no longer a safety one.

---

## 8. Cost & model tiering

- Haiku for high-frequency screening; Sonnet for specialists/study/news-classify; Fable for the manager + macro impact analyst (rare, high-stakes).

### 8.1 Token-spend estimate (G-11 — first quantified pass, 2026-07-22)

**Prices per 1M tokens** ✅ *(verified 2026-07-22)* — Haiku 4.5 **$1 / $5**, Sonnet 5 **$3 / $15**, Fable 5 **$10 / $50** (input / output).

**Session basis:** 09:15–15:30 IST = 6.25 h = 22,500 s; 250 trading days/year.

| Component | Model | Assumptions | Per session | Per year |
|---|---|---|---|---|
| Screeners | Haiku | 10 workers, 30 s cycle, **deterministic pre-filter** → ~50 instruments/call (3.5k in / 0.5k out) | $45 | **$11,250** |
| Risk manager | Fable | 100 decisions, 15k in / 5k out **incl. thinking** | $40 | **$10,000** |
| Specialists | Sonnet | 400 assessments, 8k in / 1.5k out | $19 | **$4,650** |
| News pipeline | Haiku + Fable | 500 classify + 20 impact analyses | $5 | **$1,250** |
| Static study fleet | Sonnet | 16 agents, one nightly run, 30k in / 4k out | $2 | **$600** |
| **Total** | | | **≈ $112** | **≈ $28,000** |

At roughly ₹85–90/USD that is **≈ ₹24 lakh/year, ≈ ₹2 lakh/month.** ⚠️ Order-of-magnitude only — every token count above is an assumption, not a measurement.

### 8.2 What the estimate actually tells us

**0. ⚠️ At single-user scale, ask first whether this fleet should exist.** The full fleet costs ~₹24 lakh/year against a **single account** (D-13). It breaks even — LLM cost equal to *all* gross profit — at roughly **₹1.23 crore of capital at a 20% return**, and only drops below 20% of profit above **₹6.2 crore**. Below ~₹1 crore the agent fleet cannot pay for itself and the deterministic spine alone is the rational configuration. **See G-44 before building any of what follows.**

**1. LLM spend is ~400× the broker subscription.** Kite Connect is ₹500/month; the agent fleet is ~₹2,00,000/month. Every other line in doc 10 §5 is a rounding error. **Cost control in this project means token control, full stop.**

**2. The dominant lever is not model choice — it is how much the LLM sees.**

| Screener design | Per year |
|---|---|
| **Naive** — LLM reads state for all 900 instruments in its partition | **$59,000** |
| **Pre-filtered** — deterministic code computes indicators; LLM sees only the ~50 that tripped a threshold | **$11,250** |

A **5× swing on the largest line**, with no change of model, agent count, or cadence. The design consequence is concrete and belongs in the architecture, not in a tuning pass:

> **Screeners must never receive the raw universe. Deterministic Rust computes the numeric screen; the LLM only ever adjudicates what already tripped a threshold.** An LLM asked to notice that a number crossed a level is paying frontier-model rates to do arithmetic.

This also sharpens what the screener tier is *for*: not "find movers" (code does that) but "judge whether this mover means anything," which is genuinely a language task.

**3. The singleton risk manager is 36% of the bill.** Being one agent does not make it cheap — Fable's always-on thinking bills as **output at $50/1M**, so a manager that thinks ~3k tokens per decision costs more than 400 Sonnet specialist calls. If §3.1's aggregation formula makes the manager largely arithmetic, the Fable tier is very hard to justify — **D-12 and D-10 should be revisited together against this number**, not separately.

**4. Prompt caching helps the manager, not the screeners.** The manager's prefix (book, regime, limits) is stable across calls — a 70% cache hit takes it from $10,000 to ~$7,400/year. Screener input is live market state, which changes every cycle and is structurally uncacheable. Do not expect caching to rescue the screener line.

**5. Cadence is a linear dial.** 30 s → 60 s halves the screener line ($11,250 → $5,625). Whether a 60-second scan loses real signal is an empirical question and a cheap experiment — run it in Phase 5 before sizing the fleet.

### 8.3 Ranked cost levers

| Lever | Saving | Cost of pulling it |
|---|---|---|
| Deterministic pre-filter before screeners | **~$48k/yr** | None — it is strictly better design |
| Drop the manager from Fable to Sonnet | ~$8k/yr | Weaker arbitration; depends on D-12 |
| Screener cadence 30 s → 60 s | ~$5.6k/yr | Possible signal loss — measure first |
| Prompt-cache the manager prefix | ~$2.6k/yr | None — pure implementation work |
| Cut screeners 10 → 6 | ~$4.5k/yr | Less universe coverage per cycle |

**Cheapest viable live fleet** (6 screeners at 60 s, Sonnet manager, aggressive caching): roughly **$8–10k/year**. That is the floor to plan against if the strategy turns out not to need breadth.

### 8.4 ⚠️ What would change these numbers

Every input is an assumption. The ones that would move the total most, in order:

1. **Tokens per screener call** — the largest single driver. Depends entirely on the pre-filter's output size and how state is serialized. **Measure with `count_tokens` against a real payload in Phase 5 before sizing anything.**
2. **Manager thinking length** — assumed 3k tokens/decision. Fable's effort setting moves this directly, and it is billed at the highest output rate in the stack.
3. **Decision and assessment counts** — assumed 100 and 400 per session. These follow from the strategy (G-01), which does not exist yet.
4. **Screener cycle time** — assumed 30 s. Linear in cost.

A concrete Phase 5 exit criterion: **run one paper session with full token accounting per agent tier and reconcile against this model.** If reality is within 2×, the model is good enough for planning; if not, re-derive before scaling the fleet.
