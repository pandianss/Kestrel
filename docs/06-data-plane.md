# 06 — Data Plane Spec (Rust)

**Last updated:** 2026-07-21

The data plane owns everything that reads from Kite's market-data surfaces and turns it into normalized, queryable state. No LLM here.

---

## 1. Components

### 1.1 Instruments Loader
- Fetch the daily gzipped instruments CSV (~08:30 AM) from `/instruments`.
- Parse into an in-memory + persisted map.
- Maintain **two indexes:** `exchange:tradingsymbol` (stable identity) and `instrument_token` (WS subscription).
- Detect expiries/rollovers so a reused `instrument_token` is never mis-attributed.
- Publish "instruments ready" so downstream services can start.

### 1.2 Data Ingester (WebSocket)
- Open **up to 3** connections to `wss://ws.kite.trade`.
- Subscribe up to **3,000 instruments per connection** (9,000 total).
- Parse the binary frame: 2-byte packet count → repeating [2-byte length][packet]; decode by mode (LTP 8B / Quote 44B / Full 184B; index packets 28B/32B).
- Normalize into a canonical `Tick` struct (see §3).
- Fan out: update Redis last-value cache + append to Redis Streams + persist to QuestDB.
- Handle heartbeats; detect stale connections; auto-reconnect with resubscription.

### 1.3 Subscription Manager (tiered modes)
This is the key mechanism for fitting 9,000 instruments into a sane bandwidth/CPU budget.

- **Tiers:**
  - **Full** (184B, 5-level depth) — the active/traded subset (target: a few hundred).
  - **Quote** (44B) — the broad watch.
  - **LTP** (8B) — the long tail.
- **Promotion/demotion:** driven by requests from the cognition plane (e.g., the static study fleet's morning promotion list, or a news catalyst flag) and by intraday activity heuristics (volume/volatility spikes).
- **Placement:** assign instruments across the 3 connections to balance load; keep per-connection ≤ 3,000.
- **Live mode changes** via the `mode` subscription action — no reconnect needed.

**Open (doc 11, Gap G-06):** the exact promotion/demotion policy (thresholds, hysteresis to avoid flapping, max Full-tier size) is undefined and needs specification + tuning.

### 1.4 Quote Poller (REST)
- For instruments **not currently streamed**, or to reconcile/verify, poll `/quote`, `/quote/ohlc`, `/quote/ltp`.
- Governed by a **1 req/s** token bucket; batch up to 500/1000/1000 symbols per call respectively.
- Used sparingly — streaming is the primary path.

### 1.5 Historical Backfill
- Chunked, **resumable** candle download to QuestDB, respecting per-request day caps (doc 02 §5) and a **3 req/s** token bucket.
- Supports `continuous=1` and `oi=1` where relevant.
- Runs as a batch job *before* the static study fleet needs the data.
- Tracks a per-(instrument, interval) high-water mark so restarts resume, not restart.

---

## 2. Rate-budget governance (shared, per-key)

All REST callers (quote poller, backfill, and later the live order path) draw from **centralized token buckets** that mirror Kite's per-key limits:
- Quote bucket: 1/s
- Historical bucket: 3/s
- Order bucket: 10/s, 400/min, 5,000/day

No component may call Kite except through these buckets. A single process owns each bucket; if the system is ever split across hosts, the buckets must become a shared/distributed limiter (flagged: doc 11, Gap G-07).

---

## 3. Canonical data model (draft)

```
Tick {
  instrument_token: u32,
  exchange_ts: i64,        // exchange timestamp (ms)
  recv_ts: i64,            // our receive timestamp (ms) — for latency measurement
  last_price: f64,
  last_qty: u32,
  avg_price: f64,
  volume: u64,
  buy_qty: u64,
  sell_qty: u64,
  ohlc: { open, high, low, close },
  oi: u64,                 // where applicable
  depth: Option<[DepthLevel; 5]> x2  // bids/offers, Full mode only
  mode: enum { Ltp, Quote, Full },
}
```
- Persisted to QuestDB (partitioned by day, symbol).
- Last-value cache in Redis keyed by `instrument_token`.
- Candles (from backfill + rolled-up live) stored per interval.

**Open:** corporate-action adjustment for historical candles (splits/bonus) — Kite's handling must be verified and, if needed, an adjustment layer added (doc 11, Gap G-08).

---

## 4. Reliability requirements

| Concern | Requirement |
|---|---|
| Reconnection | Auto-reconnect each WS connection with full resubscription and mode restoration; bounded backoff |
| Gap detection | Detect missed sequence/heartbeat; log gaps; backfill affected windows |
| No silent drops | Every dropped/late tick is counted and surfaced to metrics |
| Token expiry (403) | On `TokenException`, pause cleanly and resume when a fresh `access_token` is supplied |
| Crash recovery | On restart, reload instruments, resume backfill from high-water marks, re-establish streams |
| Clock discipline | NTP-synced host; record both exchange and receive timestamps; alert on skew |
| Backpressure | If QuestDB/Redis writes lag, prefer cache freshness over history completeness (history is backfillable) |

---

## 5. Metrics to expose (Prometheus)
- Ticks/sec per connection and total; parse errors/sec.
- Per-tier instrument counts; promotions/demotions per minute.
- WS reconnects; heartbeat age per connection.
- Rate-budget headroom (tokens remaining) for each bucket.
- Tick-to-cache and tick-to-QuestDB latency (p50/p99).
- Backfill progress (instruments × intervals complete).

---

## 6. Sizing note (needs validation — doc 11)
9,000 instruments, mixed modes, at Indian-market tick cadence produces a large sustained write volume. QuestDB ingest throughput, disk growth per trading day, and retention policy must be measured early (Phase 1/2) rather than assumed.
