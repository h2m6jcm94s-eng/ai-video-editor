# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Resilient Temporal worker runner with reconnect and graceful shutdown."""

import asyncio
import os
import signal
import sys
from contextlib import suppress
from typing import Any, Callable, List, Optional, Type

from temporalio.client import Client
from temporalio.worker import Worker

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("worker_runner")


async def run_worker(
    worker_name: str,
    task_queue: str,
    activities: List[Callable],
    workflows: List[Type],
    validate: Optional[Callable[[str], None]] = None,
) -> None:
    """Run a Temporal worker that reconnects on failures and shuts down cleanly.

    The worker will keep trying to connect to Temporal until a SIGINT/SIGTERM is
    received. If the worker task crashes (e.g. due to a transient network error),
    it waits a configurable delay and reconnects.
    """
    if validate:
        validate(worker_name)

    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    reconnect_delay = max(0.1, float(os.environ.get("WORKER_RECONNECT_DELAY_SECONDS", "5")))
    shutdown_timeout = max(1.0, float(os.environ.get("WORKER_SHUTDOWN_TIMEOUT_SECONDS", "30")))

    shutdown_event = asyncio.Event()

    def _request_shutdown() -> None:
        if not shutdown_event.is_set():
            logger.info(f"Shutdown signal received for {worker_name}")
            shutdown_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform == "win32":
        # Windows: signal.signal runs in the main thread; schedule the async event
        # safely. Also handle SIGBREAK (console close).
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGBREAK):
            try:
                signal.signal(sig, lambda _s, _f: loop.call_soon_threadsafe(_request_shutdown))
            except (ValueError, OSError):
                pass
    else:
        loop.add_signal_handler(signal.SIGINT, _request_shutdown)
        loop.add_signal_handler(signal.SIGTERM, _request_shutdown)

    logger.info(
        "Starting resilient worker",
        worker=worker_name,
        task_queue=task_queue,
        temporal_host=host,
        namespace=namespace,
    )

    run_task: Optional[asyncio.Task] = None
    shutdown_wait: Optional[asyncio.Task] = None

    while not shutdown_event.is_set():
        client: Optional[Client] = None
        worker: Optional[Worker] = None
        try:
            logger.info("Connecting to Temporal", worker=worker_name, host=host)
            # NOTE: temporalio 1.28 Client has no close()/async-context support;
            # the gRPC channel is cleaned up when the process exits.
            client = await Client.connect(host, namespace=namespace)
            worker = Worker(
                client,
                task_queue=task_queue,
                activities=activities,
                workflows=workflows,
            )
            logger.info(
                "Worker connected and polling",
                worker=worker_name,
                task_queue=task_queue,
            )

            run_task = asyncio.create_task(worker.run())
            shutdown_wait = asyncio.create_task(shutdown_event.wait())

            done, pending = await asyncio.wait(
                [run_task, shutdown_wait],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel the pending task and await it to avoid warnings.
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

            if shutdown_wait in done:
                exc = run_task.exception() if run_task.done() else None
                if exc is not None:
                    logger.error(
                        "Worker failed during shutdown request",
                        worker=worker_name,
                        error=str(exc),
                        exc_info=True,
                    )
                try:
                    await asyncio.wait_for(
                        worker.shutdown(),
                        timeout=shutdown_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "Graceful shutdown timed out",
                        worker=worker_name,
                    )
                # Ensure run_task completes (it should after shutdown()).
                if run_task.done():
                    # Re-awaiting a done task drains any stored exception.
                    with suppress(asyncio.CancelledError):
                        await run_task
                else:
                    try:
                        await asyncio.wait_for(run_task, timeout=shutdown_timeout)
                    except asyncio.TimeoutError:
                        logger.error(
                            "Worker did not finish after shutdown signal",
                            worker=worker_name,
                        )
                break

            # run_task finished on its own -> worker crashed or connection lost.
            exc = run_task.exception()
            if exc is not None:
                raise exc

            logger.warning(
                "Worker loop exited without error, reconnecting",
                worker=worker_name,
            )

        except asyncio.CancelledError:
            if run_task is not None and not run_task.done():
                run_task.cancel()
            if shutdown_wait is not None and not shutdown_wait.done():
                shutdown_wait.cancel()
            if worker is not None:
                with suppress(Exception):
                    await asyncio.wait_for(worker.shutdown(), timeout=shutdown_timeout)
            if run_task is not None:
                with suppress(asyncio.CancelledError):
                    await run_task
            break
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Worker crashed",
                worker=worker_name,
                error=str(exc),
                exc_info=True,
            )
        finally:
            # Only force-shutdown if we are reconnecting (not during intentional exit).
            if worker is not None and not shutdown_event.is_set():
                try:
                    await asyncio.wait_for(worker.shutdown(), timeout=shutdown_timeout)
                except Exception:  # noqa: BLE001
                    logger.exception("Cleanup shutdown failed", worker=worker_name)

        if shutdown_event.is_set():
            break

        logger.info(
            "Reconnecting worker after delay",
            worker=worker_name,
            delay_seconds=reconnect_delay,
        )
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=reconnect_delay)
        except asyncio.TimeoutError:
            pass

    logger.info("Worker exited", worker=worker_name)
