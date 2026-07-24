# Daily scheduler — reference-data snapshot

Automates the one job that **must** run every trading day and cannot be
backfilled: the point-in-time reference snapshot (G-43 / D-15). Every skipped
day is research data permanently lost.

## The split that matters

The daily login **cannot** be automated — it needs a real Kite login with 2FA
(the G-12 ToS line). So the two morning steps are deliberately different:

| Step | Who | When | What happens if skipped |
|---|---|---|---|
| Mint the token — `scripts/kite_login.py` | **Operator** (browser, 2FA) | Morning, before 09:30 IST | The snapshot exits 3 and alerts; no data written |
| Snapshot the universe — this scheduler | **Automated** | 09:30 IST, Mon–Fri | — |

The scheduler runs the snapshot in `--require-live` mode: with no valid token
it **exits 3 and writes nothing**, rather than silently archiving the dev
fallback as if it were a real trading-day snapshot. That non-zero exit is the
signal that the operator hasn't logged in yet — treated as an expected state
(`SuccessExitStatus=0 3`), not a crash.

## Windows — the operator's PC (D-18), the primary path

The host is a Windows PC (D-18), and the login needs a browser 2FA (G-12) that
cannot be unattended, so the daily driver is **one command you run each morning**
rather than a background job:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\scheduler\morning.ps1
```

`morning.ps1` sets the credentials (prompting for the secret as a SecureString
if it isn't already in the environment — never written to disk), runs the
operator-in-the-loop login, and — only if a valid token results — captures the
live snapshot in `--require-live`. About a minute, once a day.

**Optional backstop.** `snapshot_task.ps1` runs the snapshot *only* (no secrets —
it reads the already-minted token) and exits 3 if you haven't logged in yet.
Register it as a daily Task Scheduler job so that if you log in but forget to
snapshot, it still captures:

```powershell
$ps  = (Get-Command powershell).Source
$arg = '-NoProfile -ExecutionPolicy Bypass -File "' +
       (Resolve-Path deploy\scheduler\snapshot_task.ps1).Path + '"'
schtasks /Create /TN "Kestrel Snapshot" /TR "$ps $arg" /SC DAILY /ST 09:35 /F
```

(Task Scheduler fires in the host's local time; on an India PC that is IST.)

## Install (systemd — only if you move to a Linux host/relay)

Not needed for the Windows PC above. For a future Linux host (e.g. the small
order-path relay of D-18), assumes the repo at `/opt/kestrel`, a `.venv` there,
and a non-root `kestrel` service user owning the repo and `data/`.

```bash
sudo cp deploy/scheduler/kestrel-snapshot.service /etc/systemd/system/
sudo cp deploy/scheduler/kestrel-snapshot.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kestrel-snapshot.timer

systemctl list-timers kestrel-snapshot.timer   # confirm next fire (IST)
journalctl -u kestrel-snapshot.service -n 50   # see the last run
```

The timer pins `Asia/Kolkata`, so it fires at the right IST moment regardless
of the host clock (systemd ≥ 252), and `Persistent=true` catches a run missed
to downtime on the next boot.

## Install (cron alternative)

See [`crontab.example`](crontab.example). Set `CRON_TZ=Asia/Kolkata` — cron
otherwise fires in the host's local timezone.

## Local testing (Windows / any OS)

The runner is bash; on Windows use Git Bash, or just call the script directly:

```bash
python scripts/snapshot_reference.py --require-live   # exits 3 with no token
python scripts/kite_login.py                          # mint a token, then:
python scripts/snapshot_reference.py --require-live   # archives the real master
```

## What this does NOT schedule yet

Only reference-data capture. Tick ingestion, backfill, and the research jobs
are separate and not built. When they are, they become sibling units here.
