# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the standalone SAM3 segmentation Temporal worker."""

import asyncio
import os

from shared_py.startup import validate_startup
from temporalio.client import Client
from temporalio.worker import Worker

from segment_worker.activities import segment_subject
from segment_worker.workflows import SegmentSubjectWorkflow


async def main() -> None:
    validate_startup("segment-worker")

    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))
    worker = Worker(
        client,
        task_queue="segment",
        activities=[segment_subject],
        workflows=[SegmentSubjectWorkflow],
    )

    print("Segment worker started, polling task queue: segment")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
