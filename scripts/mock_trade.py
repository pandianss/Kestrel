"""Mock (paper) trade — build a Rs 1,00,000 equal-weight portfolio from the top
of the potential ranking, then mark it to market on later runs.

Honest about what this is (D-16, single-user paper book):
  * PAPER money. No Kite order is placed; nothing here touches the live account.
  * Universe gate: candidates are restricted to NIFTY 500 (a liquid, tradable
    set) so the Rs 1L can't land in the illiquid microcaps that the raw ranking
    floats to the top. Names without a fetchable price are skipped.
  * The ranking currently stands on ONE working pillar (EPS trend) — ROE / D-E
    are blank pending the balance-sheet fix — so treat this as a signal test,
    not advice.
  * Real Zerodha CNC entry costs (kestrel/costs.py) and 0.1%/leg slippage are
    charged, so the cash figure is the true fundable amount.

    python scripts/mock_trade.py                 # open a fresh Rs 1L book
    python scripts/mock_trade.py --capital 100000 --n 10
    python scripts/mock_trade.py --status        # mark the saved book to market
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kestrel.costs import one_way_cost_fraction, regime_on

RANKING = Path("data/baskets_ranking.json")
UNIVERSE = Path("data/snapshots/constituents_nifty500/2026-07-25/data.csv")
PORTFOLIO = Path("data/paper_portfolio.json")
SLIPPAGE = 0.0010   # 0.1% per leg, buy pays up (doc 07 §4.2, conservative)


def _arg(flag: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def last_close(symbol: str) -> float | None:
    """Latest daily close from Yahoo (.NS). Dev/paper price source — no token."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"
           f"?range=5d&interval=1d")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=20))
        closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        return round(float(closes[-1]), 2) if closes else None
    except Exception:      # noqa: BLE001 — unlisted on Yahoo / transient; skip the name
        return None


def _load_ranking() -> list[dict]:
    d = json.loads(RANKING.read_text(encoding="utf-8"))
    items = [i for v in d.values() for i in v if isinstance(i, dict)]
    items.sort(key=lambda x: -float(x.get("potential_score", 0.0)))
    return items


def _liquid_universe() -> set[str]:
    lines = UNIVERSE.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    sym_idx = header.index("Symbol")
    return {ln.split(",")[sym_idx].strip() for ln in lines[1:] if ln.strip()}


def open_book(capital: float, n: int) -> dict:
    ranking = _load_ranking()
    liquid = _liquid_universe()
    # long book: top improving names that are actually tradable
    candidates = [i for i in ranking
                  if i.get("symbol") in liquid and i.get("direction") == "improving"]

    per_slot = capital / n
    cash = capital
    positions = []
    considered = 0
    for item in candidates:
        if len(positions) >= n:
            break
        considered += 1
        sym = item["symbol"]
        px = last_close(sym)
        if px is None:
            continue
        fill = round(px * (1 + SLIPPAGE), 2)          # buy pays up
        qty = int(math.floor(per_slot / fill))
        if qty < 1:
            continue                                   # one share won't fit the slot
        notional = round(qty * fill, 2)
        cost = round(notional * one_way_cost_fraction("buy", regime_on(date.today())), 2)
        if notional + cost > cash:
            qty = int(math.floor((cash) / (fill * (1 + 0.002))))
            if qty < 1:
                continue
            notional = round(qty * fill, 2)
            cost = round(notional * one_way_cost_fraction("buy", regime_on(date.today())), 2)
        cash = round(cash - notional - cost, 2)
        positions.append({
            "symbol": sym, "score": round(float(item["potential_score"]), 3),
            "direction": item.get("direction"), "qty": qty,
            "entry_price": fill, "entry_notional": notional, "entry_cost": cost,
            "peak": fill,          # high-water mark for the trailing stop
        })

    invested = round(sum(p["entry_notional"] for p in positions), 2)
    costs = round(sum(p["entry_cost"] for p in positions), 2)
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "created": now,
        "inception_capital": capital, "inception_date": now, "rebalances": 0,
        "history": [], "exits": [],
        "capital": capital, "n_target": n, "n_filled": len(positions),
        "price_source": "yahoo .NS latest close (paper)",
        "universe_gate": "NIFTY 500 (2026-07-25)",
        "invested": invested, "entry_costs": costs, "cash": cash,
        "positions": positions,
    }


