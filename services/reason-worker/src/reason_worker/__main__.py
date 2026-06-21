# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the reason Temporal worker."""

import asyncio
import os

from shared_py.startup import validate_startup
from temporalio.client import Client
from temporalio.worker import Worker

from reason_worker.activities import (
    ensure_beat_grid,
    ensure_shot_boundaries,
    fail_generation_job,
    fetch_project_context,
    generate_cutlist_activity,
    publish_progress_activity,
    rank_clips_activity,
    save_generated_cutlist,
)
from reason_worker.workflows import GenerateFromReferenceWorkflow


async def main() -> None:
    validate_startup("reason-worker")

    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))
    worker = Worker(
        client,
        task_queue="generate",
        workflows=[GenerateFromReferenceWorkflow],
        activities=[
            publish_progress_activity,
            fetch_project_context,
            ensure_beat_grid,
            ensure_shot_boundaries,
            generate_cutlist_activity,
            rank_clips_activity,
            save_generated_cutlist,
            fail_generation_job,
        ],
    )

    print("Reason worker started, polling task queue: generate")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
