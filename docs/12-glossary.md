# 12 — Glossary

**Last updated:** 2026-07-21

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
- **sandbox** — `sandbox.kite.trade`, demo/testing environment (LIMIT-only orders, demo data).

## Order vocabulary

- **Order types:** MARKET, LIMIT, SL (stop-loss), SL-M (stop-loss market).
- **Products:** CNC (delivery equity), NRML (F&O overnight), MIS (intraday), MTF (margin trading facility).
- **Varieties:** regular, AMO (after-market), CO (cover order), iceberg, auction.
- **Iceberg** — a large order auto-sliced into smaller disclosed legs (≤10 slices).

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
- **Hot plane** — the Rust, latency-sensitive layer (data + execution). No LLM.
- **Cognition plane** — the Python/LLM layer (agents). No direct Kite writes.
- **I/O services** — Rust components that talk to Kite; singletons due to rate limits.
- **Static study fleet** — offline batch agents analyzing cached historical data.
- **Live funnel** — screeners → specialists → risk/portfolio manager → execution gateway.
- **Risk/Portfolio Manager** — the single LLM authority that emits (paper) orders.
- **Execution Gateway** — the single Rust writer of orders (paper simulator now, Kite later).
- **Tiered subscription** — assigning instruments to LTP/Quote/Full modes to fit 9,000 across 3 connections.
- **Full-mode promotion list** — instruments upgraded to full-depth streaming for the day.
- **Info-source agents** — news pipeline + macro/central-bank agent; independent of Kite limits.
- **Instruction-source boundary** — the rule that external content is data, never instructions.
- **Paper-first** — validate with a simulated execution backend before any real money.
