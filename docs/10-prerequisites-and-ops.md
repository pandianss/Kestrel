# 10 — Prerequisites & Operations

**Last updated:** 2026-07-22

---

## 1. Prerequisites (before any build)

| Prerequisite | Detail | Status |
|---|---|---|
| Zerodha trading account | Active, with 2FA TOTP enabled (now mandatory per API session login) | ⚠️ confirm |
| Kite Connect app | Registered at the developer portal; `api_key` + `api_secret` issued | ⚠️ confirm |
| **Production subscription** | **₹500/month, historical candle data included** ✅ *(verified 2026-07-22)*. **Required** — the free sandbox cannot stream 9,000 live instruments | ⚠️ confirm |
| **Static IP, registered** | An Elastic IP in ap-south-1, added to the developer profile's **IP Whitelist**. **Kite rejects order requests from unwhitelisted IPs** (doc 02 §9). One IP ↔ one developer profile | 🔴 **blocker for any order path** |
| **Compliance answers** | ✅ Algo-provider status — **exempt** (self + immediate family, doc 02 §9.4) · ✅ Client-level OPS limit — **10** (doc 02 §9.5) · ✅ Local data storage — **proceeding**, not shared (G-15, ACCEPTED). Remaining: how the generic Algo ID attaches | 🟡 **confirm during Phase 0 wiring** |
| Sandbox access | `sandbox.kite.trade` with demo creds — for API-contract validation | free |
| AWS ap-south-1 | Host near Zerodha for low RTT | ⚠️ provision |

> **Pricing correction (2026-07-22).** An earlier version of this document listed "~₹2,000/month." That was the old combined figure; Zerodha stopped charging the separate ₹2,000 historical-data add-on in February 2025, and Kite Connect is now **₹500/month with historical included**. There is also a free "Personal" tier, which does **not** cover our use (no streaming at this scale). The 4× error mattered only to the cost table, but it is a good illustration of why §5 now carries verification dates.

---

## 2. Daily login (unavoidable operational step)

The `access_token` **expires at 6 AM daily** by regulation; there is no refresh token. So each trading day, before market open, a fresh token must be minted via the login flow (doc 02 §1).

- **Helper to build:** guides/automates the redirect → `request_token` → checksum → `access_token` exchange, then distributes the token to all services (via Redis/secret store).
- **All services** must handle `403 TokenException` by pausing cleanly and resuming when the new token arrives.
- **Automated TOTP login** (e.g., headless browser + TOTP) is technically possible but sits in a **ToS gray area** — flagged as Gap G-12. Default to a semi-manual, operator-in-the-loop mint until ToS is confirmed.

---

## 3. Deployment

- **Region:** AWS Mumbai (ap-south-1) — meaningful, free latency win to Kite, **and a licence requirement**: the Kite ToS grants use *"within India"* only (doc 02 §9.7). This is a constraint, not an optimisation.
- **Packaging:** Docker; **Docker Compose** on a single host to start.
- **Services:** Rust (ingester, backfill, quote poller, position manager, execution gateway), Python (cognition workers, orchestrator), Redis, QuestDB, Prometheus, Grafana, log store (e.g. Loki).
- **Static IP (required):** allocate an **Elastic IP** and register it in the Kite developer profile before any order path runs. Orders from unwhitelisted IPs are rejected. Data endpoints — WebSocket, positions, order book — are not IP-restricted, so the data plane is free to move.
- **Scaling path:** cognition workers can scale horizontally later; the hot-plane I/O services stay singletons by design. If ever split across hosts, rate-limit token buckets must become distributed (Gap G-07).
- **⚠️ The order path cannot roam.** The static-IP binding pins execution to one registered address, and one IP maps to one developer profile. Any future multi-host topology must keep the Execution Gateway on the whitelisted host — this constrains the horizontal-scaling story in a way the earlier version of this document did not account for.

### 3.1 What must survive a restart

| Component | State | Recovery source |
|---|---|---|
| Ingester | Subscriptions + per-instrument modes | Rebuild from the promotion list + instruments master |
| Backfill | Per-(instrument, interval) high-water marks | Persisted marks |
| **Position Manager** | **Open positions + their exit plans** | **Ledger — must be crash-safe and reloaded before the first tick is processed** |
| Execution Gateway | Rate-budget counters (esp. the 5,000/day cap) | Persisted counters; a restart must not silently reset a daily budget |
| Redis streams | Consumer-group offsets | Redis persistence + pending-entries lists |

**The Position Manager row is the dangerous one.** A restart that loses exit plans leaves positions open with no stops and nothing watching them — the exact state §6's kill-switch exists to prevent. Reloading exit plans before processing the first tick is a hard startup ordering requirement, not a nicety.

---

## 4. Observability (non-negotiable for an autonomous trading system)

