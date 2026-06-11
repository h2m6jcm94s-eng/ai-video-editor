# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the render Temporal worker."""

import asyncio
import os

from shared_py.startup import validate_startup
from temporalio.client import Client
from temporalio.worker import Worker

from render_worker.activities import (
    compile_render,
    complete_render,
    download_render_assets,
    fetch_project,
    upload_render,
)
from render_worker.workflows import VideoRenderWorkflow


async def main() -> None:
    validate_startup("render-worker")

    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))
    worker = Worker(
        client,
        task_queue="video-render-queue",
        workflows=[VideoRenderWorkflow],
        activities=[
            fetch_project,
            download_render_assets,
            compile_render,
            upload_render,
            complete_render,
        ],
    )

    print("Render worker started, polling task queue: video-render-queue")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
