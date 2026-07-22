# 07 — Execution Plane Spec (Rust)

**Last updated:** 2026-07-22

The execution plane is the **single writer** of orders and the guardian of risk. In the paper-first build it writes to a local fill simulator; the same interface later writes to Kite's order API for live trading.

It contains two components with deliberately different authority:

- the **Execution Gateway** — validates, risk-checks, routes, and books every order;
- the **Position Manager** — owns open positions and emits exits without asking anyone.

---

## 1. Design goals
- **Single-writer discipline:** exactly one component ever emits orders. No agent bypasses it.
- **Paper/live parity:** identical interface, identical rate budgets, identical risk limits in both modes. No "paper-only" shortcuts.
- **Realistic paper fills:** simulate against the *live* tick stream so paper P&L is meaningful.
- **Deterministic safety:** risk limits, exits, and kill-switches are code, not LLM judgement.
- **Exits never depend on the cognition plane.** If every Python process dies, open positions still close correctly.

---

## 2. Order interface (mode-agnostic)

```
OrderIntent {
  client_order_id,
  intent_kind,          // ENTRY | EXIT | REDUCE  — exits bypass entry-side risk blocks
  exchange, tradingsymbol,
  side,                 // BUY / SELL
  qty,
  order_type,           // LIMIT (paper) + MARKET / SL / SL-M (live)
  product,              // CNC / NRML / MIS / MTF
  limit_price,
  trigger_price,        // SL / SL-M
  market_protection,    // REQUIRED for MARKET & SL-M; 0 is rejected by Kite. -1 = auto
  variety,              // regular / iceberg / ...
  validity,             // DAY / IOC / TTL
  algo_id,              // REQUIRED on every order, never null. Generic ID below 10 OPS;
                        // strategy-specific if formally registered. See doc 02 §9.3
  exit_plan,            // see §2.1 — mandatory on every ENTRY
  risk_context,         // sizing basis, source agent chain, data snapshot ref
  schema_version
}

OrderAck {
  client_order_id,
  broker_order_id | sim_order_id,
  status,               // ACCEPTED / REJECTED / PARTIAL / COMPLETE / CANCELLED
  reason,               // required when REJECTED — machine-readable enum + text
  fills: [ {qty, price, ts, liquidity_flag} ],
  remaining_qty,
  charges,              // modelled cost breakdown for this fill (§5)
  ts,
  schema_version
}
```

**Notes on fields that are new or easy to get wrong:**

- **`market_protection` is mandatory** for MARKET and SL-M orders under the SEBI framework — Kite rejects `0` (doc 02 §6.1). It is carried from day one even though the paper phase is LIMIT-only, because adding it at live-migration time is precisely the "paper-only shortcut that doesn't survive live" this design forbids. The simulator honours it too, so the constraint is exercised early.
- **`intent_kind` exists so the risk engine can tell risk-increasing from risk-reducing orders.** Without it, a naive "block orders when over the exposure cap" check would block the very exits that bring us back under it.
- **`exit_plan` is mandatory on every ENTRY.** An entry without a defined exit is rejected. This is what makes the Position Manager possible.
- **`algo_id` is mandatory on every order and is never null.** ⚠️ *Corrected 2026-07-22 — the earlier "null below the threshold" reading was wrong.* Every order placed through an API carries an algo tag; the 10 OPS threshold decides whether that tag is a **generic** Algo ID (below) or a **strategy-specific registered** one (above), not whether tagging applies (doc 02 §9.3).
  - **The risk engine rejects any intent without it**, in both paper and live mode. Treating it as live-only would be exactly the paper-only shortcut §1 forbids — and the one that fails on the *first* live order rather than degrading quietly.
  - Until Zerodha confirms how the generic ID is issued, carry it as a **required config value** stamped by the Execution Gateway. If it turns out to be bound server-side to the API key, the field becomes redundant but harmless; if it must be passed per order, we already have it plumbed. **Wrong in the safe direction.**

### 2.1 The exit plan

```
ExitPlan {
  stop:            { kind: FIXED | TRAILING | ATR, value, ref_price },
  target:          { kind: FIXED | R_MULTIPLE, value } | null,
  max_holding:     duration | null,        // time-based exit
  square_off_at:   timestamp | null,       // auto-set for MIS (§4.4)
  on_data_loss:    FLATTEN | HOLD,         // what to do if the feed dies (§3.2)
  adjustable_by_manager: bool
}
```