TRAIL = 0.15   # trailing-stop distance (exit if price falls 15% below its peak)


def check_exits(trail: float = TRAIL) -> tuple[dict, int]:
    """Automated EXIT leg (runs daily): mark each position to the latest close,
    ratchet its high-water peak, and sell any name that has fallen `trail` below
    its peak — a trailing stop. Proceeds (net of sell costs) go to cash; the exit
    is logged with its reason and P&L. This is the exit the paper book was missing
    — entries are the ranking, rotation is quarterly, and this protects capital in
    between."""
    bk = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
    sell_frac = one_way_cost_fraction("sell", regime_on(date.today()))
    today = date.today().isoformat()
    kept, exits = [], bk.get("exits", [])
    for p in bk["positions"]:
        px = last_close(p["symbol"])
        if px is None:
            kept.append(p); continue
        peak = max(p.get("peak", p["entry_price"]), px)
        p["peak"] = peak
        stop = peak * (1 - trail)
        if px <= stop:
            proceeds = p["qty"] * px
            cost = round(proceeds * sell_frac, 2)
            bk["cash"] = round(bk["cash"] + proceeds - cost, 2)
            exits.append({
                "date": today, "symbol": p["symbol"], "qty": p["qty"],
                "entry_price": p["entry_price"], "exit_price": round(px, 2),
                "peak": round(peak, 2),
                "pnl": round(proceeds - cost - p["entry_notional"], 2),
                "reason": f"trailing stop (-{trail:.0%} from peak {peak:,.1f})",
            })
        else:
            kept.append(p)
    exited = len(bk["positions"]) - len(kept)
    bk["positions"] = kept
    bk["invested"] = round(sum(q["entry_notional"] for q in kept), 2)
    bk["exits"] = exits[-50:]
    return bk, exited


def rebalance_book(n: int) -> dict:
    """Quarterly rebalance (the backtested cadence): mark the existing book to
    market, liquidate to cash net of sell costs, and re-open the top-N at current
    prices — carrying equity forward so the paper book is a real track record,
    not a fresh Rs 1L each quarter. Sell+buy costs on the full turnover are charged
    (conservative: names that stay are still round-tripped)."""
    old = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
    sell_frac = one_way_cost_fraction("sell", regime_on(date.today()))
    held_value = liq_costs = 0.0
    for p in old["positions"]:
        px = last_close(p["symbol"])
        if px is None:
            px = p["entry_price"]        # can't price -> assume flat at entry
        val = p["qty"] * px
        held_value += val
        liq_costs += val * sell_frac
    equity = round(held_value + old["cash"], 2)                 # mark-to-market equity
    carried = round(equity - liq_costs, 2)                      # cash after liquidation
    new = open_book(carried, n)
    new["inception_capital"] = old.get("inception_capital", old.get("capital"))
    new["inception_date"] = old.get("inception_date", old.get("created"))
    new["rebalances"] = old.get("rebalances", 0) + 1
    new["exits"] = old.get("exits", [])              # carry the exit log forward
    new["history"] = old.get("history", []) + [{
        "date": old.get("created"), "equity": equity, "liquidation_costs": round(liq_costs, 2),
    }]
    return new


