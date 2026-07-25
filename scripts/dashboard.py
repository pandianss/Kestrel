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

from kestrel.data.pit import build_nse_equity_universe, build_pit_universe
from kestrel.data.snapshot import SnapshotStore
from kestrel.kite.tokenstore import FileTokenStore

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_slice import run_slice  # noqa: E402  (reuse the exact slice computation)

TOKEN_PATH = "data/secrets/kite_token.json"
SNAPSHOT_ROOT = "data/snapshots"
KITE_CACHE = "data/cache/kite"
OUT = Path("dashboard.html")


# ---------------------------------------------------------------- gather ----

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
            eq = build_nse_equity_universe(store)
            uni["equity"] = len(eq.members_asof(latest))
            uni["all"] = len(build_pit_universe(store, source_prefix=None).members_asof(latest))
        except Exception:  # noqa: BLE001
            uni["equity"] = None
    state["universe"] = uni

    # historical cache + findings (slice per cached symbol)
    caches = sorted(glob.glob(f"{KITE_CACHE}/*_day.pkl"))
    hist, findings = [], []
    for p in caches:
        sym = Path(p).stem.replace("_day", "")
        try:
            df = pd.read_pickle(p)
            hist.append({"symbol": sym, "bars": len(df),
                         "first": df.index[0].date().isoformat(),
                         "last": df.index[-1].date().isoformat()})
            findings.append(run_slice(sym))
        except Exception:  # noqa: BLE001
            continue
    state["history"] = hist
    state["findings"] = findings

    state["recommendations"] = _recommendations(state)
    return state


def _recommendations(state: dict) -> list[dict]:
    recs = [
        {"pri": "high", "title": "Rotate the API secret",
         "why": "It was shared in chat/screenshot on 2026-07-24 — regenerate it in the Kite developer console."},
        {"pri": "med", "title": "Decide a stock-universe source",
         "why": "The instruments filter yields ~9.8k cash-segment names incl. bonds/ETFs, not a clean stock list. Index constituents (e.g. NIFTY 500 by date) also fixes survivorship (G-43)."},
        {"pri": "med", "title": "Decide a point-in-time fundamentals source",
         "why": "Needed for the value factor; Kite provides none (vendor / screener.in / filings)."},
        {"pri": "med", "title": "Decide a dividend-events source",
         "why": "Kite adjusts splits/bonuses only; ex-div gaps are artefacts until a dividend feed drives adjust_for_dividends (G-08)."},
        {"pri": "low", "title": "Static IP — only at live-order stage",
         "why": "Not needed for research/data. Source an ISP static IP or small Indian relay box before placing live orders (D-18)."},
    ]
    return recs


# ---------------------------------------------------------------- render ----

def _dot(state: str) -> str:
    return f'<span class="dot {state}"></span>'


def _pipeline(state: dict) -> str:
    tok_ok = state["token"]["ok"]
    uni = state["universe"]
    stages = [
        ("Daily token", "ok" if tok_ok else "warn",
         state["token"]["text"]),
        ("Universe capture", "ok" if uni.get("dates") else "warn",
         f"{uni.get('dates', 0)} day(s) archived" + (f", {uni['last']} latest" if uni.get('last') else "")),
        ("Historical prices", "ok" if state["history"] else "idle",
         f"{len(state['history'])} symbol(s) cached"),
        ("Backtest + exit path", "ok" if state["findings"] else "idle",
         f"{len(state['findings'])} slice(s) run"),
    ]
    rows = "".join(
        f'<div class="stage">{_dot(s)}<div><b>{html.escape(name)}</b>'
        f'<span class="muted">{html.escape(detail)}</span></div></div>'
        for name, s, detail in stages
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
    return f'<table class="kv">{"".join(rows)}</table>'


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
    return f'<div class="cards">{"".join(cards)}</div>{caveat}'


def _recs_section(state: dict) -> str:
    order = {"high": 0, "med": 1, "low": 2}
    items = sorted(state["recommendations"], key=lambda r: order.get(r["pri"], 9))
    lis = "".join(
        f'<li><span class="pri {r["pri"]}">{r["pri"]}</span>'
        f'<b>{html.escape(r["title"])}</b><span class="muted">{html.escape(r["why"])}</span></li>'
        for r in items
    )
    return f'<ul class="recs">{lis}</ul>'


def render(state: dict) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kestrel — Operator Dashboard</title>
<style>
:root {{ --bg:#fafafa; --card:#fff; --ink:#1a1a1a; --muted:#6b7280; --line:#e5e7eb;
        --ok:#16a34a; --warn:#d97706; --idle:#9ca3af; --neg:#dc2626; --pos:#16a34a; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --card:#171a21; --ink:#e6e6e6;
        --muted:#9aa3b2; --line:#262b36; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }}
.wrap {{ max-width:940px; margin:0 auto; padding:28px 20px 60px; }}
h1 {{ font-size:20px; margin:0 0 2px; }}
h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:30px 0 12px; }}
.sub {{ color:var(--muted); font-size:13px; margin-bottom:8px; }}
.panel {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; }}
.stages {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; }}
.stage {{ display:flex; gap:10px; align-items:flex-start; background:var(--card); border:1px solid var(--line);
         border-radius:10px; padding:12px 14px; }}