The risk/portfolio manager sets this when it opens the position. It may later **tighten or trail** the stop, or take partial profit, by publishing an updated plan. It may never remove the stop entirely, and it is never required for the plan to execute.

---

## 3. Risk engine (deterministic, pre-trade)

Every `OrderIntent` passes hard checks *before* any fill:

| Check | Example limit (draft — needs owner input, doc 11 G-18) | Applies to |
|---|---|---|
| Per-order notional cap | ≤ X% of paper capital | ENTRY |
| Per-instrument position cap | ≤ Y units / Z% of capital | ENTRY |
| Portfolio gross/net exposure cap | ≤ gross G%, net N% | ENTRY |
| **Margin availability (§3.1)** | required margin ≤ available margin × safety factor | ENTRY |
| Daily loss limit (kill-switch) | halt new entries if day P&L < −L% | ENTRY |
| Max open orders / positions | **Derived from exit throughput, not chosen freely — see §3.3.1** | ENTRY |
| Order rate budget | mirror 10/s, 400/min, 5,000/day; exits draw on reserved capacity (§3.3) | ALL |
| Event-window de-risk | reduce size / block new entries around scheduled central-bank events | ENTRY |
| Instrument eligibility | tradable, not in F&O ban, within circuit limits, not stale (doc 06 §1.6) | ALL |
| **Exit plan present and sane** | stop exists, is on the correct side of entry, within circuit bounds | ENTRY |
| Market protection present | non-zero for MARKET / SL-M | ALL |

- **Reject** or **resize** intents that violate a check; emit a rejection `OrderAck` with a machine-readable reason.
- **Risk checks never block an EXIT or REDUCE.** Reducing exposure is unconditionally permitted — including when the account is over its limits, the kill-switch has tripped, or the daily loss cap is breached. Those are the situations where exits matter most.
- **Kill-switch:** a single deterministic trigger (daily loss, data outage, reconciliation mismatch, or manual) that flattens/halts. Must be testable and observable. Tripping it *enables* exits and *disables* entries — never the reverse.

### 3.1 Margin model (mandatory — the paper account must be fundable)

**Why this exists:** a paper engine that checks only notional caps will happily open F&O positions the real account could never fund. Both the P&L *and* the strategy's apparent capacity become fiction, and the "flipping to live is a configuration change" promise (doc 01 §2) breaks on the first live day — with rejections, not with a bad fill.

This is genuinely harder in India than notional checks, because F&O margin is SPAN + exposure, is portfolio-offsetting, and changes intraday.

**Approach, in order of preference:**

