# 10 — Prerequisites & Operations

**Last updated:** 2026-07-21

---

## 1. Prerequisites (before any build)

| Prerequisite | Detail | Status |
|---|---|---|
| Zerodha trading account | Active, with 2FA TOTP enabled | ⚠️ confirm |
| Kite Connect app | Registered at the developer portal; `api_key` + `api_secret` issued | ⚠️ confirm |
| **Production subscription** | ~₹2,000/month (historical data now included). **Required** — the free sandbox cannot stream 9,000 live instruments | ⚠️ confirm |
| Sandbox access | `sandbox.kite.trade` with demo creds — for API-contract validation | free |
| AWS ap-south-1 | Host near Zerodha for low RTT | ⚠️ provision |

---

## 2. Daily login (unavoidable operational step)

The `access_token` **expires at 6 AM daily** by regulation; there is no refresh token. So each trading day, before market open, a fresh token must be minted via the login flow (doc 02 §1).

- **Helper to build:** guides/automates the redirect → `request_token` → checksum → `access_token` exchange, then distributes the token to all services (via Redis/secret store).
- **All services** must handle `403 TokenException` by pausing cleanly and resuming when the new token arrives.
- **Automated TOTP login** (e.g., headless browser + TOTP) is technically possible but sits in a **ToS gray area** — flagged as Gap G-12. Default to a semi-manual, operator-in-the-loop mint until ToS is confirmed.

---

## 3. Deployment

- **Region:** AWS Mumbai (ap-south-1) — meaningful, free latency win to Kite.
- **Packaging:** Docker; **Docker Compose** on a single host to start.
- **Services:** Rust (ingester, backfill, quote poller, execution engine), Python (cognition workers, orchestrator), Redis, QuestDB, Prometheus, Grafana, log store (e.g. Loki).
- **Scaling path:** cognition workers can scale horizontally later; the hot-plane I/O services stay singletons by design. If ever split across hosts, rate-limit token buckets must become distributed (Gap G-07).

---

## 4. Observability (non-negotiable for an autonomous trading system)

- **Dashboards (Grafana):** tick rates & parse errors, per-tier instrument counts, WS reconnects, **rate-budget headroom** per bucket, tick-to-cache/QuestDB latency, backfill progress, live P&L/drawdown/exposure, fill quality (slippage, partial-fill rate), kill-switch state, agent throughput & token spend.
- **Alerting:** WS disconnect, 429s (should be zero), token expiry, QuestDB write lag, reconciliation mismatch, daily-loss approaching kill-switch, source-feed outage.
- **Audit trail:** every paper order links to the agent chain + data snapshot that produced it.

---

## 5. Cost model (rough, needs firming — see doc 11)
- Kite Connect subscription: ~₹2,000/month.
- AWS ap-south-1 host + storage: TBD (driven by QuestDB disk growth at tick volume — measure in Phase 1).
- **LLM tokens:** the biggest variable — driven by live agent counts (screeners run continuously). Estimating this caps affordable concurrency (Gap G-11).
- Optional paid news/data feeds: only if justified by measured P&L contribution.

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
- Go/no-go checklist for any live consideration.
