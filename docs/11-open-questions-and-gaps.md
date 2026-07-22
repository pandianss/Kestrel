# 11 — Open Questions & Known Gaps

**Last updated:** 2026-07-22

> **This is the gap-finding target.** These are the things we know are undecided, unverified, or risky. Reviewers should (a) challenge them, (b) add ones we missed, and (c) flag anywhere the rest of the design contradicts itself.
>
> **To add a gap, follow the template in [REVIEWING.md](REVIEWING.md).** Consistent entries are what make this register usable by more than one reviewer.

**Severity:** 🔴 blocker · 🟠 significant · 🟡 to firm up
**Status:** `OPEN` · `IN DESIGN` (a direction is committed, detail pending) · `CLOSED` (resolved — with the resolution recorded) · `ACCEPTED` (known risk we are choosing to carry)

---

## Register at a glance

| ID | Sev | Status | Area | Summary | Resolve by |
|---|---|---|---|---|---|
| [G-01](#g-01) | 🔴 | OPEN | Strategy | No trading strategy exists | Before Phase 5 |
| [G-02](#g-02) | 🟠 | **IN DESIGN** | Regulatory | SEBI framework — **not an algo provider** ✅; **downgraded 🔴→🟠** | **Phase 0** |
| [G-03](#g-03) | 🔴 | OPEN | Data | QuestDB ingest at 9,000-instrument volume unmeasured | Phase 1 |
| [G-09](#g-09) | 🔴 | **IN DESIGN** | Execution | Fill fidelity — conservative defaults + replay now specified | Phase 3 |
| [G-18](#g-18) | 🔴 | OPEN | Risk | Risk limits — **starting envelope proposed** | Phase 3 |
| [G-28](#g-28) | 🔴 | **IN DESIGN** | Execution | **No exit path existed** — Position Manager added | Phase 3 |
| [G-29](#g-29) | 🔴 | **IN DESIGN** | Risk | **No margin model** — approach specified, values open | Phase 3 |
| [G-04](#g-04) | 🟠 | **IN DESIGN** | Data | Storage — estimated ~5 GB/day; retention policy open | Phase 1 |
| [G-05](#g-05) | 🟠 | **CLOSED** | Regulatory | Multiple API keys — **largely not viable** | — |
| [G-06](#g-06) | 🟠 | **IN DESIGN** | Data | Promotion policy — **priority + hysteresis specified** | Tune Phase 1 |
| [G-07](#g-07) | 🟠 | **ACCEPTED** | Ops | Distributed limiting — moot while single-host | If we split |
| [G-08](#g-08) | 🟠 | **IN DESIGN** | Data | Corp actions — **split/bonus only; dividends not** | Phase 2 |
| [G-10](#g-10) | 🟠 | OPEN | Cognition | LangGraph live-latency fit unconfirmed | Phase 5 |
| [G-11](#g-11) | 🟠 | **IN DESIGN** | Cost | **Token spend modelled — approx $28k/yr, caps fleet** | Measure Phase 5 |
| [G-12](#g-12) | 🟠 | **ACCEPTED** | Regulatory | Automated login — 2FA now mandatory; stay manual | — |
| [G-13](#g-13) | 🟠 | OPEN | Strategy | Which 9,000 — **widening now known to be cheap** | Before Phase 1 scale-up |
| [G-19](#g-19) | 🟠 | **IN DESIGN** | Execution | Cost model — **real rates sourced & dated** | Phase 3 |
| [G-21](#g-21) | 🟠 | OPEN | Cognition | Arbitration policy undefined | Phase 5 |
| [G-24](#g-24) | 🟠 | OPEN | Security | Injection defence untested | Phase 6 |
| [G-31](#g-31) | 🟠 | **IN DESIGN** | Ops | Redis streams — **caps now sized (~100 MB)** | Phase 0 |
| [G-32](#g-32) | 🟠 | **CLOSED** | Testing | **Replay harness** — now a Phase 1 deliverable | — |
| [G-33](#g-33) | 🟠 | **IN DESIGN** | Data | **Bad-tick filter** — gate specified, thresholds open | Phase 1 |
| [G-30](#g-30) | 🟠 | **IN DESIGN** | Execution | **MIS square-off** unmodelled — now specified | Phase 3 |
| [G-14](#g-14) | 🟡 | OPEN | Strategy | Profitability metrics need G-01 | After G-01 |
| [G-15](#g-15) | 🟠 | **ACCEPTED** | Regulatory | Storage **proceeding** (not shared); display/India/termination limits stand | — |
| [G-16](#g-16) | 🟡 | **CLOSED** | Data | Bandwidth — ~2 Mbps, a non-issue | — |
| [G-17](#g-17) | 🟠 | **IN DESIGN** | Data | Session calendar — **phases + rules specified** | Phase 1 |
| [G-20](#g-20) | 🟡 | **IN DESIGN** | Execution | LIMIT-only — **effects enumerated; stops optimistic** | Phase 3 |
| [G-22](#g-22) | 🟠 | **IN DESIGN** | Cognition | News → token mapping — **upgraded 🟡→🟠**; cascade adopted | Phase 4.5 |
| [G-39](#g-39) | 🟠 | **IN DESIGN** | Risk | **Exit throughput caps book size** | Phase 3 |
| [G-23](#g-23) | 🟡 | **IN DESIGN** | Research | Look-ahead — replay clock enforces structurally | Phase 2 |
| [G-25](#g-25) | 🟡 | **IN DESIGN** | Ops | Time sync — **fail-safe-on-skew specified** | Phase 1 |
| [G-26](#g-26) | 🟡 | OPEN | Ops | End-to-end recovery test | Phase 6 |
| [G-27](#g-27) | 🟡 | **ACCEPTED** | Ops | Single-host SPOF — fine for paper | Before live |
| [G-34](#g-34) | 🟡 | **CLOSED** | Scope | Coverage framing corrected | — |
| [G-35](#g-35) | 🟡 | OPEN | Process | No owner or date on any gap | Ongoing |
| [G-36](#g-36) | 🔴 | **IN DESIGN** | Execution | **Passive Limit Fill Queue Mechanics** — L2 vs L3 depth gap | Phase 3 |
| [G-37](#g-37) | 🟠 | OPEN | Cognition | **Non-Stationary Agent Weights** across market regimes | Phase 5 |
| [G-38](#g-38) | 🟠 | OPEN | Risk | **SPAN Grid Computation Latency** under multi-leg F&O | Phase 3 |
| [G-40](#g-40) | 🟠 | OPEN | Regulatory | **Exchange holds a kill switch on our Algo ID** | Before live |
| [G-41](#g-41) | 🟠 | OPEN | Regulatory | **LLM strategy likely "black box"** — 10 OPS effectively permanent | If >10 OPS contemplated |
| [G-44](#g-44) | 🔴 | OPEN | Cost | **Agent fleet may not pay for itself** at single-user scale | Before Phase 4 |
| [G-42](#g-42) | 🔴 | OPEN | Research | **LLM strategies not backtestable** — forward-test only | Before Phase 4 |
| [G-43](#g-43) | 🟠 | OPEN | Research | **Point-in-time reference data not captured** — unrecoverable | **Phase 0** |

**Where the register stands:** 44 gaps — **9 blockers, 26 significant, 9 to firm up**; by status **13 OPEN, 19 IN DESIGN, 4 CLOSED, 3 ACCEPTED**.

**The regulatory blocker is gone.** G-02 dropped 🔴 → 🟠 once algo-provider status was resolved — **no remaining regulatory question threatens the architecture.** Of the seven blockers left, **six are engineering** (G-03, G-09, G-28, G-29, G-36 and the G-18 sign-off) and exactly one is a product question: **G-01, there is still no strategy.**

**Phase 0 has no external blocker left.** Both owner questions are answered (client OPS limit = 10; local storage proceeding). The only outstanding compliance item — how the generic Algo ID attaches — is discovered during wiring, not before it.

**Nothing is CLOSED because it was solved by building something** — every closure so far is "we checked, and the concern was either misplaced or answerable on paper." Worth keeping visible: **this register has not yet been tested against reality even once.** Nineteen entries sit at IN DESIGN, which means a direction is committed and unvalidated — that is the honest state of the project, and the number to watch is how many convert to CLOSED *by measurement* rather than by further design.

**A pattern worth noting across two review passes:** the additions that most improved the design (deterministic exits, margin, tick sanity, exit throughput) all came from tracing *one position through its whole life*, while the errors that most needed catching (borrowed impact constants, string-similarity auto-binding, a locally-computed SPAN, summing correlated evidence) all came from **specifying something precisely enough to look finished before it was calibrated**. Precision is not the same as correctness, and formal notation makes unvalidated assumptions harder to see, not easier. Every asserted constant in this repo now carries a ⚠️ for that reason.

---

## A. Strategy & product

<a id="g-01"></a>

### G-01 🔴 — There is no trading strategy yet
**Status:** OPEN · **Resolve by:** before Phase 5

The entire design is **strategy-agnostic plumbing**. It can carry *a* strategy but defines *none*. What constitutes an edge — entry/exit logic, signals, holding periods, instruments, long/short, cash vs. F&O — is undefined.

*Why it matters:* everything downstream (which specialists, which risk limits, success metrics, universe selection) depends on it. A perfect pipeline with no edge loses money net of costs.

*Proposed direction:* treat the first strategy as a **pluggable module** the risk manager consumes; define at least one concrete, testable strategy before Phase 5.

*2026-07-22 note:* the exit-path and margin gaps below (G-28, G-29) strengthen the case for a thin vertical slice first — both were invisible at the architecture level and would have surfaced immediately from carrying one real position. See doc 09, "thin vertical slice."

<a id="g-13"></a>

### G-13 🟠 — Universe selection criteria
**Status:** OPEN · **Resolve by:** before scaling past a few hundred instruments in Phase 1

"Max universe" is a capacity, not a selection. Which instruments fill the 9,000 (all F&O? NIFTY 500 + their options? a liquidity filter?) is undefined and interacts with tiering, cost, and the strategy.

*2026-07-22 notes — three constraints now bound this decision that didn't before:*

1. **9,000 is a sample, not the market** (G-34). NSE cash is ~2,000 names; NFO option contracts run into the tens of thousands. This is a sampling decision with real consequences.
2. **Breadth of watching ≠ breadth of holding** (G-39). Exit throughput caps concurrent positions at roughly 10 for a 5-second worst-case flatten. Watching 9,000 instruments to hold 10 positions is defensible — that *is* the funnel thesis — but it should be a deliberate ratio, not an accident.
3. **Universe size no longer drives screener cost the way it appeared to** (G-11). With the deterministic pre-filter, screener cost scales with *how many instruments trip a threshold per cycle*, not with universe size. **Widening the universe is much cheaper than it looks; loosening the filter is much more expensive than it looks.** That inverts the intuitive trade-off and should shape the selection criteria directly.

*Proposed direction (owner decision):* select on **liquidity and tradability** rather than count — an instrument earns a slot if it could actually be traded at the intended size without dominating the book. That naturally excludes the illiquid option strikes that inflate the raw contract count while being untradable in practice. Start narrow (a few hundred liquid names), measure, and widen — the cost model says widening is affordable.

<a id="g-14"></a>

### G-14 🟡 — Success metrics beyond system quality
**Status:** OPEN · **Resolve by:** after G-01

Profitability and risk-adjusted targets (Sharpe, max DD) can't be set without a strategy. Doc 01 §6 defines only system-quality metrics.

<a id="g-34"></a>

### G-34 🟡 — 9,000 is a sample, not "the market" *(new)*
**Status:** **CLOSED — framing corrected** *(2026-07-22)*

The README described watching "**all** 9,000 instruments." NSE cash carries roughly 2,000 names and NFO option contracts run into the tens of thousands, so 9,000 is a **selection**, not full coverage. G-13 asked *which* 9,000 without noting that the headline claim overstated reach — and "breadth is our edge" is the core thesis, so the number should be described accurately.

*Resolution:* README updated to describe the universe as the largest slice one API key can stream, with selection called out as the open decision it is (G-13). No architectural change.

---

## B. Regulatory & ToS (India-specific — do not skip)

<a id="g-02"></a>

### G-02 🟠 — SEBI retail algo framework
**Status:** **IN DESIGN** · **Severity downgraded 🔴 → 🟠** *(2026-07-22)* · **Resolve by:** **Phase 0**

> **Why downgraded:** 🔴 meant *"building further produces work that must be thrown away."* The scenario that justified it — being classified an **algo provider**, requiring exchange empanelment and a different operating model — is now **resolved: we are not one** (below). What remains is integration detail discovered during Phase 0 wiring, which does not invalidate work already done. Still 🟠: it is in force, it constrains deployment, and regulation moves.

**⚠️ This gap was previously scoped as "verify in Phase 6, before any live consideration." That is no longer available.** The framework took full effect **1 April 2026**, following a phased rollout (broker registration November 2025, mock trading January 2026, new-client cutoff 5 January 2026).

**What we now know applies** (detail in doc 02 §9):

| Requirement | Status in this design |
|---|---|
| Static IP whitelisting for order endpoints | ✅ Specified — doc 10 §1, §3 (Phase 0 prerequisite) |
| **Every API order must carry an algo tag** ⚠️ *corrected* | ✅ `algo_id` now mandatory on every `OrderIntent`, never null — doc 07 §2 |
| >10 OPS ⇒ formal strategy registration | ✅ Our 10/s bucket keeps us in the generic-ID regime |
| Market protection on MARKET/SL-M | ✅ Field added to `OrderIntent` — doc 07 §2 |
| 2FA on every session login | ✅ Reinforces operator-in-the-loop mint — G-12 |
| Algo-provider empanelment | ⚠️ **Open — must confirm self-use is exempt** |

**⚠️ Correction, 2026-07-22 (second) — a stated fact here was wrong.** This gap previously recorded that "below the threshold, API orders are not tagged as algo," and framed one of the Phase 0 questions as *finding* that threshold. **There is no such threshold.**

| | Below 10 OPS | Above 10 OPS |
|---|---|---|
| Algo tag required | ✅ **Yes** | ✅ Yes |
| Identifier | **Generic** Algo ID | Strategy-specific, exchange-issued |
| Formal registration + testing | ❌ No | ✅ **Yes** |

The 10 OPS line governs the **approval burden**, not the **tagging obligation**. Every order generated by API or automation carries an identifier for auditability.

*Why it matters:* the wrong reading would have shipped `algo_id` as a nullable field populated only above a threshold we'd never cross — i.e. **every paper and live order untagged**, which is the precise failure the framework exists to prevent. Fixed in doc 07 §2 (mandatory, never null) and doc 02 §9.3.

*Worth noting about how it was caught:* this was not a fact that went stale — it was **wrong when written**, sourced from a summary that compressed "no strategy registration required" into "not treated as algo." The README's *facts with an expiry date* discipline catches drift; it does not catch a misreading on first pass. **Compliance facts warrant a primary source, not a summary** — added to REVIEWING.md.

**✅ Resolved 2026-07-22 — we are not an "algo provider."** Running an algorithm exclusively for yourself and **immediate family** on a single account does not trigger exchange empanelment. Broader than the earlier framing, which considered only single-account self-use. Corroborated by Kite's static-IP rules, which permit sharing among spouse, dependent children, and dependent parents — the IP rule and the algo-provider rule draw the same family boundary (doc 02 §9.4).

**Why this was the load-bearing question.** The algo-provider path is a different regulatory regime — empanelment, broker-as-Principal, per-strategy approval. It was the one open item that could have made this design *the wrong shape* rather than merely needing adjustment. With it closed, no remaining regulatory question threatens the architecture.

⚠️ *Not a capacity lever.* Family accounts have their own client IDs and their own 10/s budgets, but using a relative's account to raise throughput for one strategy is the pattern G-05 already ruled out. The exemption concerns *whose money is traded*, not rate-limit aggregation. **G-05 stays closed.**

**✅ Answered 2026-07-22 — our client-level OPS limit is 10.** NSE §F permits the broker to set a lower per-client limit; Zerodha does not — retail algo trading is **10 orders per second**, matching TOPS. Corroborated across three independent sources: NSE `INVG/67858` §B.2/§F, the Kite Connect FAQ (*"10 orders per second (OPS) per client (trading) account"*), and owner confirmation. **G-39's book-size derivation therefore stands as written** — 10/s total, 2/s reserved for exits.

**What remains genuinely open — integration details, not design risks:**
1. **How the generic Algo ID is issued and attached** — bound to the API key server-side, or passed per order? Determines whether `algo_id` is config or a request field. *(This replaces the earlier question about a no-tagging threshold, which rested on a wrong premise — see below.)*
3. Whether anything further applies specifically to LLM-driven decisioning — the framework was written with conventional algos in mind.

*Direction:* ask Zerodha all three in **Phase 0** and record the answers with dates in doc 13. These can invalidate the project, so they precede the ingester.

⚠️ *This area moves faster than this document. Re-verify before live regardless of what is written here — and note that this gap's own original text said "verify the current (2026) rules — they have evolved." It was right.*

<a id="g-05"></a>

### G-05 🟠 — Multiple API keys to raise the ceiling
**Status:** **CLOSED — largely not viable** *(2026-07-22)*

*Original claim:* additional keys/subscriptions each add 3 WS connections and a fresh rate budget, raising the ceiling.

*Finding:* two facts undercut it. The **10 orders/second limit is scoped to the Kite client ID**, applying regardless of how many apps sit under one developer profile. And the SEBI framework pushes toward **unique credentials per client with one static IP per developer profile** — a fan of keys under one operator is the pattern the rules discourage.

*Resolution:* plan all capacity on **one key, one budget**. Extra WebSocket capacity may remain technically possible, but it is a question for Zerodha, not a planning assumption. Doc 05 §2 updated.

<a id="g-12"></a>

### G-12 🟠 — Automated daily login (TOTP)
**Status:** **ACCEPTED — stay operator-in-the-loop** *(2026-07-22)*

Automating the 6 AM mint via headless browser + TOTP was flagged as a ToS gray area. **2FA is now mandatory on every API session login under the SEBI framework**, which makes unattended automation harder to defend, not easier.

*Resolution:* accept the daily manual step. Build the helper to make it fast (one click, token distributed to all services), not to remove the human.

*Residual:* doc 02 §1 notes a `refresh_token` exists for "approved platforms." Worth one question to Zerodha about what that status requires — but do not design around it.

<a id="g-15"></a>

### G-15 🟠 — Data redistribution & storage terms
**Status:** **IN DESIGN** · **Severity upgraded 🟡 → 🟠** *(2026-07-22)* · **Resolve by:** before any dashboard leaves the host

✅ **Answered on the redistribution half** (Zerodha Kite Connect FAQ): *"Displaying or redistributing Kite Connect API data on external platforms violates exchange data vending policies."* Kite Connect is an **order execution platform, not a data distribution service**. Data sharing requires an exchange-authorised vendor.

*Why upgraded:* the design has a **Grafana instance showing live tick rates, P&L, and per-instrument state** (doc 10 §4). Local and private, that is clearly fine. But "put the dashboard behind a login so I can check it from my phone" is a completely ordinary thing to do, costs nothing, and may cross into **displaying exchange data on an external platform**. This was filed as a Phase 6 licensing footnote; it is actually a constraint on a component already in the design.

*Direction:*
- **Dashboards stay on the host, reachable only over VPN or SSH tunnel.** No public endpoint, no hosted Grafana, no third-party alerting service that would carry price data in its payload.
- **Alerts carry state, not prices.** "Kill-switch tripped," "reconciliation mismatch," "feed stale for 30 s" — not "NIFTY at X." Keeps notification channels clear of market data entirely.
- **Derived outputs are the open question.** P&L, positions, and agent decisions are ours; a screenshot of a live depth ladder is not. ⚠️ The line between "our derived analytics" and "redistributed exchange data" needs Zerodha's read before anything is shared, published, or shown to anyone outside the family scope (§9.4).

**✅ Kite ToS reviewed 2026-07-22 — three findings and one unresolved ambiguity** (full text in doc 02 §9.7):

1. **The display restriction is narrower than feared:** *"cannot be displayed to **the public at large**."* A private operator dashboard is not that. Grafana behind VPN stays viable.
2. **`ap-south-1` is a licence term, not a latency choice:** *"limited license… for use **within India**."* A future cost optimisation moving the host offshore would breach it. Record it as a constraint (doc 03 §5, doc 10 §3).
3. **The research corpus is a leasehold:** on termination we must *"delete any cached or stored content."* Years of accumulated ticks are **rented, not owned** — worth knowing before anyone treats proprietary history as a moat.

🔴 **The unresolved ambiguity, and it is load-bearing.** The ToS prohibits *"scrape, **build databases**, or otherwise create permanent copies of such content, or keep cached copies **with the intent of redistributing**."* Does the redistribution qualifier scope the whole list or only the last item?

| Reading | Effect |
|---|---|
| **Strict** — no database-building at all | **QuestDB tick store and the entire research plane are non-compliant** |
| **Permissive** — only when for redistribution | We are fine; we redistribute nothing |

Permissive is far more plausible (Zerodha *sells* historical data; the support page frames the concern entirely as display on other platforms; a blanket storage ban would make the historical API near-useless). But this is exactly the compressed-negation pattern that produced the algo-tagging error — **plausible is not confirmed.**

**✅ Owner decision, 2026-07-22 — proceed on the permissive reading. Status → ACCEPTED.**

Data will be stored locally for backtesting and **will not be shared, displayed, or redistributed** in any form.

*Why this resolves it in practice:* every restriction the ToS actually imposes is about content leaving our control — public display, sale, lease, distribution, sublicensing, misrepresenting ownership. A local store that never leaves the host does not engage any of them. The sibling-bullet context (doc 02 §9.7) supports this reading, and Zerodha selling historical data as part of the subscription would make a blanket storage ban incoherent.

**⚠️ Recorded as ACCEPTED, not CLOSED — and the distinction is deliberate.** Zerodha has not ruled on the clause; we are choosing to proceed on the more plausible of two readings. That is a reasonable risk to carry, but it is a *carried risk*, not a resolved question, and the compliance record should say so.

**What would force a revisit:**
- Any intent to display, publish, or share data or derived visualisations outside the family scope (doc 02 §9.4) — that crosses from storage into distribution and re-opens this immediately.
- A Zerodha ToS revision touching §4(b).
- Termination of the subscription — ToS §9(b) requires deleting stored content, so the research corpus does not survive the agreement (doc 02 §9.7).

*Standing constraints that remain in force regardless:* dashboards stay on-host behind VPN, alerts carry state not prices, and the host stays in India (ToS §1).

---

## C. Data plane

<a id="g-03"></a>

### G-03 🔴 — QuestDB ingest throughput
**Status:** OPEN · **Resolve by:** Phase 1

Assumed, not measured. 9,000 instruments in mixed modes is a large sustained write load.

*2026-07-22 note:* doc 06 §6 now estimates ~233 KB/s and ~9,000 updates/sec. **The byte volume is trivial; the write *rate* is the risk.** This remains 🔴 — but the question is now specifically "can QuestDB sustain ~9k writes/sec on our host," which is directly testable in an afternoon.

*Direction:* measure in Phase 1 before committing; TimescaleDB / ClickHouse as fallbacks.

<a id="g-04"></a>

### G-04 🟠 — Storage sizing & retention
**Status:** **IN DESIGN** · **Resolve by:** Phase 1

*Estimated 2026-07-22:* ~5.2 GB/day raw (~1.2 TB/year) uncompressed, per doc 06 §6.

*What remains open:* actual compression ratio, and the **retention policy** — specifically how long to keep Full-mode depth, which is the bulk of the volume and the least reusable. Measure in Phase 1, then decide.

<a id="g-06"></a>

### G-06 🟠 — Tiered subscription promotion/demotion policy
**Status:** **IN DESIGN — policy specified** *(2026-07-22)* · **Resolve by:** tune in Phase 1

The *mechanism* was defined; the *policy* was not. Now specified in doc 06 §1.3:

- **The cap is CPU/storage/usefulness-bound, not bandwidth-bound** — doc 06 §6 shows even all-Full is ~13 Mbps. This reframes the whole tuning question away from network fear.
- **Priority-ordered admission** rather than first-come: open positions → pending orders → news catalysts → morning promotion list → intraday heuristics, with eviction from the bottom.
- **Hysteresis**: asymmetric promote/demote thresholds, minimum dwell time, demotion grace period, and a global mode-change rate limit.
- **Single-writer arbitration** — the Subscription Manager owns Full-tier allocation; all promotion requests are advisory and enter a priority queue.

**The finding worth carrying:** *an instrument with an open position must never lose Full-mode depth.* Stop evaluation degrades to last-price without it, which silently weakens the exit path (G-28). This is now a hard invariant with a zero-tolerance metric attached, not a tuning preference — and it is the kind of cross-component coupling that only appears when you trace one position's whole life.

*Still open:* every threshold is asserted. Tune against replayed sessions, measuring mode-changes/minute, time-to-promote after a catalyst, and how often the cap binds.

<a id="g-08"></a>

### G-08 🟠 — Corporate-action adjustment
**Status:** **IN DESIGN — partially answered** *(2026-07-22)* · **Resolve by:** Phase 2

**Verified:** Kite adjusts historical candles for **splits and bonuses only**, applied at start-of-day on the ex-date, covering data from 2012 onward. **Dividends, rights issues, and demergers are not adjusted.** Full detail in doc 02 §5.1.

**The gap is narrower than feared but three real problems remain:**

1. **Unadjusted dividend ex-dates are systematic, not occasional.** Every ex-date produces a gap down that was never a real loss. Gap-detection, momentum, and stop-distance logic all read it as a genuine move — a backtest can manufacture signal from the dividend calendar.
2. **Adjustment timing creates a live-vs-historical inconsistency.** The same historical date returns different prices before and after the ex-date SOD process. **Any derived data cached across an adjustment is silently stale** — indicators, regime priors, the study fleet's watchlist. Backfill must *detect adjustment events and invalidate downstream derived data*, not merely append new candles. This is the part most likely to be missed in implementation.
3. **Pre-2019 intraday adjustment is inconsistent** (adjusted intraday from 2015 for active contracts only). Long intraday backtests crossing that boundary are unreliable — start after 2019 or treat earlier intraday as unadjusted.

*Direction:* build a dividend/rights/demerger adjustment layer on top of Kite's split/bonus handling, plus an adjustment-detection step in backfill that invalidates derived data. Neither is optional.

⚠️ *Still to confirm:* exact SOD adjustment timing, and whether `continuous=1` stitched F&O series carry their own adjustment behaviour.

<a id="g-16"></a>

### G-16 🟡 — Bandwidth budget
**Status:** **CLOSED — not a constraint** *(2026-07-22)*

*Resolution:* the target tier mix is **≈233 KB/s ≈ 1.9 Mbps sustained** (doc 06 §6). Even a large open-bell burst multiple leaves this far inside any reasonable host's capacity. Closed as a design question; Phase 1 confirms the number rather than investigating the concern.

*Method note:* this gap sat open because nobody did five lines of arithmetic. Worth remembering when triaging the rest.

<a id="g-17"></a>

### G-17 🟠 — Market hours, holidays, sessions
**Status:** **IN DESIGN** *(2026-07-22)* · **Severity upgraded 🟡 → 🟠** · **Resolve by:** Phase 1

Pre-open, close, holidays, muhurat/special sessions, and F&O expiry-day behaviour are unspecified.

*Why upgraded:* this quietly contains **MIS auto square-off timing** (now G-30), **expiry-day settlement**, and **the pre-open auction window where prices behave differently** — each capable of corrupting paper P&L on its own. It is a cluster of correctness issues, not a calendar detail.

*Direction (adopted):* **one authoritative session calendar**, loaded as data, consumed by the ingester, tick sanity filter, fill simulator, Position Manager, and study fleet alike. Nothing derives session state independently.

**The phases it must expose,** because each changes behaviour somewhere:

| Phase | Typical window (⚠️ verify) | What depends on it |
|---|---|---|
| Pre-open auction | 09:00–09:15 | **No continuous trading — fills must not simulate.** Sets the reference price for the tick filter's open handling (doc 06 §1.6) |
| Continuous | 09:15–15:30 | Normal operation |
| MIS square-off | 15:25 equity / 15:26 F&O | Position Manager's `square_off_at` (doc 07 §4.4) |
| Closing auction | 15:30–15:40 | Different price dynamics; not continuous |
| Post-close / AMO | after 15:40 | Only AMO orders valid |
| Holiday | full day | Everything idle; backfill must not treat as a gap |
| Muhurat / special session | irregular | Short, off-calendar — a hard-coded weekday assumption breaks here |
| F&O expiry day | weekly/monthly | Settlement, position expiry, `continuous=1` stitching boundary |

**Rules that fall out:**
- **The simulator must know the phase.** Filling a paper order during the pre-open auction or on a holiday is a phantom fill, and the tick sanity gate alone won't catch it — the ticks are real, the trading is not.
- **Holidays are not gaps.** Backfill's gap detection must consult the calendar or it will chase missing data that was never generated.
- **Expiry day changes instrument identity.** A reused `instrument_token` after expiry (doc 02 §4) is exactly the case the `exchange:tradingsymbol` key exists for — expiry-day handling is where that mapping earns its place.

⚠️ **Timings above are the shape, not verified values.** They change (MIS square-off moved in December 2025). The calendar is **config with a source and verification date**, refreshed at least annually and checked against exchange circulars.

<a id="g-33"></a>

### G-33 🟠 — No bad-tick sanity filter *(new)*
**Status:** **IN DESIGN** *(2026-07-22)* · **Resolve by:** Phase 1

The fill simulator matches orders against the live tick stream, so an erroneous exchange print, a stale post-reconnect tick, or a circuit artifact produces a **phantom fill and a corrupted ledger**. Doc 06 §4 covered ticks we *didn't get*; nothing covered ticks we *shouldn't trust*. A dropped tick is loud; a wrong tick is silent.

*Direction:* the tick sanity gate in doc 06 §1.6 — circuit bounds, jump filter with confirm-or-reject quarantine, staleness, monotonic volume, post-reconnect resync marking. Suspect ticks reach the cache tagged but are **never fill-eligible**.

*2026-07-22, second pass:* the jump filter is now specified concretely as an **EWMA volatility band** ($\lambda = 0.94$, RiskMetrics-standard) with a two-tick quarantine state machine. This is the strongest-specified check in the data plane.

⚠️ **Session-start handling added, and it is the part that matters most.** Carrying yesterday's intraday $\sigma$ across the overnight break would reject *legitimate* opening gaps — a 5% results-driven gap-up breaches any band fitted to yesterday's tick-to-tick variance. The open is when genuine gaps and bad prints both cluster, so the filter is now: seeded from gap-aware daily range with a widened $\kappa_{\text{open}}$ that decays over ~15 minutes, referenced to the **pre-open auction equilibrium price** rather than the previous close, and running **observe-only until 30 accepted ticks** exist. Illiquid instruments that never warm up keep the jump filter permanently advisory — *a filter with no statistical basis must not hold veto power over its own input.*

*Open:* $\kappa_{\text{open}}$, $N_{\text{warm}}$, $k_1$, $k_2$, and $\theta_{\text{floor}}$ are all asserted. Fit against replayed opening sessions **including known gap days**, and note the asymmetry — at the open, over-rejecting is worse than under-rejecting, because a suppressed genuine gap blinds every downstream agent to the day's most informative move.

---

## D. Execution & risk

<a id="g-09"></a>

### G-09 🔴 — Fill-simulator fidelity
**Status:** **IN DESIGN** · **Resolve by:** Phase 3

An over-optimistic simulator invalidates the whole paper exercise.

*2026-07-22 progress:* doc 07 §4.2 now specifies **conservative defaults for every ambiguous choice** (no fill on touch, cap at displayed depth, non-zero latency and slippage, assume last in queue), and §4.3 makes the **replay harness a Phase 1 deliverable** so validation has a home. Doc 06 §1.6 keeps bad ticks out of the matcher.

*2026-07-22, second pass:* a slippage model now exists — square-root impact law plus half-spread and a stochastic latency term (doc 07 §4.1), together with queue-depletion mechanics that replace the "assume last in queue" placeholder with an actual model. Both are real progress.

⚠️ **But the impact coefficients are borrowed, not fitted.** $\gamma \approx 0.5$ comes from developed-market large-cap studies; Indian mid/small-caps and illiquid NFO strikes — most of a 9,000-instrument universe — show materially higher impact at the same participation rate. Per §4.2's own rule, starting values are now set **above** the literature figure (1.0 liquid, 1.5–2.0 illiquid) and explicitly labelled unfitted priors. Any P&L they produce is a floor, not an estimate.

*Still open:* fitting $\gamma$ per liquidity bucket against replayed sessions, validating the conservative defaults, and confirming the queue model against real fills. Remains 🔴 — this is the assumption the go/no-go rests on, and borrowed constants are precisely how a simulator becomes quietly optimistic.

<a id="g-18"></a>

### G-18 🔴 — Risk limits are placeholders
**Status:** OPEN · **Resolve by:** Phase 3

Doc 07 §3 lists *draft* limits. Real values — per-order cap, exposure caps, daily-loss kill-switch level, sizing method — need an owner decision. They are the core safety envelope.

*2026-07-22 additions to the same decision:* the **feed-loss grace window** and per-product `on_data_loss` default (doc 07 §3.2), the **default stop distance and max holding time** for exit plans, and the **margin safety factor** (G-29). All are owner calls, all are cheap to decide and expensive to leave implicit.

#### A starting envelope to react to (2026-07-22)

These are **not decisions** — they are defensible defaults, put on the table because an owner reacts to concrete numbers far faster than to an empty form. Every one needs your sign-off; the point is to make disagreeing easy.

| Limit | Proposed | Reasoning |
|---|---|---|
| Per-order notional | ≤ 2% of paper capital | Survives ~50 consecutive maximum-size losses |
| Per-instrument position | ≤ 5% of capital | No single name dominates the book |
| Portfolio gross exposure | ≤ 100% (no leverage initially) | Leverage before edge is proven inverts the risk/reward of the paper phase |
| Portfolio net exposure | ≤ 50% | Forces some hedging discipline; loosen once the strategy justifies it |
| **Max concurrent positions** | **10** | **Derived, not chosen** — 5 s worst-case flatten at 2 exits/s (G-39) |
| Daily loss kill-switch | −3% of capital | Roughly 1.5 maximum-size losing positions; stops a bad day becoming a bad week |
| Default stop distance | 2 × ATR(14) | Volatility-scaled rather than fixed % — a 2% stop means different things on different names |
| Max holding time (intraday) | Until `square_off_at` | MIS is force-closed anyway (doc 07 §4.4) |
| Feed-loss grace window | 30 s | Long enough to survive a reconnect; short enough to matter |
| `on_data_loss` default | `FLATTEN` for MIS/leveraged, `HOLD` for CNC | Leveraged risk without prices is the unacceptable state |
| Margin safety factor | 0.7 (use ≤ 70% of available) | Buffer against intraday margin revision, which happens |

**Two of these are load-bearing in a way the others aren't:**

- **Max concurrent positions is derived from exit throughput** (G-39), not chosen for comfort. Changing it means accepting a longer worst-case flatten time — state which you're trading.
- **The daily loss limit and per-order cap must be consistent.** At 2% per order and −3% daily, roughly 1.5 maximum-size losers trip the switch. If that feels too tight, the per-order cap is what should move, not the kill-switch — the kill-switch is the backstop and should not be the flexible number.

⚠️ **Sizing method is still genuinely open** and is the one item here I'd resist defaulting: fixed-fractional, volatility-parity, and Kelly-derived sizing produce very different books from the same signals, and the right answer depends on the strategy (G-01). Left blank deliberately.

<a id="g-19"></a>

### G-19 🟠 — Indian cost model accuracy
**Status:** **IN DESIGN** · **Resolve by:** Phase 3

*2026-07-22 progress:* doc 07 §5.1 enumerates the components — brokerage, STT/CTT (asymmetric by side and segment), exchange transaction charges, SEBI turnover fees, stamp duty, GST, DP charges, **and the ₹50 + GST auto-square-off charge** that was previously missing entirely.

*Still open:* sourcing current rates and putting them in a **dated, versioned config** so historical backtests can run under the cost regime that applied at the time.

<a id="g-20"></a>

### G-20 🟡 — LIMIT-only constraint effects
**Status:** **IN DESIGN — effects enumerated** *(2026-07-22)* · **Resolve by:** Phase 3

Sandbox and simulator support LIMIT only. `market_protection` is now carried from day one (doc 07 §2), so the *payload* is live-ready even though the paper *backend* is LIMIT-only.

**What LIMIT-only actually rules out in the paper phase:**

| Strategy shape | Paper-testable? | Why |
|---|---|---|
| Limit entries, limit exits | ✅ Fully | The design's native case |
| Marketable-limit (cross the spread) | ✅ Mostly | Expressible; exercises the impact model (doc 07 §4.1) |
| **Stop-loss exits** | ⚠️ **Partially** | The Position Manager emits a *limit* order on stop trigger. In a fast gap-down the limit may not fill — real SL-M would. **Paper stops are optimistic in exactly the scenario stops exist for** |
| Momentum / breakout chasing | ⚠️ Degraded | Depends on immediate marketable fills; limit orders miss |
| Gap-open trading | ❌ Not faithfully | Requires market orders into the open |
| Liquidation under stress | ❌ Not faithfully | Fastest-possible exit is a market order by definition |

**The one that matters is the stop-loss row**, and it interacts with G-28: the exit path is the safety spine, and in the paper phase its worst-case behaviour is *better* than reality. A paper session showing clean stop fills does not prove live stops will fill at those prices.

*Direction:* have the simulator model a **pessimistic stop fill** — on stop trigger, fill at a configurable adverse offset from the trigger, or not at all if the gap exceeds a threshold, rather than assuming the limit fills at the stop price. That approximates SL-M behaviour conservatively without needing market orders. Record which strategies remain untestable and defer them explicitly rather than testing them misleadingly.

<a id="g-28"></a>

### G-28 🔴 — No exit/stop management path *(new)*
**Status:** **IN DESIGN** *(2026-07-22)* · **Resolve by:** Phase 3

**The design had no exit path.** Every document described entries — screeners flag, specialists assess, manager emits intent, gateway fills — and nothing described who watches an open position or emits the exit. `OrderIntent.risk_context` mentioned a stop as metadata that no component consumed.

*Why it matters:* if the LLM manager must emit exits, then **LLM latency and availability sit in the loss path**. It also made doc 05 §6's "if the manager lags, its safe default is to do nothing" false — doing nothing while holding a losing position is unbounded, not safe.

*Direction (adopted):* a deterministic Rust **Position Manager** (doc 07 §4) owning stops, targets, time-exits, square-off, and feed-loss policy, running with no LLM in the path. Every ENTRY carries a mandatory `exit_plan`. The manager may tighten a stop but is never required for an exit. Risk checks may block entries but never exits. Doc 03 §2.1 records the reasoning.

*Still open:* default stop/target/holding parameters (folded into G-18), and the live-mode complication that exit acknowledgement becomes asynchronous and failable (doc 07 §6).

<a id="g-39"></a>

### G-39 🟠 — Exit throughput bounds the book *(new)*
**Status:** **IN DESIGN** *(2026-07-22)* · **Resolve by:** Phase 3

Reserved exit capacity (doc 07 §3.3) protects exits from being starved by entries, but it is a **rate**, and in a market-wide selloff **every stop fires simultaneously**. At 2 exits/second, 50 open positions take ~25 seconds to flatten — during precisely the move that triggered all 50 stops. The last position out pays for the queue.

*Why it matters:* it means the maximum open-position count is **derived, not chosen**. $N_{\max} \le r_{\text{exit}} \cdot t_{\text{flatten,target}}$. A 5-second worst-case flatten at 2/s permits 10 concurrent positions — which silently caps strategy breadth. This is a hard constraint on what strategies are even expressible, and discovering it during a selloff rather than at design time is the bad outcome.

*Direction (adopted):* pick the tolerable worst-case flatten time first and let it set the position cap (doc 07 §3.3.1). Under kill-switch or deep exit queue, exits escalate to claim the **entire** 10/s budget — entries are halted in that state anyway. Reserved capacity is the steady-state floor, not the ceiling.

*Still open:* $t_{\text{flatten,target}}$ is an owner decision (folded into G-18). Also unquantified: partial fills mean exits may need modification or reissue, so real order consumption exceeds one per position.

✅ **2026-07-22 — the input is confirmed.** NSE §F lets brokers set a lower per-client limit; **Zerodha applies the full 10 OPS** for retail algo trading (owner-confirmed, corroborated by the Kite FAQ and NSE §B.2). The derivation stands as written: 10/s total, 2/s reserved for exits, ~10 concurrent positions for a 5-second worst-case flatten.

⚠️ Still config, not a constant — NSE may adjust TOPS "after due notice," and the limiter must read it from config so a tightening does not silently breach (doc 02 §9.5).

*Interacts with G-13:* a wide universe implies many candidates, but the book cannot grow past what the exit path can drain. Breadth of *watching* and breadth of *holding* are separate budgets, and only the first is set by the 9,000 figure.

<a id="g-29"></a>

### G-29 🔴 — No margin model *(new)*
**Status:** **IN DESIGN** *(2026-07-22)* · **Resolve by:** Phase 3

Risk checks were notional- and percentage-based only. **F&O paper trading without SPAN + exposure margin opens positions the real account could never fund**, making both the P&L and the strategy's apparent capacity fiction — and breaking the "flipping to live is a configuration change" promise on day one, with rejections rather than bad fills.

*Compounding:* the sandbox does not support margin APIs (doc 02 §7), so this can only be validated against production.

*Direction (adopted):* doc 07 §3.1 — prefer Kite's margin APIs, fall back to a daily per-instrument margin table with no portfolio offset (which over-estimates, the safe direction), and failing both, a hard conservative gross cap with the limitation recorded in the ledger. Margin breach trips the kill-switch. **Never model margin more favourably than reality.**

*2026-07-22, second pass — a trap worth naming.* A SPAN formula was briefly added in a form that read as an implementation spec. **NSE SPAN cannot be computed locally**: scan ranges and volatility shifts come from the exchange's daily risk parameter file per underlying, and a scenario-grid formula omits short-option minimum charge, calendar-spread charges, inter-month credits, and delivery margins. Building it yields a confidently wrong number that fails in the one direction this gap forbids. It is now explicitly relabelled *reference for interpreting the API's answer*, with option 1 kept visually on top. **If you must approximate, use published per-lot tables — never a home-grown scenario engine.**

*Still open:* which approach, the safety factor, and how to keep the local table current.

<a id="g-30"></a>

### G-30 🟠 — MIS auto square-off unmodelled *(new)*
**Status:** **IN DESIGN** *(2026-07-22)* · **Resolve by:** Phase 3

Zerodha force-closes intraday positions at **3:25 PM (equity) / 3:26 PM (F&O)** and charges **₹50 + 18% GST per squared-off order**. Neither the forced exit nor the charge was modelled, so every MIS strategy's paper results were optimistic by an amount scaling with trade count — an easy way to manufacture a fake edge.

*Direction (adopted):* doc 07 §4.4 — the Position Manager sets `square_off_at` on every MIS entry with a configurable margin before the broker's cut-off, so we close our own positions; anything the broker would have closed is charged in the ledger.

*⚠️ Timings live in config, not code.* They changed in December 2025 (from 3:20/3:25) and will change again.

---

## E. Cognition & agents

<a id="g-10"></a>

### G-10 🟠 — LangGraph vs. custom orchestrator
**Status:** OPEN · **Resolve by:** Phase 5

Confirm LangGraph meets the live-path latency budget, or use a lighter custom orchestrator for live while keeping LangGraph for static study.

*2026-07-22 note:* materially less risky now. With exits deterministic (G-28), orchestrator latency only delays *entries* — a missed opportunity, not an unmanaged position. This could arguably drop to 🟡; kept at 🟠 pending measurement.

<a id="g-11"></a>

### G-11 🟠 — LLM token-spend estimate
**Status:** **IN DESIGN — first quantified pass complete** *(2026-07-22)* · **Resolve by:** measure in Phase 5

Continuous screeners dominate cost. Without an estimate we can't size the live fleet responsibly.

**Modelled against verified pricing** (Haiku $1/$5, Sonnet $3/$15, Fable $10/$50 per 1M tokens) — full derivation in doc 08 §8:

| Configuration | Per year |
|---|---|
| Naive screeners (LLM reads the raw universe) | ~$76,000 total |
| **Target design** (deterministic pre-filter) | **≈ $28,000** |
| Lean viable (6 screeners @ 60 s, Sonnet manager) | ≈ $8–10,000 |

**Four findings, in order of consequence:**

1. **LLM spend is ~400× the broker subscription** (₹2 lakh/month vs ₹500/month). Cost control in this project means token control; nothing else in doc 10 §5 matters.
2. **The dominant lever is architectural, not commercial.** Sending screeners the raw universe vs. a deterministically pre-filtered candidate set is a **5× swing on the largest line** — same models, same agent count, same cadence. This is now an architectural rule (doc 08 §8.2): *screeners never receive the raw universe; deterministic Rust computes the numeric screen and the LLM only adjudicates what already tripped a threshold.* An LLM paid frontier rates to notice a number crossed a level is the single most expensive mistake available here.
3. **The singleton risk manager is 36% of the bill.** Fable's always-on thinking bills as **output at $50/1M**, so one agent outcosts 400 Sonnet specialist calls. **Singleton ≠ cheap** — and if D-12's aggregation formula makes the manager largely arithmetic, the Fable tier is very hard to justify. **Revisit D-10 and D-12 together against this number.**
4. **Prompt caching helps the manager, not the screeners.** The manager's prefix (book, regime, limits) is stable and cacheable (~26% saving); screener input is live market state and structurally uncacheable. Don't expect caching to rescue the largest line.

**Answers the meta-question** in §G.3 — *are ~15–25 live agents affordable?* **Yes, but only with the pre-filter.** Without it the same roster is ~$76,000/year.

*Still open:* every token count is an **assumption**, not a measurement. Phase 5 must run one session with per-tier token accounting and reconcile against the model (doc 08 §8.4). If reality is within 2×, plan on it; if not, re-derive before scaling. Tokens per screener call is the single largest driver — measure it with `count_tokens` against a real payload first.

<a id="g-21"></a>

### G-21 🟠 — Conflicting-signal resolution
**Status:** OPEN · **Resolve by:** Phase 5

"The manager arbitrates" — but the actual policy (weighing a bullish technical against a bearish macro against neutral news) is undefined, and a lot of decision quality lives there.

*2026-07-22 note — an aggregation model now exists, and it does not close this gap.* Doc 08 §3.1 proposes correlation-discounted Bayesian LLR aggregation with corroboration and veto gates. That answers *how to combine scores*; G-21 asks *what should happen when specialists genuinely disagree*, which is a different question. Still open:
- Which specialists hold veto authority, at what strength, over what horizon?
- How are disagreements **between market-plane** specialists resolved (technical bullish vs. options-OI bearish)?
- Does $\theta_{\text{threshold}}$ vary by regime, liquidity, or time of day?

*Two cautions recorded during that review:*
1. **The naive LLR sum assumed specialist independence, which is false** — they read overlapping data about the same instrument. Summing correlated evidence overstates confidence *most when all specialists agree*, i.e. exactly when the model would size up hardest. Corrected in §3.1.1 with an effective-sample-size discount; the correlation matrix is still unmeasured, so $\bar{\rho}_{\text{corr}} = 0.7$ is assumed pessimistically.
2. **A pure sum violated the instruction-source boundary** (doc 08 §6): a strong enough news score alone could cross $\theta$ and initiate a trade on text. No threshold value fixes that — it is now a hard gate requiring market-plane confirmation for entries.

*Also see doc 13, D-12* — adopting a formula moves the manager from judge to calculator, which is an architectural change with cost implications, recorded there rather than left implicit here.

<a id="g-22"></a>

### G-22 🟠 — Entity resolution accuracy
**Status:** **IN DESIGN** · **Severity upgraded 🟡 → 🟠** *(2026-07-22)* · **Resolve by:** Phase 4.5

Mapping headlines to the correct instrument (name changes, ambiguous names, subsidiaries, ADRs) is error-prone; a wrong mapping can trigger the wrong trade.

*Why upgraded:* an interim design proposed pure string similarity (Jaro-Winkler + Levenshtein) with auto-binding above 0.85. Review found this **fails hardest exactly where the damage is worst.** Indian corporate groups share name prefixes across many separately-listed entities — Bajaj Finance / Bajaj Finserv / Bajaj Auto, HDFC Bank / HDFC Ltd, Tata Motors / Tata Motors DVR, Motherson / Motherson Sumi Wiring. All score far above 0.85 against each other and would have auto-bound to the wrong instrument, with the pipeline reporting high confidence while doing it.

**The general principle, worth remembering beyond this gap:** in this market, orthographic similarity is close to *anti*-correlated with referential identity. The more alike two tradingsymbols look, the more likely they are to be different companies.

*Direction (adopted):* doc 08 §4 now specifies a **cascade** —
- **Tier 0:** NSE/BSE announcement feeds already carry the scrip symbol. Dictionary lookup, confidence 1.0, no matching at all. This covers most of our volume, and running fuzzy matching over it was introducing error for free.
- **Tier 1:** curated alias dictionary (exact/normalized match only).
- **Tier 2:** context disambiguation on sector, ISIN, exchange, named executives.
- **Tier 3:** string similarity — **quarantine only, never auto-binds.**

*Still open:* thresholds are asserted rather than fitted; needs a labelled test set containing deliberate sibling-entity traps, with precision tracked per tier.

*Mitigating factor:* the corroboration gate (doc 08 §3.1.2) means a resolution error causes a wrong or missed *flag*, not by itself a wrong *position* — a trade still requires market-plane confirmation.

<a id="g-23"></a>

### G-23 🟡 — Look-ahead bias
**Status:** **IN DESIGN** · **Resolve by:** Phase 2

*2026-07-22 progress:* the replay harness (doc 07 §4.3) **enforces as-of discipline structurally** — the replay clock gates data access, so an agent physically cannot read a future tick. That is far stronger than a code-review convention.

*Still open:* applying the same discipline to the DuckDB research store, where a careless query can still reach across the timestamp boundary.

---

## F. Cross-cutting / ops

<a id="g-07"></a>

### G-07 🟠 — Distributed rate limiting
**Status:** **ACCEPTED** — moot while single-host · **Revisit:** if we ever split

Token buckets are single-process. If services split across hosts, per-key limits need a shared limiter or we risk 429s and bans.

*2026-07-22 note:* the static-IP requirement (doc 02 §9) means the **order path cannot move off the whitelisted host anyway**, so the highest-stakes bucket is pinned by regulation. Only the quote and historical buckets could ever be distributed.

<a id="g-24"></a>

### G-24 🟠 — Prompt-injection defence validation
**Status:** OPEN · **Resolve by:** Phase 6

The instruction-source boundary (doc 08 §6) is stated as policy; it needs **testing with adversarial inputs** before live. A policy that has never been attacked is an assumption. Doc 10 §8 now names this as a required Phase 6 activity.

<a id="g-25"></a>

### G-25 🟡 — Time synchronization
**Status:** **IN DESIGN** *(2026-07-22)* · **Resolve by:** Phase 1

NTP discipline, exchange-vs-receive timestamp handling, and skew alerting need to be concrete.

**Why it's load-bearing:** the staleness check (doc 06 §1.6) computes `recv_ts − exchange_ts` against a threshold. A clock 2 seconds fast makes every tick look stale (nothing is fill-eligible — the system silently stops trading); 2 seconds slow makes stale ticks look fresh (fills against dead prices). **Both failure modes are silent**, and the second one corrupts the ledger.

*Direction (adopted):*

- **NTP on the host, monitored** — chrony or systemd-timesyncd with **offset exported as a metric**, not merely configured. An unmonitored NTP daemon that has silently stopped syncing is the actual failure mode.
- **Alert on offset, not on daemon liveness.** Threshold well below the staleness bound (e.g. alert at 200 ms when staleness is 1,500 ms) so drift is caught long before it distorts behaviour.
- **Record both timestamps on every tick** (already in the `Tick` model) and export the `recv_ts − exchange_ts` distribution — a shifting distribution reveals clock drift and feed-latency changes alike.
- **Fail safe on skew.** If measured offset exceeds the staleness threshold, treat it as a **data-plane outage** (doc 07 §3.2), not a warning: the staleness check can no longer be trusted in either direction, so neither can fill eligibility.
- **Use monotonic time for intervals** (dwell timers, cooldowns, `max_holding`) and wall-clock only for market-relative decisions. An NTP step correction must never make a holding period appear to jump.

⚠️ *Open:* whether Kite's `exchange_ts` is exchange-stamped or gateway-stamped materially changes what the difference means — verify in Phase 1.

<a id="g-26"></a>

### G-26 🟡 — Crash/state recovery completeness
**Status:** OPEN · **Resolve by:** Phase 6

*2026-07-22 note:* doc 10 §3.1 now tabulates per-component recovery state and flags the dangerous case — **a restart that loses exit plans leaves positions open with nothing watching them.** Reloading exit plans before the first tick is a hard startup ordering requirement.

<a id="g-27"></a>

### G-27 🟡 — Disaster/failover for a single host
**Status:** **ACCEPTED** for paper · **Revisit:** before live

A single Docker-Compose host is a single point of failure. Acceptable while no real money is at risk; needs a plan before live — noting that the static-IP binding constrains what failover can even look like.

<a id="g-31"></a>

### G-31 🟠 — Redis streams were unbounded *(new)*
**Status:** **IN DESIGN** *(2026-07-22)* · **Resolve by:** Phase 0

Redis is in-memory, and the design appended every tick-derived event to Redis Streams with **no trim policy, no consumer-group specification, no dead-letter path, and no schema versioning** — on the boundary doc 03 explicitly calls "the contract." At 9,000-instrument volume this exhausts RAM within a session.

*Direction (adopted):* doc 06 §2.1 — per-stream `MAXLEN` caps, consumer groups with acks and `XAUTOCLAIM`, a DLQ, versioned schemas generated for both planes from one source, and the rule that **no stream is the system of record**. Backpressure throttles producers rather than letting trimming silently hide lag.

*2026-07-22 — caps now sized.* From the §6 arithmetic (~9,000 events/s, ~200 B/event), a 500k-entry `kestrel:ticks` cap is **~100 MB and ~1 minute of history** — enough to survive a GC pause or brief consumer restart, not enough to mask a real outage. Total stream memory should sit well under half of host RAM; the last-value cache is negligible beside it (~9 MB).

*Still open:* confirm the measured event rate in Phase 1 and set the caps explicitly from it. **The failure mode to avoid is discovering the right cap during a session** — by then Redis has OOMed and taken the contract boundary with it.

<a id="g-32"></a>

### G-32 🟠 — Replay harness was nobody's deliverable *(new)*
**Status:** **CLOSED** *(2026-07-22)*

G-09 said "validate by replay" and G-23 said "enforce as-of discipline" — both depending on a deterministic replay harness that appeared in **no phase's deliverables**.

*Resolution:* specified in doc 07 §4.3 and added as a **Phase 1 deliverable**, alongside the ingester that produces its input. It is the most reused test asset in the project: fill-fidelity validation, look-ahead-safe **deterministic-plane** backtests, risk-engine regression tests, and incident reproduction all run on it. ⚠️ *2026-07-22:* its determinism guarantee holds for the hot plane only — LLM replay needs cached responses and is forensics, not validation (G-42).

<a id="g-35"></a>

### G-35 🟡 — Ownership and dates are unassigned *(new)*
**Status:** OPEN · **Resolve by:** ongoing

Every gap has a severity and a phase, and **none has a named owner or a target date**. For a register intended to drive work rather than describe it, that is the difference between a plan and a list. Add an Owner column once there is more than one person, and a date on anything 🔴.

<a id="g-36"></a>

### G-36 🔴 — Passive Limit Fill Queue Mechanics & L2/L3 Depth Limitation *(new)*
**Status:** **IN DESIGN** *(2026-07-22)* · **Resolve by:** Phase 3

Kite Connect provides 5-level market depth (Level 2), not full order book queue depth (Level 3). Simulating passive limit order fills requires assuming queue position $q_0 = D_0(P_{\text{limit}})$. Without Level 3 order queue tracking, queue priority cancellation/replacement dynamics cannot be directly observed.

*Why it matters:* Over-estimating passive fill rates manufactures unrealizable paper edge for market-making or mean-reverting strategies that rely on limit orders.

*Direction:* Enforce pessimistic queue position assumptions (last in queue) and require price trade-through $P_{\text{trade}} < P_{\text{limit}}$ for complete fill validation until tick replay calibration.

<a id="g-37"></a>

### G-37 🟠 — Non-Stationary Agent Weights across Market Regimes *(new)*
**Status:** OPEN · **Resolve by:** Phase 5

Specialist precision weights $w_k$ in the Bayesian likelihood aggregation formula (doc 08 §3) assume stationary predictive power. In reality, technical analysis specialists perform poorly in high-volatility regime shifts, while macro/options-OI specialists dominate.

*Why it matters:* Static weighting causes the portfolio manager to trust outdated specialist signals during regime transitions.

*Direction:* Implement dynamic regime-dependent weighting vectors $w_k(R_t)$ conditioned on macro regime $R_t \in \{\text{LowVol-Trend}, \text{HighVol-Reversal}, \text{Binary-Event}\}$.

*⚠️ 2026-07-22 note — this collides with the cold-start problem, and the collision is multiplicative.* Doc 08 §3.2 already stages $w_k$ introduction because the weights need ~1,000 scored calls per specialist before they mean anything. **Conditioning on regime multiplies that requirement by the number of regimes** — and worse, regimes are unevenly sampled: `Binary-Event` occurs a handful of times a year, so its weights would be fitted on almost no data precisely where the stakes are highest.

This is the classic trap in regime-conditional models: they look most valuable exactly where they are least estimable.

*Refined direction:*
- **Do not fit per-regime weights from paper history.** There will never be enough of it in the regimes that matter.
- Prefer **shrinkage toward the global weight**: $w_k(R_t) = \beta_{R_t} w_k^{\text{global}} + (1 - \beta_{R_t}) w_k^{R_t}$, with $\beta$ near 1 for rarely-observed regimes. Sparse data pulls toward the pooled estimate rather than producing confident nonsense.
- For `Binary-Event` specifically, **prefer the deterministic route already available**: event-window de-risk (doc 08 §5) reduces exposure into known events without needing any regime-conditional weight at all. A rule that sidesteps the estimation problem beats a weight fitted on six observations.
- Also note $\Sigma$ (specialist correlation, §3.1.1) is **itself regime-dependent** — correlations rise in stress, which is when the independence assumption is already most wrong. Regime-conditioning $\Sigma$ likely matters more than regime-conditioning $w_k$, and has the same data problem.

<a id="g-38"></a>

<a id="g-44"></a>

### G-44 🔴 — The agent fleet may not pay for itself at single-user scale *(new)*
**Status:** OPEN · **Resolve by:** before Phase 4 — this decides whether the cognition plane gets built at all

**Single-user is now a fixed constraint** (doc 13, D-13). LLM cost is **fixed**; trading profit **scales with capital**. Those two facts intersect at a capital threshold below which the agent fleet cannot pay for itself — and the threshold is high.

From doc 08 §8's model (≈$28,000/yr full fleet, ≈$9,000/yr lean), at a **20% annual gross return**:

| Capital | LLM cost as % of gross profit | Verdict |
|---|---|---|
| ₹0.4 cr | 280% | Absurd |
| ₹0.9 cr | **140%** | **Costs more than it earns** |
| ₹2.2 cr | 56% | Dominates the P&L |
| ₹4.4 cr | 28% | Heavy but arguable |
| ₹8.8 cr | 14% | Reasonable |

**Break-even — LLM cost equals *all* gross profit:**

| Configuration | $/yr | Break-even capital | Capital for cost < 20% of profit |
|---|---|---|---|
| Full fleet | 28,000 | **₹1.23 cr** | **₹6.2 cr** |
| Lean (6 screeners @60 s, Sonnet manager) | 9,000 | ₹0.40 cr | ₹2.0 cr |
| **Deterministic plane only** | **0** | **any** | **any** |

*(20% gross return assumed; scale inversely — at 15% every threshold rises by a third.)*

**Why this is 🔴 rather than a budgeting note:** building the agent fleet and *then* discovering it costs more than it returns means throwing the fleet away. The arithmetic is available now, before a line of cognition-plane code exists. That is exactly the shape 🔴 is for.

**What it does *not* say:** it is not "the agents are worthless." It says agent value must exceed a **fixed ~₹24 lakh/year hurdle**, and that hurdle does not shrink with account size. The agents must beat the deterministic spine by more than that margin — an unusually demanding bar, and one nobody has had to state before because the cost was unquantified (G-11 was OPEN until this pass).

**The fourth convergent argument.** G-11 (5× cost lever), G-41 (white-box describability), G-42 (only validatable plane), and now G-44 (the only affordable plane at retail scale) all point the same way: **the deterministic plane should do as much as possible.** Four unrelated pressures — cost efficiency, regulation, epistemics, and unit economics — with one conclusion is about as strong as a design argument gets.

*Direction (owner decision, and it is a real fork):*

| Path | When it fits |
|---|---|
| **Deterministic spine only** — no LLM fleet | Capital below ~₹1 cr, or before an edge is proven. Costs ~₹6k/yr all-in (broker + host). **This is the default the arithmetic recommends.** |
| **Lean fleet** — 6 screeners @60 s, Sonnet manager, aggressive caching | ₹2 cr+, once the spine is profitable and the agents can be shown to add value |
| **Full fleet** | ₹6 cr+, or if the agents demonstrably contribute far more than their cost |

**Sequencing that falls out of this:** build the deterministic spine, prove it, measure its return — *then* add agents incrementally and require each tier to earn its cost. Which is D-09's thin vertical slice, reached by a completely independent route.

⚠️ *The return assumption is doing real work here and there is no strategy yet (G-01).* But the **structure** holds regardless: fixed cost against capital-scaled profit always produces a threshold. Only its position moves.

<a id="g-42"></a>

### G-42 🔴 — LLM strategies cannot be validated by historical backtest *(new)*
**Status:** OPEN · **Resolve by:** before Phase 4, and it reshapes what Phase 5 is *for*

Backtesting appears **13 times across the docs** as something the replay harness enables — and is **specified nowhere**. `walk-forward`, `out-of-sample`, and `in-sample` return **zero hits in the entire repo**. That alone would be a 🟠 documentation gap. It is 🔴 because of what happens when you try to write the spec: **three of the standard backtesting assumptions do not hold for an LLM-driven system**, and one of them cannot be fixed.

#### 1. ⚠️ The model has already seen the period you are testing — and this is unfixable

Claude's training data includes market history. Backtest a screener on NIFTY in 2023 and the model may not be *reasoning* from the data in the prompt — it may be **recalling what happened**. Ask it to assess a stock on a given date and it can know how that quarter ended.

**No pipeline discipline fixes this.** G-23's replay clock gates what the *data layer* exposes; the leak is inside the model weights. As-of-timestamp enforcement is exactly as strong as claimed and completely irrelevant here.

Partial mitigations, all with real costs:

| Mitigation | Cost |
|---|---|
| Anonymise instruments (strip symbols, use opaque IDs) | Destroys the sector, news, and macro reasoning that justifies using an LLM at all |
| Test only on data **after the model's training cutoff** | A small, ever-shrinking window — and you cannot iterate, because each attempt burns some of it |
| Restrict the LLM to derived features, never raw identifiable history | Narrows the LLM's role toward something a deterministic model could do |

**None recovers a conventional backtest.** They trade away the thing the LLM was for.

#### 2. Cost makes iteration impossible

From the doc 08 §8 model: **≈$112 per live session.** A one-year backtest replaying the full funnel is 250 sessions ≈ **$28,000 per run**. Strategy development means dozens of runs. **That is a $500k+ iteration loop**, which is not a budget problem — it is a "this workflow does not exist" problem.

#### 3. Non-determinism breaks reproducibility

Same prompt, different completion. Two runs of the same "backtest" give different results, so you cannot tell a strategy change from sampling noise. Response caching (doc 07 §4.3.1) restores reproducibility but **only for the exact prompts already recorded** — the moment you change a prompt, which is the whole point of iterating, you are back to live cost and live non-determinism.

---

### The resolution: split validation along the plane boundary

The architecture already draws the right line — it just wasn't being used for this.

| Plane | Validation method | Why it works |
|---|---|---|
| **Hot plane** — pre-filter, exits, stops, risk engine, margin, cost model, square-off, sanity filter | ✅ **Conventional backtest.** Deterministic, free to re-run, byte-identical, walk-forward-able | It is ordinary code over historical data. All the standard rigour applies |
| **Cognition plane** — screener/specialist/manager judgement | ❌ **Not backtestable. Forward-test only** | Every problem above |

**This makes paper trading the *only* available validation path for the cognition plane** — not the prudent choice, the only one. It substantially strengthens D-01, and it means **"backtest, then paper trade" is not an available sequence** for the agent fleet. Phase 5 is not a rehearsal before the real test; **Phase 5 *is* the test.**

*Consequences to carry:*

- **Paper duration is a statistical requirement, not a comfort measure.** If forward testing is the only evidence, Phase 6's "N sessions of stable operation" needs an N derived from the strategy's trade frequency and the effect size you need to detect — not a round number. That belongs with G-14.
- **A third independent argument for pushing logic into the deterministic plane.** G-11 said the pre-filter is a 5× cost lever; G-41 said deterministic logic is white-box-describable if registration is ever needed; this says **it is the only part you can validate rigorously.** Three unrelated pressures, one conclusion: *the more the deterministic plane does, the better this project works.*
- **The paper P&L attribution problem gets sharper.** With the deterministic plane backtested and the LLM plane only forward-tested, you need per-decision attribution to tell whether a good paper result came from the agents or from the plumbing (stops, cost model, sizing). Doc 07's per-order agent-chain attribution was designed for debuggability; it is now the **only way to know whether the LLMs are adding anything.**

*Direction:* write the missing backtest spec, but scope it honestly to the deterministic plane — pre-registration, hold-out, walk-forward, multiple-comparison discipline, and a stated protocol for how many strategy variants get tried before the result stops meaning anything. For the LLM plane, define what forward-test evidence would be sufficient, in advance, before anyone is looking at a P&L curve they like.

⚠️ **The uncomfortable version:** if the LLM fleet cannot be validated historically and forward validation takes many months of paper trading, that is a real argument for proving the deterministic strategy spine first and adding agents only where they demonstrably beat it. That is a G-01 and D-09 question, and this gap is evidence for the thin vertical slice.

<a id="g-43"></a>

### G-43 🟠 — Point-in-time reference data is not being captured, and cannot be recovered later *(new)*
**Status:** OPEN · **Resolve by:** **Phase 0** — every day of delay is permanently lost data

`point-in-time` returns **zero hits** in the repo. The design fetches the instruments master daily (doc 06 §1.1) and **overwrites it**. The same is true of every other piece of reference data.

**Any backtest that uses today's reference data against yesterday's prices is silently using future information:**

| Reference data | Changes | Leak if not snapshotted |
|---|---|---|
| Instruments master | Daily | Survivorship bias — delisted names vanish; today's list is the list that *survived* |
| F&O ban list | Daily | A backtest trades instruments that were actually banned that day |
| Circuit limits | Daily | The tick sanity filter (doc 06 §1.6) validates history against today's bands |
| Margin rates | Daily | G-29's margin model prices old positions at today's requirements |
| `instrument_token` ↔ symbol mapping | On expiry/rollover | Tokens are reused (doc 02 §4); the mapping must be as-of, not current |

**Survivorship bias is the one that will actually bite.** A universe built from today's instruments master contains only companies that still exist. Backtest on it and every strategy looks better than it was — the failures were removed from the sample before you started.

*Why this is Phase 0 and not Phase 2:* the data is **free to capture now and impossible to reconstruct later.** A daily snapshot of the instruments master, ban list, and circuit limits is a few MB — trivial against the ~5 GB/day of ticks (doc 06 §6). But there is no archive to backfill from. **Every day the ingester runs without snapshotting is a day of research data destroyed.**

*Direction:* the Instruments Loader writes a **dated, immutable snapshot** rather than overwriting, and the research store resolves reference data **as-of the simulation date**, never as-of now. Cheap to do in Phase 0; unrecoverable if skipped.

*Interacts with G-08:* corporate-action adjustment already re-bases price history mid-life. Combined with un-snapshotted reference data, a backtest can be wrong about *both* the prices and the universe — and neither error announces itself.

<a id="g-40"></a>

### G-40 🟠 — The exchange holds a kill switch on our Algo ID *(new)*
**Status:** OPEN · **Resolve by:** before live; runbook in Phase 6

SEBI Feb 2025 §IV(a)(iii) requires exchanges to *"continue to have the ability to use the kill switch for orders emanating from a particular algo id."*

**Our kill switch is not the only one.** A third party can halt our orders, at a time we don't choose, for reasons we may not immediately know.

*Why it matters, and it is worse than it first sounds:* doc 07 §4 guarantees the Position Manager will always be able to exit a position. That guarantee **assumes the order path is available**. An externally-triggered kill switch violates the assumption directly — and unlike a feed outage (where doc 07 §3.2 has a defined `on_data_loss` policy), there is **no code-side remedy**. We would hold open positions with prices visible, stops evaluating correctly, and no way to act on them.

*Direction:*
- **Detect it as a distinct state.** Mass order rejection with no local cause is diagnosably different from a network fault, a token expiry, or a margin block. It needs its own detector and its own alert — misdiagnosing it as a network problem would waste the minutes that matter.
- **Operator runbook, not code** (doc 10 §7): who to call at the broker, what to check, and what to do with open positions meanwhile — including manual exit through the Kite web terminal, which does **not** depend on our API path.
- **Feeds the risk envelope** (G-18): if positions can become temporarily unexitable through no fault of ours, that is an argument for smaller concurrent exposure than exit-throughput math alone suggests (G-39).

**✅ Researched 2026-07-22 — what the public record establishes.**

SEBI's own footnote defines it: *"The kill switch is an emergency function and the last level of defence against any Algorithm malfunction. It is expected to **automatically trigger** a halt on trading activity based on **pre-defined conditions**."*

**There are three kill switches, not one** — and only the first is ours:

| # | Held by | Basis | Can we see it coming? |
|---|---|---|---|
| 1 | **Us** — doc 07 §3 | Our own daily-loss, reconciliation, data-outage triggers | Yes, we define them |
| 2 | **The broker** — NSE mandates brokers have one | Broker's own RMS: price/volume sanity, exposure, per-client OPS | Partially — some surfaces as order rejection |
| 3 | **The exchange** — SEBI §IV(a)(iii) | Per algo ID; conditions not public | **No** |

Also established: brokers run **pre-order** price and volume control checks, so orders with implausible price or size may never reach the book — a rejection path distinct from all three kill switches.

**⚠️ The pre-defined conditions are not published.** They live in exchange SOPs and broker RMS policy, neither of which is public. This is not a gap in the research — it is genuinely not disclosed, and it should be treated as permanently unknowable from outside.

*What follows from that:*
- **Design for the effect, not the trigger.** We cannot enumerate the conditions, so the system must detect and survive *"our orders are being rejected and it isn't us"* regardless of cause. That detector covers all three switches plus pre-order rejection, which is more robust than chasing a condition list we'd never complete.
- **The rejection reason is the diagnostic.** Broker rejection carries a reason code; that is the only signal distinguishing an exchange-level halt from a margin block or a bad payload. **Log every rejection reason verbatim and alert on any spike** — this is the cheapest possible insurance against a failure mode with no code-side remedy.
- **Manual exit is the fallback.** Kite's web terminal does not depend on our API path or our algo ID. The runbook (doc 10 §7) should assume that is the recovery route.

⚠️ *Still worth asking Zerodha:* whether there is any warning, notification, or typical resolution time. But plan as though there is none.

<a id="g-41"></a>

### G-41 🟠 — An LLM strategy is probably a "black box" algo *(new)*
**Status:** OPEN · **Resolve by:** only if exceeding 10 OPS is ever contemplated

SEBI Feb 2025 §V splits algos into **white box** (logic disclosed and replicable) and **black box** (*"where the user cannot see the internal workings and rationale of the Algo or an Algo where the logic is not known to the user and is not replicable"*). Black box algos require the provider to **register as a Research Analyst**, maintain a research report per algo, and — the operative clause — *"in case of any change in the logic governing the algo, register such algo as a fresh algo."*

*Why it matters:* an LLM's decision process is not replicable in the sense meant here, and **a prompt edit or model upgrade is arguably a change in governing logic**. Under that reading, registering an LLM strategy means re-registering on every prompt change — operationally impossible for a system built to iterate on prompts.

**The consequence is strategic:** the 10 OPS ceiling is not merely a rate limit to respect. For *this* design it is close to a **permanent boundary**, because the registration path on the far side is impractical for us specifically. Any future plan that assumes "we'll register if we outgrow the threshold" should be treated as unavailable until this is resolved.

*Mitigating:* the categorisation applies most cleanly to **algo providers** serving others, and we are not one (G-02). Below TOPS none of it binds.

⚠️ *This is an interpretation, not a ruling.* If exceeding 10 OPS is ever contemplated, this question goes to Zerodha and likely a compliance advisor **before any engineering** — not after.

*Design note:* it also mildly strengthens the case for keeping deterministic logic deterministic. The more of the strategy that lives in auditable Rust (doc 08 §8.2's pre-filter, doc 07's exit rules) rather than in model judgement, the more of the system is white-box-describable if the question is ever asked.

<a id="g-38"></a>

### G-38 🟠 — SPAN Grid Scenario Calculation Latency *(new)*
**Status:** OPEN · **Resolve by:** Phase 3

Evaluating 16 SPAN stress scenarios for complex multi-leg options baskets in real-time pre-trade risk checks may introduce microsecond-to-millisecond processing latency into the Execution Gateway.

*Why it matters:* Risk check latency directly inflates the tick-to-order lifecycle latency budget.

*Direction:* Pre-compute SPAN scenario vectors for standard option strikes in C/Rust SIMD data structures, updated asynchronously on every option chain tick.

*⚠️ 2026-07-22 note — the premise shifts, and the problem gets worse, not better.* G-29's resolution is that **NSE SPAN cannot be computed locally** (doc 07 §3.1): the scan ranges live in the exchange's daily risk parameter file, and a scenario grid omits short-option minimum, calendar-spread, and delivery-margin components. So a local SIMD scenario engine is fast **and wrong** — the worst combination for a pre-trade risk check.

Under the adopted approach the latency concern becomes a **different and harder one**: margin pricing via `order_margins` is a **network round-trip drawing on the 10 req/s budget, sitting in the pre-trade path of every entry.** That is worse than compute latency on all three axes — slower, rate-limited, and able to fail.

Reframed direction:
- **Cache aggressively.** Margin for a given instrument/lot/product changes slowly; price it once per instrument per session and on material moves, not per order.
- **Pre-price the candidate set.** The manager knows its watchlist ahead of the entry decision; margin the candidates in the background so the pre-trade check is a cache hit.
- **Fail closed on a miss.** If margin is unpriced when an entry arrives, reject the entry rather than guessing or blocking on the call. Missing an entry is free (doc 03 §2.1).
- **Exits never wait for margin.** Exits reduce margin by construction and must never sit behind a margin API call.

⚠️ This makes G-38 primarily a **caching and rate-budget** problem, not a compute problem. Retitle when the direction is confirmed.

---

## G. Meta / process questions for reviewers

1. **Sequencing sanity:** is building 9,000-instrument infrastructure *before* proving any strategy (G-01) right, or should a thin vertical slice come first? *(2026-07-22: the review that found G-28 and G-29 argues for the slice — both were invisible architecturally and would have surfaced from one real position. See doc 09.)*
2. **Complexity vs. payoff:** does the Rust hot plane earn its cost at the *paper* stage? *(Now recorded as a decision with rationale in doc 13, D-02, rather than left as a floating question.)*
3. **Agent-count realism:** are ~15–25 live agents affordable per G-11?
4. **Redundancy:** anywhere two agents/components do effectively the same job?
5. **Unhandled failure modes:** what breaks that we haven't listed?
6. **What else has an expiry date?** Three of the five factual errors found in the 2026-07-22 review were facts that were true when written and had since changed. See the README's *Facts with an expiry date* table — what belongs on it that isn't there?

---

## Change log

- **2026-07-22** — external review pass.
  - **Added:** G-28 (no exit path, 🔴), G-29 (no margin model, 🔴), G-30 (MIS square-off), G-31 (unbounded Redis streams), G-32 (replay harness), G-33 (bad-tick filter), G-34 (coverage framing), G-35 (no owners/dates).
  - **Closed:** G-05 (extra API keys not viable), G-16 (bandwidth a non-issue), G-32, G-34.
  - **Accepted:** G-07, G-12, G-27.
  - **Materially revised:** G-02 (framework now live — moved to Phase 0), G-17 (upgraded 🟡→🟠).
  - **Progressed to IN DESIGN:** G-04, G-09, G-19, G-23.
  - **Structural:** added the register-at-a-glance table, `Status` field, and the [REVIEWING.md](REVIEWING.md) entry template.
- **2026-07-22 (tenth pass)** — **single-user confirmed as a design constraint (D-13), and the unit economics that fall out of it.**
  - **G-44 🔴:** LLM cost is fixed while profit scales with capital, so there is a capital threshold below which the agent fleet cannot pay for itself. The full fleet **breaks even at ~₹1.23 cr** and needs **~₹6.2 cr** to be a sane cost line; the lean config breaks even at ₹0.4 cr. **Below ~₹1 cr the deterministic spine alone is the rational configuration.**
  - **The fourth convergent argument** for maximising the deterministic plane — joining G-11 (cost lever), G-41 (white-box describability) and G-42 (only validatable plane). Four unrelated pressures, one conclusion.
  - **D-13 recorded** with what single-user buys (no auth, multi-tenancy, user model, public API — do not build them "in case") and what it does not soften (every correctness and compliance requirement). Notably it makes **D-07 deterministic exits load-bearing rather than prudent**: one operator means no on-call backstop, so safe unattended operation is a hard requirement.
- **2026-07-22 (ninth pass)** — **both Phase 0 blockers answered by the owner.**
  - **Client-level OPS limit = 10.** Zerodha applies the regulatory ceiling rather than a lower per-client value. Corroborated by NSE `INVG/67858` §B.2/§F and the Kite FAQ. **G-39's book-size derivation stands** (10/s, 2/s reserved, ~10 concurrent positions).
  - **Local storage for backtesting: proceeding.** Data will not be shared, displayed, or redistributed. **G-15 → ACCEPTED, deliberately not CLOSED** — Zerodha has not ruled on the ambiguous ToS clause; we are choosing the more plausible reading. That is a carried risk, and the record says so. Revisit triggers documented.
  - **Phase 0 no longer has an external blocker.** The only remaining compliance item (how the generic Algo ID attaches) is discovered during wiring.
- **2026-07-22 (eighth pass)** — **backtesting audit.** Backtesting was referenced 13× as a replay-harness use case and specified nowhere; `walk-forward` / `out-of-sample` / `in-sample` returned **zero hits repo-wide**.
  - **G-42 🔴:** the LLM plane **cannot be validated by historical backtest** — the model has seen the test period (unfixable by pipeline discipline; the leak is in the weights), a year-long replay costs ~$28k per run, and responses are non-deterministic. **Resolution: split validation along the plane boundary** — backtest the deterministic plane conventionally, forward-test the cognition plane. This makes paper trading the *only* validation path for the agents and reframes Phase 5 as the test rather than a rehearsal.
  - **G-43 🟠:** point-in-time reference data is **not captured and cannot be recovered** — the instruments master is overwritten daily, giving every future backtest survivorship bias. Moved to **Phase 0**; a few MB/day now, impossible later.
  - **Corrected:** doc 07 §4.3 claimed the replay harness is deterministic. True for the hot plane, **false for anything touching an LLM**. Added §4.3.1 on response caching, and scoped it honestly — cached replay is a **forensics** tool, not a backtesting tool.
  - **Third convergent argument** for pushing logic into the deterministic plane: G-11 (5× cost lever), G-41 (white-box describable), and now G-42 (the only rigorously validatable part).
- **2026-07-22 (seventh pass)** — chased the remaining compliance unknowns to their sources.
  - **Kill switch (G-40):** the pre-defined conditions are **not published** and should be treated as permanently unknowable from outside. Established there are **three** kill switches — ours, the broker's, the exchange's — plus pre-order price/volume checks. Reframed the design response around *detecting the effect* (mass rejection with no local cause) rather than enumerating triggers, with rejection-reason logging as the diagnostic.
  - **Data licence (G-15):** Kite ToS reviewed. Display restriction is **narrower** than feared ("public at large"), but two new constraints found — **`ap-south-1` is a licence term** ("use within India"), and stored data must be **deleted on termination**, making the research corpus a leasehold. 🔴 **One clause is genuinely ambiguous and load-bearing**: whether "build databases" is prohibited outright or only for redistribution. Our entire tick store depends on it.
  - **New 🔴 Phase 0 question (NSE §F):** the broker may set a **client-level OPS limit below 10**, which is a direct input to G-39's book-size derivation. Do not assume 10.
  - **TOPS scope:** the NSE circular is **internally inconsistent** (§B.2 "per exchange" vs §F "per exchange/segment"). Recorded as ambiguous; budget per exchange.
- **2026-07-22 (sixth pass)** — **primary-source verification** against SEBI and NSE circulars, replacing commentary-sourced claims.
  - **Sources of record:** SEBI `CIR/2025/0000013` (4 Feb 2025), SEBI `CIR/2025/132` (30 Sep 2025), NSE `INVG/67858` (5 May 2025).
  - **Confirmed:** the family carve-out verbatim (*self, spouse, dependent children, dependent parents*); generic Algo ID below TOPS; full applicability 1 Apr 2026.
  - **Corrected:** TOPS is **per exchange**, not per segment; measured on the **calendar clock second** (a rolling-window limiter does not satisfy it); **two** static IPs permitted, changeable **once per week**; breaching TOPS means the **broker rejects** the excess orders.
  - **Added:** G-40 (exchange kill switch on our Algo ID — no code-side remedy), G-41 (LLM strategy likely black box → 10 OPS effectively permanent).
  - **Upgraded:** G-15 🟡→🟠 — redistribution is prohibited, which constrains a Grafana instance already in the design.
- **2026-07-22 (fifth pass)** — **algo-provider status resolved (owner-supplied).** Running an algorithm for yourself and **immediate family** on a single account does not trigger exchange empanelment — broader than the earlier single-account framing, and corroborated by Kite's family static-IP rules. **G-02 downgraded 🔴 → 🟠**; the regulatory blocker is gone and no remaining regulatory question threatens the architecture. Recorded in doc 02 §9.4.
- **2026-07-22 (fourth pass)** — **algo-tagging correction (owner-supplied).** The register stated that API orders below a rate threshold "are not tagged as algo." **Wrong.** Every API-placed order carries an algo tag; the 10 OPS line separates a *generic* Algo ID from *formal strategy registration*. Propagated through 9 files; `algo_id` changed from nullable-above-threshold to **mandatory on every order**. The wrong reading would have shipped every order untagged. Details in G-02 and doc 02 §9.3.
- **2026-07-22 (third pass)** — gap-resolution work: research, quantification, and design on the resolvable entries.
  - **G-11 quantified** (the headline): token spend modelled against verified pricing → **≈$28k/yr**, ~400× the broker subscription. Established that the **deterministic pre-filter is a 5× lever on the largest line** — now an architectural rule, not a tuning option — and that the **singleton Fable manager is 36% of the bill** because always-on thinking bills as output.
  - **G-19 sourced**: real Zerodha rates, dated, with four asymmetry traps called out (STT by side/segment, flat ₹20 option brokerage, per-scrip DP charges, "free" delivery isn't free).
  - **G-08 answered**: Kite adjusts **splits and bonuses only** — dividends, rights, and demergers are not. The subtle consequence is that adjustment lands mid-life, so **derived data cached across an ex-date is silently stale**.
  - **G-06, G-17, G-25, G-20 specified**: tier promotion policy with priority ordering and hysteresis (including the invariant that *an open position never loses depth*); session-phase calendar; fail-safe-on-skew time discipline; LIMIT-only effects enumerated (**paper stops are optimistic in exactly the scenario stops exist for**).
  - **G-31 sized**, **G-13 reframed** (widening the universe is cheap; loosening the filter is expensive), **G-18 given a starting envelope** to react to.
- **2026-07-22 (second pass)** — review of the quantitative specifications added after the first pass.
  - **Added:** G-39 (exit throughput bounds book size). *Numbered 39, not 36 — G-36/37/38 were added concurrently; IDs are never reused, so the later entry moved.*
  - **Cross-linked the concurrent additions:** G-38's premise shifts materially now that SPAN is not locally computable (it becomes a caching/rate-budget problem, not a compute one); G-37's regime-conditional weights collide multiplicatively with the §3.2 cold-start problem, worst in the rarest and highest-stakes regime.
  - **Upgraded:** G-22 🟡 → 🟠 (string-similarity auto-binding would mis-resolve sibling entities in Indian corporate groups — the highest-confidence matches were the most dangerous ones).
  - **Corrected before adoption:** the LLR aggregation assumed specialist independence (overconfident exactly when all specialists agree) and allowed news alone to initiate a trade in violation of doc 08 §6; the SPAN formula read as an implementation spec for something not locally computable; impact coefficients were developed-market defaults applied to Indian mid-caps and illiquid options.
  - **Extended:** G-33 with session-start warm-up and overnight-gap handling — the case the filter most needs to get right.
  - **Structural:** design math moved out of doc 02 (which stays purely verifiable facts) into doc 07 §3.3; new decision D-12 recorded for formula-based arbitration.
- 2026-07-21 — initial gap register (G-01 … G-27).
