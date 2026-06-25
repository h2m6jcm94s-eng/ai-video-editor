# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the render Temporal worker."""

import asyncio

from shared_py.startup import validate_startup
from shared_py.worker_runner import run_worker

from render_worker.activities import (
    cleanup_render_assets,
    compile_render,
    complete_render,
    download_render_assets,
    fetch_project,
    upload_render,
)
from render_worker.workflows import VideoRenderWorkflow


async def main() -> None:
    await run_worker(
        worker_name="render-worker",
        task_queue="video-render-queue",
        workflows=[VideoRenderWorkflow],
        activities=[
            fetch_project,
            download_render_assets,
            compile_render,
            upload_render,
            complete_render,
            cleanup_render_assets,
        ],
        validate=validate_startup,
    )


if __name__ == "__main__":
    asyncio.run(main())
