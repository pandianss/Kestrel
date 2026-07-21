# 07 — Execution Plane Spec (Rust)

**Last updated:** 2026-07-21

The execution plane is the **single writer** of orders and the guardian of risk. In the paper-first build it writes to a local fill simulator; the same interface later writes to Kite's order API for live trading.

---

## 1. Design goals
- **Single-writer discipline:** exactly one component ever emits orders. No agent bypasses it.
- **Paper/live parity:** identical interface, identical rate budgets, identical risk limits in both modes. No "paper-only" shortcuts.
- **Realistic paper fills:** simulate against the *live* tick stream so paper P&L is meaningful.
- **Deterministic safety:** risk limits and kill-switches are code, not LLM judgement.

---

## 2. Order interface (mode-agnostic)

```
OrderIntent {                      OrderAck {
  client_order_id,                   client_order_id,
  exchange, tradingsymbol,           broker_order_id | sim_order_id,
  side (BUY/SELL),                   status,            // ACCEPTED/REJECTED/...
  qty,                               reason,
  order_type,  // LIMIT (paper), + others live   fills: [ {qty, price, ts} ],
  product,     // CNC/NRML/MIS                    remaining_qty,
  limit_price,                       ts,
  variety,     // regular/iceberg/...          }
  risk_context // sizing basis, stop, source chain
}
```

- The **risk/portfolio manager** (cognition plane) produces `OrderIntent`s onto the execution stream.
- The execution engine consumes them, validates, routes to the active backend (simulator | Kite), and emits `OrderAck`s back.
- **Note:** the sandbox and this simulator support **LIMIT only** (no MARKET). Strategies must be expressed with limit/stop-limit orders in the paper phase.

---

## 3. Risk engine (deterministic, pre-trade)

Every `OrderIntent` passes hard checks *before* any fill:

| Check | Example limit (draft — needs owner input, doc 11) |
|---|---|
| Per-order notional cap | ≤ X% of paper capital |
| Per-instrument position cap | ≤ Y units / Z% of capital |
| Portfolio gross/net exposure cap | ≤ gross G%, net N% |
| Daily loss limit (kill-switch) | halt new entries if day P&L < −L% |
| Max open orders / positions | ≤ counts |
| Order rate budget | mirror 10/s, 400/min, 5,000/day |
| Event-window de-risk | reduce size / block new entries around scheduled central-bank events (from macro agent) |
| Instrument eligibility | tradable, not in F&O ban, within circuit limits |

- **Reject** or **resize** intents that violate a check; emit a rejection `OrderAck` with reason.
- **Kill-switch:** a single deterministic trigger (daily loss, data outage, reconciliation mismatch, or manual) that flattens/halts. Must be testable and observable.

---

## 4. Fill simulator (paper backend)

Matches paper LIMIT orders against the live tick stream:

- **Fill rule:** a BUY LIMIT fills when the live price (and/or offer depth) trades at/through the limit; symmetric for SELL. Use Full-mode depth where available for realism.
- **Models:** configurable slippage, latency (simulate the delay a real order would experience), and **partial fills** against available depth/volume.
- **Queue position (optional, later):** approximate exchange queue priority for limit orders resting at a price.
- **Outputs:** `OrderAck` with fills → updates positions → updates the P&L ledger.

**Fidelity is a first-class concern:** an over-optimistic simulator invalidates the whole paper exercise. The simulator's assumptions (instant fill? full depth? zero slippage?) must be explicit, conservative by default, and validated by replay (doc 11, Gap G-09).

---

## 5. P&L ledger & position state
- Authoritative record of paper positions, realized/unrealized P&L, fees/taxes model (STT, brokerage, exchange charges — Indian cost model), and per-trade attribution back to the agent chain that produced it.
- Marked-to-market continuously from the live cache.
- Persisted (crash-safe) and exposed to Grafana.
- **Reconciliation:** paper position state is periodically reconciled against the ledger; any mismatch trips the kill-switch.

---

## 6. Live migration (later, behind go/no-go)
Flipping to live = change the execution backend from `simulator` to `kite_orders` behind the same `OrderIntent`/`OrderAck` interface, and:
- Route through the real order token bucket (10/s, 400/min, 5,000/day).
- Subscribe to **postbacks/webhooks** for authoritative order-status updates (instead of simulator acks).
- Enable real fills, real fees, real slippage.
- **Nothing upstream changes** — screeners, specialists, and the risk manager are unaware of the backend.
- **Gated by:** doc 09 Phase 6 review + the regulatory checks in doc 11 (Gap G-02, SEBI algo framework).

---

## 7. Metrics to expose
- Intents received / accepted / rejected (by reason).
- Fill latency, partial-fill rate, average slippage (sim).
- Order-budget headroom (10/s, 400/min, 5,000/day).
- Live paper P&L, drawdown, open exposure (gross/net).
- Kill-switch state and trigger history.
- Reconciliation status.
