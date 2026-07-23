#!/usr/bin/env bash
# Daily reference-data snapshot runner (doc 10 §3.1). Invoked by the systemd
# timer or cron on the deployment host. Runs the snapshot in require-live mode
# so it NEVER archives dev data as a real trading-day snapshot — if today's
# token has not been minted, it exits non-zero and the scheduler surfaces it.
#
# Reads no secrets: the access_token was already minted and stored by the
# operator's morning login (scripts/kite_login.py). This script only reads it.
#
# Env:
#   KESTREL_HOME   repo root (default: two levels up from this script)
#   KESTREL_PYTHON python interpreter (default: $KESTREL_HOME/.venv/bin/python)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KESTREL_HOME="${KESTREL_HOME:-$(cd "$HERE/../.." && pwd)}"
KESTREL_PYTHON="${KESTREL_PYTHON:-$KESTREL_HOME/.venv/bin/python}"
LOG_DIR="${KESTREL_LOG_DIR:-$KESTREL_HOME/logs}"

cd "$KESTREL_HOME"
mkdir -p "$LOG_DIR"

# Fall back to whatever python is on PATH if the venv is absent.
if [[ ! -x "$KESTREL_PYTHON" ]]; then
  KESTREL_PYTHON="$(command -v python3 || command -v python)"
fi

export PYTHONPATH="${PYTHONPATH:-$KESTREL_HOME}"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[$ts] daily_snapshot start (python=$KESTREL_PYTHON)" >> "$LOG_DIR/snapshot.log"

# require-live: no valid token -> exit 3, nothing written. Tee so both the
# systemd journal and the rolling log get it.
set +e
"$KESTREL_PYTHON" scripts/snapshot_reference.py --require-live 2>&1 | tee -a "$LOG_DIR/snapshot.log"
rc="${PIPESTATUS[0]}"
set -e

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ "$rc" -eq 0 ]]; then
  echo "[$ts] daily_snapshot ok" >> "$LOG_DIR/snapshot.log"
elif [[ "$rc" -eq 3 ]]; then
  echo "[$ts] daily_snapshot: NO TOKEN — operator must run kite_login.py (rc=3)" >> "$LOG_DIR/snapshot.log"
else
  echo "[$ts] daily_snapshot FAILED rc=$rc" >> "$LOG_DIR/snapshot.log"
fi
exit "$rc"