.stage b {{ display:block; font-size:14px; }}
.dot {{ width:9px; height:9px; border-radius:50%; margin-top:5px; flex:0 0 auto; }}
.dot.ok {{ background:var(--ok); }} .dot.warn {{ background:var(--warn); }} .dot.idle {{ background:var(--idle); }}
.muted {{ color:var(--muted); font-size:12.5px; display:block; margin-top:2px; }}
table.kv {{ width:100%; border-collapse:collapse; }}
table.kv td {{ padding:7px 4px; border-bottom:1px solid var(--line); vertical-align:top; }}
table.kv td.k {{ color:var(--muted); width:38%; }}
table.kv.small td {{ padding:4px 2px; font-size:13px; border-bottom:1px dotted var(--line); }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.card-h {{ font-weight:600; margin-bottom:6px; }}
.tag {{ font-size:11px; color:var(--muted); border:1px solid var(--line); border-radius:6px; padding:1px 6px; }}
.big {{ font-size:24px; font-weight:700; margin:2px 0 8px; }}
.big .muted {{ display:inline; font-size:13px; font-weight:400; }}
.pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }}
ul.recs {{ list-style:none; padding:0; margin:0; }}
ul.recs li {{ padding:10px 0; border-bottom:1px solid var(--line); }}
ul.recs b {{ margin-right:6px; }}
.pri {{ font-size:10px; text-transform:uppercase; letter-spacing:.04em; border-radius:5px; padding:1px 6px;
        margin-right:8px; color:#fff; }}
.pri.high {{ background:var(--neg); }} .pri.med {{ background:var(--warn); }} .pri.low {{ background:var(--idle); }}
.warn-t {{ color:var(--warn); }}
footer {{ margin-top:36px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); padding-top:14px; }}
</style></head><body><div class="wrap">
<h1>Kestrel — Operator Dashboard</h1>
<div class="sub">Generated {html.escape(state["generated"])} · single-user, on-host (data stays local)</div>

<h2>What the pipeline is doing</h2>
{_pipeline(state)}

<h2>Data status</h2>
<div class="panel">{_data_section(state)}</div>

<h2>Findings — vertical slice on real data</h2>
{_findings_section(state)}

<h2>Recommendations &amp; pending decisions</h2>
<div class="panel">{_recs_section(state)}</div>

<footer>
On-host only. This page embeds market-data-derived figures and must not be shared,
published, or transmitted (Kite licence, G-15). It is regenerated by
<code>scripts/dashboard.py</code>. The daily routine is <code>deploy/scheduler/morning.ps1</code>.
</footer>
</div></body></html>"""


def main() -> None:
    state = gather()
    OUT.write_text(render(state), encoding="utf-8")
    print(f"Wrote {OUT.resolve()}")
    print("Open it in your browser (double-click, or: start dashboard.html)")


if __name__ == "__main__":
    main()
