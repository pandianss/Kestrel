# 04 — Technology Stack

**Last updated:** 2026-07-21
**Confirmed decision:** Rust (hot plane) + Python (cognition plane).

---

## 1. Languages / runtimes

### Rust — hot plane
**Why:** the 9,000-instrument Full-depth tick stream is a serious parsing/throughput workload; the execution engine must be deterministic and low-latency. Rust gives predictable performance without GC pauses, strong concurrency, and a single deployable binary.

Candidate crates (to confirm at build time):
- WebSocket: `tokio-tungstenite` (async) on `tokio`.
- Binary parsing: `bytes` / `nom` or hand-rolled zero-copy parsing.
- Redis: `redis` / `fred`.
- QuestDB ingest: line protocol (ILP) client.
- Serialization for the bus: `serde` + `rmp-serde` (MessagePack) or JSON for debuggability.

### Python — cognition plane
**Why:** the agent ecosystem (LangGraph, Anthropic SDK) and the official `pykiteconnect` SDK live here; iteration speed matters for agent logic. Python is *not* on the latency-critical path.

Candidate libraries:
- Orchestration: **LangGraph** (stateful, graph-based multi-agent control flow).
- LLM: **Anthropic SDK** (Claude — tiered, see §4).
- Kite (non-hot-path use, research): `pykiteconnect`.
- Research/backtest: `polars` (fast dataframes), `duckdb`, `vectorbt`/custom event-driven backtester.
- Redis: `redis-py`.

## 2. The Rust ↔ Python boundary

- **Start with Redis** (Streams + last-value cache) as the contract. Clean separation, language-agnostic, easy to inspect and debug, and lets the two planes deploy/scale independently.
- **Optimize later only if profiling demands it:**
  - **PyO3** — compile a Rust module importable by Python for the hottest read paths (e.g., tick decode) to avoid serialization overhead.
  - **Shared-memory ring buffer** — for the absolute lowest-latency hand-off if Redis round-trips become the bottleneck.
- **Decision rule:** do not pre-optimize the boundary. Redis first; measure; upgrade the specific hot path that profiling flags.

## 3. Data stores

| Store | Role | Why |
|---|---|---|
| **Redis** | Hot last-value cache + event bus (Streams/pub-sub) | One system for cache + messaging; sub-ms; simple to start |
| **QuestDB** | Live tick capture + candle history (time-series) | Purpose-built for high-ingest market data; SQL; fast time queries |
| **DuckDB + Parquet** | Research/backtest analytical store | Blazing on columnar Parquet; zero-server; ideal for the static study fleet |

**Alternative considered:** TimescaleDB (Postgres) instead of QuestDB — gives relational + time-series in one and is a fine substitute if we want Postgres tooling; QuestDB chosen for ingest speed at 9,000-instrument tick volume. ClickHouse considered for heavy analytics but adds ops weight; DuckDB covers research needs without a server. **Open:** validate QuestDB ingest throughput at target tick volume (doc 11).

## 4. LLM model tiering (Claude)

Cost and latency are managed by matching model strength to job frequency/stakes:

| Tier | Model (current family) | Used by | Rationale |
|---|---|---|---|
| **Cheap/fast** | Claude Haiku | Live screeners (high frequency, wide fan-out) | Thousands of cheap judgements/scans; must be fast and low-cost |
| **Mid** | Claude Sonnet | Specialists, news classification/sentiment, static study agents | Deeper reasoning on the filtered set |
| **Strong** | Claude Fable | Risk/portfolio manager, macro impact analyst (high-salience only) | Rare, high-stakes judgement where quality dominates cost |

**Principle:** the funnel narrows *volume* as it climbs *model strength* — many cheap calls at the bottom, one strong call at the top. Exact model IDs to be pinned at build time (see the Claude API reference).

## 5. Infrastructure / ops

| Concern | Choice |
|---|---|
| Region | AWS Mumbai (ap-south-1) — near Zerodha, low RTT to Kite |
| Packaging | Docker; Docker Compose to start (single host) |
| Metrics | Prometheus |
| Dashboards | Grafana (system health, tick rates, P&L, fill quality, rate-budget headroom) |
| Logs | Structured JSON logs (per-service), shipped to a central store (e.g. Loki) |
| Secrets | Environment/secret manager; `api_secret` and `access_token` never in code or client (doc 10 §6) |
| CI | Build/test both planes; type-check Python; `cargo test`/`clippy` for Rust |

## 6. Why not X (brief)

- **Python-only hot path:** viable for a smaller universe, but 9,000 Full-depth instruments is exactly where Python's parsing/GC overhead starts to hurt; Rust was chosen deliberately for this scale.
- **C++/FPGA/co-location:** unjustified — Kite is a throttled retail feed; the latency floor is Kite's, not ours. Rust captures ~all the achievable speed at a fraction of the complexity.
- **Kafka for the bus:** heavier than needed at single-host start; Redis Streams (or NATS JetStream) is leaner. Revisit if we outgrow a single host.

## 7. Stack-level open items (see doc 11)
- Confirm QuestDB ingest throughput and storage sizing at 9,000-instrument tick volume.
- Confirm LangGraph fits the live latency budget for the screener→specialist→manager funnel (or whether a lighter custom orchestrator is better for the live path, keeping LangGraph for static study).
- Pin exact Claude model IDs and estimate monthly token spend under target agent counts.
