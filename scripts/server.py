"""Kestrel Mission Control HTTP Server & REST API.

Provides a lightweight, zero-dependency control server on http://localhost:8000:
- Serves dashboard.html and local assets
- Exposes REST API for live process status, log streaming, and process lifecycle controls
- Allows starting/stopping the fundamentals harvester, history harvester, and refreshing dashboard

Usage:
    python scripts/server.py                  # Start server on port 8000
    python scripts/server.py --port 8080       # Custom port
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kestrel.kite.tokenstore import FileTokenStore

PORT = 8000
DASHBOARD_FILE = REPO_ROOT / "dashboard.html"
TOKEN_PATH = REPO_ROOT / "data/secrets/kite_token.json"
PID_FILE = REPO_ROOT / "logs/fundamentals_worker.pid"
STATUS_FILE = REPO_ROOT / "logs/fundamentals_worker_status.json"
LOG_FILE = REPO_ROOT / "logs/fundamentals_worker.log"
CACHE_DIR = REPO_ROOT / "data/cache/kite"
FUNDAMENTALS_DIR = REPO_ROOT / "data/fundamentals"
SNAPSHOTS_DIR = REPO_ROOT / "data/snapshots"


def is_pid_alive(pid: int) -> bool:
    if os.name == 'nt':
        try:
            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], encoding="utf-8")
            return str(pid) in out
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def get_system_status() -> dict:
    now = datetime.now(timezone.utc)
    
    # 1. Token status
    token_valid = False
    token_exp = "Expired / Missing"
    try:
        tstore = FileTokenStore(TOKEN_PATH)
        tok = tstore.load()
        if tok is not None:
            token_valid = tok.is_valid(now)
            token_exp = tok.expires_at
    except Exception:
        pass

    # 2. Fundamentals Worker status
    worker_status = "STOPPED"
    worker_pid = None
    last_cycle = "Never"
    log_lines = []

    if PID_FILE.exists():
        try:
            worker_pid = int(PID_FILE.read_text().strip())
            if is_pid_alive(worker_pid):
                worker_status = "RUNNING"
        except Exception:
            pass

    if STATUS_FILE.exists():
        try:
            sdata = json.loads(STATUS_FILE.read_text("utf-8"))
            last_cycle = sdata.get("last_cycle", "Never")
        except Exception:
            pass

    if LOG_FILE.exists():
        try:
            lines = LOG_FILE.read_text("utf-8").splitlines()
            log_lines = lines[-8:]
        except Exception:
            pass

    # 3. Counts
    cached_history = len(list(CACHE_DIR.glob("*.pkl"))) if CACHE_DIR.exists() else 0
    fundamentals_count = len(list(FUNDAMENTALS_DIR.glob("*.jsonl"))) if FUNDAMENTALS_DIR.exists() else 0
    relations_dir = REPO_ROOT / "data/relations/segments"
    relations_count = len(list(relations_dir.glob("*.jsonl"))) if relations_dir.exists() else 0

    return {
        "generated_at": now.isoformat(),
        "token": {
            "valid": token_valid,
            "expires_at": token_exp
        },
        "worker": {
            "status": worker_status,
            "pid": worker_pid,
            "last_cycle": last_cycle,
            "logs": log_lines
        },
        "counts": {
            "cached_history_symbols": cached_history,
            "fundamentals_symbols": fundamentals_count,
            "relations_symbols": relations_count,
        }
    }


def get_decrypted_credentials() -> tuple[str, str]:
    token_path = REPO_ROOT / "data/secrets/kite_token.json"
    if token_path.exists():
        try:
            tdata = json.loads(token_path.read_text("utf-8"))
            if tdata.get("api_key"):
                return tdata["api_key"], "3ld4jsseopfhr5y18nztyvqtkojp47su"
        except Exception:
            pass
    return "97x3bf78zyoncg1p", "3ld4jsseopfhr5y18nztyvqtkojp47su"


def mint_token_from_redirect(redirect_input: str) -> dict:
    from kestrel.kite.auth import exchange_request_token, extract_request_token
    from kestrel.kite.tokenstore import FileTokenStore

    req_token = extract_request_token(redirect_input.strip())
    api_key, api_secret = get_decrypted_credentials()
    now = datetime.now(timezone.utc)

    token_record = exchange_request_token(api_key, api_secret, req_token, now=now)
    store = FileTokenStore(TOKEN_PATH)
    store.save(token_record)

    # Asynchronously run reference snapshot & dashboard refresh in background thread
    def _bg_post_mint():
        try:
            subprocess.run([sys.executable, "scripts/snapshot_reference.py"], cwd=str(REPO_ROOT), check=False)
            subprocess.run([sys.executable, "scripts/dashboard.py"], cwd=str(REPO_ROOT), check=False)
        except Exception:
            pass

    import threading
    threading.Thread(target=_bg_post_mint, daemon=True).start()

    return {
        "ok": True,
        "message": f"✓ Token minted successfully! User: {token_record.user_id}, Expires at: {token_record.expires_at}",
        "user_id": token_record.user_id,
        "expires_at": token_record.expires_at
    }


class MissionControlHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict, code: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, file_path: Path, content_type: str = "text/html") -> None:
        if not file_path.exists():
            self.send_error(404, "File Not Found")
            return
        raw = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_html(self, markup: str) -> None:
        raw = markup.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/", "/dashboard.html"):
            # Render LIVE from precomputed artifacts (fast, ~0.7s) so the page is
            # always current — no stale static file. Falls back to the file if the
            # live render ever fails.
            try:
                import importlib
                import scripts.dashboard as dash
                importlib.reload(dash)
                self._send_html(dash.render_live(dash.gather_live(get_system_status())))
            except Exception:
                self._send_file(DASHBOARD_FILE, "text/html")
        elif path == "/api/status":
            self._send_json(get_system_status())
        elif path == "/api/backtest/progress":
            p = REPO_ROOT / "data/backtest_progress.json"
            try:
                self._send_json(json.loads(p.read_text(encoding="utf-8")) if p.exists()
                                else {"status": "idle"})
            except Exception:
                self._send_json({"status": "idle"})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        
        if path == "/api/token/mint":
            try:
                content_len = int(self.headers.get('Content-Length', 0))
                post_body = self.rfile.read(content_len).decode('utf-8') if content_len > 0 else ""
                pdata = json.loads(post_body) if post_body else {}
                redirect_url = pdata.get("redirect", "").strip()
                
                if not redirect_url:
                    self._send_json({"ok": False, "error": "Redirect URL or request_token cannot be empty"}, 200)
                    return
                
                res = mint_token_from_redirect(redirect_url)
                self._send_json(res, 200)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 200)

        elif path == "/api/worker/start":
            # Start harvest_worker.py in background
            status = get_system_status()
            if status["worker"]["status"] == "RUNNING":
                self._send_json({"ok": True, "message": f"Worker is already running (PID {status['worker']['pid']})", "pid": status["worker"]["pid"]})
                return
            
            # Unlink stale PID file if worker is not running
            if PID_FILE.exists():
                try:
                    PID_FILE.unlink(missing_ok=True)
                except Exception:
                    pass

            try:
                flags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                proc = subprocess.Popen([sys.executable, "scripts/harvest_worker.py"], cwd=str(REPO_ROOT), creationflags=flags)
                self._send_json({"ok": True, "message": f"Started harvester worker (PID {proc.pid})", "pid": proc.pid})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        elif path == "/api/worker/stop":
            # Stop harvest_worker.py
            if PID_FILE.exists():
                try:
                    pid = int(PID_FILE.read_text().strip())
                    if os.name == 'nt':
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
                    else:
                        os.kill(pid, signal.SIGTERM)
                    PID_FILE.unlink(missing_ok=True)
                    self._send_json({"ok": True, "message": f"Stopped harvester worker (PID {pid})"})
                except Exception as e:
                    self._send_json({"ok": False, "error": str(e)}, 500)
            else:
                self._send_json({"ok": True, "message": "Worker was not running"})

        elif path == "/api/login/start":
            try:
                ps_script = str(REPO_ROOT / "deploy/scheduler/login_starter.ps1")
                cmd = f'cmd /c start powershell -NoProfile -ExecutionPolicy Bypass -File "{ps_script}"'
                subprocess.Popen(cmd, shell=True, cwd=str(REPO_ROOT))

                self._send_json({
                    "ok": True,
                    "message": "Launched login starter window on desktop",
                })
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        elif path == "/api/history/start":
            # Start harvest_history.py
            try:
                flags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                proc = subprocess.Popen([sys.executable, "scripts/harvest_history.py"], cwd=str(REPO_ROOT), creationflags=flags)
                self._send_json({"ok": True, "message": f"Started history harvester (PID {proc.pid})", "pid": proc.pid})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        elif path == "/api/relations/harvest":
            # Start harvest_relations.py
            try:
                flags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                proc = subprocess.Popen([sys.executable, "scripts/harvest_relations.py"], cwd=str(REPO_ROOT), creationflags=flags)
                self._send_json({"ok": True, "message": f"Started corporate relations harvester (PID {proc.pid})", "pid": proc.pid})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        elif path == "/api/dashboard/refresh":
            try:
                res = subprocess.run([sys.executable, "scripts/dashboard.py"], cwd=str(REPO_ROOT), capture_output=True, text=True)
                if res.returncode == 0:
                    self._send_json({"ok": True, "message": "Dashboard regenerated successfully"})
                else:
                    self._send_json({"ok": False, "error": res.stderr}, 500)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        elif path in ("/api/ranking/refresh", "/api/backtest/run",
                      "/api/book/rebalance", "/api/book/exits"):
            # Fire-and-forget background jobs; the live dashboard reflects the
            # updated artifacts (ranking / backtest / paper book) on its next refresh.
            jobs = {
                "/api/ranking/refresh": (["scripts/rank_baskets.py"],
                                         "Ranking refresh started (rank_baskets.py)."),
                "/api/backtest/run": (["scripts/backtest_ranking.py", "--n", "10",
                                       "--pit-universe", "--sector-val", "--quarterly", "--save"],
                                      "Backtest started; the Backtest tab updates when done."),
                "/api/book/rebalance": (["scripts/mock_trade.py", "--rebalance"],
                                        "Quarterly rebalance started."),
                "/api/book/exits": (["scripts/mock_trade.py", "--check-exits"],
                                    "Trailing-stop exit check started."),
            }
            argv, msg = jobs[path]
            if path == "/api/backtest/run":   # seed progress so the bar shows instantly
                try:
                    (REPO_ROOT / "data/backtest_progress.json").write_text(
                        json.dumps({"status": "running", "pct": 0, "phase": "starting…"}),
                        encoding="utf-8")
                except Exception:
                    pass
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                (REPO_ROOT / "logs").mkdir(exist_ok=True)
                log = open(REPO_ROOT / "logs" / (Path(argv[0]).stem + ".out.log"), "ab")
                subprocess.Popen([sys.executable, *argv], cwd=str(REPO_ROOT),
                                 stdout=log, stderr=log, creationflags=flags)
                self._send_json({"ok": True, "message": msg})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        else:
            self.send_error(404, "Unknown POST endpoint")


def ensure_worker_running() -> str:
    """Start the fundamentals worker if it isn't already running (idempotent).
    Called on server startup so bringing up Mission Control brings up the whole
    background pipeline. Windowless so it doesn't pop a console."""
    status = get_system_status()
    if status["worker"]["status"] == "RUNNING":
        return f"worker already running (pid {status['worker']['pid']})"
    if PID_FILE.exists():
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
    proc = subprocess.Popen([sys.executable, "scripts/harvest_worker.py"],
                            cwd=str(REPO_ROOT), creationflags=flags)
    return f"started worker (pid {proc.pid})"


def run_server(port: int = PORT) -> None:
    # Bring up the background worker as part of startup (idempotent).
    try:
        print(f"  worker: {ensure_worker_running()}")
    except Exception as e:  # noqa: BLE001
        print(f"  worker: could not auto-start ({e})")
    # Bind to loopback ONLY. This server can start/stop processes and mint
    # tokens, so it must never be reachable from the network — on-host operator
    # control plane only (matches the design's on-host posture, D-18 / doc 10).
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, MissionControlHandler)
    print(f"============================================================")
    print(f"  Kestrel Mission Control Server")
    print(f"  Listening on: http://localhost:{port}")
    print(f"  Open http://localhost:{port} in your browser to view dashboard")
    print(f"============================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Mission Control Server...")
        httpd.server_close()


if __name__ == "__main__":
    p = PORT
    if "--port" in sys.argv:
        p = int(sys.argv[sys.argv.index("--port") + 1])
    run_server(p)
