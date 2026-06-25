# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the standalone SAM3 segmentation Temporal worker."""

import asyncio

from shared_py.startup import validate_startup
from shared_py.worker_runner import run_worker

from segment_worker.activities import segment_subject
from segment_worker.workflows import SegmentSubjectWorkflow


async def main() -> None:
    await run_worker(
        worker_name="segment-worker",
        task_queue="segment",
        workflows=[SegmentSubjectWorkflow],
        activities=[segment_subject],
        validate=validate_startup,
    )


if __name__ == "__main__":
    asyncio.run(main())
