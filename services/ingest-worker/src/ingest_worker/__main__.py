# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the ingest Temporal worker."""

import asyncio
import os

from shared_py.startup import validate_startup
from temporalio.client import Client
from temporalio.worker import Worker

from ingest_worker.activities import probe_asset
from ingest_worker.workflows import ProbeAssetWorkflow


async def main() -> None:
    validate_startup("ingest-worker")

    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))
    worker = Worker(
        client,
        task_queue="ingest",
        workflows=[ProbeAssetWorkflow],
        activities=[probe_asset],
    )

    print("Ingest worker started, polling task queue: ingest")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