- **Dashboards (Grafana):** tick rates & parse errors, per-tier instrument counts, WS reconnects, **rate-budget headroom** per bucket, tick-to-cache/QuestDB latency, backfill progress, live P&L/drawdown/exposure, fill quality (slippage, partial-fill rate), kill-switch state, agent throughput & token spend.
- **Alerting:** WS disconnect, 429s (should be zero), token expiry, QuestDB write lag, reconciliation mismatch, daily-loss approaching kill-switch, source-feed outage.
- **Audit trail:** every paper order links to the agent chain + data snapshot that produced it.

---

## 5. Cost model (rough, needs firming — see doc 11)

| Line item | Estimate | Confidence |
|---|---|---|
| Kite Connect subscription | **₹500/month**, historical included | ✅ *verified 2026-07-22* |
| AWS ap-south-1 host | TBD — modest; the workload is ~2 Mbps and single-host | 🟡 estimate in Phase 1 |
| Storage | ~5 GB/day raw before compression (doc 06 §6) → retention policy drives cost | 🟡 measure in Phase 1 |
| Elastic IP | Negligible, but **required** (§1) | ✅ |
| **LLM tokens** | **≈ $28,000/yr ≈ ₹2 lakh/month** at target fleet size | 🟠 *modelled 2026-07-22, unmeasured* |
| Paid news/data feeds | Optional; only if justified by measured P&L contribution | — |

### 5.1 The cost model in one line

**LLM spend is roughly 400× the broker subscription.** ₹500/month to Zerodha; ~₹2,00,000/month to Anthropic at the target fleet. Every other line in this table is a rounding error, and **cost control in this project means token control.**

Full derivation, assumptions, and sensitivity: **doc 08 §8**. Headline figures:

| Fleet configuration | Per year |
|---|---|
| Naive screeners (LLM reads the raw universe) | ~$59,000 just for screeners |
| **Target design** (deterministic pre-filter, 10 screeners @ 30 s, Fable manager) | **≈ $28,000** |
| Lean viable (6 screeners @ 60 s, Sonnet manager, cached prefix) | **≈ $8–10,000** |

Three things worth carrying into planning:

- **The biggest lever is architectural, not commercial.** Pre-filtering deterministically before the LLM sees anything is a **5× saving on the largest line** and costs nothing — it is strictly better design. Screeners must never receive the raw universe (doc 08 §8.2).
- **The singleton manager is 36% of the bill.** Fable's always-on thinking bills as output at $50/1M, so one agent outcosts 400 specialist calls. Being a singleton does not make a component cheap.
- **This caps fleet size, which is what G-11 existed to determine.** ~15–25 live agents is affordable *only* with the pre-filter. Without it, the same roster runs ~$76,000/year.

⚠️ **Modelled, not measured.** Every token count is an assumption; the estimate is order-of-magnitude. Phase 5 must run one session with per-tier token accounting and reconcile (doc 08 §8.4).

⚠️ Broker pricing has changed twice in recent memory (historical add-on removed February 2025). Re-verify at the cadence in the README's *Facts with an expiry date* table.

---

## 6. Security posture

- **Secrets:** `api_secret` and `access_token` are **server-side only**, never in code, client, or logs. Use a secret manager / environment injection.
- **Single-writer to orders:** enforced structurally (doc 07); no agent has order-placing credentials.
- **Instruction-source boundary:** all external content (news, scraped pages, central-bank text) is treated as **data, never instructions**; extracted to structured fields before any agent reasons over it (doc 08 §6). This is the primary defense against prompt injection in an autonomous loop.
- **Least privilege:** the data-only production token path is read-only in the paper phase; order credentials are introduced only at live migration behind the go/no-go.
- **Network:** restrict inbound; the postback/webhook endpoint (live phase) must validate authenticity and be treated as untrusted input.
- **Kill-switch:** operable manually and automatically; tested in Phase 6.

---

## 7. Runbooks to write (Phase 6)
- Morning start-up (login, instruments load, stream health check).
- WS disconnect / reconnect verification.
- Token-expiry-mid-session recovery.
- Kill-switch activation & post-mortem.
- Backfill restart.
- **Restart with open positions** — the exit-plan reload ordering (§3.1) and how to verify every position is being watched again before resuming.
- **Cognition plane down during market hours** — confirm the exit path is still live, decide whether to flatten or hold.
- **Redis memory pressure / stream trim under consumer lag** — how to detect data loss and what to replay.
- Go/no-go checklist for any live consideration.

---

## 8. Security posture — additions from the 2026-07-22 review

The §6 posture stands. Two additions:

- **The static IP is now a security boundary as well as a compliance one.** It is the only network-level control preventing a leaked `access_token` from being used to place orders from elsewhere. Treat the whitelisted host accordingly: minimal inbound, no shared credentials, and rotate immediately on any suspicion.
- **Prompt-injection defence needs a test, not just a policy** (G-24). The instruction-source boundary in doc 08 §6 is stated as a rule; Phase 6 must include adversarial inputs — a news item crafted to look like an instruction, an announcement containing text that impersonates an operator message — and demonstrate that none of them changes an action. A policy that has never been attacked is an assumption.
