# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Entry point for the ingest Temporal worker."""

import asyncio

from shared_py.startup import validate_startup
from shared_py.worker_runner import run_worker

from ingest_worker.activities import (
    analyze_clip_emotion_activity,
    analyze_loudness_activity,
    compute_siglip2_embedding_activity,
    analyze_song_meaning_activity,
    analyze_song_mood_activity,
    analyze_vocal_emotion_activity,
    compute_clip_heatmap_activity,
    compute_clip_semantic_activity,
    detect_beats_activity,
    detect_music_events_activity,
    detect_shot_boundaries_activity,
    probe_asset,
)
from ingest_worker.workflows import ProbeAssetWorkflow


async def main() -> None:
    await run_worker(
        worker_name="ingest-worker",
        task_queue="ingest",
        workflows=[ProbeAssetWorkflow],
        activities=[
            probe_asset,
            detect_beats_activity,
            detect_shot_boundaries_activity,
            compute_clip_heatmap_activity,
            compute_clip_semantic_activity,
            compute_siglip2_embedding_activity,
            analyze_clip_emotion_activity,
            analyze_song_mood_activity,
            analyze_vocal_emotion_activity,
            detect_music_events_activity,
            analyze_loudness_activity,
            analyze_song_meaning_activity,
        ],
        validate=validate_startup,
    )


if __name__ == "__main__":
    asyncio.run(main())
