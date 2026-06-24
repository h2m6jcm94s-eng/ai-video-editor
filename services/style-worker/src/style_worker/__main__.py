# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the style-analysis Temporal worker."""

import asyncio
import os

from shared_py.startup import validate_startup
from temporalio.client import Client
from temporalio.worker import Worker

from style_worker.activities import (
    download_reference_video,
    extract_lut,
    detect_text_overlays,
    analyze_motion,
    classify_shot_transitions,
    cleanup_style_assets,
)
from style_worker.workflows import AnalyzeStyleWorkflow


async def main() -> None:
    validate_startup("style-worker")

    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))
    worker = Worker(
        client,
        task_queue="style",
        workflows=[AnalyzeStyleWorkflow],
        activities=[
            download_reference_video,
            extract_lut,
            detect_text_overlays,
            analyze_motion,
            classify_shot_transitions,
            cleanup_style_assets,
        ],
    )

    print("Style worker started, polling task queue: style")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
