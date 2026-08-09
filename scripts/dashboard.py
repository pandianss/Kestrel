"""Kestrel research dashboard — LIVE, on-host (D-18, G-15: data never leaves the PC).

Reworked to be fast and current instead of a stale 3.6 MB snapshot. The old
generator recomputed every trend and relation tree (~60 s) into one static file
that nobody regenerated often — so it always looked stale. This version reads
only PRE-COMPUTED artifacts (the ranking JSON, the paper book, the saved backtest)
and the OFFLINE Kite price cache — no per-request network, no heavy recompute —
so it renders in well under a second. The server renders it LIVE on every request
and the page auto-refreshes, so what you see is always current.

    python scripts/dashboard.py        # writes dashboard.html (static fallback)

The server imports gather_live()/render_live() and renders per request.
"""
from __future__ import annotations

import html
import json
import pickle
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RANKING = REPO / "data/baskets_ranking.json"
PORTFOLIO = REPO / "data/paper_portfolio.json"
BACKTEST = REPO / "data/backtest_results.json"
KITE_CACHE = REPO / "data/cache/kite"
FUND_DIR = REPO / "data/fundamentals"
PID_FILE = REPO / "logs/fundamentals_worker.pid"
TOKEN_PATH = REPO / "data/secrets/kite_token.json"
OUT = REPO / "dashboard.html"


# ---- cheap data access (no recompute, no network) -----------------------

def _mtime(p: Path) -> datetime | None:
    return datetime.fromtimestamp(p.stat().st_mtime) if p.exists() else None


