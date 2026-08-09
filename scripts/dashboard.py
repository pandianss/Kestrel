"""Generate a local operator dashboard — data, findings, recommendations, and
what the pipeline is doing.

⚠️ On-host only (G-15, Kite licence, D-18). This writes a self-contained
`dashboard.html` you open in your own browser on your PC. It embeds market-data-
derived figures, so it is **never** published, shared, or transmitted — it is
gitignored, and it must not be. A single-user, on-host dashboard is exactly
what doc 10 §4 permits; putting the same content on any external platform is
what the licence forbids.

    python scripts/dashboard.py         # writes dashboard.html, then open it
"""
from __future__ import annotations

import glob
import html
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from kestrel.data.snapshot import SnapshotStore
from kestrel.kite.tokenstore import FileTokenStore

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_slice import run_slice  # noqa: E402  (reuse the exact slice computation)

TOKEN_PATH = "data/secrets/kite_token.json"
SNAPSHOT_ROOT = "data/snapshots"
KITE_CACHE = "data/cache/kite"
OUT = Path("dashboard.html")


# ---------------------------------------------------------------- gather ----

def _render_tree_node_html(store, symbol: str, d: date, visited: set[str] | None = None) -> str:
    if visited is None:
        visited = set()
    if symbol in visited:
        return ""
    visited.add(symbol)
    
    direct = store.relations_asof(symbol, d)
    if not direct:
        visited.remove(symbol)
        return ""
        
    html_parts = []
    html_parts.append('<ul class="tree-branch">')
    for r in direct:
        target = r.target_name_or_symbol
        holding = r.holding_pct * 100
        
        # Check if target has sub-relations
        sub_html = _render_tree_node_html(store, target, d, visited)
        if sub_html:
            html_parts.append(
                f'<li><details open><summary class="tree-summary"><b>{html.escape(target)}</b> '
                f'<span class="stake-tag">{holding:.1f}%</span></summary>{sub_html}</details></li>'
            )
        else:
            html_parts.append(
                f'<li><span class="tree-item">{html.escape(target)} '
                f'<span class="stake-tag">{holding:.1f}%</span></span></li>'
            )
            
    html_parts.append("</ul>")
    visited.remove(symbol)
    return "".join(html_parts)


