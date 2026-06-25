# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for the resilient Temporal worker runner."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared_py.worker_runner import run_worker


async def _block_forever():
    """Never-returning coroutine for simulating a healthy worker loop."""
    await asyncio.Event().wait()


@pytest.fixture
def mock_worker():
    worker = MagicMock()
    worker.run = AsyncMock()
    worker.shutdown = AsyncMock()
    return worker


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


async def _run_until_cancelled(coro, timeout: float = 0.2):
    """Run a coroutine and cancel it after a short delay.

    The runner catches CancelledError and returns gracefully, so we do not
    expect the task to raise.
    """
    task = asyncio.create_task(coro)
    await asyncio.sleep(timeout)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_runner_validates_startup(mock_client, mock_worker):
    validate = MagicMock()
    mock_worker.run.side_effect = _block_forever

    with patch("shared_py.worker_runner.Client") as ClientMock:
        ClientMock.connect = AsyncMock(return_value=mock_client)
        with patch("shared_py.worker_runner.Worker", return_value=mock_worker):
            await _run_until_cancelled(
                run_worker(
                    worker_name="test-worker",
                    task_queue="test-queue",
                    activities=[],
                    workflows=[],
                    validate=validate,
                )
            )

    validate.assert_called_once_with("test-worker")


@pytest.mark.asyncio
async def test_runner_connects_with_env_host_and_namespace(mock_client, mock_worker):
    with patch.dict(
        "os.environ",
        {"TEMPORAL_HOST": "temporal.example.com:7233", "TEMPORAL_NAMESPACE": "prod"},
    ):
        mock_worker.run.side_effect = _block_forever
        with patch("shared_py.worker_runner.Client") as ClientMock:
            ClientMock.connect = AsyncMock(return_value=mock_client)
            with patch("shared_py.worker_runner.Worker", return_value=mock_worker):
                await _run_until_cancelled(
                    run_worker(
                        worker_name="test-worker",
                        task_queue="test-queue",
                        activities=[],
                        workflows=[],
                    )
                )

    ClientMock.connect.assert_called_once_with("temporal.example.com:7233", namespace="prod")


@pytest.mark.asyncio
async def test_runner_creates_worker_with_activities_and_workflows(mock_client, mock_worker):
    activities = [MagicMock()]
    workflows = [MagicMock()]
    mock_worker.run.side_effect = _block_forever

    with patch("shared_py.worker_runner.Client") as ClientMock:
        ClientMock.connect = AsyncMock(return_value=mock_client)
        with patch("shared_py.worker_runner.Worker", return_value=mock_worker) as WorkerMock:
            await _run_until_cancelled(
                run_worker(
                    worker_name="test-worker",
                    task_queue="test-queue",
                    activities=activities,
                    workflows=workflows,
                )
            )

    WorkerMock.assert_called_once_with(
        mock_client,  # async context manager __aenter__ returns the client itself
        task_queue="test-queue",
        activities=activities,
        workflows=workflows,
    )


@pytest.mark.asyncio
async def test_runner_reconnects_after_worker_crash(mock_client, mock_worker):
    call_count = 0

    def _run_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        return _block_forever()

    mock_worker.run.side_effect = _run_side_effect

    with patch.dict("os.environ", {"WORKER_RECONNECT_DELAY_SECONDS": "0.01"}):
        with patch("shared_py.worker_runner.Client") as ClientMock:
            ClientMock.connect = AsyncMock(return_value=mock_client)
            with patch("shared_py.worker_runner.Worker", return_value=mock_worker):
                await _run_until_cancelled(
                    run_worker(
                        worker_name="test-worker",
                        task_queue="test-queue",
                        activities=[],
                        workflows=[],
                    ),
                    timeout=0.5,
                )

    assert ClientMock.connect.call_count >= 2
