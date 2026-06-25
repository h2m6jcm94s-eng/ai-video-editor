#!/usr/bin/env python3
# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""One-command full-stack launcher for local AI video editor development.

Starts Docker infrastructure, runs migrations, starts workers, the API dev
server, and the Next.js web dev server.  Everything runs in one terminal;
Ctrl+C stops the whole stack gracefully.
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_LOCAL = ROOT / "apps" / "api" / ".env.local"
PID_FILE = ROOT / ".tmp" / "dev-stack.pid"
LOG_DIR = ROOT / ".tmp" / "dev-logs"

SERVICES = [
    ("infra", "PostgreSQL, Redis, Temporal, MinIO"),
    ("api", "Fastify API on http://localhost:4000"),
    ("workers", "Python Temporal workers"),
    ("web", "Next.js on http://localhost:3000"),
]


def _color(code: int, text: str) -> str:
    if os.environ.get("NO_COLOR") or sys.platform == "win32" and not os.environ.get("FORCE_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


def _bold(text: str) -> str:
    return _color("1", text)


def _green(text: str) -> str:
    return _color("32", text)


def _yellow(text: str) -> str:
    return _color("33", text)


def _red(text: str) -> str:
    return _color("31", text)


def _blue(text: str) -> str:
    return _color("34", text)


def _prefix(service: str, text: str) -> str:
    colors = {
        "infra": "34",
        "api": "32",
        "workers": "33",
        "web": "35",
    }
    color = colors.get(service, "36")
    return f"{_color(color, f'[{service.upper():8}]')} {text}"


def _load_env() -> None:
    if ENV_LOCAL.exists():
        load_dotenv(ENV_LOCAL, override=False)


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _wait_for_ports(ports: list[tuple[str, int]], timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(_is_port_open(h, p) for h, p in ports):
            return True
        time.sleep(0.5)
    return False


def _infra_ports() -> list[tuple[str, int]]:
    return [
        ("localhost", 5432),
        ("localhost", 6379),
        ("localhost", 7233),
        ("localhost", 9000),
    ]


def _banner() -> None:
    print()
    print(_bold("AI Video Editor — Local Dev Stack"))
    print(_blue("Ctrl+C stops everything gracefully"))
    print()
    for name, desc in SERVICES:
        print(f"  {_green('•')} {name:7} — {desc}")
    print()


def _log_file(service: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"{service}.log"


def _start_infra() -> bool:
    print(_prefix("infra", "Starting Docker infrastructure..."))
    compose_file = ROOT / "infra" / "local" / "docker-compose.yml"
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d"],
        cwd=ROOT,
        check=True,
    )
    print(_prefix("infra", "Waiting for services to be healthy..."))
    if not _wait_for_ports(_infra_ports(), timeout=90.0):
        print(_red("Infrastructure did not become healthy in time."))
        print(_yellow(f"Check logs: docker compose -f {compose_file} logs"))
        return False
    print(_prefix("infra", _green("Infrastructure ready")))
    return True


def _infra_is_running() -> bool:
    return all(_is_port_open(h, p) for h, p in _infra_ports())


def _run_migrations() -> bool:
    print(_prefix("infra", "Running database migrations..."))
    result = subprocess.run(
        ["pnpm", "--filter", "@ai-video-editor/api", "db:migrate"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print(_red("Migrations failed."))
        return False
    print(_prefix("infra", _green("Migrations complete")))
    return True


def _write_pid_file(children: list[tuple[str, subprocess.Popen]]) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [str(os.getpid())]
    for service, proc in children:
        lines.append(f"{service}:{proc.pid}")
    PID_FILE.write_text("\n".join(lines))


def _remove_pid_file() -> None:
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _start_service(
    service: str,
    cmd: list[str],
    cwd: Path,
    env: dict,
    shell: bool = False,
) -> subprocess.Popen:
    log = _log_file(service)
    print(_prefix(service, f"Starting ({log.name})..."))
    log.write_text("")
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        # pnpm is a .cmd file on Windows and needs shell=True to be found.
        shell = shell or any(str(part).endswith(".cmd") for part in cmd)
    proc = subprocess.Popen(
        " ".join(str(c) for c in cmd) if shell else cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
        shell=shell,
        **kwargs,
    )
    return proc


def _stream_output(service: str, proc: subprocess.Popen) -> None:
    log = _log_file(service)
    try:
        with open(log, "a", encoding="utf-8") as f:
            if proc.stdout is None:
                return
            for line in proc.stdout:
                stripped = line.rstrip()
                print(_prefix(service, stripped))
                f.write(line)
                f.flush()
    except Exception:
        pass


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


def main() -> int:
    _load_env()
    _banner()

    # Sanity-check prerequisites.
    if not shutil.which("docker"):
        print(_red("Docker is not installed or not in PATH."))
        return 1
    if not shutil.which("pnpm"):
        print(_red("pnpm is not installed or not in PATH."))
        return 1
    if not shutil.which("uv"):
        print(_red("uv is not installed or not in PATH."))
        return 1

    children: list[tuple[str, subprocess.Popen]] = []

    def _shutdown(signum: int, _frame) -> None:
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        print()
        print(_yellow(f"Received {sig_name}, shutting down dev stack..."))
        for service, proc in reversed(children):
            print(_prefix(service, "Stopping..."))
            _terminate(proc)
        _remove_pid_file()
        print(_green("Dev stack stopped."))
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):
            pass

    try:
        if not _infra_is_running():
            if not _start_infra():
                return 1
            if not _run_migrations():
                return 1
        else:
            print(_prefix("infra", _green("Infrastructure already running")))

        env = os.environ.copy()
        # Ensure workers pick up the local env file.
        if ENV_LOCAL.exists():
            load_dotenv(ENV_LOCAL, override=False)
            env = os.environ.copy()

        # Start workers.
        workers_proc = _start_service(
            "workers",
            [sys.executable, str(ROOT / "scripts" / "run-workers.py")],
            ROOT,
            env,
            shell=sys.platform == "win32",
        )
        children.append(("workers", workers_proc))

        # Start API.
        api_proc = _start_service(
            "api",
            ["pnpm", "--filter", "@ai-video-editor/api", "dev"],
            ROOT,
            env,
            shell=True,
        )
        children.append(("api", api_proc))

        # Wait for API to be ready.
        print(_prefix("api", "Waiting for API health check..."))
        api_ready = False
        for _ in range(60):
            if api_proc.poll() is not None:
                print(_red("API process exited early."))
                return 1
            if _is_port_open("localhost", 4000):
                api_ready = True
                break
            time.sleep(0.5)
        if not api_ready:
            print(_red("API did not start in time."))
            return 1
        print(_prefix("api", _green("API ready at http://localhost:4000")))

        # Start web in foreground so the user sees the Next.js logs.
        web_proc = _start_service(
            "web",
            ["pnpm", "--filter", "@ai-video-editor/web", "dev"],
            ROOT,
            env,
            shell=True,
        )
        children.append(("web", web_proc))

        _write_pid_file(children)

        print()
        print(_green("All services are starting."))
        print(_blue("  API:    http://localhost:4000"))
        print(_blue("  Web:    http://localhost:3000"))
        print(_blue("  Temporal UI: http://localhost:8080"))
        print(_yellow(f"  Logs:   {LOG_DIR}"))
        print()

        # Stream output from all children until the web process exits.
        import threading
        threads = []
        for service, proc in children:
            t = threading.Thread(target=_stream_output, args=(service, proc), daemon=True)
            t.start()
            threads.append(t)

        # Wait on web process (foreground service).
        web_proc.wait()
        return web_proc.returncode or 0
    except KeyboardInterrupt:
        _shutdown(int(signal.SIGINT), None)
    finally:
        for _, proc in children:
            _terminate(proc)
        _remove_pid_file()
    return 0


if __name__ == "__main__":
    sys.exit(main())