def _print_book(bk: dict, marks: dict | None = None) -> None:
    print("=" * 78)
    print(f"  KESTREL PAPER BOOK — Rs {bk['capital']:,.0f} — created {bk['created']}")
    print(f"  universe: {bk['universe_gate']}   price: {bk['price_source']}")
    print("=" * 78)
    if marks is None:
        hdr = f"{'symbol':12}{'score':>6}{'qty':>6}{'entry':>10}{'value':>12}{'wt%':>7}"
        print(hdr); print("-" * len(hdr))
        for p in bk["positions"]:
            wt = 100 * p["entry_notional"] / bk["capital"]
            print(f"{p['symbol']:12}{p['score']:>6.2f}{p['qty']:>6}{p['entry_price']:>10,.2f}"
                  f"{p['entry_notional']:>12,.2f}{wt:>7.1f}")
        print("-" * len(hdr))
        print(f"  invested Rs {bk['invested']:,.2f} + costs Rs {bk['entry_costs']:,.2f} "
              f"→ cash left Rs {bk['cash']:,.2f}   ({bk['n_filled']} positions)")
    else:
        hdr = (f"{'symbol':12}{'qty':>6}{'entry':>10}{'now':>10}{'value':>12}"
               f"{'P&L':>11}{'P&L%':>8}")
        print(hdr); print("-" * len(hdr))
        mv_tot = pnl_tot = 0.0
        for p in bk["positions"]:
            now = marks.get(p["symbol"])
            if now is None:
                print(f"{p['symbol']:12}{p['qty']:>6}{p['entry_price']:>10,.2f}{'—':>10}")
                continue
            mv = p["qty"] * now
            pnl = mv - p["entry_notional"]
            mv_tot += mv; pnl_tot += pnl
            print(f"{p['symbol']:12}{p['qty']:>6}{p['entry_price']:>10,.2f}{now:>10,.2f}"
                  f"{mv:>12,.2f}{pnl:>+11,.2f}{100*pnl/p['entry_notional']:>+7.1f}%")
        print("-" * len(hdr))
        equity = mv_tot + bk["cash"]
        print(f"  holdings Rs {mv_tot:,.2f} + cash Rs {bk['cash']:,.2f} = equity Rs {equity:,.2f}")
        print(f"  unrealised P&L Rs {pnl_tot:+,.2f}   "
              f"total return {100*(equity-bk['capital'])/bk['capital']:+.2f}% vs Rs {bk['capital']:,.0f}")


def main() -> int:
    if "--status" in sys.argv:
        if not PORTFOLIO.exists():
            print("No saved paper book. Run without --status to open one first.")
            return 1
        bk = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
        marks = {p["symbol"]: last_close(p["symbol"]) for p in bk["positions"]}
        _print_book(bk, marks)
        return 0

    n = int(_arg("--n", "10") or 10)
    if "--check-exits" in sys.argv:
        if not PORTFOLIO.exists():
            print("No saved paper book. Open one first (no flags).")
            return 1
        bk, exited = check_exits()
        PORTFOLIO.write_text(json.dumps(bk, indent=2), encoding="utf-8")
        if exited:
            for e in bk["exits"][-exited:]:
                print(f"  EXIT {e['symbol']}: {e['reason']}  P&L Rs {e['pnl']:+,.0f}")
            print(f"{exited} position(s) stopped out → cash Rs {bk['cash']:,.0f}. "
                  f"{len(bk['positions'])} still held.")
        else:
            print(f"No exits triggered. {len(bk['positions'])} position(s) held; "
                  f"trailing stop {TRAIL:.0%} below each peak.")
        return 0

    if "--rebalance" in sys.argv:
        if not PORTFOLIO.exists():
            print("No saved paper book to rebalance. Open one first (no flags).")
            return 1
        print(f"Quarterly rebalance: marking to market and re-selecting top {n}...\n")
        bk = rebalance_book(n)
        PORTFOLIO.write_text(json.dumps(bk, indent=2), encoding="utf-8")
        _print_book(bk)
        incep = bk.get("inception_capital", bk["capital"])
        equity_now = bk["invested"] + bk["cash"]
        print(f"\n  rebalance #{bk.get('rebalances', 0)}  |  since inception Rs {incep:,.0f} "
              f"→ ~Rs {equity_now:,.0f} ({100*(equity_now-incep)/incep:+.1f}%)")
        print(f"Saved → {PORTFOLIO}.")
        return 0

    capital = float(_arg("--capital", "100000") or 100000)
    print(f"Opening a paper book: Rs {capital:,.0f} across up to {n} names "
          f"(fetching latest prices)...\n")
    bk = open_book(capital, n)
    PORTFOLIO.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO.write_text(json.dumps(bk, indent=2), encoding="utf-8")
    _print_book(bk)
    print(f"\nSaved → {PORTFOLIO}.  Rebalance quarterly: python scripts/mock_trade.py --rebalance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