def _age(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    secs = (datetime.now() - dt).total_seconds()
    if secs < 90:
        return f"{int(secs)}s ago"
    if secs < 5400:
        return f"{int(secs // 60)}m ago"
    if secs < 172800:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _latest_close(symbol: str) -> float | None:
    f = KITE_CACHE / f"{symbol}_day.pkl"
    if not f.exists():
        return None
    try:
        df = pickle.loads(f.read_bytes())
        c = df["close"].dropna()
        return float(c.iloc[-1]) if len(c) else None
    except Exception:
        return None


def _latest_price_date() -> str | None:
    """Date of the most recent candle across the cache (read one recent file)."""
    files = sorted(KITE_CACHE.glob("*_day.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[:5]:
        try:
            df = pickle.loads(f.read_bytes())
            return df.index[-1].date().isoformat()
        except Exception:
            continue
    return None


def _latest_fundamental_quarter() -> str | None:
    """Newest period_end across a few recently-updated symbol files (cheap peek)."""
    files = sorted(FUND_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    best = None
    for f in files[:40]:
        try:
            last = f.read_text(encoding="utf-8").strip().splitlines()[-1]
            pe = json.loads(last).get("period_end")
            if pe and (best is None or pe > best):
                best = pe
        except Exception:
            continue
    return best


def _worker_alive() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        return False
    import os
    import subprocess
    if os.name == "nt":
        try:
            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], encoding="utf-8", stderr=subprocess.DEVNULL)
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _token_valid() -> bool:
    try:
        from kestrel.kite.tokenstore import FileTokenStore
        tok = FileTokenStore(TOKEN_PATH).load()
        return bool(tok and tok.is_valid(datetime.now(timezone.utc)))
    except Exception:
        return False


def gather_live(status: dict | None = None) -> dict:
    """Assemble the dashboard state from precomputed artifacts + cheap status.
    `status` may be passed by the server (its get_system_status) to avoid a second
    process probe; otherwise it is computed here."""
    now = datetime.now()
    st: dict = {"generated": now.strftime("%Y-%m-%d %H:%M:%S"),
                "generated_epoch": now.timestamp()}

    # Ranking (tradeable leaderboard)
    ranking, tradeable, total = [], 0, 0
    if RANKING.exists():
        try:
            d = json.loads(RANKING.read_text(encoding="utf-8"))
            items = [i for v in d.values() for i in v if isinstance(i, dict)]
            total = len(items)
            trade = [i for i in items if i.get("tradeable")]
            tradeable = len(trade)
            trade.sort(key=lambda x: -float(x.get("potential_score", 0)))
            ranking = trade[:25]
        except Exception:
            pass
    st["ranking"] = ranking
    st["ranking_counts"] = (tradeable, total)
    st["ranking_at"] = _mtime(RANKING)

    # Paper book, marked to market on the offline Kite cache
    book = None
    if PORTFOLIO.exists():
        try:
            bk = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
            rows, mv = [], 0.0
            for p in bk.get("positions", []):
                now_px = _latest_close(p["symbol"])
                val = (p["qty"] * now_px) if now_px else p["entry_notional"]
                mv += val
                rows.append({**p, "now_px": now_px, "value": val,
                             "pnl": val - p["entry_notional"]})
            equity = mv + bk.get("cash", 0)
            incep = bk.get("inception_capital", bk.get("capital", 0)) or 1
            book = {"rows": rows, "equity": equity, "cash": bk.get("cash", 0),
                    "inception": incep, "ret": (equity - incep) / incep,
                    "rebalances": bk.get("rebalances", 0), "created": bk.get("created"),
                    "exits": bk.get("exits", [])}
        except Exception:
            pass
    st["book"] = book

    # Backtest
    st["backtest"] = json.loads(BACKTEST.read_text(encoding="utf-8")) if BACKTEST.exists() else None

    # Freshness + pipeline status
    st["fund_latest_q"] = _latest_fundamental_quarter()
    st["price_latest"] = _latest_price_date()
    st["counts"] = {
        "fundamentals": len(list(FUND_DIR.glob("*.jsonl"))) if FUND_DIR.exists() else 0,
        "prices": len(list(KITE_CACHE.glob("*_day.pkl"))) if KITE_CACHE.exists() else 0,
    }
    if status:   # nested shape from server.get_system_status()
        st["worker_alive"] = (status.get("worker") or {}).get("status") == "RUNNING"
        st["token_valid"] = bool((status.get("token") or {}).get("valid"))
    else:
        st["worker_alive"] = _worker_alive()
        st["token_valid"] = _token_valid()
    return st


# ---- rendering ----------------------------------------------------------

def _svg_equity(bt: dict) -> str:
    dates = bt["dates"]
    s = bt["strategy_equity"]
    b = bt["benchmark_equity"]
    n = len(dates)
    if n < 2:
        return "<p class='muted'>No backtest series.</p>"
    W, H, pad = 720, 300, 34
    lo = min(min(s), min(b))
    hi = max(max(s), max(b))
    import math
    lo_l, hi_l = math.log(lo), math.log(hi)   # log scale (6x growth reads better)

    def pt(i, v):
        x = pad + (W - 2 * pad) * i / (n - 1)
        y = H - pad - (H - 2 * pad) * (math.log(v) - lo_l) / (hi_l - lo_l or 1)
        return f"{x:.1f},{y:.1f}"
    sp = " ".join(pt(i, v) for i, v in enumerate(s))
    bp = " ".join(pt(i, v) for i, v in enumerate(b))
    # year gridlines
    ticks = []
    for i, dt in enumerate(dates):
        if dt.endswith("-01") or dt.endswith("-12"):
            x = pad + (W - 2 * pad) * i / (n - 1)
            ticks.append(f'<line x1="{x:.0f}" y1="{pad}" x2="{x:.0f}" y2="{H-pad}" class="grid"/>'
                         f'<text x="{x:.0f}" y="{H-pad+16}" class="axis" text-anchor="middle">{dt[:4]}</text>')
    yl = []
    for v in (lo, (lo * hi) ** 0.5, hi):
        y = H - pad - (H - 2 * pad) * (math.log(v) - lo_l) / (hi_l - lo_l or 1)
        yl.append(f'<text x="{pad-6}" y="{y+3:.0f}" class="axis" text-anchor="end">{v:.1f}x</text>')
    return f'''<svg viewBox="0 0 {W} {H}" class="equity" role="img" aria-label="equity curve">
      {"".join(ticks)}{"".join(yl)}
      <polyline points="{bp}" class="line-bench"/>
      <polyline points="{sp}" class="line-strat"/>
    </svg>'''


def _badge(label: str, value: str, ok: bool | None = None) -> str:
    cls = "" if ok is None else (" ok" if ok else " bad")
    return f'<div class="badge{cls}"><span class="blabel">{label}</span><span class="bval">{html.escape(value)}</span></div>'


def _pipeline(st: dict) -> str:
    b = [
        _badge("Fundamentals worker", "running" if st["worker_alive"] else "stopped", st["worker_alive"]),
        _badge("Kite token", "valid" if st["token_valid"] else "expired (re-mint AM)", st["token_valid"]),
        _badge("Latest quarter", st["fund_latest_q"] or "—"),
        _badge("Latest price", st["price_latest"] or "—"),
        _badge("Ranking built", _age(st["ranking_at"])),
        _badge("Tradeable / total", f'{st["ranking_counts"][0]:,} / {st["ranking_counts"][1]:,}'),
    ]
    return f'<div class="badges">{"".join(b)}</div>'


def _stage(name: str, ok: bool, lines: list[str]) -> str:
    dot = "up" if ok else "down"
    body = "".join(f'<div class="sline">{html.escape(x)}</div>' for x in lines)
    return (f'<div class="stage"><div class="shead"><span class="sdot {dot}">●</span>'
            f'<span class="sname">{html.escape(name)}</span></div>{body}</div>')


def _pipeline_detail(st: dict) -> str:
    c = st.get("counts", {})
    stages = [
        _stage("Fundamentals", st["worker_alive"], [
            f'worker {"running" if st["worker_alive"] else "stopped"} · latest quarter {st["fund_latest_q"] or "—"}',
            f'{c.get("fundamentals", 0):,} companies · source: NSE results (legacy + Integrated Filing)',
        ]),
        _stage("Prices", bool(st["price_latest"]), [
            f'latest candle {st["price_latest"] or "—"} · {c.get("prices", 0):,} instruments',
            f'source: Kite daily OHLCV{" · token valid" if st["token_valid"] else " · token expired (re-mint AM)"}',
        ]),
        _stage("Ranking", st["ranking_counts"][0] > 0, [
            f'built {_age(st["ranking_at"])} · {st["ranking_counts"][0]:,} tradeable / {st["ranking_counts"][1]:,} total',
            'score: 5-pillar (EPS trend · ROE · D/E · promoter · sector-relative valuation)',
        ]),
        _stage("Paper book", st["book"] is not None, [
            (f'equity ₹{st["book"]["equity"]:,.0f} · {st["book"]["ret"]*100:+.1f}% since inception'
             if st["book"] else 'not opened') + (f' · rebalance #{st["book"]["rebalances"]}' if st["book"] else ''),
            'quarterly rebalance + daily stop/target exit checks',
        ]),
    ]
    return (f'<p class="muted">The on-host data plane, most-upstream first. Everything stays local (G-15).</p>'
            f'<div class="stages">{"".join(stages)}</div>')


def _controls(st: dict) -> str:
    tok = "valid" if st["token_valid"] else "expired"
    tcls = "ok" if st["token_valid"] else "bad"
    def b(action, label, danger=False):
        return f'<button class="btn{" danger" if danger else ""}" onclick="post(\'{action}\')">{label}</button>'
    return f'''<p class="muted">Run the pipeline by hand. Jobs launch in the background; the page reflects results on its next refresh (auto-refresh pauses while this tab is open).</p>
      <div class="ctlgrid">
        <div class="ctlcard"><h4>Session <span class="badge {tcls}" style="margin-left:6px"><span class="bval">{tok}</span></span></h4>
          {b("/api/login/start", "Launch login window")}
          <div class="mintrow"><input id="redir" placeholder="paste Kite redirect URL / request_token">
            <button class="btn" onclick="mint()">Mint token</button></div>
          <div class="hint">Login needs your Zerodha 2FA in a browser (G-12); the token expires ~06:00 IST daily.</div>
        </div>
        <div class="ctlcard"><h4>Data workers</h4>
          {b("/api/worker/start", "Start fundamentals worker")}{b("/api/worker/stop", "Stop", True)}
          {b("/api/history/start", "Harvest prices (Kite)")}{b("/api/relations/harvest", "Harvest relations")}
        </div>
        <div class="ctlcard"><h4>Signal &amp; book</h4>
          {b("/api/ranking/refresh", "Refresh ranking")}{b("/api/backtest/run", "Run backtest")}
          {b("/api/book/rebalance", "Rebalance book")}{b("/api/book/exits", "Check exits")}
        </div>
      </div>
      <div id="ctlmsg" class="ctlmsg" role="status"></div>'''


def _leaderboard(st: dict) -> str:
    rows = []
    for i in st["ranking"]:
        sc = float(i.get("potential_score", 0))
        roe = i.get("latest_roe"); d2e = i.get("latest_d2e")
        dirn = i.get("direction", "")
        dc = "up" if dirn == "improving" else "down" if dirn == "declining" else "flat"
        roe_c = f"{roe*100:.0f}%" if isinstance(roe, (int, float)) else "—"
        d2e_c = f"{d2e:.2f}" if isinstance(d2e, (int, float)) else "—"
        rows.append(
            f'<tr><td class="sym">{html.escape(str(i.get("symbol", "?")))}</td>'
            f'<td class="barcell"><div class="bar"><span style="width:{sc*100:.1f}%"></span></div></td>'
            f'<td class="num">{sc*100:.0f}</td>'
            f'<td class="num">{roe_c}</td><td class="num">{d2e_c}</td>'
            f'<td class="{dc}">{html.escape(dirn)}</td></tr>')
    return f'''<p class="muted">Top by four/five-pillar potential — tradeable (NIFTY 500, valuation-active) only; the set the paper book trades.</p>
      <table class="grid"><thead><tr><th>Symbol</th><th>Score</th><th></th><th>ROE</th><th>D/E</th><th>Trend</th></tr></thead>
      <tbody>{"".join(rows)}</tbody></table>'''


def _paper(st: dict) -> str:
    bk = st["book"]
    if not bk:
        return '<p class="muted">No paper book yet. Run <code>python scripts/mock_trade.py</code>.</p>'
    rows = []
    for p in bk["rows"]:
        pnl = p["pnl"]; pct = 100 * pnl / p["entry_notional"] if p["entry_notional"] else 0
        cls = "up" if pnl >= 0 else "down"
        now_px = f'{p["now_px"]:,.1f}' if p["now_px"] else "—"
        peak = p.get("peak", p["entry_price"])
        stop = peak * (1 - 0.15)
        near = p["now_px"] and p["now_px"] <= stop * 1.05   # within 5% of the stop
        rows.append(f'''<tr><td class="sym">{html.escape(p["symbol"])}</td><td class="num">{p["qty"]}</td>
          <td class="num">{p["entry_price"]:,.1f}</td><td class="num">{now_px}</td>
          <td class="num {'down' if near else 'muted-c'}">{stop:,.1f}</td>
          <td class="num">{p["value"]:,.0f}</td><td class="num {cls}">{pnl:+,.0f} ({pct:+.1f}%)</td></tr>''')
    rc = f'· rebalance #{bk["rebalances"]}' if bk["rebalances"] else ""
    tot_cls = "up" if bk["ret"] >= 0 else "down"
    exits = bk.get("exits") or []
    exlog = ""
    if exits:
        er = "".join(
            f'<tr><td class="sym">{html.escape(e["date"])}</td><td class="sym">{html.escape(e["symbol"])}</td>'
            f'<td>{html.escape(e["reason"])}</td>'
            f'<td class="num {"up" if e["pnl"]>=0 else "down"}">{e["pnl"]:+,.0f}</td></tr>'
            for e in reversed(exits[-12:]))
        exlog = (f'<h3 class="h3">Exits (trailing stop)</h3>'
                 f'<table class="grid"><thead><tr><th>Date</th><th>Symbol</th><th>Reason</th><th>P&L</th></tr></thead>'
                 f'<tbody>{er}</tbody></table>')
    return f'''<p class="muted">₹1L paper book, marked to the latest Kite close (offline). Quarterly rebalance {rc};
      daily trailing-stop exit at 15% below each name's peak (the <em>Stop</em> column).</p>
      <div class="statrow">
        <div class="stat"><div class="sv">₹{bk["equity"]:,.0f}</div><div class="sl">equity</div></div>
        <div class="stat"><div class="sv {tot_cls}">{bk["ret"]*100:+.1f}%</div><div class="sl">since inception ₹{bk["inception"]:,.0f}</div></div>
        <div class="stat"><div class="sv">₹{bk["cash"]:,.0f}</div><div class="sl">cash</div></div>
      </div>
      <table class="grid"><thead><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Now</th><th>Stop</th><th>Value</th><th>P&L</th></tr></thead>
      <tbody>{"".join(rows)}</tbody></table>
      {exlog}'''


def _backtest(st: dict) -> str:
    bt = st["backtest"]
    if not bt:
        return '<p class="muted">No saved backtest. Run <code>python scripts/backtest_ranking.py --pit-universe --sector-val --quarterly --save</code>.</p>'
    s, bn = bt["stats"]["strategy"], bt["stats"]["benchmark"]
    def row(lbl, a, b, fmt):
        return f'<tr><td>{lbl}</td><td class="num">{fmt.format(a)}</td><td class="num">{fmt.format(b)}</td></tr>'
    tbl = (row("CAGR", s["cagr"], bn["cagr"], "{:.1%}")
           + row("Sharpe", s["sharpe"], bn["sharpe"], "{:.2f}")
           + row("Max drawdown", s["maxdd"], bn["maxdd"], "{:.1%}")
           + row("Total return", s["total"], bn["total"], "{:.0%}"))
    return f'''<p class="muted">{html.escape(bt["config"])} · {html.escape(bt["window"])} · {bt["months"]} months · built {html.escape(bt["generated"][:16])}</p>
      {_svg_equity(bt)}
      <div class="legend"><span class="k strat"></span>strategy (net)<span class="k bench"></span>benchmark (equal-weight, same pool)</div>
      <div class="statrow">
        <div class="stat"><div class="sv up">{bt["stats"]["active"]*100:+.1f}%</div><div class="sl">active return / yr</div></div>
        <div class="stat"><div class="sv">{bt["stats"]["ir"]:.2f}</div><div class="sl">information ratio</div></div>
        <div class="stat"><div class="sv">{bt["stats"]["turnover"]*100:.0f}%</div><div class="sl">turnover / mo</div></div>
      </div>
      <table class="grid narrow"><thead><tr><th></th><th>Strategy</th><th>Benchmark</th></tr></thead><tbody>{tbl}</tbody></table>
      {_backtest_trades(bt)}
      <p class="caveat">⚠️ {html.escape(bt.get("caveat",""))} Point-in-time membership + costs applied; not a P&L promise.</p>'''


def _chips(syms: list[str]) -> str:
    return "".join(f'<span class="chip">{html.escape(s)}</span>' for s in syms)


def _backtest_trades(bt: dict) -> str:
    trades = bt.get("trades") or []
    if not trades:
        return ""
    held = bt.get("current_holdings") or []
    # most recent rebalances first (each is a change-point: names bought/sold)
    rows = []
    for t in reversed(trades):
        rows.append(
            f'<tr><td class="sym">{html.escape(t["date"])}</td>'
            f'<td class="chipcell">{_chips(t["bought"]) or "—"}</td>'
            f'<td class="chipcell sold">{_chips(t["sold"]) or "—"}</td>'
            f'<td class="num">{t["n"]}</td></tr>')
    return f'''<h3 class="h3">Holdings &amp; trades over time</h3>
      <p class="muted">The book rebalances quarterly; a name leaving the top-N <em>is</em> the exit
      (the strategy exits by rotation). {len(trades)} rebalances in this run. Current book:</p>
      <div class="chips">{_chips(held)}</div>
      <table class="grid trades"><thead><tr><th>Rebalance</th><th>Bought (entered)</th><th>Sold (exited)</th><th>#held</th></tr></thead>
      <tbody>{"".join(rows)}</tbody></table>'''


def render_live(st: dict) -> str:
    tabs = [("pipeline", "Pipeline", _pipeline_detail(st)),
            ("leaderboard", "Leaderboard", _leaderboard(st)),
            ("paper", "Paper Book", _paper(st)),
            ("backtest", "Backtest", _backtest(st)),
            ("controls", "Controls", _controls(st))]
    nav = "".join(f'<button class="tab" data-t="{k}">{lbl}</button>' for k, lbl, _ in tabs)
    panes = "".join(f'<section class="pane" id="p-{k}">{body}</section>' for k, _, body in tabs)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kestrel — Research</title>
<style>
:root {{ --bg:#0a0e14; --panel:#111722; --line:#1e2836; --fg:#e6edf3; --muted:#7d8998;
  --accent:#39d3c3; --up:#3fb950; --down:#f85149; --bar:#39d3c3; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }}
.wrap {{ max-width:960px; margin:0 auto; padding:20px 16px 60px; }}
header {{ display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
h1 {{ font-size:20px; margin:0; letter-spacing:.3px; }} h1 .dot {{ color:var(--accent); }}
.live {{ color:var(--muted); font-size:12px; }} .live b {{ color:var(--up); }}
.badges {{ display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 6px; }}
.badge {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:7px 11px;
  display:flex; flex-direction:column; gap:1px; min-width:120px; }}
.badge.ok {{ border-color:#1d3b2a; }} .badge.bad {{ border-color:#4a2020; }}
.blabel {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.4px; }}
.bval {{ font-weight:600; font-size:13px; }} .badge.ok .bval {{ color:var(--up); }} .badge.bad .bval {{ color:var(--down); }}
.tabs {{ display:flex; gap:4px; margin:18px 0 0; border-bottom:1px solid var(--line); }}
.tab {{ background:none; border:none; color:var(--muted); padding:9px 14px; cursor:pointer; font-size:14px;
  border-bottom:2px solid transparent; }}
.tab.on {{ color:var(--fg); border-bottom-color:var(--accent); }}
.pane {{ display:none; padding-top:16px; }} .pane.on {{ display:block; }}
.muted {{ color:var(--muted); font-size:13px; margin:0 0 12px; }}
table.grid {{ width:100%; border-collapse:collapse; font-size:13px; }}
.grid th {{ text-align:right; color:var(--muted); font-weight:500; font-size:11px; text-transform:uppercase;
  padding:6px 8px; border-bottom:1px solid var(--line); }}
.grid th:first-child {{ text-align:left; }}
.grid td {{ padding:7px 8px; border-bottom:1px solid #151c28; }}
.grid td.sym {{ font-weight:600; }} .grid td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.grid.narrow {{ max-width:360px; }}
.barcell {{ width:40%; }} .bar {{ background:#141b26; border-radius:6px; height:9px; overflow:hidden; }}
.bar span {{ display:block; height:100%; background:var(--bar); }}
.up {{ color:var(--up); }} .down {{ color:var(--down); }} .flat {{ color:var(--muted); }} .muted-c {{ color:var(--muted); }}
.statrow {{ display:flex; gap:22px; margin:14px 0; flex-wrap:wrap; }}
.stat .sv {{ font-size:22px; font-weight:700; }} .stat .sl {{ color:var(--muted); font-size:12px; }}
.equity {{ width:100%; height:auto; background:var(--panel); border:1px solid var(--line); border-radius:10px; }}
.equity .grid {{ stroke:#182234; stroke-width:1; }} .equity .axis {{ fill:var(--muted); font-size:10px; }}
.line-strat {{ fill:none; stroke:var(--accent); stroke-width:2; }}
.line-bench {{ fill:none; stroke:#5b6675; stroke-width:1.5; stroke-dasharray:4 3; }}
.legend {{ color:var(--muted); font-size:12px; margin:8px 0; display:flex; align-items:center; gap:6px; }}
.legend .k {{ width:14px; height:3px; display:inline-block; margin:0 4px 0 12px; }}
.legend .k.strat {{ background:var(--accent); }} .legend .k.bench {{ background:#5b6675; }}
.caveat {{ color:var(--muted); font-size:12px; margin-top:12px; }}
code {{ background:#151c28; padding:1px 5px; border-radius:4px; font-size:12px; }}
.stages {{ display:flex; flex-direction:column; gap:10px; }}
.stage {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.shead {{ display:flex; align-items:center; gap:8px; margin-bottom:4px; }}
.sdot {{ font-size:10px; }} .sdot.up {{ color:var(--up); }} .sdot.down {{ color:var(--down); }}
.sname {{ font-weight:600; }} .sline {{ color:var(--muted); font-size:12.5px; }}
.h3 {{ font-size:14px; margin:22px 0 4px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:5px; margin:6px 0 14px; }}
.chip {{ background:#141b26; border:1px solid var(--line); border-radius:5px; padding:2px 7px;
  font-size:11.5px; font-weight:600; }}
.chipcell {{ }} .chipcell .chip {{ background:#12241a; border-color:#1d3b2a; }}
.chipcell.sold .chip {{ background:#251518; border-color:#4a2020; color:#f0a3a0; }}
.grid.trades td {{ vertical-align:top; }} .grid.trades th:nth-child(4) {{ text-align:right; }}
.ctlgrid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }}
.ctlcard {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px; }}
.ctlcard h4 {{ margin:0 0 10px; font-size:13px; }}
.btn {{ background:#182234; color:var(--fg); border:1px solid var(--line); border-radius:7px;
  padding:7px 11px; margin:0 6px 8px 0; cursor:pointer; font-size:13px; }}
.btn:hover {{ border-color:var(--accent); }} .btn.danger:hover {{ border-color:var(--down); }}
.mintrow {{ display:flex; gap:6px; margin:4px 0; }}
.mintrow input {{ flex:1; background:#0c121b; border:1px solid var(--line); border-radius:7px;
  color:var(--fg); padding:7px 9px; font-size:12px; }}
.hint {{ color:var(--muted); font-size:11.5px; margin-top:6px; }}
.ctlmsg {{ margin-top:14px; color:var(--accent); font-size:13px; min-height:18px; }}
</style></head><body><div class="wrap">
<header>
  <h1><span class="dot">◆</span> Kestrel <span style="color:var(--muted);font-weight:400">Research</span></h1>
  <div class="live">rendered {html.escape(st["generated"])} · <b id="ago">live</b> · auto-refresh 45s · on-host</div>
</header>
{_pipeline(st)}
<div class="tabs">{nav}</div>
{panes}
</div>
<script>
 var gen={st["generated_epoch"]:.0f};
 function ago(){{ var s=Math.max(0,Math.floor(Date.now()/1000-gen));
   document.getElementById('ago').textContent = s<60? 'updated '+s+'s ago' : 'updated '+Math.floor(s/60)+'m ago'; }}
 setInterval(ago,1000); ago();
 var tabs=document.querySelectorAll('.tab'), panes=document.querySelectorAll('.pane');
 function show(k){{ tabs.forEach(t=>t.classList.toggle('on',t.dataset.t===k));
   panes.forEach(p=>p.classList.toggle('on',p.id==='p-'+k)); location.hash=k; }}
 tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.t)));
 show((location.hash||'#pipeline').slice(1));
 // Soft auto-refresh: reload for fresh data, but never while you're using the
 // Controls tab or typing in a field.
 setInterval(function(){{
   if(location.hash==='#controls') return;
   if(document.activeElement && document.activeElement.tagName==='INPUT') return;
   location.reload();
 }}, 45000);
 function post(url, body){{
   var m=document.getElementById('ctlmsg'); if(m) m.textContent='working…';
   fetch(url,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:body?JSON.stringify(body):null}})
     .then(r=>r.json()).then(d=>{{ if(m) m.textContent=(d.ok?'✓ ':'✗ ')+(d.message||d.error||''); }})
     .catch(e=>{{ if(m) m.textContent='✗ Cannot reach the local server. Open this dashboard at http://localhost:8000 in your browser — the controls only work on the live served page, not a saved/preview copy.'; }});
 }}
 function mint(){{ var r=document.getElementById('redir').value.trim();
   var m=document.getElementById('ctlmsg');
   if(!r){{ if(m) m.textContent='Paste the Kite redirect URL first.'; return; }}
   post('/api/token/mint',{{redirect:r}}); }}
</script></body></html>'''


def main() -> None:
    OUT.write_text(render_live(gather_live()), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
