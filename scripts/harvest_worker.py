"""Background fundamentals worker — keeps the store current while the system runs.

Polite and resumable: each cycle ingests only filings the store does not already
have (`store.has`), rate-limited, then sleeps until the next cycle. After the
first full pass, cycles are cheap (almost all skips, no network) and just idle-
check for newly-filed results. Safe to stop (Ctrl-C, or Task Scheduler end) and
restart — it resumes where it left off; a second instance won't start while one
is alive (PID lock).

    python scripts/harvest_worker.py                  # loop, 6h cycles
    python scripts/harvest_worker.py --once           # a single cycle, then exit
    python scripts/harvest_worker.py --interval 3600  # hourly

Launch it detached (and auto-start at logon) with deploy/scheduler/
harvest_worker.ps1; morning.ps1 also ensures it is running.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kestrel.data.filings import NSEFilingsSource
from kestrel.data.fundamentals_store import FundamentalsStore
from kestrel.data.nse_http import make_nse_getter
from scripts.harvest_fundamentals import STORE_ROOT, run_harvest

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG = Path("logs/fundamentals_worker.log")
STATUS = Path("logs/fundamentals_worker_status.json")
PIDFILE = Path("logs/fundamentals_worker.pid")
_stop = {"flag": False}


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _sleep(seconds: float) -> None:
    """Interruptible sleep in 1s steps so a stop request is responsive."""
    for _ in range(int(seconds)):
        if _stop["flag"]:
            return
        time.sleep(1)


def _write_status(counts: dict, symbols: int) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    STATUS.write_text(json.dumps({"last_cycle": ts, "symbols": symbols, **counts}, indent=2))


def _pid_alive(pid: int) -> bool:
    if os.name == 'nt':
        try:
            import subprocess
            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], encoding="utf-8", creationflags=0x08000000)
            return str(pid) in out
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def _acquire_lock() -> bool:
    if PIDFILE.exists():
        try:
            other = int(PIDFILE.read_text().strip())
            if other != os.getpid() and _pid_alive(other):
                # A duplicate-start attempt is normal (Task Scheduler, morning.ps1,
                # a dashboard click). Keep it OUT of the streamed worker log — that
                # log should show real harvest cycles, not lock rejections — so
                # print to stdout only.
                print(f"another worker already running (pid {other}) — exiting", flush=True)
                return False
        except (ValueError, OSError):
            pass
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(str(os.getpid()))
    return True


def _cycle(pause: float) -> None:
    src = NSEFilingsSource(http=make_nse_getter())
    store = FundamentalsStore(STORE_ROOT)
    c = run_harvest(src, store, date(2000, 1, 1), pause=pause,
                    sleep=_sleep, log=_log, should_stop=lambda: _stop["flag"])
    n = len(store.symbols())

    # Automate corporate relations, segments, and industry extraction
    try:
        from kestrel.data.relations_extractor import harvest_all_relations
        rel_res = harvest_all_relations(STORE_ROOT, REPO_ROOT / "data/relations")
        _log(f"relations updated: +{rel_res['relations_added']} rels, "
             f"+{rel_res['segments_added']} segs, +{rel_res['industry_added']} ind")
    except Exception as e:
        _log(f"relations extraction error: {e}")

    _log(f"cycle done: +{c['written']} new, {c['skipped']} already-had, "
         f"{c['errors']} err; store holds {n} symbol(s)")
    _write_status(c, n)


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main() -> int:
    interval = int(_arg("--interval", "21600"))   # 6h
    pause = float(_arg("--pause", "0.3"))
    once = "--once" in sys.argv

    def _handler(_sig, _frame):
        _stop["flag"] = True
        _log("stop requested")

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, AttributeError):
        pass

    if not _acquire_lock():
        return 0

    _log(f"worker starting (interval {interval}s, pause {pause}s, once={once})")
    try:
        while not _stop["flag"]:
            try:
                _cycle(pause)
            except Exception as e:  # noqa: BLE001 — a bad cycle backs off, never dies
                _log(f"cycle error: {type(e).__name__}: {e} — backing off 5 min")
                if once:
                    break
                _sleep(300)
                continue
            if once:
                break
            _sleep(interval)
    finally:
        try:
            if PIDFILE.exists() and PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink()
        except OSError:
            pass
        _log("worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
