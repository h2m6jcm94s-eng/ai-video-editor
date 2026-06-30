# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the style-analysis Temporal worker."""

import asyncio

from shared_py.startup import validate_startup
from shared_py.worker_runner import run_worker

from style_worker.activities import (
    analyze_motion,
    analyze_reference_activity,
    classify_shot_transitions,
    cleanup_style_assets,
    detect_text_overlays,
    download_reference_video,
    extract_genome_activity,
    extract_lut,
)
from style_worker.workflows import AnalyzeGenomeWorkflow, AnalyzeStyleWorkflow


async def main() -> None:
    await run_worker(
        worker_name="style-worker",
        task_queue="style",
        workflows=[AnalyzeStyleWorkflow, AnalyzeGenomeWorkflow],
        activities=[
            download_reference_video,
            analyze_reference_activity,
            extract_lut,
            detect_text_overlays,
            analyze_motion,
            classify_shot_transitions,
            cleanup_style_assets,
            extract_genome_activity,
        ],
        validate=validate_startup,
    )


if __name__ == "__main__":
    asyncio.run(main())
