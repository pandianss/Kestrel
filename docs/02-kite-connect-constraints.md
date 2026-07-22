# 02 — Kite Connect API Constraints (the load-bearing facts)

**Last updated:** 2026-07-22
**Source:** [Kite Connect v3 docs](https://kite.trade/docs/connect/v3/).

**Verification convention used in this document:**

| Marker | Meaning |
|---|---|
| ✅ *(verified YYYY-MM-DD)* | Checked against the cited primary source on that date |
| ⚠️ | Not confirmable from the public docs, or known to drift — re-verify before relying on it |

Facts here have an expiry date. Broker limits, pricing, and regulation all change — see the README's *Facts with an expiry date* table for the re-verification cadence.

> **Why this document exists:** every architectural decision in this repo traces back to a constraint here. Two meta-facts govern everything else:
>
> 1. **All rate limits are per API key, not per process.** Spawning more agents that call Kite does not multiply throughput — they share one budget. This forces the I/O-facing layer to be centralized singletons.
> 2. **Since 1 April 2026, SEBI's retail algo framework is a live constraint, not a future one** (§8). It shapes deployment topology and the order payload itself, so it belongs in Phase 0 rather than a pre-live review.

---

## 1. Authentication & session

- **Model:** `api_key` + `api_secret` (secret stays server-side only, never in a client).
- **Login flow:** redirect user to Kite login → receive temporary `request_token` at redirect URL → POST `request_token` + `checksum` to `/session/token` → receive `access_token`.
- **Checksum:** `SHA-256(api_key + request_token + api_secret)`.
- **Auth header on every call:** `Authorization: token api_key:access_token`.
- **Token lifetime:** `access_token` **expires at 6:00 AM the next day** (regulatory requirement), or on explicit logout / master-logout from Kite web. ✅ *(verified 2026-07-22 against the [user/session docs](https://kite.trade/docs/connect/v3/user/); the docs' exact wording is "it'll expire at 6 AM on the next day (regulatory requirement)")*. This means **a fresh login is required every day** before market open.
- **Refresh token:** a `refresh_token` field *does* exist in the session response, documented as "a token for getting long standing read permissions… only available to certain approved platforms." ✅ *(verified 2026-07-22)*
  - **It is not available to us**, and no refresh mechanism is documented for ordinary API keys. Treat the daily mint as unavoidable.
  - ⚠️ Worth one email to Zerodha before Phase 6 asking what "approved platform" status requires — if obtainable, it removes the single most annoying operational step in the system. Do not design around it until answered.
- **2FA:** TOTP-based 2FA is mandatory on every API session login under the SEBI framework (§8). This is what makes fully-unattended login a ToS problem, not merely a technical one.
- **Logout:** `DELETE /session/token` invalidates the session.

**Architectural consequence:** a daily token-minting step is unavoidable (see doc 10 §2). All services must handle `403 TokenException` (session expired) gracefully and block until a new token is provided.

---

## 2. Rate limits (per API key)

✅ *(whole section verified 2026-07-22 against the [exceptions/rate-limiting docs](https://kite.trade/docs/connect/v3/exceptions/#rate-limiting))*

| Endpoint category | Limit |
|---|---|
| Quote (`/quote`, `/quote/ohlc`, `/quote/ltp`) | **1 request / second** |
| Historical candle | **3 requests / second** |
| Order placement | **10 requests / second** |
| All other endpoints | **10 requests / second** |

> **How we enforce these** — token-bucket dynamics, the nested order windows, and reserved exit capacity — is **our design, not Kite's constraint**, and lives in **doc 07 §3.3**. This document stays limited to externally verifiable facts so that its claims can be checked one by one against the source. Mixing our design into it would dilute the one thing it is for.

**Order-specific limits:**
- **10 orders / second**, **400 orders / minute**, **5,000 orders / day** per user/API key.
- **Max 25 modifications** per order before it must be cancelled and re-submitted.
- Auto-sliced (iceberg) orders: **max 10 slices** per placement.

**Only order placement has per-minute and per-day caps.** Quote and historical are throttled per-second only — there is no daily quota on historical calls. ✅ *(verified 2026-07-22)* This matters for backfill planning: a long backfill is bounded by wall-clock at 3/s, not by a daily allowance that could strand it.

**The 10/s order limit is account-scoped, not app-scoped** — it applies per Kite client ID regardless of how many apps sit under one developer profile. Additional apps do not buy additional order throughput.

**Architectural consequence:** exactly one governed component may talk to each rate-limited surface. Order placement is a **single-writer** with a token bucket enforcing 10/s, 400/min, 5,000/day. Quote polling is centralized behind a 1/s bucket. Historical backfill behind a 3/s bucket.

**Compliance consequence (see §9):** exceeding 10 orders/second pushes a strategy from "casual API usage" — which still carries a **generic** Algo ID — into **formal strategy registration and testing** through the broker. Our 10/s bucket therefore marks the line between generic and registered, **not** between untagged and tagged: every API order carries an algo tag either way (§9.3). Staying under it is a *design constraint* that avoids a registration burden, not a way to avoid tagging.

⚠️ **Two limits, same number, different authorities.** Kite's 10 req/s is a **broker rate limit per Kite client ID**; the regulatory TOPS is **10 OPS per exchange**, measured on the **calendar clock second** of the broker server ✅ *(NSE/INVG/67858 §B.2)*. They coincide numerically and are not the same constraint — and the calendar-second basis means a rolling-window limiter does **not** satisfy it. See §9.5.

---

## 3. WebSocket streaming

✅ *(whole section verified 2026-07-22 against the [WebSocket docs](https://kite.trade/docs/connect/v3/websocket/), including the index-packet byte table)*

- **Endpoint:** `wss://ws.kite.trade?api_key=...&access_token=...`
- **Concurrent connections:** **up to 3 per API key.**
- **Instruments per connection:** **up to 3,000.**
- **Therefore max streamed instruments:** **3 × 3,000 = 9,000.** (This is why the "max universe" choice consumes all 3 connections on one key.)
- **Modes** (per subscribed instrument, can differ per instrument):

  | Mode | Contents | Packet size |
  |---|---|---|
  | LTP | last traded price only | 8 bytes |
  | Quote | several fields, **no** market depth | 44 bytes |
  | Full | several fields **+ 5-level market depth** | 184 bytes |

  Index instruments (e.g. NIFTY 50) use smaller packets: **28 bytes (quote)**, **32 bytes (full)**. The index packet is 8 × `int32`: token, LTP, high, low, open, close, price-change *(quote ends here at byte 28)*, exchange timestamp *(full ends at byte 32)*.
- **Binary framing:** message = 2-byte packet count, then repeating [2-byte length][packet]. Market depth in Full mode = 10 entries (5 bid + 5 offer), 12 bytes each.
- **Subscription control:** JSON messages with actions `subscribe`, `unsubscribe`, `mode`. Mode can be changed live per instrument.
- **Keepalive:** when there is no data to stream, the server sends a **1-byte heartbeat every couple of seconds**, which can be safely ignored as payload — but its *absence* is our staleness signal (doc 06 §4).

**Architectural consequence:** the design uses **tiered modes** (Full for the active few hundred, Quote for the broad watch, LTP for the long tail) with dynamic promotion/demotion. See doc 06.

⚠️ *Reason corrected 2026-07-22.* An earlier version justified tiering as a **bandwidth** measure. The arithmetic in doc 06 §6 does not support that: even all 9,000 in Full mode is roughly 1.7 MB/s (~13 Mbps), which is unremarkable. The real costs of Full mode are **parse CPU** (10 depth entries per packet, per instrument, per tick), **storage** (depth is the bulk of the volume and the least reusable), and **downstream usefulness** — depth on an instrument nobody is trading is pure overhead. Tiering is still right; the justification was wrong, and it matters because it changes what the Full-tier cap should be tuned against (G-06).

---

## 4. Market quotes (REST) & instruments

- **`/quote`** (full snapshot): up to **500 instruments / call**. Includes OHLC, OI, bid/ask depth, volume, avg price, circuit limits, last trade.
- **`/quote/ohlc`**: up to **1,000 instruments / call**. Last price + OHLC.
- **`/quote/ltp`**: up to **1,000 instruments / call**. Last price only.
✅ *(batch sizes verified 2026-07-22 against the [market-quotes docs](https://kite.trade/docs/connect/v3/market-quotes/))*

- All subject to the 1 req/sec quote limit. Missing instruments are **absent** from the response map (not null) — presence must be checked.
- **Instruments master dump** (`/instruments`): gzipped CSV of all tradable instruments, **regenerated once daily** (~08:30 AM recommended fetch). Fields include `instrument_token`, `exchange_token`, `tradingsymbol`, `name`, `last_price`, `expiry`, `strike`, `tick_size`, `lot_size`, `instrument_type`, `segment`, `exchange`.
- **Stable identifier:** use `exchange + tradingsymbol`. Numeric `instrument_token` **may be reused** after a derivative expires — do not treat it as permanent.

**Architectural consequence:** fetch and store the instruments master locally each morning; maintain a mapping layer keyed on `exchange:tradingsymbol` for stable identity and on `instrument_token` for WebSocket subscription.

---

## 5. Historical candle data

- **Intervals:** `minute`, `3minute`, `5minute`, `10minute`, `15minute`, `30minute`, `60minute`, `day`.
- **Max date range per request** — ⚠️ **these numbers are not published on the public docs page.** They circulate via the developer forum and SDK behaviour. Treat them as a starting assumption and have the backfill job *discover* the real cap by catching the error and bisecting, rather than hard-coding it:

  | Interval | Max days / request (assumed) |
  |---|---|
  | minute | 60 |
  | 3–10 minute | 100 |
  | 15 / 30 minute | 200 |
  | 60 minute | 400 |
  | day | 2,000 |

- **Rate limit:** 3 requests / second, with **no per-day cap**. ✅ *(verified 2026-07-22)*
- **Options:** `continuous=1` (stitch expired futures contracts for NFO/MCX), `oi=1` (include Open Interest as a 7th value). ✅ *(verified 2026-07-22)*
- **Retention:** the docs say only "several years" without committing to a figure. ⚠️ Forum reports suggest roughly 3 years for minute candles, longer for coarser intervals — **measure the actual available start date per interval during Phase 2 backfill and record it**, because backtest window length depends on it.
- **Included with the base subscription** since February 2025 — the former ₹2,000/month historical add-on no longer exists. ✅ *(verified 2026-07-22 — see doc 10 §5)*

### 5.1 Corporate-action adjustment — partial, and the gaps matter

✅ *(verified 2026-07-22 via the Kite developer forum; ⚠️ confirm with Zerodha before relying on it for backtests)*

**Kite adjusts historical candles for splits and bonuses only.** Adjustments are applied at the start-of-day process **on the ex-date**, and once applied the API returns adjusted prices for all historical dates from 2012 onward.

**Not adjusted:** dividends, rights issues, demergers, and other corporate actions.

| Action | Kite adjusts? | Consequence for us |
|---|---|---|
| Split | ✅ Yes | Handled |
| Bonus | ✅ Yes | Handled |
| **Dividend** | ❌ No | Price series shows an ex-date gap down that was not a real loss. Any gap-detection, momentum, or stop-distance logic reads it as a genuine move |
| **Rights issue** | ❌ No | Unadjusted discontinuity |
| **Demerger** | ❌ No | Largest distortion — the price step can be very large and is pure artifact |

**Architectural consequences:**

1. **We need a corporate-actions layer regardless.** Splits and bonuses being handled removes the worst of the problem but not the requirement. Dividend ex-dates in particular are frequent and systematic — a backtest that treats every ex-date gap as a real move will manufacture signal from a calendar.
2. **The ex-date timing creates a live-vs-historical inconsistency.** Adjustment lands at start-of-day *on* the ex-date, so a series fetched the day before and the same series fetched the day after **differ for identical historical dates**. Any cached or derived data — indicators, regime priors, the study fleet's watchlist — is silently stale across an adjustment. **Backfill must detect adjustment events and invalidate downstream derived data**, not just append new candles.
3. **Pre-2019 intraday data is inconsistently adjusted.** Forum reports indicate intraday candles were not adjusted for all contracts before 2019 (adjusted intraday exists from 2015 for active contracts only). **Long intraday backtests spanning that boundary are unreliable** — either start after 2019 or treat earlier intraday data as unadjusted.
4. **The replay harness inherits this.** Look-ahead discipline (G-23) does not help if the underlying series is silently re-based mid-study.

⚠️ **Verify before Phase 2:** exact adjustment timing relative to the SOD process, and whether the F&O `continuous=1` stitched series carries its own adjustment behaviour. Both are load-bearing for backtest validity.

**Architectural consequence:** long lookbacks on fine intervals require many chunked requests, all sharing 3/s. Backfill is a governed, resumable batch job that runs *before* analysis, so the study agents read from local storage, not the live API.

---

## 6. Orders (reference)

- **Order types:** MARKET, LIMIT, SL (stop-loss), SL-M (stop-loss market).
- **Products:** CNC (delivery equity), NRML (F&O carry), MIS (intraday), MTF (margin trading facility).
- **Varieties:** `regular`, `amo` (after-market), `co` (cover order), `iceberg`, `auction`.
- **Operations:** `POST /orders/:variety` (place), `PUT` (modify), `DELETE` (cancel).
- **Statuses:** VALIDATION PENDING, OPEN PENDING, TRIGGER PENDING, OPEN, COMPLETE, CANCELLED, REJECTED (+ interim MODIFY states).
- **Postbacks / webhooks:** Kite can POST order-status updates to a registered URL — the push alternative to polling order state.

### 6.1 Market protection (mandatory since the SEBI framework) ⚠️ *new*

**MARKET and SL-M orders must now carry a non-zero market-protection value. Orders submitted with market protection `0` are rejected.** Passing `-1` applies the automatic per-instrument limit derived from circuit restrictions. This applies across all SDKs and to MCX commodities as well.

Market protection converts a MARKET order into a limit-capped market order: the order will not fill worse than *N%* away from the reference price. It is a broker-side guard against a market order sweeping a thin book.

**Architectural consequence:** `OrderIntent` carries a `market_protection` field from the outset, even though the paper phase is LIMIT-only (§7). Adding it at live-migration time would be exactly the kind of "paper-only shortcut that doesn't survive live" that doc 07 §1 forbids. The fill simulator should honour it too, so the constraint is exercised before it matters.

### 6.2 MIS auto square-off

Zerodha force-closes open intraday (MIS) positions near the close, and charges for doing so:

| Segment | Auto square-off time | Charge |
|---|---|---|
| Equity intraday | **3:25 PM** | ₹50 + 18% GST **per order squared off** |
| F&O intraday | **3:26 PM** | ₹50 + 18% GST **per order squared off** |

✅ *(verified 2026-07-22; revised from 3:20/3:25 PM in December 2025 — ⚠️ these timings have changed before and will change again)*

**Architectural consequence:** the fill simulator and P&L ledger must model both the forced exit *and* its charge, or every MIS strategy's paper results are optimistic by an amount that scales with trade count. See doc 07 §4.4.

---

## 7. Sandbox

- **Host:** `sandbox.kite.trade`. Demo credentials `sandboxdemo` / `sandboxdemo-secret` (safe to commit).
- **Supports:** simulated order placement (**LIMIT only — no MARKET via API**), modify/cancel, order status, positions, holdings, margins, position conversion; market data (instruments, quotes, OHLC, LTP, historical, WebSocket ticker).
- **Limitations:** **historical data may not be enabled** in every sandbox; **no** GTT, margin calculation, or MARKET order placement; enforces production-level rate limiting; data is demo, not necessarily live/real.

**Architectural consequence (important):** the sandbox alone cannot supply realistic live data for 9,000 instruments. Our paper-first design therefore uses **production API read-only for live data** + a **local fill simulator** for orders, keeping the sandbox for API-contract validation only. See doc 03 §4 and doc 07.

---

## 8. SDKs & agent-friendliness

- Official **`pykiteconnect`** Python SDK (installable via `uv`/`pip`).
- **Markdown versions of the docs exist, but the URL recipe is `<page>/index.md`, not `<page>.md`.** ✅ *(tested 2026-07-22)*

  ```
  https://kite.trade/docs/connect/v3/websocket.md        → 404
  https://kite.trade/docs/connect/v3/websocket/.md       → 404
  https://kite.trade/docs/connect/v3/websocket/index.md  → 200   ← use this
  https://kite.trade/docs/connect/v3/llms.txt            → 404   (no llms.txt)
  ```

  This matters because the recipe exists specifically to feed pages to coding agents; a wrong one costs every downstream agent a wasted fetch.
- "Agent setup" guide exists for pointing AI coding agents at the SDK.

---

## 9. SEBI retail algo framework (live since 1 April 2026) ⚠️ *new section*

> **This is not a pre-live concern. It is in force now and it constrains Phase 0.**

**✅ Verified against primary sources 2026-07-22.** This section is no longer sourced from commentary:

| Source | Reference | What it settles |
|---|---|---|
| **SEBI circular** | `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013`, **4 Feb 2025** | The framework: registration threshold, family use, tagging, auth requirements, algo categorisation |
| **SEBI circular** | `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/132`, **30 Sep 2025** | Timeline — full applicability **w.e.f. 1 April 2026** |
| **NSE circular** | `NSE/INVG/67858` (Ref. 471/2025), **5 May 2025** | Operational modalities: TOPS mechanics, generic Algo ID, static IP rules |

⚠️ *Still not legal advice, and thresholds are explicitly adjustable by the exchanges "after due notice." Re-verify before live.*

**Timeline (for context):** originally slated for 1 August 2025, deferred to 1 October 2025, then rolled out in phases — broker algo registration by 30 November 2025, mock trading by 3 January 2026, brokers barred from onboarding new API algo clients from 5 January 2026, **full effect for all brokers 1 April 2026.**

### 9.1 What it requires of us

| Requirement | Practical effect on Kestrel |
|---|---|
| **Static IP whitelisting** — order requests from an unregistered IP are **rejected**. ✅ *NSE §A.2: up to **two** IPs — primary plus optional secondary for redundancy.* | The order host needs a **pinned Elastic IP**, and we may register a **second for failover**. Non-order endpoints — WebSocket, positions, order book — are not IP-restricted, so the data plane is unaffected. |
| **A static IP maps to one client at a time**, but may be **shared within one family** (SEBI's definition) with an undertaking to the broker. ✅ *NSE §A.7* | Constrains the order path to one registered host. See §9.5 and doc 10 §3. |
| **Every order placed via API must carry an algo tag — there is no exemption.** ⚠️ *corrected 2026-07-22* | `OrderIntent.algo_id` is **mandatory from day one**, never null. See §9.3. |
| **The 10 OPS threshold decides *which kind* of Algo ID**, not whether one is needed. Below it: a **generic** Algo ID, no strategy-level approval. Above it: **formal registration and testing** of the strategy through the broker. | Our 10/s bucket keeps us in the generic-ID regime — avoiding per-strategy registration, **not** avoiding tagging. |
| **Market protection mandatory on MARKET/SL-M** (§6.1). | New required field on the order payload. |
| **2FA mandatory on every API session login.** | Reinforces operator-in-the-loop daily login. Unattended TOTP automation is a ToS problem. |
| **Open third-party APIs discontinued**; brokers are Principals, algo providers are Agents who must empanel with exchanges. | ✅ **Resolved — we are not an algo provider.** Running an algorithm exclusively for yourself and immediate family on a single account does not trigger empanelment. See §9.4. |

### 9.2 What this changes in the design

1. **Static IP is a Phase 0 prerequisite**, not a Phase 6 checklist item (doc 09, doc 10 §1).
2. **The "buy more API keys to raise the ceiling" escape hatch is largely closed.** The 10/s order limit is per client ID regardless of app count, and the framework pushes toward unique credentials per client. Capacity planning should assume **one key, one budget** (doc 05 §2, doc 11 G-05).
3. **The single-writer execution gateway is now a compliance control**, not only a safety one — it is the thing that guarantees we stay in the generic-ID regime and the single point where the algo tag is stamped on every outbound order.

### 9.3 ⚠️ Algo tagging — corrected 2026-07-22

An earlier version of this document stated that orders below the 10 OPS threshold "are not tagged as algo." **That was wrong, and it was wrong in the direction that produces a compliance gap.**

**The actual rule:**

| | Below 10 OPS | Above 10 OPS |
|---|---|---|
| Algo tag on every order | ✅ **Required** | ✅ Required |
| Kind of identifier | **Generic Algo ID** | Strategy-specific, exchange-issued |
| Formal strategy registration | ❌ Not required | ✅ **Required** — registration + testing through the broker |
| Treated as | "Casual API usage" | Registered algo strategy |

**Every order generated through an API or any automation carries an identifier for auditability. There is no volume below which orders escape the tag.** The threshold governs the *approval burden*, not the *tagging obligation*.

**What this changes in the design:**

1. **`algo_id` is mandatory on every `OrderIntent`, never null** (doc 07 §2). The previous "null below the threshold" semantics would have produced untagged orders — the exact failure the framework exists to prevent.
2. **It cannot be deferred to live migration.** Under the paper/live parity rule (doc 07 §1), the field must be populated and carried through the paper phase or we'd be building a paper-only shortcut that fails on the first live order.
3. **The 10/s bucket is still worth holding** — it keeps us out of per-strategy registration and testing, which is a real and recurring cost. But it buys *less* than previously assumed: staying under it avoids paperwork, not the tag.

**⚠️ Two things to confirm with Zerodha** (this replaces the now-answered "what's the threshold" question):

- **How is the generic Algo ID obtained and attached?** Is it bound to the API key server-side, or must it be passed per order in the payload? This determines whether `algo_id` is config or a per-request field.
- ✅ **Answered (NSE §B.2):** TOPS is **10 OPS per exchange**, on the **calendar clock second**. Kite's is per client ID on its own basis. NSE and BSE are separate budgets; segments within one exchange share one. Our limiter must bucket by wall-clock second and account per exchange — see §9.5.

⚠️ *Sourced from secondary reporting (broker and industry commentary). Confirm against the exchange circular and Zerodha directly before relying on it — but note that the corrected reading is the conservative one, and building to it is safe even if details shift.*

### 9.4 Algo-provider status — resolved: we are not one

✅ **Running an algorithm exclusively for yourself and your immediate family, on a single account, does not classify you as an "algo provider."** Empanelment with the exchanges is not required.

**Why this was the question that mattered most.** The algo-provider path is a different regime entirely: exchange empanelment, a formal relationship with the broker as Principal, and per-strategy approval obligations. Had it applied, it would have reshaped the project from "a system I run" into "a regulated service I operate" — which is the one open item that could have made the whole design the wrong shape rather than merely needing adjustment.

**The boundary.** The exemption tracks **who is being served**, not how sophisticated the system is:

| | Algo provider? |
|---|---|
| You, on your own account | ❌ No |
| **You + immediate family, single account** | ❌ **No** |
| Third parties, or accounts you don't own | ✅ Yes — empanelment required |

**Corroborating detail:** Kite's own static-IP rules permit sharing among **spouse, dependent children, and dependent parents**, and allow multiple Zerodha accounts under one developer profile (§9.1). The IP rule and the algo-provider rule draw the same family boundary — two independent mechanisms agreeing is reasonable evidence the reading is right.

**⚠️ Do not read this as a capacity lever.** Family accounts each have their own Kite client ID and therefore their own 10 orders/second budget. Using a relative's account to raise throughput for *your* strategy would be exactly the pattern G-05 concluded is not available — the exemption is about *whose money is being traded*, not about aggregating rate limits. It does not reopen G-05.

**What this leaves open:** nothing existential. The remaining framework questions (§9.3) are about *how* the generic Algo ID attaches and *how* the two 10-limits are scoped — integration details discovered during Phase 0, not decisions that reshape the design.

**Verbatim, SEBI Feb 2025 §I(c)** — the clause this rests on:

> *"Algos developed by tech-savvy retail investors themselves, using programming knowledge, shall also be registered with the Exchange, through their broker, only if they cross the specified order per second threshold. Further, the same registered Algo shall be permitted to be used by such retail investors for their family (but not for other investors). 'Family' for this purpose would mean self, spouse, dependent children and dependent parents."*

That definition of *family* — **self, spouse, dependent children, dependent parents** — is the same one NSE's static-IP sharing rule points to (§9.5). One definition, two mechanisms.

---

### 9.5 TOPS mechanics — exact, from NSE/INVG/67858

The operational detail the framework circular doesn't give:

| Rule | Source | Design consequence |
|---|---|---|
| TOPS is **10 orders/second**, "initially set" and **adjustable by the exchanges after due notice** | NSE §B.2 | Treat 10 as **config, not a constant**. A tightening would silently break a hard-coded bucket |
| Scope: **the circular is internally inconsistent** — §B.2 says "10 OPS **per exchange**", §F says "per exchange **/segment**" | NSE §B.2 vs §F | ⚠️ **Do not resolve this by picking one.** Budget per *exchange* (the stricter reading) and ask Zerodha. Getting it wrong upward means silently breaching TOPS |
| The broker **may** set a lower client-level limit — *"may vary from client to client not exceeding the current prescribed Threshold"* | NSE §F | ✅ **Zerodha applies the full 10 OPS** for retail algo (owner-confirmed 2026-07-22; matches the Kite FAQ's *"10 OPS per client (trading) account"*). G-39's book sizing stands |
| Measured on the **calendar clock second of the broker server** | NSE §B.2 | **Not a rolling window.** A leaky-bucket or sliding-window limiter can pass 10 in any 1 s window while still putting >10 inside one wall-clock second. Our limiter must bucket by wall-clock second to match |
| Below TOPS: **no registration**, and the exchange issues a **generic Algo ID** | NSE §B.3 | Confirms §9.3 from the primary source |
| Above TOPS: **the broker rejects the excess orders** | NSE §B.5 | Breaching is not a warning — orders are dropped. Combined with the reserved-exit-capacity design (doc 07 §3.3), a burst that breaches TOPS could drop **exit** orders. Our own limiter must bind *before* the broker's |
| Exchanges may specify **restricted order types / contracts** for client algos | NSE §B.4 | A list we don't control can change what's placeable. Instrument eligibility (doc 07 §3) must be data-driven |
| Static IP: **up to two** (primary + secondary), changeable **once per calendar week** | NSE §A.2, §A.6 | Register both up front. ⚠️ **The weekly change limit is an operational trap** — a host migration or IP loss cannot be fixed twice in a week except by exception request |
| Static IP **shareable within one family**, with an undertaking to the broker | NSE §A.7 | Same family definition as §9.4 |

**The calendar-second detail is the one most likely to be implemented wrong.** A standard token bucket smooths across second boundaries by design; the regulation does not. Doc 07 §3.3's limiter must count per wall-clock second, and should target **8/s** rather than 10 to leave margin for clock skew between our host and the broker's server.

✅ **Our client-level limit is the full 10 OPS** — Zerodha applies the regulatory ceiling for retail algo trading rather than a lower per-client value (owner-confirmed 2026-07-22; consistent with the Kite FAQ's *"10 orders per second (OPS) per client (trading) account"* and NSE §B.2).

This mattered because it is an input to G-39's derivation of maximum concurrent positions — $N_{\max} \le r_{\text{exit}} \cdot t_{\text{flatten,target}}$ — not merely a rate ceiling. A lower limit would have roughly halved the safe book size. **The derivation stands: 10/s total, 2/s reserved for exits, ~10 concurrent positions for a 5-second worst-case flatten.**

⚠️ **Read it from config regardless.** NSE may adjust TOPS "after due notice" (§B.2), and a hard-coded 10 would silently breach after a tightening.

**Verbatim, NSE §G** — the clause that settles the tagging question beyond argument:

> *"All algo orders (**Below and above the threshold**) shall be tagged with a unique identifier provided by the Exchange in order to establish audit trail."*

**Also confirmed by NSE §I:** audit trail data must be retained **at least 5 years**; OAuth-only authentication (all other mechanisms discontinued); two-factor authentication on API access.

---

### 9.7 Data licence — what we may and may not do with market data

✅ *Sourced from the [Kite Connect terms](https://kite.trade/terms/) and Zerodha support, 2026-07-22.*

| Clause (verbatim) | Consequence |
|---|---|
| *"live market data obtained via Kite Connect cannot be displayed to **the public at large**"* | **Narrower than feared.** A private dashboard for the operator is not "the public at large." Keeps doc 10 §4's Grafana viable — behind VPN, not on the internet |
| *"scrape, **build databases**, or otherwise create permanent copies of such content, or keep cached copies **with the intent of redistributing**"* | 🔴 **Genuinely ambiguous — and our whole design depends on the answer.** See below |
| *"limited license… for use **within India**"* | **AWS ap-south-1 is a licence requirement, not a latency optimisation.** Moving the host offshore for cost would breach the licence |
| On termination: *"delete any cached or stored content"* | **The research corpus is a leasehold, not an asset.** Years of accumulated ticks must be deleted if the subscription ends |

#### The ambiguity that matters

The clause sits in a list under this stem ✅ *(verbatim from the archived ToS, `regulatory/zerodha/`)*:

> *"Unless expressly permitted by Zerodha or by the applicable laws, you will not… do the following **with content returned from the APIs**:*
> - *Scrape, build databases, or otherwise create permanent copies of such content, or keep cached copies with the intent of redistributing.*
> - *Copy, translate, modify, create a derivative work of, sell, lease, lend, convey, distribute, publicly display, or sublicense to any third party.*
> - *Misrepresent the source or ownership…"*

**Reading the list as a whole helps.** Every sibling bullet is about *moving content to third parties* — sell, lease, distribute, sublicense, misrepresent ownership. That context supports the permissive reading of the first bullet: the concern is redistribution, not private storage. **It does not settle it** — the first bullet is still the only one that names "build databases" independently of a third party.

Does *"with the intent of redistributing"* qualify the whole list, or only *"keep cached copies"*?

| Reading | Meaning | Effect on Kestrel |
|---|---|---|
| **A (strict)** | Building a database of market data is prohibited outright | **The QuestDB tick store and the entire research plane are non-compliant** |
| **B (permissive)** | Prohibited only when done *for redistribution* | We are fine — we redistribute nothing |

**Reading B is much more plausible** — Zerodha sells historical data as part of the ₹500 subscription, the support page frames the concern entirely as *display on other platforms*, and a blanket ban on local storage would make the historical API almost useless. But plausible is not confirmed, and this is precisely the compressed-negation pattern that produced the algo-tagging error (see REVIEWING.md).

**Ask Zerodha explicitly:** *"May we store Kite Connect tick and candle data indefinitely in a local database for our own backtesting and analysis, given we never display or redistribute it?"* Phrase it so a one-word answer is unambiguous.

⚠️ **Do not treat silence as permission.** The design stores every tick for 9,000 instruments indefinitely; if Reading A holds, doc 06's storage plan and the entire static study fleet need rethinking. This is the largest remaining unknown in the compliance area — bigger than the kill switch, because it touches a component we are about to build.

#### Two consequences worth carrying regardless

1. **Pin the region for the right reason.** Doc 03 §5 and doc 10 §3 present ap-south-1 as a latency win. It is *also* a licence term. Record it as a constraint so a future cost optimisation doesn't quietly breach it.
2. **The data moat evaporates with the subscription.** A natural long-term plan is "accumulate years of tick data nobody else has." Under the termination clause that corpus must be deleted if the agreement ends — so it is rented, not owned. Worth knowing before anyone builds strategy on the assumption of a permanent proprietary history.

---

### 9.6 ⚠️ Two consequences nobody had flagged

**1. The exchange holds a kill switch on our Algo ID.**

SEBI §IV(a)(iii) requires exchanges to *"continue to have the ability to use the kill switch for orders emanating from a particular algo id."*

Our kill switch (doc 07 §3) is not the only one. A third party can halt our orders, at a moment we don't choose, for reasons we may not immediately know. The design must treat this as a **failure mode**, not a surprise:

- Orders rejected en masse with no local cause is a **specific diagnosable state**, distinct from a network fault or a token expiry. It needs its own detection and alert.
- **Critically: if the exchange kills our algo ID, we may be unable to place exit orders.** The Position Manager's guarantee (doc 07 §4) assumes the order path is available. An external kill switch violates that assumption, and there is no code-side answer — only an operator runbook. **This belongs in doc 10 §7 and in the risk envelope discussion (G-18).**

**2. An LLM-driven strategy is probably a "black box" algo — which makes the 10 OPS ceiling effectively permanent.**

SEBI §V categorises algos as:
- **White box / Execution algos** — logic disclosed, replicable;
- **Black box** — *"where the user cannot see the internal workings and rationale of the Algo or an Algo where the logic is not known to the user and is not replicable."*

For black box algos the provider must **register as a Research Analyst**, maintain a detailed research report per algo, and — the operative clause — *"in case of any change in the logic governing the algo, register such algo as a fresh algo."*

An LLM's decision process is not replicable in the sense meant here, and **a prompt edit or model upgrade is arguably a change in governing logic**. Under that reading, registering an LLM strategy would mean re-registering on every prompt change. That is operationally impossible for a system designed to iterate on prompts.

**The consequence is strategic, not cosmetic: this design should never plan to exceed 10 OPS.** The ceiling is not merely a rate limit to respect — for an LLM-driven strategy it is close to a permanent boundary, because the registration path on the other side of it is impractical for us specifically.

⚠️ *This is an interpretation, not a ruling.* The categorisation applies most cleanly to *algo providers* serving others, and we are not one (§9.4). But if there is ever a plan to exceed 10 OPS, **this question goes to Zerodha and possibly to a compliance advisor before any engineering.** Recorded so the option is evaluated with its real cost visible.
4. **Order tagging and audit trail acquire a regulatory motive.** Doc 07's per-order attribution to the agent chain was designed for debuggability; it is now also the evidence trail if order provenance is ever questioned.

---

## 10. Summary of consequences (the constraint → design map)

| Constraint | Forces this design choice |
|---|---|
| Rate limits are per-key & shared | Centralized, single-writer I/O components (not scaled by copies) |
| Token expires 6 AM daily; no usable refresh token | Mandatory daily login step; all services handle `403` and re-auth |
| 3 WS conns × 3,000 = 9,000 | Tiered subscription modes; universe fits exactly on one key |
| Quote 1/s, historical 3/s, no daily cap | Poll/backfill are governed batch jobs; agents read local caches |
| Order 10/s, 400/min, 5,000/day | Single execution gateway with a token bucket (mirrored in paper) |
| Instrument tokens reused after expiry | `exchange:tradingsymbol` as the stable key |
| Sandbox data is demo / limited | Paper-first = production read-only data + local fill simulator |
| **Static IP required for order endpoints** | Pinned Elastic IP; order path cannot roam across hosts (doc 10 §3) |
| **Every API order carries an algo tag; >10 OPS ⇒ formal registration** | `algo_id` mandatory on every order; 10/s bucket avoids per-strategy registration (§9.3) |
| **Market protection mandatory on MARKET/SL-M** | `market_protection` field on `OrderIntent` from day one (doc 07 §2) |
| **MIS auto square-off 3:25 / 3:26 PM + ₹50/order** | Simulator must force-close and charge for it (doc 07 §4.4) |
| **2FA on every session login** | Operator-in-the-loop daily mint; no unattended TOTP |
| Historical day-caps undocumented | Backfill discovers caps at runtime rather than hard-coding them |
