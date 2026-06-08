# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal worker that polls and executes video processing activities."""

import asyncio
import os
import sys

# Add services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/ingest-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/style-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/reason-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/render-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/shared-py/src"))

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

from shared_py.models import CutList, BeatGrid, ShotBoundary, RenderConfig
from workflows import VideoRenderWorkflow


# ------------------------------------------------------------------
# Activities
# ------------------------------------------------------------------

@activity.defn
async def probe_inputs(reference_id: str, song_id: str, clip_ids: list) -> dict:
    """Probe all input assets for metadata."""
    from ingest_worker.probe import probe_video
    return {"status": "probed", "reference_id": reference_id, "song_id": song_id}


@activity.defn
async def detect_beats(song_asset_id: str) -> dict:
    """Detect beat grid from song."""
    return {"bpm": 120, "beats": [], "status": "mock"}


@activity.defn
async def detect_shots(reference_asset_id: str) -> list:
    """Detect shot boundaries from reference."""
    return []


@activity.defn
async def analyze_reference_style(reference_asset_id: str, tier: str) -> dict:
    """Extract style features from reference."""
    return {"tier": tier, "lut_extracted": False}


@activity.defn
async def embed_user_clips(clip_asset_ids: list) -> dict:
    """Generate embeddings for user clips."""
    return {"embedded": len(clip_asset_ids)}


@activity.defn
async def generate_cutlist_claude(beats: dict, shots: list, style: dict, tier: str) -> dict:
    """Generate cut-list using AI provider."""
    return {"slots": [], "globals": {}}


@activity.defn
async def rank_clips_per_slot(cutlist: dict, clip_ids: list) -> dict:
    """Rank clips for each slot."""
    return {"rankings": {}}


@activity.defn
async def render_720p(cutlist: dict, clip_ids: list, lut_path: str = None) -> str:
    """Render 720p master."""
    return "/tmp/render.mp4"


@activity.defn
async def upload_to_r2(output_path: str, project_id: str) -> str:
    """Upload rendered video to R2."""
    return "r2://key"


@activity.defn
async def notify_user(user_id: str, project_id: str) -> None:
    """Send completion notification."""
    pass


# ------------------------------------------------------------------
# Worker setup
# ------------------------------------------------------------------

async def main():
    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))

    worker = Worker(
        client,
        task_queue="video-render-queue",
        workflows=[VideoRenderWorkflow],
        activities=[
            probe_inputs,
            detect_beats,
            detect_shots,
            analyze_reference_style,
            embed_user_clips,
            generate_cutlist_claude,
            rank_clips_per_slot,
            render_720p,
            upload_to_r2,
            notify_user,
        ],
    )

    print("Temporal worker started, polling task queue...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
