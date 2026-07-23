# 12 — Glossary

**Last updated:** 2026-07-23

For reviewers unfamiliar with Kite/Indian-market vocabulary or this project's terms.

---

## Kite Connect / Zerodha

- **Kite Connect** — Zerodha's REST + WebSocket API for trading, portfolio, and market data.
- **Zerodha** — the Indian broker providing Kite Connect.
- **api_key / api_secret** — app credentials; secret stays server-side.
- **request_token** — temporary token from the login redirect, exchanged for an access token.
- **access_token** — session credential for all authenticated calls; **expires 6 AM next day**.
- **checksum** — `SHA-256(api_key + request_token + api_secret)`, used in the token exchange.
- **instrument_token** — numeric ID for an instrument (used in WebSocket subscriptions); **may be reused after derivative expiry**.
- **tradingsymbol** — human-readable symbol (e.g. `INFY`); `exchange:tradingsymbol` is the stable identity.
- **instruments master / dump** — daily gzipped CSV of all tradable instruments.
- **LTP / Quote / Full** — WebSocket streaming modes (8 / 44 / 184 bytes; Full includes 5-level depth).
- **market depth** — top 5 bid + 5 offer price/quantity levels.
- **OHLC** — Open, High, Low, Close.
- **OI (Open Interest)** — outstanding derivative contracts; a key F&O signal.
- **postback / webhook** — Kite push notification of order-status changes.
- **GTT** — Good-Till-Triggered orders (out of scope for now).
- **sandbox** — `sandbox.kite.trade`, demo/testing environment (LIMIT-only orders, demo data, no margin APIs).
- **refresh_token** — a long-lived read-permission token available only to "approved platforms." Not available to us; the daily login stands.

## Order vocabulary

- **Order types:** MARKET, LIMIT, SL (stop-loss), SL-M (stop-loss market).
- **Products:** CNC (delivery equity), NRML (F&O overnight), MIS (intraday), MTF (margin trading facility).
- **Varieties:** regular, AMO (after-market), CO (cover order), iceberg, auction.
- **Iceberg** — a large order auto-sliced into smaller disclosed legs (≤10 slices).
- **market protection** — a mandatory non-zero cap on how far a MARKET or SL-M order may fill from the reference price. Kite **rejects** orders with market protection `0`; `-1` applies the automatic per-instrument limit. A broker-side guard against a market order sweeping a thin book.
- **auto square-off** — the broker force-closing open intraday (MIS) positions near the close: 3:25 PM equity, 3:26 PM F&O, ₹50 + 18% GST **per order**. Must be modelled or intraday paper P&L is optimistic.
- **SPAN / exposure margin** — the two components of F&O margin. SPAN covers portfolio risk under simulated scenarios; exposure is an additional flat requirement. Portfolio-offsetting and intraday-variable, which is why margin cannot be approximated as a simple percentage.

## Regulatory (SEBI framework, in force since 1 April 2026)

- **SEBI** — Securities and Exchange Board of India, the market regulator.
- **retail algo framework** — SEBI's rules for retail participation in algorithmic trading through broker APIs. Fully effective 1 April 2026 after a phased 2025 rollout.
- **Algo ID** — the identifier every API-placed order must carry for auditability. **There is no volume below which orders are exempt.** Below 10 OPS a *generic* Algo ID suffices; above it, the strategy needs formal exchange registration and a strategy-specific ID.
- **10 OPS threshold** — SEBI's orders-per-second-per-exchange-segment line separating "casual API usage" (generic ID, no approval) from a registered algo strategy (formal registration + testing). Numerically equal to, but scoped differently from, Kite's per-client-ID rate limit.
- **static IP whitelist** — the registered IP address from which order requests must originate. Orders from unwhitelisted addresses are **rejected**. One IP maps to one developer profile. Data endpoints are unaffected.
- **algo provider** — a developer or firm supplying algo order facilities **to others** through a broker's API; must be empanelled with the exchanges. ✅ **Kestrel is not one** — running an algorithm for yourself and immediate family on a single account is exempt (doc 02 §9.4). The boundary is *whose money is traded*, not system sophistication.

## Indian market

- **NSE / BSE** — National / Bombay Stock Exchange.
- **NFO** — NSE Futures & Options segment. **MCX** — commodity exchange.
- **F&O** — Futures and Options.
- **NIFTY 50 / NIFTY 500** — benchmark indices.
- **F&O ban list** — securities barred from fresh F&O positions when OI limits breach.
- **circuit limits** — price bands beyond which trading halts.
- **FII / FPI / DII** — Foreign Institutional / Foreign Portfolio / Domestic Institutional Investors; their flows heavily move Indian indices.
- **STT** — Securities Transaction Tax (part of the cost model).
- **India VIX** — volatility index.
- **muhurat trading** — special ceremonial session (Diwali).

