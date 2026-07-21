# 02 — Kite Connect API Constraints (the load-bearing facts)

**Last updated:** 2026-07-21
**Source:** [Kite Connect v3 docs](https://kite.trade/docs/connect/v3/) (studied 2026-07-21). Values marked ⚠️ should be re-verified against the live docs before implementation, as broker limits change.

> **Why this document exists:** every architectural decision in this repo traces back to a constraint here. The single most important meta-fact: **all rate limits are per API key, not per process.** Spawning more agents that call Kite does not multiply throughput — they share one budget. This forces the I/O-facing layer to be centralized singletons.

---

## 1. Authentication & session

- **Model:** `api_key` + `api_secret` (secret stays server-side only, never in a client).
- **Login flow:** redirect user to Kite login → receive temporary `request_token` at redirect URL → POST `request_token` + `checksum` to `/session/token` → receive `access_token`.
- **Checksum:** `SHA-256(api_key + request_token + api_secret)`.
- **Auth header on every call:** `Authorization: token api_key:access_token`.
- **Token lifetime:** `access_token` **expires at 6:00 AM the next day** (regulatory requirement), or on explicit logout / master-logout from Kite web. ⚠️ This means **a fresh login is required every day** before market open. There is no refresh-token flow.
- **Logout:** `DELETE /session/token` invalidates the session.

**Architectural consequence:** a daily token-minting step is unavoidable (see doc 10 §2). All services must handle `403 TokenException` (session expired) gracefully and block until a new token is provided.

---

## 2. Rate limits (per API key)

| Endpoint category | Limit |
|---|---|
| Quote (`/quote`, `/quote/ohlc`, `/quote/ltp`) | **1 request / second** |
| Historical candle | **3 requests / second** |
| Order placement | **10 requests / second** |
| All other endpoints | **10 requests / second** |

**Order-specific limits:**
- **10 orders / second**, **400 orders / minute**, **5,000 orders / day** per user/API key. ⚠️
- **Max 25 modifications** per order before it must be cancelled and re-submitted.
- Auto-sliced (iceberg) orders: **max 10 slices** per placement.

**Architectural consequence:** exactly one governed component may talk to each rate-limited surface. Order placement is a **single-writer** with a token bucket enforcing 10/s, 400/min, 5,000/day. Quote polling is centralized behind a 1/s bucket. Historical backfill behind a 3/s bucket.

---

## 3. WebSocket streaming

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

  Index instruments (e.g. NIFTY 50) use smaller packets: **28 bytes (quote)**, **32 bytes (full)**.
- **Binary framing:** message = 2-byte packet count, then repeating [2-byte length][packet]. Market depth in Full mode = 10 entries (5 bid + 5 offer), 12 bytes each.
- **Subscription control:** JSON messages with actions `subscribe`, `unsubscribe`, `mode`. Mode can be changed live per instrument.
- **Keepalive:** server sends periodic heartbeats.

**Architectural consequence:** streaming all 9,000 in Full mode is bandwidth- and CPU-heavy. The design uses **tiered modes** (Full for the active few hundred, Quote for the broad watch, LTP for the long tail) with dynamic promotion/demotion. See doc 06.

---

## 4. Market quotes (REST) & instruments

- **`/quote`** (full snapshot): up to **500 instruments / call**. Includes OHLC, OI, bid/ask depth, volume, avg price, circuit limits, last trade.
- **`/quote/ohlc`**: up to **1,000 instruments / call**. Last price + OHLC.
- **`/quote/ltp`**: up to **1,000 instruments / call**. Last price only.
- All subject to the 1 req/sec quote limit. Missing instruments are **absent** from the response map (not null) — presence must be checked.
- **Instruments master dump** (`/instruments`): gzipped CSV of all tradable instruments, **regenerated once daily** (~08:30 AM recommended fetch). Fields include `instrument_token`, `exchange_token`, `tradingsymbol`, `name`, `last_price`, `expiry`, `strike`, `tick_size`, `lot_size`, `instrument_type`, `segment`, `exchange`.
- **Stable identifier:** use `exchange + tradingsymbol`. Numeric `instrument_token` **may be reused** after a derivative expires — do not treat it as permanent.

**Architectural consequence:** fetch and store the instruments master locally each morning; maintain a mapping layer keyed on `exchange:tradingsymbol` for stable identity and on `instrument_token` for WebSocket subscription.

---

## 5. Historical candle data

- **Intervals:** `minute`, `3minute`, `5minute`, `10minute`, `15minute`, `30minute`, `60minute`, `day`.
- **Max date range per request** (⚠️ verify):

  | Interval | Max days / request |
  |---|---|
  | minute | 60 |
  | 3–10 minute | 100 |
  | 15 / 30 minute | 200 |
  | 60 minute | 400 |
  | day | 2,000 |

- **Rate limit:** 3 requests / second. No documented per-day cap on historical calls (other than the rate).
- **Options:** `continuous=1` (stitch expired futures contracts for NFO/MCX), `oi=1` (include Open Interest as a 7th value).
- **Retention:** "several years"; now included with the base Kite Connect subscription. ⚠️

**Architectural consequence:** long lookbacks on fine intervals require many chunked requests, all sharing 3/s. Backfill is a governed, resumable batch job that runs *before* analysis, so the study agents read from local storage, not the live API.

---

## 6. Orders (reference)

- **Order types:** MARKET, LIMIT, SL (stop-loss), SL-M (stop-loss market).
- **Products:** CNC (delivery equity), NRML (F&O carry), MIS (intraday), MTF (margin trading facility).
- **Varieties:** `regular`, `amo` (after-market), `co` (cover order), `iceberg`, `auction`.
- **Operations:** `POST /orders/:variety` (place), `PUT` (modify), `DELETE` (cancel).
- **Statuses:** VALIDATION PENDING, OPEN PENDING, TRIGGER PENDING, OPEN, COMPLETE, CANCELLED, REJECTED (+ interim MODIFY states).
- **Postbacks / webhooks:** Kite can POST order-status updates to a registered URL — the push alternative to polling order state.

---

## 7. Sandbox

- **Host:** `sandbox.kite.trade`. Demo credentials `sandboxdemo` / `sandboxdemo-secret` (safe to commit).
- **Supports:** simulated order placement (**LIMIT only — no MARKET via API**), modify/cancel, order status, positions, holdings, margins, position conversion; market data (instruments, quotes, OHLC, LTP, historical, WebSocket ticker).
- **Limitations:** **historical data may not be enabled** in every sandbox; **no** GTT, margin calculation, or MARKET order placement; enforces production-level rate limiting; data is demo, not necessarily live/real.

**Architectural consequence (important):** the sandbox alone cannot supply realistic live data for 9,000 instruments. Our paper-first design therefore uses **production API read-only for live data** + a **local fill simulator** for orders, keeping the sandbox for API-contract validation only. See doc 03 §4 and doc 07.

---

## 8. SDKs & agent-friendliness

- Official **`pykiteconnect`** Python SDK (installable via `uv`/`pip`).
- Docs are available as **Markdown** (append `.md` to any doc URL) — useful for feeding pages directly to coding agents.
- "Agent setup" guide exists for pointing AI coding agents at the SDK.

---

## 9. Summary of consequences (the constraint → design map)

| Constraint | Forces this design choice |
|---|---|
| Rate limits are per-key & shared | Centralized, single-writer I/O components (not scaled by copies) |
| Token expires 6 AM daily | Mandatory daily login step; all services handle `403` and re-auth |
| 3 WS conns × 3,000 = 9,000 | Tiered subscription modes; universe fits exactly on one key |
| Quote 1/s, historical 3/s | Poll/backfill are governed batch jobs; agents read local caches |
| Order 10/s, 400/min, 5,000/day | Single execution gateway with a token bucket (mirrored in paper) |
| Instrument tokens reused after expiry | `exchange:tradingsymbol` as the stable key |
| Sandbox data is demo / limited | Paper-first = production read-only data + local fill simulator |
