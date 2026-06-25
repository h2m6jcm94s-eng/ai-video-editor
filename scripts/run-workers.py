#!/usr/bin/env python3
# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Run all Python Temporal workers under one supervisor that auto-restarts them."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Each worker lives in services/<name>/src and is started with `python -m <module>`.
WORKERS = [
    ("ingest-worker", "ingest_worker"),
    ("reason-worker", "reason_worker"),
    ("render-worker", "render_worker"),
    ("style-worker", "style_worker"),
    ("segment-worker", "segment_worker"),
]

# How long to wait between crash checks.
POLL_INTERVAL_SECONDS = 2
# Max restarts within a window before we give up on a worker.
MAX_RESTARTS = 5
RESTART_WINDOW_SECONDS = 60
# Graceful shutdown timeout per worker.
SHUTDOWN_TIMEOUT_SECONDS = 10


def _load_env() -> dict:
    env = os.environ.copy()
    env_local = ROOT / "apps" / "api" / ".env.local"
    if env_local.exists():
        load_dotenv(env_local, override=False)
        # load_dotenv mutates os.environ, so copy the updated values back.
        env = os.environ.copy()
    return env


def _start_worker(name: str, module: str, env: dict) -> subprocess.Popen:
    cwd = ROOT / "services" / name / "src"
    cmd = [sys.executable, "-u", "-m", module]
    print(f"[supervisor] Starting {name}...", flush=True)

    # On Windows put each worker in its own process group so the supervisor can
    # signal it directly without the console sending Ctrl+C to every child.
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        **kwargs,
    )


def _signal_worker(proc: subprocess.Popen) -> None:
    """Ask a worker to shut down gracefully.

    On Windows we send CTRL_BREAK_EVENT to the worker's process group; the
    worker_runner installs a SIGBREAK handler that starts graceful shutdown.
    Elsewhere we send SIGTERM.
    """
    if sys.platform == "win32" and proc.pid:
        try:
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            return
        except (OSError, ValueError):
            pass
    proc.terminate()


def main() -> int:
    env = _load_env()

    procs: dict[str, subprocess.Popen] = {}
    restart_times: dict[str, list[float]] = {}
    shutting_down = False

    def _shutdown(signum: int, _frame) -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        print(f"\n[supervisor] Received signal {signum}, stopping workers...", flush=True)
        for proc in procs.values():
            _signal_worker(proc)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):
            pass

    for name, module in WORKERS:
        procs[name] = _start_worker(name, module, env)
        restart_times[name] = []

    print("[supervisor] All workers running. Press Ctrl+C to stop.", flush=True)

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)

        if shutting_down:
            break

        for name, module in WORKERS:
            proc = procs.get(name)
            if proc is None:
                continue

            ret = proc.poll()
            if ret is None:
                # Still running.
                continue

            print(
                f"[supervisor] {name} exited with code {ret}, restarting...",
                flush=True,
            )

            now = time.monotonic()
            restarts = restart_times.setdefault(name, [])
            restarts.append(now)
            restarts[:] = [t for t in restarts if now - t < RESTART_WINDOW_SECONDS]

            if len(restarts) > MAX_RESTARTS:
                print(
                    f"[supervisor] {name} restarted more than {MAX_RESTARTS} times "
                    f"in {RESTART_WINDOW_SECONDS}s; giving up.",
                    flush=True,
                )
                del procs[name]
                continue

            procs[name] = _start_worker(name, module, env)

    # Graceful shutdown: wait up to SHUTDOWN_TIMEOUT_SECONDS per worker, then kill.
    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_SECONDS
    for name, proc in list(procs.items()):
        remaining = deadline - time.monotonic()
        if remaining > 0:
            try:
                proc.wait(timeout=max(remaining, 0.5))
                print(f"[supervisor] {name} stopped gracefully", flush=True)
                continue
            except subprocess.TimeoutExpired:
                pass
        print(f"[supervisor] {name} did not exit gracefully, killing", flush=True)
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            print(f"[supervisor] {name} refused to die", flush=True)

    print("[supervisor] Shutdown complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