1. **Use Kite's margin APIs** (`order_margins`, `basket_order_margins`) to price margin for a proposed basket. Most accurate, costs a rate-budget call. ⚠️ **Not available in the sandbox** (doc 02 §7), so this path can only be validated against production.
2. **Local approximation** — maintain a per-instrument margin table refreshed daily (span + exposure per lot from the broker's published files), applied with no portfolio offset. Systematically **over**-estimates margin for hedged positions, which is the safe direction.
3. **Fallback if neither is available: a hard conservative gross-exposure cap** with a large buffer, and a loud note in the ledger that margin is unmodelled so the results are read correctly.

**Rules:**
- Track `margin_used` and `margin_available` in the ledger continuously, marked to market like P&L.
- A margin breach is a **kill-switch trigger**, not a warning.
- **Never model margin more favourably than reality.** An over-estimate costs us paper trades we could have taken; an under-estimate invalidates the entire paper exercise. Bias hard toward the first.

#### Reference — what SPAN is computing on your behalf

> ⚠️ **This is background for interpreting the API's answer. It is NOT an implementation spec — do not build option 2 from it.** See the caveats below.

For a portfolio of derivative and underlying holdings $\mathbf{w} = [w_1, \dots, w_M]^T$:

$$\text{Margin}_{\text{required}}(\mathbf{w}) = \text{SPAN}(\mathbf{w}) + \sum_{i=1}^M \text{ExposureMargin}(w_i)$$

1. **SPAN scanning risk** — max loss across a standard array of 16 price/volatility stress scenarios:
   $$\text{SPAN}(\mathbf{w}) = \max_{k \in \{1 \dots 16\}} \left( -\sum_{i=1}^M w_i \cdot \Delta V_{i,k} \right)$$
2. **Exposure margin** — a floor on gross derivative exposure, shaped roughly as:
   $$\text{ExposureMargin}(w_i) = |w_i| \cdot S_i \cdot \max\left(\text{pct}_{\text{segment}}, \, 1.5 \cdot \sigma_{\text{daily}, i}\right)$$

**Why you cannot compute this yourself, and must not try:**

| Issue | Consequence |
|---|---|
| **Scan ranges and volatility shifts come from the exchange's daily risk parameter file**, per underlying, and change every day | Any hardcoded ±3σ price / ±4% vol shift is wrong for most instruments on most days. The ±4% figure is roughly index-option-shaped; stock options run materially wider |
| **The formula omits short option minimum charge** | Short option positions under-margined — the most dangerous direction |
| **Omits calendar-spread charges and inter-month/inter-commodity credits** | Spread positions mis-margined in both directions |
| **Omits the premium/assignment and delivery-margin components** | Expiry-week positions badly wrong, which is when they matter most |

**The trap this creates:** the formula looks tractable, so option 2 looks like "just implement SPAN." It is not — it is a substantial project that will produce a confidently wrong number, failing in exactly the direction §3.1 forbids. **Prefer option 1. If you must approximate, use published per-lot margin tables (option 2) rather than a scenario engine of your own**, and treat this section purely as an explanation of what those numbers mean.

---

### 3.2 Behaviour when the data feed dies

Open positions plus no prices is the most dangerous state the system can be in — stops cannot be evaluated, so risk is unmanaged and invisible.

| Feed state | Position Manager behaviour |
|---|---|
| Stale beyond threshold, reconnect in progress | Freeze new entries; hold exits; alert. Exits still fire on the last known price if a stop was already breached |
| Data loss beyond the grace window | Honour each position's `on_data_loss`: `FLATTEN` (default for MIS/leveraged) or `HOLD` (defensible for CNC delivery) |
| Reconnected, resyncing | No fills against `resync`-tagged ticks until a snapshot confirms state (doc 06 §1.6) |

⚠️ The grace window and the per-product default are owner decisions (doc 11 G-18). The design requirement is only that **the behaviour is explicit and pre-decided**, not improvised during an outage.

---

### 3.3 Rate-budget governor and reserved exit capacity

*(Moved here from doc 02 §2 — this is our design, not a Kite constraint. Doc 02 records the limits; this records how we live inside them.)*

**Token bucket.** For request category $c$, available tokens $T(t)$ refill at rate $r_c$ up to capacity $B_{\max,c}$:

$$T(t) = \min\left(B_{\max, c}, \; T(t_{\text{prev}}) + r_c \cdot (t - t_{\text{prev}})\right)$$

A request needing $w$ tokens executes if $T(t) \ge w$, then $T(t) \leftarrow T(t) - w$. Parameters mirror doc 02 §2 exactly: $r_{\text{quote}}=1$, $r_{\text{hist}}=3$, $r_{\text{order}}=10$, each with $B_{\max}=r$.

**⚠️ Orders are bucketed by wall-clock second, not a rolling window.** The regulatory TOPS is measured on the **calendar clock second of the broker server** (doc 02 §9.5) — a leaky-bucket or sliding-window limiter can pass "10 in any 1 s window" while still placing >10 inside one wall-clock second, breaching TOPS while appearing compliant. Count per calendar second, and **target 8/s rather than 10** to absorb clock skew between our host and the broker.

**Orders additionally satisfy three nested windows simultaneously:**

$$\sum_{t_i \in [t-1\text{s},\, t]} c_i \le 10, \qquad \sum_{t_i \in [t-60\text{s},\, t]} c_i \le 400, \qquad \sum_{t_i \in \text{Session}} c_i \le 5{,}000$$

**Reserved exit capacity.** Exit intents (`intent_kind = EXIT | REDUCE`) draw from a reserved allocation $B_{\text{reserved}} = 2$ tokens/s that entries cannot consume, and preempt queued entries. Without this, a burst of entries can starve the exit path at precisely the moment exits matter — which would defeat the entry/exit asymmetry (§4) at the level of the rate limiter.

#### 3.3.1 ⚠️ Exit throughput bounds how many positions we may hold

Reserved capacity is a **rate**, and in a market-wide selloff **every stop fires at once**. That makes exit throughput a hard constraint on book size, not a background detail:

$$t_{\text{flatten}} \approx \frac{N_{\text{open}}}{r_{\text{exit}}}$$

At $r_{\text{exit}} = 2$/s, 50 open positions take **~25 seconds** to flatten — during a move fast enough to have triggered all 50 stops. The last position out is the one that pays for the queue.

**Therefore the position-count limit is derived, not chosen:**

$$N_{\max} \le r_{\text{exit}} \cdot t_{\text{flatten,target}}$$

Pick the tolerable worst-case flatten time first, then let it set the cap. A 5-second target at $r_{\text{exit}}=2$ gives $N_{\max}=10$ concurrent positions.

**Escalation under duress.** When the kill-switch trips, or when queued exits exceed a threshold, exits may claim the **entire** 10/s budget — entries are already halted in that state, so nothing is lost by handing over the whole bucket. Reserved capacity is the steady-state floor; the ceiling under stress is the full limit.

⚠️ **Never escalate past the TOPS ceiling.** Above 10 OPS *the broker rejects the excess orders outright* (doc 02 §9.5, NSE §B.5) — so a burst that breaches TOPS in a crisis would drop the very **exit** orders escalation exists to protect. Our limiter must bind before the broker's: escalation reallocates the budget between entries and exits, it never raises the total.

⚠️ $t_{\text{flatten,target}}$ is an owner decision (G-18) and it is more consequential than it looks: it silently caps strategy breadth. A strategy wanting 40 concurrent positions is asking for a 20-second worst-case flatten, and that trade-off should be made deliberately rather than discovered during a selloff.

**A note on units:** these are *orders*, not positions. A partially-filled exit may need modification or reissue, so budget headroom above $N_{\max}$ is required, not optional.

---

## 4. Position Manager (Rust) — owns every open position

**Why this component exists** (see also doc 03 §2.1): entries and exits have opposite failure modes. A late entry costs an opportunity; a late exit costs money without bound. So entries are LLM-decided and exits are code-decided.

**Responsibilities:**
- Take ownership of a position the moment the `OrderAck` reports a fill.
- Evaluate every open position's `ExitPlan` against every tick from the live cache.
- Emit `EXIT` / `REDUCE` intents deterministically on: stop hit, target hit, `max_holding` reached, `square_off_at` window, feed-loss policy, or kill-switch.
- Maintain trailing-stop state; apply manager-published plan updates atomically.
- **Never require the cognition plane to be alive.**

**Latency budget:** tick → stop evaluation → exit intent emitted, well inside the tick-to-cache budget (doc 01 §6). It reads the same last-value cache the screeners do, so it inherits the p99 < 5 ms path.

**Interaction with the manager:** the manager can *tighten* a stop, trail it, take partial profit, or request a full exit. It cannot widen a stop beyond the plan's original risk, remove a stop, or veto an exit that has already triggered. Adjustments are versioned so a late-arriving stale update never resurrects an old plan.

### 4.1 Fill simulator & Microstructure Physics (paper backend)

Matches paper LIMIT/MARKET orders against the live tick stream using microstructural execution dynamics:

#### Market impact & slippage — square-root impact law

> **Scope:** this applies to **marketable** orders. The paper phase is LIMIT-only (doc 02 §7, G-20), so in Phase 3 it governs only marketable-limit fills that cross the spread. It becomes fully load-bearing at live migration — specified now so the model exists and can be calibrated before it matters.

For marketable orders, execution price $P_{\text{exec}}$ incorporates half-spread plus non-linear impact:

$$P_{\text{exec}} = P_{\text{arrival}} \cdot \left(1 + \text{Sign}(Q) \cdot \left[ \frac{\text{Spread}}{2 \cdot P_{\text{arrival}}} + \gamma \cdot \sigma_{\text{daily}} \left( \frac{|Q|}{V_{\text{ADV}}} \right)^\alpha + \eta_{\text{latency}} \right] \right)$$

where $Q$ is order size, $V_{\text{ADV}}$ is 30-day average daily volume, $\gamma$ and $\alpha$ are the impact coefficients, and $\eta_{\text{latency}} \sim \mathcal{N}(\mu_{\text{lat}}, \sigma_{\text{lat}}^2)$ is a stochastic latency penalty.

**⚠️ On $\gamma$ and $\alpha$ — start pessimistic, not at the literature value.**

$\alpha \approx 0.5$ (the square-root law) is robust across markets and is a reasonable default. **$\gamma \approx 0.5$ is not ours to borrow** — it comes from studies of large-cap developed-market equities. Indian mid- and small-cap names, and the illiquid strikes that make up most of the NFO option chain, exhibit materially higher impact for the same participation rate. The long tail of our 9,000-instrument universe is exactly where the borrowed constant is least applicable.

Per §4.2 — *every ambiguous modelling choice defaults to the pessimistic side* — the starting value must sit **above** the literature figure, not at it:

| Parameter | Start | Rationale |
|---|---|---|
| $\alpha$ | 0.5 | Square-root law; robust across markets |
| $\gamma$ (liquid large-cap) | **1.0** | 2× the developed-market figure until fitted |
| $\gamma$ (mid/small-cap, illiquid options) | **1.5–2.0**, by liquidity bucket | Impact rises sharply as ADV falls |
| $\eta_{\text{latency}}$ | Non-zero mean | Never model zero-latency execution |

**Calibration is a Phase 6 task, not an assumption:** fit $\gamma$ per liquidity bucket against replayed sessions (§4.3), and record the fitted values with their date and sample. Until then the numbers above are **unfitted priors chosen to be conservative**, and every P&L figure they produce should be read as a floor rather than an estimate.

*Naming note: this is the square-root impact law plus a half-spread term. It is a component of the Almgren-Chriss optimal-execution framework, not that framework itself — we are not solving an execution-scheduling problem here.*

#### Passive Limit Order Queue Depletion Mechanics

For a resting limit order $O_{\text{limit}}$ at price $P_{\text{limit}}$ submitted at time $t_0$ when displayed depth at $P_{\text{limit}}$ is $D_0$:

1. Initial Queue position: $q(t_0) = D_0(P_{\text{limit}})$
2. Queue depletion via subsequent ticks $t > t_0$:
   $$q(t) = \max\left(0, \, q(t_0) - \sum_{t_i = t_0}^t V_{\text{trade}}(P_{\text{limit}}, t_i)\right)$$
3. **Fill Execution**: Order fills quantity $Q_{\text{fill}} = \min\left(Q_{\text{order}}, \sum_{t_i} V_{\text{trade}}(P_{\text{limit}}, t_i) - q(t_0)\right)$ once $q(t) = 0$, OR immediately fills $100\%$ if any trade executes through the level ($P_{\text{trade}} < P_{\text{limit}}$ for BUY, $P_{\text{trade}} > P_{\text{limit}}$ for SELL).

- **Only sane ticks are fill-eligible** — `suspect`, `stale`, and `resync` ticks cannot trigger a fill (doc 06 §1.6). This prevents one bad print from manufacturing a position.
- **Outputs:** `OrderAck` with fills → updates positions → hands the position to the Position Manager → updates the P&L ledger.

**Fidelity is a first-class concern:** an over-optimistic simulator invalidates the whole paper exercise. The simulator's assumptions (instant fill? full depth? zero slippage?) must be explicit, conservative by default, and validated by replay (doc 11, Gap G-09).

### 4.2 Conservative defaults

Every ambiguous modelling choice defaults to the pessimistic side, and each default is logged so results can be re-read if it changes:

| Question | Default |
|---|---|
| Fill on a touch of the limit price? | **No** — require trade-through, or depth confirmation at the level |
| Fill the full quantity? | **No** — cap at displayed depth; partial otherwise |
| Zero latency? | **No** — model a configurable submit→ack delay, and re-check the price after it |
| Queue priority? | **Assume last in queue** until a queue model exists |
| Slippage on marketable orders? | **Always non-zero** |

### 4.3 Replay harness (a Phase 1 deliverable, not an afterthought)

Two open gaps — fill fidelity (G-09) and look-ahead bias (G-23) — both resolve to "validate by replay," yet replay appeared in no phase's deliverables. It is promoted to a first-class component:

- **Deterministic *across the hot plane*:** given the same captured tick file and the same config, the ingester, sanity filter, risk engine, Position Manager, fill simulator, and ledger produce byte-identical results. No wall-clock, no RNG without a seed.
  - ⚠️ **This guarantee stops at the plane boundary.** An LLM call is not deterministic — the same prompt yields different completions. Any replay that includes the cognition plane is *not* reproducible unless LLM responses are recorded and replayed from cache. See §4.3.1.
- **Drives the real components**, not a copy of them — the same simulator and Position Manager code paths that run live.
- **As-of discipline enforced structurally:** the replay clock gates data access, so an agent physically cannot read a tick from the future. This is a far stronger guarantee than a code-review convention (G-23) — **but it cannot gate what the model already knows** (G-42).
- **Used for:** fill-fidelity validation, **deterministic-plane backtests**, regression tests on the risk engine, and reproducing any production incident from captured ticks.

It is the most reused piece of test infrastructure in the project, so it lands in Phase 1 alongside the ingester that produces its input.

#### 4.3.1 LLM response caching — required for any replay touching the cognition plane

To replay a session that included agent decisions, every LLM request/response pair must be **recorded at the time it happened** and replayed from that record. Keyed on a hash of `(model, prompt, params)`, stored alongside the tick capture.

This gives reproducibility, but note precisely what it buys and what it doesn't:

| | Replaying cached responses | Re-running the agents live |
|---|---|---|
| Reproducible | ✅ Byte-identical | ❌ Different every run |
| Cost of a re-run | ✅ Free | ❌ Full token cost (doc 08 §8) |
| Tests a **prompt change** | ❌ Cache misses; you are back to live cost | ✅ |
| Valid for **incident forensics** | ✅ The intended use | — |
| Valid for **strategy validation** | ❌ You are replaying one sampled path, not the distribution | ❌ See G-42 |

**So cached replay is a debugging tool, not a backtesting tool.** It answers *"what did the system do on 14 March and why?"* — which is exactly what you need after a loss, and is worth building for that alone. It does **not** answer *"would this strategy have worked?"*

### 4.4 MIS auto square-off (must be modelled)

Zerodha force-closes intraday positions near the close and charges for it — **3:25 PM equity, 3:26 PM F&O, ₹50 + 18% GST per squared-off order** (doc 02 §6.2).

- The Position Manager sets `square_off_at` automatically on every MIS entry, **a configurable margin before the broker's own cut-off**, so Kestrel closes its own positions rather than being closed.
- Any position the broker would have squared off is charged the ₹50 + GST in the ledger, so a strategy that relies on being force-closed sees its true cost.
- ⚠️ These timings changed in December 2025 and will change again. They live in **config, not code**, with the source and verification date recorded.

Without this, every MIS strategy's paper results are optimistic by an amount that scales with trade count — one of the easiest ways to manufacture a fake edge.

---

## 5. P&L ledger & position state
- Authoritative record of paper positions, realized/unrealized P&L, and per-trade attribution back to the agent chain that produced it.
- Marked-to-market continuously from the live cache.
- **Append-only and crash-safe**, exposed to Grafana. **Redis is transport; the ledger is the record** (doc 06 §2.1).
  - **Corrections are new entries, never in-place edits** (D-15). A reconciliation adjustment, a cost-model restatement, or a mis-booked fill is appended with a reference to what it supersedes. The ledger is therefore replayable to any point in time, and *"what did we believe our position was at 14:32?"* is answerable — which is exactly the question a post-mortem asks.
- **Reconciliation:** paper position state is periodically reconciled against the ledger; any mismatch trips the kill-switch.
- Tracks `margin_used` / `margin_available` alongside P&L (§3.1).

### 5.1 Indian cost model (doc 11, G-19)

Paper P&L is only meaningful if costs are modelled accurately — for intraday strategies costs routinely exceed the gross edge.

**Rates as of 2026-07-22** ✅ *(sourced from [Zerodha's charges page](https://zerodha.com/charges/); ⚠️ these change with every budget and exchange circular — see the versioning rule below)*:

| Component | Equity delivery | Equity intraday | Equity futures | Equity options |
|---|---|---|---|---|
| **Brokerage** | **Zero** | 0.03% or ₹20/order, **whichever is lower** | 0.03% or ₹20/order, lower | **Flat ₹20/order** |
| **STT** | 0.1% **both sides** | 0.025% **sell only** | 0.05% **sell only** | 0.15% on premium, sell (0.15% on intrinsic if exercised) |
| **Exchange txn (NSE)** | 0.00307% | 0.00307% | 0.00183% | 0.03553% on premium |
| **Exchange txn (BSE)** | 0.00375% | 0.00375% | 0% | 0.0325% on premium |
| **SEBI turnover** | ₹10 per crore | ₹10 per crore | ₹10 per crore | ₹10 per crore |
| **Stamp duty** | 0.015% (₹1,500/cr), **buy only** | buy only | buy only | buy only |
| **GST** | 18% on (brokerage + SEBI + exchange txn) | same | same | same |
| **DP charges** | **₹15.34 per scrip on sell** | — | — | — |
| **Auto square-off** | — | **₹50 + 18% GST per order** (§4.4) | **₹50 + 18% GST per order** | **₹50 + 18% GST per order** |

**Four traps this table exposes — each one silently inflates paper P&L if missed:**

1. **STT is asymmetric and segment-specific.** Delivery charges both sides; intraday and futures charge **sell only**; options charge on **premium**, not notional. A model that applies one STT rate uniformly is wrong in every segment.
2. **Options brokerage is flat ₹20, not percentage.** On small option lots ₹20/leg can exceed the entire gross edge — a strategy trading many cheap options is cost-dominated in a way a percentage model would never reveal.
3. **DP charges are per-scrip, not per-trade.** ₹15.34 on every delivery sell regardless of size makes small delivery positions structurally unprofitable.
4. **Zero delivery brokerage is not zero cost.** STT, stamp duty, exchange charges, GST, and DP charges all still apply. "Free" delivery trades carry real friction.

**The versioning rule.** Rates live in a **dated, versioned config file** with the source URL and verification date recorded — never scattered through code. A backtest over 2024 must run under 2024's cost regime, not today's. The ledger records which cost-config version priced each fill, so historical results stay reproducible after a rate change.

⚠️ **Still to confirm before relying on these:** exact GST treatment of DP charges; whether stamp duty varies by state for our account; the current option-exercise STT mechanics. Confirm with Zerodha and record the answers with dates.

---

## 6. Live migration (later, behind go/no-go)
Flipping to live = change the execution backend from `simulator` to `kite_orders` behind the same `OrderIntent`/`OrderAck` interface, and:
- Route through the real order token bucket (10/s, 400/min, 5,000/day).
- **Place the order path behind the registered static IP** — Kite rejects orders from unwhitelisted IPs (doc 02 §9). Verify before the first live order, not after.
- Subscribe to **postbacks/webhooks** for authoritative order-status updates (instead of simulator acks), treating the endpoint as untrusted input.
- Switch margin checks from the local approximation to Kite's margin APIs (§3.1).
- Enable real fills, real fees, real slippage.
- **Nothing upstream changes** — screeners, specialists, and the risk manager are unaware of the backend.
- **Gated by:** doc 09 Phase 6 review + the regulatory checks in doc 11 (G-02).

**Two things that do change and must be re-tested:** the Position Manager now races real exchange state rather than a simulator it controls, so exit acknowledgement becomes asynchronous and can fail; and partial fills become real, so position state must be derived from postbacks rather than assumed from intent.

---

## 7. Metrics to expose
- Intents received / accepted / rejected (by reason, by `intent_kind`).
- Fill latency, partial-fill rate, average slippage (sim).
- Order-budget headroom (10/s, 400/min, 5,000/day) — and **distance to the 10 OPS formal-registration threshold**, tracked per exchange segment as well as in aggregate (doc 02 §9.3).
- **Orders emitted without a populated `algo_id`: must be zero.** Alert on any non-zero value — it is a compliance defect, not a warning.
- **Reserved-exit-capacity utilisation; queued exit depth; projected $t_{\text{flatten}}$ at the current position count** (§3.3.1). Alert on the last one — it measures how close the book is to being un-flattenable inside its target.
- Live paper P&L, drawdown, open exposure (gross/net).
- **Margin used / available / headroom.**
- **Open positions by age; positions approaching `max_holding` or `square_off_at`.**
- **Exit-trigger counts by cause** (stop / target / time / square-off / kill-switch) — the mix is a strategy-health signal.
- **Stop-evaluation latency (p99)** — the number that matters most if the exit path is ever slow.
- Kill-switch state and trigger history.
- Reconciliation status.