def gather() -> dict:
    now = datetime.now(timezone.utc)
    state: dict = {"generated": now.astimezone().strftime("%Y-%m-%d %H:%M %Z")}

    # token
    tok = FileTokenStore(TOKEN_PATH).load()
    if tok is None:
        state["token"] = {"ok": False, "text": "no token — run kite_login.py"}
    else:
        state["token"] = {
            "ok": tok.is_valid(now),
            "text": ("valid" if tok.is_valid(now) else "EXPIRED") + f" · user {tok.user_id} · until {tok.expires_at}",
        }

    # universe snapshots
    store = SnapshotStore(SNAPSHOT_ROOT)
    dates = store.list_dates("instruments")
    uni: dict = {"dates": len(dates)}
    if dates:
        latest = dates[-1]
        m = store.read_manifest("instruments", latest)
        uni.update(first=dates[0].isoformat(), last=latest.isoformat(),
                   source=(m.source if m else "?"), size_mb=(m.size_bytes / 1e6 if m else 0))
        try:
            # count from the LATEST snapshot in a single parse (the 10 MB CSV),
            # rather than building two full point-in-time universes over all dates
            import csv as _csv
            import io as _io
            from kestrel.data.pit import nse_equity_row
            rows = list(_csv.DictReader(_io.StringIO(store.read("instruments", latest).decode("utf-8"))))
            uni["all"] = len(rows)
            uni["equity"] = sum(1 for r in rows if nse_equity_row(r))
        except Exception:  # noqa: BLE001
            uni["equity"] = None
    state["universe"] = uni

    # historical cache + findings — the dashboard runs a slice for only a FEW
    # cached names (there can be thousands of cached symbols; slicing all of
    # them would take minutes and bloat the page). Prefer well-known names.
    _FINDINGS_MAX = 5
    caches = sorted(glob.glob(f"{KITE_CACHE}/*_day.pkl"))
    all_syms = [Path(p).stem.replace("_day", "") for p in caches]
    _preferred = [s for s in ("RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC") if s in all_syms]
    pick = (_preferred + [s for s in all_syms if s not in _preferred])[:_FINDINGS_MAX]
    hist, findings = [], []
    for sym in pick:
        try:
            df = pd.read_pickle(Path(KITE_CACHE) / f"{sym}_day.pkl")
            hist.append({"symbol": sym, "bars": len(df),
                         "first": df.index[0].date().isoformat(),
                         "last": df.index[-1].date().isoformat()})
            findings.append(run_slice(sym))
        except Exception:  # noqa: BLE001
            continue
    state["history"] = hist
    state["findings"] = findings
    state["history_total"] = len(all_syms)

    # fundamentals coverage
    try:
        from kestrel.data.fundamentals_store import FundamentalsStore
        state["fundamentals"] = FundamentalsStore("data/fundamentals").symbols()
    except Exception:  # noqa: BLE001
        state["fundamentals"] = []

    # fundamental trends — only names with real history (>=2 quarters); most of
    # the market has a single quarter so far, so filter first to keep it fast.
    try:
        from kestrel.analysis.fundamentals_trend import company_trend
        from kestrel.data.fundamentals_store import FundamentalsStore as _FS
        _fs = _FS("data/fundamentals")
        deep = [s for s in _fs.symbols() if len(_fs.records(s)) >= 2]
        trends = [company_trend(_fs, s) for s in deep]
        state["trends"] = sorted((t for t in trends if t.direction != "insufficient"),
                                 key=lambda t: -(t.slope or 0.0))
    except Exception:  # noqa: BLE001
        state["trends"] = []

    # background fundamentals worker status
    import json as _json
    wstatus = Path("logs/fundamentals_worker_status.json")
    wpid = Path("logs/fundamentals_worker.pid")
    wlog = Path("logs/fundamentals_worker.log")
    
    worker_state = {"status": "STOPPED", "logs": []}
    try:
        if wstatus.exists():
            worker_state.update(_json.loads(wstatus.read_text()))
        
        if wpid.exists():
            pid = int(wpid.read_text().strip())
            # check if PID is active
            import os
            import subprocess
            is_running = False
            if os.name == 'nt':
                try:
                    output = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], encoding="utf-8")
                    is_running = str(pid) in output
                except Exception:
                    is_running = False
            else:
                try:
                    os.kill(pid, 0)
                    is_running = True
                except OSError:
                    is_running = False
            
            if is_running:
                worker_state["status"] = "RUNNING"
                
        if wlog.exists():
            lines = wlog.read_text("utf-8").splitlines()
            worker_state["logs"] = lines[-8:]
    except Exception:  # noqa: BLE001
        pass
    state["worker"] = worker_state

    # Corporate data is discovered from the store.  The dashboard must never
    # privilege a named company: every symbol with stored relations, segments,
    # or industry metadata is selectable.
    try:
        from kestrel.data.relations_store import RelationsStore as _RS
        from kestrel.analysis.relations_analysis import get_sector_peers
        rstore = _RS("data/relations")
        if not rstore.symbols():
            rstore = _RS("data/relations_demo")
        relation_date = datetime.now().date()
        companies = []
        for symbol in rstore.symbols():
            direct = rstore.relations_asof(symbol, relation_date)
            tree_html = ""
            if direct:
                tree_html = (
                    f'<ul class="hierarchical-tree"><li><details open>'
                    f'<summary class="tree-summary root-summary"><b>{html.escape(symbol)}</b></summary>'
                    f'{_render_tree_node_html(rstore, symbol, relation_date)}'
                    f'</details></li></ul>'
                )
            companies.append({
                "symbol": symbol,
                "tree_html": tree_html,
                "segments": rstore.segments_asof(symbol, relation_date),
                "industry": rstore.industry_asof(symbol, relation_date),
                "peers": get_sector_peers(rstore, symbol, relation_date),
            })
        state["relation_companies"] = companies
    except Exception:  # noqa: BLE001
        state["relation_companies"] = []

    # baskets ranking
    bfile = Path("data/baskets_ranking.json")
    if bfile.exists():
        try:
            state["baskets"] = _json.loads(bfile.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            state["baskets"] = None
    else:
        try:
            from kestrel.analysis.baskets import rank_and_group_baskets
            from kestrel.analysis.fundamentals_trend import compare
            from kestrel.data.fundamentals_store import FundamentalsStore as _FS
            fstore = _FS("data/fundamentals")
            if fstore.symbols():
                tr_list = compare(fstore)
                b_map = rank_and_group_baskets(tr_list)
                state["baskets"] = {k: [item.to_dict() for item in v] for k, v in b_map.items()}
            else:
                state["baskets"] = None
        except Exception:  # noqa: BLE001
            state["baskets"] = None

    state["recommendations"] = _recommendations(state)
    return state


def _has_constituents() -> bool:
    base = Path("data/snapshots")
    return base.exists() and any(base.glob("constituents_*"))


def _recommendations(state: dict) -> list[dict]:
    """Derive pending items from actual local state — the three data sources are
    now built, so what remains is coverage and genuinely-deferred decisions."""
    funda_n = len(state.get("fundamentals", []))
    candidates = [
        {"pri": "med", "title": "Snapshot index constituents",
         "done": _has_constituents(),
         "why": "Run scripts/snapshot_constituents.py to build the clean stock universe (NIFTY 500) and start point-in-time membership (G-43)."},
        {"pri": "med", "title": "Run the full fundamentals harvest",
         "done": funda_n >= 100,
         "why": f"Only {funda_n} symbol(s) ingested. Run scripts/harvest_fundamentals.py for the full filing set (feeds value/earnings)."},
        {"pri": "low", "title": "Quality/ROE needs balance-sheet data",
         "done": False,
         "why": "A results XBRL gives EPS/revenue/PAT but not net worth, so ROE-based quality needs annual filings or a vendor — value/earnings works today."},
        {"pri": "low", "title": "Static IP — only at live-order stage",
         "done": False,
         "why": "Not needed for research/data. Source an ISP static IP or small Indian relay box before placing live orders (D-18)."},
    ]
    return [c for c in candidates if not c["done"]]


# ---------------------------------------------------------------- render ----

def _dot(state: str) -> str:
    return f'<span class="dot {state}"></span>'


def _pipeline(state: dict) -> str:
    tok_ok = state["token"]["ok"]
    uni = state["universe"]
    stages = [
        ("Daily token", "ok" if tok_ok else "warn",
         state["token"]["text"], "token-status-dot", "token-status-text"),
        ("Universe capture", "ok" if uni.get("dates") else "warn",
         f"{uni.get('dates', 0)} day(s) archived" + (f", {uni['last']} latest" if uni.get('last') else ""), "uni-status-dot", "uni-status-text"),
        ("Historical prices", "ok" if state["history"] else "idle",
         f"{len(state['history'])} symbol(s) cached", "hist-status-dot", "hist-status-text"),
        ("Backtest + exit path", "ok" if state["findings"] else "idle",
         f"{len(state['findings'])} slice(s) run", "slice-status-dot", "slice-status-text"),
    ]
    rows = "".join(
        f'<div class="stage"><span id="{dot_id}" class="dot {s}"></span><div><b>{html.escape(name)}</b>'
        f'<span id="{text_id}" class="muted">{html.escape(detail)}</span></div></div>'
        for name, s, detail, dot_id, text_id in stages
    )
    return f'<div class="stages">{rows}</div>'


def _kv(label: str, value: str) -> str:
    return f'<tr><td class="k">{html.escape(label)}</td><td class="v">{value}</td></tr>'


def _data_section(state: dict) -> str:
    uni = state["universe"]
    rows = [_kv("Kite token", html.escape(state["token"]["text"]))]
    if uni.get("dates"):
        src = html.escape(uni.get("source", "?"))
        real = uni.get("source", "").startswith("kite:")
        rows.append(_kv("Universe snapshots", f'{uni["dates"]} day(s), {uni["first"]} → {uni["last"]}'))
        rows.append(_kv("Latest source", f'{src} {"✓ real" if real else "⚠ dev"}, {uni.get("size_mb",0):.1f} MB'))
        if uni.get("equity") is not None:
            rows.append(_kv("NSE cash names", f'{uni["equity"]:,} of {uni.get("all",0):,} instruments '
                                              f'<span class="muted">(incl. ETFs/bonds — see recs)</span>'))
    else:
        rows.append(_kv("Universe snapshots", '<span class="warn-t">none — run snapshot_reference.py</span>'))
    for h in state["history"]:
        rows.append(_kv(f'History · {h["symbol"]}', f'{h["bars"]:,} bars, {h["first"]} → {h["last"]}'))
    funda = state.get("fundamentals", [])
    if funda:
        shown = ", ".join(funda[:8]) + (" …" if len(funda) > 8 else "")
        rows.append(_kv("Fundamentals (filed)", f'{len(funda)} symbol(s): {html.escape(shown)}'))
    wk = state.get("worker")
    if wk:
        rows.append(_kv("Fundamentals worker",
                        f'last cycle {html.escape(str(wk.get("last_cycle", "?")))} · '
                        f'+{wk.get("written", 0)} that cycle · {wk.get("symbols", 0)} symbols'))
    return f'<table class="kv">{"".join(rows)}</table>'


def _format_inr(value: float) -> str:
    """Compact, signed rupee label for an axis or chart annotation."""
    absolute = abs(value)
    if absolute >= 100_000:
        number = f"{absolute / 100_000:.1f}L"
    elif absolute >= 1_000:
        number = f"{absolute / 1_000:.0f}k"
    else:
        number = f"{absolute:.0f}"
    return f"{'−' if value < 0 else ''}₹{number}"


def _slice_outcomes_chart(state: dict) -> str:
    """A zero-centred chart makes the exit-path slice outcomes scannable."""
    findings = state.get("findings", [])
    if not findings:
        return '<p class="muted">No slice outcomes to plot yet.</p>'

    ordered = sorted(findings, key=lambda finding: finding["net_pnl"])
    values = [float(finding["net_pnl"]) for finding in ordered]
    low, high = min(0.0, min(values)), max(0.0, max(values))
    padding = max((high - low) * 0.08, 500.0)
    low -= padding
    high += padding
    width, left, right, top, row_height = 820, 132, 82, 44, 46
    height = top + row_height * len(ordered) + 38

    def x(value: float) -> float:
        return left + (value - low) / (high - low) * (width - left - right)

    zero = x(0)
    tick_values = [low, 0.0, high]
    ticks = "".join(
        f'<text class="chart-tick" x="{x(value):.1f}" y="24" '
        f'text-anchor="middle">{_format_inr(value)}</text>'
        for value in tick_values
    )
    grid = "".join(
        f'<line class="chart-grid" x1="{x(value):.1f}" y1="32" '
        f'x2="{x(value):.1f}" y2="{height - 24}" />'
        for value in tick_values
        if value != 0
    )

    rows = []
    for index, finding in enumerate(ordered):
        net = float(finding["net_pnl"])
        y = top + index * row_height
        value_x = x(net)
        rect_x = min(zero, value_x)
        rect_width = abs(value_x - zero)
        direction = "positive" if net >= 0 else "negative"
        text_anchor = "start" if net >= 0 else "end"
        label_x = value_x + 8 if net >= 0 else value_x - 8
        rows.append(
            f'<g class="outcome-row">'
            f'<text class="chart-label" x="{left - 12}" y="{y + 18}" text-anchor="end">'
            f'{html.escape(finding["symbol"])}</text>'
            f'<rect class="outcome-bar {direction}" x="{rect_x:.1f}" y="{y + 5}" '
            f'width="{rect_width:.1f}" height="18" rx="3" />'
            f'<text class="chart-value" x="{label_x:.1f}" y="{y + 18}" '
            f'text-anchor="{text_anchor}">{_format_inr(net)}</text>'
            f'</g>'
        )

    return f'''
    <figure class="chart-figure slice-chart-figure">
      <svg class="chart" viewBox="0 0 {width} {height}" role="img"
           aria-labelledby="slice-outcomes-title slice-outcomes-desc">
        <title id="slice-outcomes-title">Net P&amp;L by vertical slice</title>
        <desc id="slice-outcomes-desc">Each bar extends from zero. Teal is a positive net result and red is a negative net result.</desc>
        {ticks}
        {grid}
        <line class="chart-zero" x1="{zero:.1f}" y1="32" x2="{zero:.1f}" y2="{height - 24}" />
        {"".join(rows)}
      </svg>
      <figcaption>Net P&amp;L after modelled costs. This validates the deterministic slice; it is not factor evidence.</figcaption>
    </figure>'''


def _trend_sparkline(trend) -> str:
    """Render one company's EPS history on its own scale for honest comparison."""
    points = trend.points
    values = [point.eps for point in points]
    width, height, left, right, top, bottom = 310, 136, 36, 14, 22, 28
    low, high = min(values), max(values)
    spread = high - low
    padding = max(spread * 0.12, max(abs(low), abs(high), 1.0) * 0.04)
    low -= padding
    high += padding

    def x(index: int) -> float:
        if len(points) == 1:
            return (left + width - right) / 2
        return left + index / (len(points) - 1) * (width - left - right)

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * (height - top - bottom)

    path = " ".join(f"{x(index):.1f},{y(value):.1f}" for index, value in enumerate(values))
    latest = points[-1]
    first = points[0]
    direction = trend.direction if trend.direction in {"improving", "declining"} else "flat"
    qoq = "—" if trend.qoq_growth is None else f"{trend.qoq_growth:+.0%} QoQ"
    return f'''
    <figure class="trend-figure">
      <figcaption>
        <span class="trend-symbol">{html.escape(trend.symbol)}</span>
        <span class="trend-summary">EPS {latest.eps:.2f} · {qoq}</span>
      </figcaption>
      <svg class="trend-chart" viewBox="0 0 {width} {height}" role="img"
           aria-label="{html.escape(trend.symbol)} EPS history from {first.period_end.isoformat()} to {latest.period_end.isoformat()}">
        <line class="chart-grid" x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" />
        <line class="chart-grid" x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" />
        <polyline class="trend-line {direction}" points="{path}" />
        <circle class="trend-point {direction}" cx="{x(len(points) - 1):.1f}" cy="{y(latest.eps):.1f}" r="4" />
        <text class="chart-tick" x="{left - 6}" y="{top + 4}" text-anchor="end">{high - padding:.2f}</text>
        <text class="chart-tick" x="{left - 6}" y="{height - bottom + 4}" text-anchor="end">{low + padding:.2f}</text>
        <text class="chart-tick" x="{left}" y="{height - 8}" text-anchor="start">{first.period_end.strftime('%Y')}</text>
        <text class="chart-tick" x="{width - right}" y="{height - 8}" text-anchor="end">{latest.period_end.strftime('%Y')}</text>
      </svg>
    </figure>'''


def _fundamental_trends_chart(state: dict) -> str:
    trends = state.get("trends", [])
    if not trends:
        return '<p class="muted">No multi-quarter fundamentals to plot yet.</p>'
    measurable = [trend for trend in trends if len(trend.points) >= 2]
    improving = [trend for trend in measurable if trend.direction == "improving"]
    declining = [trend for trend in measurable if trend.direction == "declining"]
    neutral = [trend for trend in measurable if trend.direction == "flat"]
    selected = (improving[:4] + declining[:4] + neutral[:2])[:8]
    charts = "".join(_trend_sparkline(trend) for trend in selected)
    return f'''
    <div class="trend-chart-grid" aria-label="EPS trajectory small multiples">
      {charts}
    </div>
    <p class="muted">{len(improving)} improving · {len(declining)} declining · {len(neutral)} flat. Each chart has its own EPS scale; compare direction, not line height.</p>'''


def _findings_section(state: dict) -> str:
    if not state["findings"]:
        return '<p class="muted">No slices run yet — pull history (pull_history.py) then reload.</p>'
    cards = []
    for f in state["findings"]:
        reasons = ", ".join(f"{k} {v}" for k, v in sorted(f["exit_reasons"].items()))
        net = f["net_pnl"]
        cls = "pos" if net >= 0 else "neg"
        cards.append(f'''
        <div class="card">
          <div class="card-h">{html.escape(f["symbol"])} <span class="tag">{html.escape(f["source"])}</span></div>
          <div class="big {cls}">₹{net:,.0f}<span class="muted"> net</span></div>
          <table class="kv small">
            {_kv("Window", f'{f["start"]} → {f["end"]}')}
            {_kv("Trades", str(f["trades"]))}
            {_kv("Win rate", f'{f["win_rate"]:.0%}')}
            {_kv("Avg hold", f'{f["avg_hold_days"]:.0f}d')}
            {_kv("Exits", html.escape(reasons))}
            {_kv("Costs", f'₹{f["costs"]:,.0f} ({f["costs"]/f["capital"]:.2%})')}
          </table>
        </div>''')
    caveat = ('<p class="muted">Placeholder trend entry — this shows the '
              '<b>exit path and cash accounting working on real data</b>, not an edge. '
              'A real factor verdict needs a point-in-time universe (G-43).</p>')
    return f'{_slice_outcomes_chart(state)}<div class="cards">{"".join(cards)}</div>{caveat}'


def _trends_section(state: dict) -> str:
    trends = state.get("trends", [])
    if not trends:
        return ('<p class="muted">No multi-quarter fundamentals yet — backfill with '
                '<code>scripts/backfill_fundamentals.py SYMBOL …</code> to compare companies over time.</p>')
    return _fundamental_trends_chart(state)


def _recs_section(state: dict) -> str:
    order = {"high": 0, "med": 1, "low": 2}
    items = sorted(state["recommendations"], key=lambda r: order.get(r["pri"], 9))
    if not items:
        return '<p class="muted">All tracked data sources are wired — nothing pending. ✓</p>'
    lis = "".join(
        f'<li><span class="pri {r["pri"]}">{r["pri"]}</span>'
        f'<b>{html.escape(r["title"])}</b><span class="muted">{html.escape(r["why"])}</span></li>'
        for r in items
    )
    return (f'<ul class="recs">{lis}</ul>'
            '<p class="muted">State-driven: each item clears itself once its data lands under '
            '<code>data/</code>.</p>')


def _worker_console_section(state: dict) -> str:
    wk = state.get("worker")
    if not wk:
        return '<p class="muted">No background worker status available.</p>'
        
    status = wk.get("status", "STOPPED")
    status_cls = "ok" if status == "RUNNING" else "neg"
    pulse_dot = f'<span id="worker-status-dot" class="dot {status_cls}" style="display:inline-block; margin-right:6px; vertical-align:middle; width:10px; height:10px; border-radius:50%; background:{"var(--ok)" if status == "RUNNING" else "var(--neg)"}; box-shadow: 0 0 8px {"var(--ok)" if status == "RUNNING" else "var(--neg)"};"></span>'
    
    log_lines = wk.get("logs", [])
    log_content = html.escape("\n".join(log_lines)) if log_lines else "No recent logs."
    
    return f'''
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 10px;">
      <div><b>Status:</b> {pulse_dot} <span id="worker-status-badge" style="font-weight: bold; color: {"var(--ok)" if status == "RUNNING" else "var(--neg)"};">{status}</span></div>
      <div id="worker-pid" class="muted">PID: {wk.get("pid", "N/A")} · Last Cycle: {html.escape(str(wk.get("last_cycle", "Never")))}</div>
    </div>
    
    <div class="token-mint-box" style="margin-bottom: 16px; background: rgba(102, 252, 241, 0.04); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px;">
        <span style="font-weight: 600; font-size: 13px; color: var(--accent);">🔑 Daily Session Token Mint</span>
        <a href="https://kite.zerodha.com/connect/login?v=3&api_key=97x3bf78zyoncg1p" target="_blank" class="btn-action" style="font-size: 11.5px; padding: 4px 10px; text-decoration: none;">1. Open Zerodha Login Page ↗</a>
      </div>
      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
        <input type="text" id="redirect-input" placeholder="2. Paste full redirect URL or request_token here..." style="flex: 1; min-width: 250px; background: rgba(0,0,0,0.3); border: 1px solid var(--line); color: #fff; padding: 7px 12px; border-radius: 4px; font-size: 12.5px; outline: none;">
        <button class="btn-action" style="background: var(--accent); color: #0b0c10; font-weight: 600;" onclick="submitRedirect()">3. Mint Session Token</button>
      </div>
      <div id="token-mint-msg" style="margin-top: 6px; font-size: 12px;"></div>
    </div>

    <div class="control-toolbar" style="display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; align-items: center;">
      <button class="btn-action btn-start" onclick="callApi('/api/worker/start', 'Starting Harvester...')">▶ Start Harvester</button>
      <button class="btn-action btn-stop" onclick="callApi('/api/worker/stop', 'Stopping Harvester...')">⏹ Stop Harvester</button>
      <button class="btn-action btn-history" onclick="callApi('/api/history/start', 'Harvesting History...')">⚡ Harvest Price History</button>
      <button class="btn-action btn-relations" onclick="callApi('/api/relations/harvest', 'Harvesting Corporate Relations...')">🌲 Harvest Corporate Relations</button>
      <button class="btn-action btn-refresh" onclick="callApi('/api/dashboard/refresh', 'Refreshing Dashboard...')">🔄 Re-compile Dashboard</button>
      <span id="api-status-msg" class="muted" style="font-size: 12px; margin-left: 8px;"></span>
    </div>

    <div id="worker-console-log" class="console-box" style="background: #020c17; border: 1px solid var(--line); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 12.5px; color: #00ffcc; white-space: pre-wrap; overflow-x: auto; max-height: 200px; box-shadow: inset 0 0 10px rgba(0,255,204,0.1);">
{log_content}
    </div>
    '''


def _segment_mix_chart(segments) -> str:
    """Use the stored segment names and shares; no company-specific mapping."""
    if not segments:
        return '<p class="muted">No reported segment mix is stored for this company.</p>'

    rows = []
    for segment in sorted(segments, key=lambda item: -item.revenue_pct):
        share = max(0.0, min(1.0, segment.revenue_pct))
        rows.append(f'''
        <li class="segment-row" style="margin-bottom: 10px;">
          <div class="segment-label" style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span>{html.escape(segment.segment_name)}</span> <strong>{share:.1%}</strong></div>
          <div class="segment-track" role="progressbar" aria-label="{html.escape(segment.segment_name)} revenue share"
               aria-valuemin="0" aria-valuemax="100" aria-valuenow="{share * 100:.1f}" style="background: rgba(255,255,255,0.08); height: 8px; border-radius: 4px; overflow: hidden;">
            <span class="segment-fill" style="display: block; height: 100%; width:{share * 100:.2f}%; background: var(--accent);"></span>
          </div>
        </li>''')
    period_end = max(segment.period_end for segment in segments)
    return f'''
    <figure class="segment-chart">
      <ol class="segment-list" style="list-style: none; padding: 0; margin: 0 0 10px 0;">{"".join(rows)}</ol>
      <figcaption class="muted" style="font-size: 12px;">Revenue mix for the latest reported period, ended {period_end.isoformat()}.</figcaption>
    </figure>'''


def _industry_card(industry, peers: list[str]) -> str:
    if industry is None:
        return ''
    related = ", ".join(industry.related_industries) if industry.related_industries else "None mapped"
    if len(peers) > 15:
        peers_text = ", ".join(peers[:15]) + f" (+{len(peers) - 15} more)"
    else:
        peers_text = ", ".join(peers) if peers else "No mapped peers"
    return f'''
    <section class="relations-card">
      <h3>Industry mapping</h3>
      <dl class="relation-facts">
        <div><dt>Primary industry</dt><dd>{html.escape(industry.primary_industry)}</dd></div>
        <div><dt>Sub-sector</dt><dd>{html.escape(industry.sub_sector)}</dd></div>
        <div><dt>Related industries</dt><dd>{html.escape(related)}</dd></div>
        <div><dt>Mapped peers ({len(peers)})</dt><dd>{html.escape(peers_text)}</dd></div>
      </dl>
    </section>'''


def _relations_section(state: dict) -> str:
    companies = state.get("relation_companies", [])
    if not companies:
        return '<p class="muted">No corporate data stored. Run a harvest or seed script to populate it.</p>'

    options = []
    panes = []
    for index, company in enumerate(companies):
        symbol = company["symbol"]
        selected = " selected" if index == 0 else ""
        hidden = "" if index == 0 else " hidden"
        capabilities = []
        if company["tree_html"]:
            capabilities.append("relations")
        if company["segments"]:
            capabilities.append("segments")
        if company["industry"]:
            capabilities.append("industry")
        source_summary = ", ".join(capabilities) or "no current records"
        options.append(
            f'<option value="{html.escape(symbol)}"{selected}>{html.escape(symbol)} — {html.escape(source_summary)}</option>'
        )

        cards = []
        if company["tree_html"]:
            cards.append(f'''
            <section class="relations-card">
              <h3>Corporate hierarchy</h3>
              <div class="tree-container">{company["tree_html"]}</div>
            </section>''')
        if company["segments"]:
            cards.append(f'''
            <section class="relations-card">
              <h3>Segment revenue mix</h3>
              {_segment_mix_chart(company["segments"])}
            </section>''')
        industry_card = _industry_card(company["industry"], company["peers"])
        if industry_card:
            cards.append(industry_card)
        if not cards:
            cards.append('<p class="muted">No corporate relations, segment mix, or industry mapping is available for this company.</p>')
        panes.append(f'''
        <div class="relation-company-pane" data-company-pane="{html.escape(symbol)}"{hidden}>
          <h3 class="company-heading">{html.escape(symbol)}</h3>
          <div class="relations-grid">{"".join(cards)}</div>
        </div>''')

    return f'''
    <section class="relations-explorer" aria-label="Corporate data explorer">
      <div class="relations-controls">
        <label for="relation-company-select">Company</label>
        <select id="relation-company-select" onchange="selectRelationCompany(this)">
          {"".join(options)}
        </select>
      </div>
      {"".join(panes)}
    </section>'''


def _basket_rank_chart(state: dict) -> str:
    """Compact score bars make the top of the current research ranking legible."""
    baskets = state.get("baskets") or {}
    all_items = [item for basket in baskets.values() for item in basket]
    if not all_items:
        return ""

    # Gate to the TRADEABLE universe: names with the valuation pillar active
    # (liquid + priced, i.e. NIFTY 500) — the same set the paper book trades and
    # the backtest validated. Non-tradeable names are scored on 4 pillars only and
    # can float to the top on thin data, so they don't belong in the headline list.
    items = [i for i in all_items if i.get("tradeable")] or all_items
    gated = bool([i for i in all_items if i.get("tradeable")])

    def score(item: dict) -> float:
        try:
            return max(0.0, min(1.0, float(item.get("potential_score", 0.0))))
        except (TypeError, ValueError):
            return 0.0

    ranked = sorted(items, key=score, reverse=True)[:18]
    rows = []
    for item in ranked:
        value = score(item)
        direction = item.get("direction", "insufficient")
        direction_class = direction if direction in {"improving", "declining"} else "flat"
        rows.append(f'''
        <li class="rank-row">
          <span class="rank-symbol">{html.escape(str(item.get("symbol", "?")))}</span>
          <div class="rank-track" role="progressbar" aria-label="{html.escape(str(item.get("symbol", "?")))} potential score"
               aria-valuemin="0" aria-valuemax="100" aria-valuenow="{value * 100:.1f}">
            <span class="rank-fill" style="width:{value * 100:.2f}%"></span>
          </div>
          <span class="rank-score">{value:.0%}</span>
          <span class="trend-marker {direction_class}">{html.escape(direction)}</span>
        </li>''')

    quality_available = sum(item.get("latest_roe") is not None for item in items)
    leverage_available = sum(item.get("latest_d2e") is not None for item in items)
    return f'''
    <figure class="chart-figure ranking-chart">
      <div class="rank-axis" aria-hidden="true"><span>0</span><span>50</span><span>100</span></div>
      <ol class="rank-list">{"".join(rows)}</ol>
      <figcaption>Top {len(ranked)} by composite research score{', tradeable (NIFTY 500, 5-pillar with valuation) — the set the paper book trades' if gated else ''}. ROE available for {quality_available:,}/{len(items):,}; D/E for {leverage_available:,}/{len(items):,}. Research ranking, not an order signal.</figcaption>
    </figure>'''


def _baskets_section(state: dict) -> str:
    baskets = state.get("baskets")
    if not baskets:
        return '<p class="muted">No basket rankings available — run <code>python scripts/rank_baskets.py</code> to generate.</p>'
        
    html_parts = [_basket_rank_chart(state)]
    
    for b_name, items in baskets.items():
        if not items:
            continue
            
        badge = items[0].get("basket_badge", b_name) if items else b_name
        
        rows = []
        for item in items[:15]:
            score_pct = item.get("potential_pct", "0%")
            direction = item.get("direction", "flat")
            roe_str = item.get("roe_pct", "—")
            d2e_str = item.get("d2e_ratio", "—")
            promoter_str = item.get("promoter_pct", "—")
            
            slope = item.get("slope")
            slope_str = f"{slope:+.2f}" if slope is not None else "—"
            
            dir_color = "var(--ok)" if direction == "improving" else ("var(--neg)" if direction == "declining" else "var(--muted)")
            
            rows.append(f'''
            <tr>
              <td style="padding: 8px 6px; font-weight: bold; color: #fff;">{html.escape(item["symbol"])}</td>
              <td style="padding: 8px 6px; text-align: right;"><span class="stake-tag" style="font-size: 12px;">{score_pct}</span></td>
              <td style="padding: 8px 6px; color: {dir_color}; font-size: 13px;">{direction.upper()} ({slope_str})</td>
              <td style="padding: 8px 6px; text-align: right; font-size: 13px;">{roe_str}</td>
              <td style="padding: 8px 6px; text-align: right; font-size: 13px;">{d2e_str}</td>
              <td style="padding: 8px 6px; text-align: right; font-size: 13px;">{promoter_str}</td>
            </tr>
            ''')
            
        more_msg = f"<p class='muted' style='margin-top: 10px;'>… showing top 15 of {len(items)} instruments</p>" if len(items) > 15 else ""
        
        html_parts.append(f'''
        <div class="panel" style="margin-bottom: 20px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; border-bottom: 1px solid var(--line); padding-bottom: 8px;">
            <h3 style="margin: 0; font-size: 16px; color: #fff;">{html.escape(badge)} <span class="muted" style="font-size: 13px; font-weight: normal;">({len(items)} total instruments)</span></h3>
          </div>
          <table class="kv" style="width: 100%; border-collapse: collapse;">
            <thead>
              <tr style="border-bottom: 1px solid var(--line); color: var(--muted); font-size: 12px; text-transform: uppercase;">
                <th style="text-align: left; padding: 6px;">Symbol</th>
                <th style="text-align: right; padding: 6px;">Potential Score</th>
                <th style="text-align: left; padding: 6px;">EPS Direction (Slope)</th>
                <th style="text-align: right; padding: 6px;">ROE</th>
                <th style="text-align: right; padding: 6px;">Debt/Equity</th>
                <th style="text-align: right; padding: 6px;">Promoter %</th>
              </tr>
            </thead>
            <tbody>
              {"".join(rows)}
            </tbody>
          </table>
          {more_msg}
        </div>
        ''')
        
    return "".join(html_parts)


def render(state: dict) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kestrel — Operator Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
    --bg: #0b0c10;
    --card: rgba(26, 28, 36, 0.7);
    --ink: #c5c6c7;
    --muted: #8892b0;
    --line: #1f2833;
    --ok: #66fcf1;
    --warn: #ffb703;
    --idle: #45a29e;
    --neg: #ef4444;
    --pos: #66fcf1;
    --accent: #66fcf1;
    --glow: rgba(102, 252, 241, 0.15);
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family: 'Outfit', -apple-system, sans-serif; line-height: 1.5; }}
.wrap {{ max-width:1000px; margin:0 auto; padding:40px 24px 80px; }}
h1 {{ font-size:24px; margin:0 0 2px; color:#fff; font-weight:700; }}
h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:.08em; color:var(--accent); margin:10px 0 16px; border-left: 3px solid var(--accent); padding-left: 8px; }}
.sub {{ color:var(--muted); font-size:13.5px; margin-bottom:8px; }}
.panel {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px 22px; backdrop-filter: blur(12px); box-shadow: 0 10px 30px -10px rgba(2,12,27,0.7); margin-bottom: 24px; }}
.btn-action {{ background: rgba(255, 255, 255, 0.05); border: 1px solid var(--line); color: #fff; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 6px; }}
.btn-action:hover {{ background: var(--accent); color: #0b0c10; border-color: var(--accent); transform: translateY(-1px); box-shadow: 0 0 10px var(--glow); }}
.btn-stop:hover {{ background: var(--neg); color: #fff; border-color: var(--neg); box-shadow: 0 0 10px rgba(255,107,107,0.3); }}
.stages {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-bottom: 20px; }}
.stage {{ display:flex; gap:12px; align-items:flex-start; background:var(--card); border:1px solid var(--line);
         border-radius:10px; padding:14px 16px; transition: all 0.3s; }}
.stage:hover {{ transform: translateY(-2px); border-color: var(--accent); box-shadow: 0 0 10px var(--glow); }}
.stage b {{ display:block; font-size:14px; color:#fff; }}
.dot {{ width:9px; height:9px; border-radius:50%; margin-top:5px; flex:0 0 auto; }}
.dot.ok {{ background:var(--ok); box-shadow: 0 0 8px var(--ok); }} .dot.warn {{ background:var(--warn); }} .dot.idle {{ background:var(--idle); }}
.muted {{ color:var(--muted); font-size:12.5px; display:block; margin-top:2px; }}
table.kv {{ width:100%; border-collapse:collapse; }}
table.kv td {{ padding:9px 6px; border-bottom:1px solid var(--line); vertical-align:top; }}
table.kv td.k {{ color:var(--muted); width:35%; }}
table.kv.small td {{ padding:6px 4px; font-size:13px; border-bottom:1px dotted var(--line); }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px; transition: all 0.3s; }}
.card:hover {{ transform: translateY(-3px); border-color: var(--accent); box-shadow: 0 0 15px var(--glow); }}
.card-h {{ font-weight:600; margin-bottom:8px; color:#fff; }}
.tag {{ font-size:11px; color:var(--muted); border:1px solid var(--line); border-radius:6px; padding:1px 6px; }}
.big {{ font-size:26px; font-weight:700; margin:2px 0 10px; }}
.big .muted {{ display:inline; font-size:13px; font-weight:400; }}
.pos {{ color:var(--pos); text-shadow: 0 0 10px var(--glow); }} .neg {{ color:var(--neg); }}
ul.recs {{ list-style:none; padding:0; margin:0; }}
ul.recs li {{ padding:12px 0; border-bottom:1px solid var(--line); display: flex; align-items: center; gap: 8px; }}
ul.recs b {{ margin-right:6px; color:#fff; }}
.pri {{ font-size:10px; text-transform:uppercase; letter-spacing:.04em; border-radius:5px; padding:1px 6px;
        margin-right:8px; color:#fff; font-weight: 700; }}
.pri.high {{ background:var(--neg); }} .pri.med {{ background:var(--warn); color:#000; }} .pri.low {{ background:var(--idle); }}
.warn-t {{ color:var(--warn); }}
footer {{ margin-top:40px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); padding-top:16px; }}

/* Tabs styling */
.tabs {{ display: flex; gap: 8px; margin: 24px 0; border-bottom: 1px solid var(--line); padding-bottom: 8px; }}
.tab-btn {{ background: transparent; border: none; color: var(--muted); font-family: inherit; font-size: 14px; font-weight: 500; padding: 10px 18px; cursor: pointer; border-radius: 6px; transition: all 0.3s; }}
.tab-btn:hover {{ color: #fff; background: rgba(255,255,255,0.03); }}
.tab-btn.active {{ color: #0b0c10; background: var(--accent); font-weight: 600; box-shadow: 0 0 12px var(--accent); }}
.tab-content {{ display: none; }}

/* Collapsible Tree styling */
.tree-container {{ padding: 12px 0; }}
ul.hierarchical-tree, ul.hierarchical-tree ul {{ list-style: none; margin: 0; padding: 0 0 0 20px; position: relative; }}
ul.hierarchical-tree li {{ margin: 0; padding: 8px 0 8px 16px; position: relative; border-left: 1px solid var(--line); }}
ul.hierarchical-tree li::before {{ content: ""; position: absolute; top: 18px; left: 0; width: 12px; height: 1px; border-top: 1px solid var(--line); }}
ul.hierarchical-tree li:last-child {{ border-left: none; }}
ul.hierarchical-tree li:last-child::before {{ border-left: 1px solid var(--line); height: 18px; top: 0; }}
.tree-summary {{ cursor: pointer; font-weight: 500; padding: 6px 12px; border-radius: 6px; background: rgba(255,255,255,0.02); border: 1px solid var(--line); display: inline-flex; align-items: center; gap: 8px; outline: none; transition: all 0.3s; color:#fff; }}
.tree-summary:hover {{ border-color: var(--accent); box-shadow: 0 0 8px var(--glow); }}
.root-summary {{ border-color: var(--accent); background: var(--glow); color: #fff; font-weight: 600; }}
.tree-item {{ padding: 6px 12px; display: inline-block; border-radius: 6px; background: rgba(255,255,255,0.01); border: 1px solid var(--line); font-size: 13.5px; }}
.stake-tag {{ font-size: 11px; color: var(--accent); background: var(--glow); padding: 2px 6px; border-radius: 4px; font-weight: bold; margin-left: 4px; }}
.legend-color {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; vertical-align: middle; }}
.bar-part {{ height: 100%; transition: all 0.3s; cursor: pointer; }}
.bar-part:hover {{ opacity: 0.85; filter: brightness(1.2); }}

/* Search box styling */
.search-container {{ margin-bottom: 16px; }}
.search-input {{ width: 100%; background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 10px 16px; color: #fff; font-family: inherit; font-size: 14px; outline: none; transition: all 0.3s; }}
.search-input:focus {{ border-color: var(--accent); box-shadow: 0 0 10px var(--glow); }}

/* Decision charts */
.chart-figure {{ margin: 0 0 24px; padding: 18px 0 0; border-top: 1px solid var(--line); }}
.chart-figure:first-child {{ border-top: 0; padding-top: 0; }}
.chart {{ display: block; width: 100%; height: auto; overflow: visible; }}
.chart-grid {{ stroke: var(--line); stroke-width: 1; }}
.chart-zero {{ stroke: var(--muted); stroke-width: 1.5; }}
.chart-label {{ fill: #fff; font-size: 13px; font-weight: 600; }}
.chart-tick {{ fill: var(--muted); font-size: 11px; }}
.chart-value {{ fill: var(--ink); font-size: 12px; font-weight: 600; }}
.outcome-bar.positive {{ fill: var(--pos); }}
.outcome-bar.negative {{ fill: var(--neg); }}
.chart-figure figcaption {{ color: var(--muted); font-size: 12.5px; margin: 8px 0 0 132px; }}
.trend-chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 16px; }}
.trend-figure {{ margin: 0; padding: 14px; background: rgba(255,255,255,0.015); border: 1px solid var(--line); border-radius: 10px; }}
.trend-figure figcaption {{ display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin: 0 0 8px; }}
.trend-symbol {{ color: #fff; font-weight: 600; }}
.trend-summary {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
.trend-chart {{ display: block; width: 100%; height: auto; }}
.trend-line {{ fill: none; stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; }}
.trend-line.improving {{ stroke: var(--pos); }} .trend-line.declining {{ stroke: var(--neg); }} .trend-line.flat {{ stroke: var(--warn); }}
.trend-point.improving {{ fill: var(--pos); }} .trend-point.declining {{ fill: var(--neg); }} .trend-point.flat {{ fill: var(--warn); }}
.ranking-chart {{ max-width: 860px; }}
.rank-axis {{ display: grid; grid-template-columns: 1fr 1fr 1fr; margin: 0 94px 6px 126px; color: var(--muted); font-size: 11px; }}
.rank-axis span:nth-child(2) {{ text-align: center; }} .rank-axis span:last-child {{ text-align: right; }}
.rank-list {{ list-style: none; padding: 0; margin: 0; }}
.rank-row {{ display: grid; grid-template-columns: 112px minmax(80px, 1fr) 48px 82px; align-items: center; gap: 10px; min-height: 30px; }}
.rank-symbol {{ color: #fff; font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.rank-track {{ height: 11px; background: rgba(255,255,255,0.06); border-radius: 999px; overflow: hidden; }}
.rank-fill {{ display: block; height: 100%; background: var(--accent); border-radius: inherit; }}
.rank-score {{ color: #fff; text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; }}
.trend-marker {{ color: var(--muted); font-size: 11px; text-transform: capitalize; }}
.trend-marker.improving {{ color: var(--pos); }} .trend-marker.declining {{ color: var(--neg); }}
@media (max-width: 620px) {{
  .wrap {{ padding: 24px 14px 56px; }}
  .tabs {{ overflow-x: auto; }}
  .tab-btn {{ white-space: nowrap; padding: 9px 12px; }}
  .chart-label {{ font-size: 12px; }}
  .chart-figure figcaption {{ margin-left: 0; }}
  .rank-axis {{ margin-left: 88px; margin-right: 0; }}
  .rank-row {{ grid-template-columns: 76px minmax(60px, 1fr) 40px; gap: 7px; }}
  .trend-marker {{ display: none; }}
}}
</style>
<script>
function showTab(id, btn) {{
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(id).style.display = 'block';
    btn.classList.add('active');
}}
function filterCards() {{
    let input = document.getElementById('symbol-search').value.toUpperCase();
    document.querySelectorAll('.card').forEach(card => {{
        let text = card.querySelector('.card-h').innerText.toUpperCase();
        if (text.includes(input)) {{
            card.style.display = 'block';
        }} else {{
            card.style.display = 'none';
        }}
    }});
}}
</script>
</head><body><div class="wrap">
<h1>Kestrel — Operator Dashboard</h1>
<div class="sub">Generated {html.escape(state["generated"])} · single-user, on-host (data stays local)</div>
<div class="sub">Static snapshot — re-run <code>python scripts/dashboard.py</code> to refresh (the daily <code>morning.ps1</code> does this automatically). The token expires 06:00 IST daily, so it reads EXPIRED until the next morning mint.</div>

<div class="tabs">
  <button class="tab-btn active" onclick="showTab('tab-overview', this)">Overview &amp; Pipeline</button>
  <button class="tab-btn" onclick="showTab('tab-baskets', this)">🏆 Factor Baskets &amp; Potential Rankings</button>
  <button class="tab-btn" onclick="showTab('tab-relations', this)">Corporate Hierarchy &amp; Mapped Data</button>
  <button class="tab-btn" onclick="showTab('tab-trends', this)">Fundamental Trends &amp; Slices</button>
  <button class="tab-btn" onclick="showTab('tab-recs', this)">Recommendations</button>
</div>

<!-- TAB 1: OVERVIEW -->
<div id="tab-overview" class="tab-content" style="display: block;">
  <h2>What the pipeline is doing</h2>
  {_pipeline(state)}
  
  <h2>Background Activity Monitor</h2>
  <div class="panel">{_worker_console_section(state)}</div>
  
  <h2>Data status</h2>
  <div class="panel">{_data_section(state)}</div>
</div>

<!-- TAB 2: BASKETS -->
<div id="tab-baskets" class="tab-content">
  <h2>Instruments Ranked by Potential (Most to Least)</h2>
  {_baskets_section(state)}
</div>

<!-- TAB 3: CORPORATE RELATIONS -->
<div id="tab-relations" class="tab-content">
  <h2>Corporate Relations &amp; Segments</h2>
  {_relations_section(state)}
</div>

<!-- TAB 4: TRENDS & SLICES -->
<div id="tab-trends" class="tab-content">
  <div class="search-container">
    <input type="text" id="symbol-search" class="search-input" onkeyup="filterCards()" placeholder="Search symbol/findings...">
  </div>
  <h2>Findings — vertical slice on real data</h2>
  {_findings_section(state)}
  
  <h2>Fundamental trends — improving vs declining</h2>
  <div class="panel">{_trends_section(state)}</div>
</div>

<!-- TAB 5: RECS -->
<div id="tab-recs" class="tab-content">
  <h2>Recommendations &amp; pending decisions</h2>
  <div class="panel">{_recs_section(state)}</div>
</div>

<footer>
On-host only. This page embeds market-data-derived figures and must not be shared,
published, or transmitted (Kite licence, G-15). It is regenerated by
<code>scripts/dashboard.py</code>. The daily routine is <code>deploy/scheduler/morning.ps1</code>.
</footer>
</div>
<script>
function showTab(tabId, btn) {{
  document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(tabId).style.display = 'block';
  btn.classList.add('active');
}}
function selectRelationCompany(selectEl) {{
  var selected = selectEl.value;
  document.querySelectorAll('[data-company-pane]').forEach(function(pane) {{
    if (pane.getAttribute('data-company-pane') === selected) {{
      pane.removeAttribute('hidden');
      pane.style.display = 'block';
    }} else {{
      pane.setAttribute('hidden', 'hidden');
      pane.style.display = 'none';
    }}
  }});
}}
function filterCards() {{
  var q = document.getElementById('symbol-search').value.toUpperCase();
  document.querySelectorAll('.card').forEach(c => {{
    var text = c.textContent.toUpperCase();
    c.style.display = text.indexOf(q) > -1 ? 'block' : 'none';
  }});
}}
const API_BASE = (window.location.protocol === 'http:' || window.location.protocol === 'https:') ? '' : 'http://localhost:8000';

function submitRedirect() {{
  const inputEl = document.getElementById('redirect-input');
  const val = inputEl ? inputEl.value.trim() : '';
  const msgBox = document.getElementById('token-mint-msg');
  if (!val) {{
    if (msgBox) {{ msgBox.style.color = 'var(--neg)'; msgBox.innerText = '⚠️ Please paste the redirect URL or request_token first.'; }}
    return;
  }}
  if (msgBox) {{ msgBox.style.color = 'var(--accent)'; msgBox.innerText = 'Exchanging token & running reference snapshot...'; }}
  fetch(API_BASE + '/api/token/mint', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ redirect: val }})
  }})
  .then(r => r.json())
  .then(data => {{
    if (data.ok) {{
      if (msgBox) {{ msgBox.style.color = 'var(--ok)'; msgBox.innerText = data.message; }}
      if (inputEl) inputEl.value = '';
      pollStatus();
    }} else {{
      if (msgBox) {{ msgBox.style.color = 'var(--neg)'; msgBox.innerText = '✗ ' + (data.error || 'Token minting failed'); }}
    }}
  }})
  .catch(err => {{
    if (msgBox) {{ msgBox.style.color = 'var(--neg)'; msgBox.innerText = '⚠️ Control Server offline. Run: python scripts/server.py'; }}
  }});
}}

function callApi(endpoint, loadingMsg) {{
  const statusBox = document.getElementById('api-status-msg');
  if (statusBox) {{ statusBox.innerText = loadingMsg; }}
  fetch(API_BASE + endpoint, {{ method: 'POST' }})
    .then(r => r.json())
    .then(data => {{
      if (statusBox) {{ statusBox.innerText = data.message || 'Done'; }}
      if (data.login_url) {{ window.open(data.login_url, '_blank'); }}
      pollStatus();
    }})
    .catch(err => {{
      if (statusBox) {{ statusBox.innerText = '⚠️ Control Server offline. Run: python scripts/server.py'; }}
    }});
}}
function pollStatus() {{
  fetch(API_BASE + '/api/status')
    .then(r => r.json())
    .then(data => {{
      const wk = data.worker;
      if (wk) {{
        const statusEl = document.getElementById('worker-status-badge');
        if (statusEl) {{
          statusEl.innerText = wk.status;
          statusEl.style.color = wk.status === 'RUNNING' ? 'var(--ok)' : 'var(--neg)';
        }}
        const dotEl = document.getElementById('worker-status-dot');
        if (dotEl) {{
          dotEl.style.background = wk.status === 'RUNNING' ? 'var(--ok)' : 'var(--neg)';
          dotEl.style.boxShadow = '0 0 8px ' + (wk.status === 'RUNNING' ? 'var(--ok)' : 'var(--neg)');
        }}
        const pidEl = document.getElementById('worker-pid');
        if (pidEl) {{ pidEl.innerText = 'PID: ' + (wk.pid || 'N/A') + ' · Last Cycle: ' + (wk.last_cycle || 'Never'); }}
        const consoleEl = document.getElementById('worker-console-log');
        if (consoleEl && wk.logs) {{ consoleEl.innerText = wk.logs.join(String.fromCharCode(10)); }}
      }}
      const tok = data.token;
      if (tok) {{
        const tokText = document.getElementById('token-status-text');
        if (tokText) {{
          tokText.innerText = (tok.valid ? "valid" : "EXPIRED — run login_starter.ps1") + " · until " + tok.expires_at;
        }}
        const tokDot = document.getElementById('token-status-dot');
        if (tokDot) {{
          tokDot.className = "dot " + (tok.valid ? "ok" : "warn");
        }}
      }}
    }})
    .catch(() => {{}});
}}
setInterval(pollStatus, 3000);
pollStatus();
</script>
</body></html>"""


def main() -> None:
    state = gather()
    OUT.write_text(render(state), encoding="utf-8")
    print(f"Wrote {OUT.resolve()}")
    print("Open it in your browser (double-click, or: start dashboard.html)")


if __name__ == "__main__":
    main()
