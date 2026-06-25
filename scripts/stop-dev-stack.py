#!/usr/bin/env python3
# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Stop a running local dev stack launched by `scripts/dev-stack.py`.

Also kills any stray node/python processes on the API (4000) and web (3000)
ports as a safety net.
"""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / ".tmp" / "dev-stack.pid"


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _kill_pid(pid: int) -> None:
    try:
        if sys.platform == "win32":
            os.kill(pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            # Give the process a moment to exit gracefully.
            for _ in range(20):
                try:
                    os.kill(pid, 0)
                except OSError:
                    return
                time.sleep(0.1)
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                try:
                    os.kill(pid, 0)
                except OSError:
                    return
                time.sleep(0.1)
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _kill_port_listeners(port: int) -> None:
    try:
        if sys.platform == "win32":
            output = subprocess.check_output(
                f'netstat -ano | findstr ":{port} "', shell=True, text=True
            )
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                    pid = parts[4]
                    subprocess.run(["taskkill", "/F", "/PID", pid], check=False)
        else:
            try:
                pid = subprocess.check_output(f"lsof -ti tcp:{port}", shell=True, text=True).strip()
                if pid:
                    subprocess.run(["kill", "-9", pid], check=False)
            except subprocess.CalledProcessError:
                pass
    except Exception:
        pass


def main() -> int:
    print("Stopping dev stack...")

    if PID_FILE.exists():
        content = PID_FILE.read_text().strip()
        lines = content.splitlines()
        # First line is the launcher PID; rest are child service PIDs.
        for line in lines:
            if ":" in line:
                service, pid_str = line.split(":", 1)
            else:
                pid_str = line
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            print(f"  Stopping process {pid}...")
            _kill_pid(pid)
        try:
            PID_FILE.unlink()
        except FileNotFoundError:
            pass
    else:
        print("  No PID file found; looking for stray listeners...")

    # Safety net: kill anything still on 4000/3000.
    for port in (4000, 3000):
        if _is_port_open("localhost", port):
            print(f"  Cleaning up listener on port {port}...")
            _kill_port_listeners(port)

    print("Dev stack stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
