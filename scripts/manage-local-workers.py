#!/usr/bin/env python3
"""Manage all local Temporal Python workers as one long-running process.

On Windows, `uv run` exits after spawning the actual Python worker, so we track
the spawned Python PIDs by command line and kill them on shutdown.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

def log(msg: str) -> None:
    print(msg, flush=True)

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKERS = [
    ("ingest", "ingest_worker"),
    ("reason", "reason_worker"),
    ("render", "render_worker"),
    ("segment", "segment_worker"),
    ("style", "style_worker"),
]

LOG_DIR = REPO_ROOT / ".tmp" / "worker-logs"
ENV = os.environ.copy()
ENV.setdefault("AI_PROVIDER", "programmatic")

pids_to_kill: list[int] = []


def find_python_pids(module: str) -> list[int]:
    """Find Windows python.exe PIDs whose command line contains the module."""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine", "/format:list"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        log(f"[manage-local-workers] wmic failed: {exc}")
        return []

    pids: list[int] = []
    current_pid: int | None = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("ProcessId="):
            try:
                current_pid = int(line.split("=", 1)[1])
            except ValueError:
                current_pid = None
        elif line.startswith("CommandLine="):
            cmd = line.split("=", 1)[1]
            if module in cmd and str(REPO_ROOT) in cmd:
                if current_pid and current_pid not in pids:
                    pids.append(current_pid)
            current_pid = None
    return pids


def start_worker(name: str, module: str) -> list[int]:
    log_path = LOG_DIR / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", buffering=1)
    log(f"[manage-local-workers] Starting {name} -> {log_path}")
    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", module],
        cwd=REPO_ROOT,
        env=ENV,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # Give uv a moment to spawn the actual worker process.
    time.sleep(3)
    pids = find_python_pids(module)
    if not pids:
        log(f"[manage-local-workers] Warning: could not find Python PID for {name}; using uv PID {proc.pid}")
        pids = [proc.pid]
    else:
        log(f"[manage-local-workers] {name} Python PID(s): {pids}")
    return pids


def shutdown(signum=None, frame=None):
    log("[manage-local-workers] Shutting down workers...")
    for pid in pids_to_kill:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
        except Exception as exc:
            log(f"[manage-local-workers] Failed to kill PID {pid}: {exc}")
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Source .env by loading KEY=VALUE pairs into ENV.
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                ENV.setdefault(key, value.strip('"\''))

    for name, module in WORKERS:
        pids = start_worker(name, module)
        pids_to_kill.extend(pids)

    log(f"[manage-local-workers] All workers started. Monitoring PIDs: {pids_to_kill}")

    while True:
        time.sleep(5)
        # Optionally check health and restart crashed workers.
        alive = 0
        for pid in list(pids_to_kill):
            if subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"], capture_output=True).returncode == 0:
                alive += 1
        if alive == 0:
            log("[manage-local-workers] All workers have exited.")
            break


if __name__ == "__main__":
    main()