## Central banks / macro

- **RBI** — Reserve Bank of India (domestic central bank).
- **MPC** — RBI's Monetary Policy Committee (rate decisions, ~6/yr).
- **Fed / FOMC** — US Federal Reserve / its rate-setting committee (8/yr); dominant driver of EM flows.
- **ECB / BoJ / PBoC** — European Central Bank / Bank of Japan / People's Bank of China.
- **DXY** — US dollar index. **US 10Y** — 10-year Treasury yield. **USD/INR** — rupee exchange rate.
- **yen carry trade** — borrowing cheap JPY to buy higher-yield assets; unwinds hit EM broadly.

## Kestrel (this project)

- **Kestrel** — the project codename: a multi-agent trading system on Kite Connect. Named for the bird of prey that hovers to scan a wide field, then stoops on a single target — watch broadly, act selectively.
- **Hot plane** — *(term superseded 2026-07-23)* originally the Rust data+execution layer. Under D-02/D-16 only the **execution plane** is Rust (the safety core); the data plane is Python. Prefer "execution safety core" and "data services."
- **Rust safety core** — the execution plane (Execution Gateway, risk engine, Position Manager) — the only Rust in the system, chosen for compile-time correctness on the money-losing-if-wrong path, not speed (D-02).
- **Cognition plane** — the Python/LLM layer (agents). No direct Kite writes.
- **I/O services** — components that talk to Kite; singletons due to rate limits. Order I/O is the Rust execution core; data I/O (ingest, backfill) is Python (D-02).
- **Static study fleet** — offline batch agents analyzing cached historical data.
- **Live funnel** — screeners → specialists → risk/portfolio manager → execution gateway. This is the **entry** path only.
- **Risk/Portfolio Manager** — the single LLM authority that may **open** a position. It cannot be relied on to close one.
- **Position Manager** — the deterministic Rust component that owns every open position and emits exits — stop, target, time, square-off, feed loss — with no LLM in the path.
- **Exit plan** — the stop, target, max holding time, and feed-loss policy attached to every entry. Mandatory; an entry without one is rejected.
- **Entry/exit asymmetry** — the principle that a late entry costs an opportunity while a late exit costs money without bound, so the two get different deciders (doc 03 §2.1).
- **Execution Gateway** — the single Rust writer of orders (paper simulator now, Kite later). Two components may send it intents; only it talks to the broker.
- **Tiered subscription** — assigning instruments to LTP/Quote/Full modes to fit 9,000 across 3 connections.
- **Full-mode promotion list** — instruments upgraded to full-depth streaming for the day.
- **Tick sanity filter** — the gate that rejects or quarantines implausible ticks before they reach the cache or the fill simulator. Suspect ticks are visible but never fill-eligible.
- **Replay harness** — the deterministic tick-replay component used for fill-fidelity validation, look-ahead-safe **deterministic-plane** backtests, regression tests, and incident reproduction. Its determinism holds across the hot plane only; replaying LLM decisions requires cached responses and serves forensics, not validation (G-42).
- **Deterministic-plane backtest** — a conventional backtest of the code half of the system (signals, entries, exits, stops, sizing, costs). Free to re-run, reproducible, walk-forward-able.
- **Forward test** — validation by running on genuinely unseen future data, i.e. paper trading. The **only** validation available to the LLM agents, because the model has already seen historical periods (G-42).
- **Point-in-time data** — reference data (instruments master, ban list, circuit limits) snapshotted as it stood on a given date. Required to avoid survivorship bias; **unrecoverable if not captured daily** (G-43).
- **Info-source agents** — news pipeline + macro/central-bank agent; independent of Kite limits.
- **Instruction-source boundary** — the rule that external content is data, never instructions.
- **Paper-first** — validate with a simulated execution backend before any real money.
- **No destruction of data** — the invariant that data is added to, tiered, or (only where an external obligation requires) deleted with a recorded reason. Never dropped, sampled away, aged out, or overwritten (doc 13, D-15).
- **Append-only** — a store where corrections are new entries referencing what they supersede, never in-place edits. Makes "what did we believe at time T?" answerable. Applies to the P&L ledger.
- **Tiering** — moving older data to cheaper storage classes. Replaces *retention* in this design, because nothing expires.
- **Facts with an expiry date** — externally-owned facts (broker limits, pricing, regulation) that carry a source and verification date because they change without notice. See the README.
