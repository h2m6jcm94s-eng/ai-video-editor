# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the reason worker."""

import os
from typing import Dict, List, Optional

import httpx
from shared_py.config import settings
from shared_py.logging_config import StructuredLogger
from shared_py.models import BeatGrid, CutList, ShotBoundary
from shared_py.storage import download_asset
from temporalio import activity

from reason_worker.clip_rank import compute_confidence, rank_clips_for_slots
from reason_worker.cutlist_gen import generate_cutlist

logger = StructuredLogger("reason_worker.activities")


def _internal_headers() -> Dict[str, str]:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return {"x-internal-token": token}


def _activity_run_id() -> str:
    try:
        return activity.info().workflow_run_id or "0"
    except RuntimeError:
        return "0"


@activity.defn
async def publish_progress_activity(job_id: str, stage: str, progress: float, message: str) -> None:
    """Publish a progress event for the generation job."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.api_base}/internal/progress/{job_id}",
            json={"stage": stage, "progress": progress, "message": message},
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()


@activity.defn
async def fetch_project_context(project_id: str) -> dict:
    """Fetch project details from the internal API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.api_base}/internal/projects/{project_id}",
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()


@activity.defn
async def ensure_beat_grid(song_asset_id: str, song_metadata: dict, storage_key: str) -> dict:
    """Return cached beat grid or detect it from the song asset."""
    from ingest_worker.beat_detect import compute_energy_curve, detect_beats

    existing = (song_metadata or {}).get("beatGrid")
    energy_existing = (song_metadata or {}).get("energyCurve")
    if existing and energy_existing is not None:
        return {"beat_grid": existing, "energy_curve": energy_existing}

    local_path = download_asset(storage_key)
    try:
        beat_grid = detect_beats(local_path)
        energy_curve = compute_energy_curve(local_path)
        metadata = {"beatGrid": beat_grid.model_dump(by_alias=True), "energyCurve": energy_curve}
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{settings.api_base}/internal/assets/{song_asset_id}/metadata",
                json={"metadata": metadata},
                headers=_internal_headers(),
                timeout=30,
            )
        resp.raise_for_status()
        return {"beat_grid": metadata["beatGrid"], "energy_curve": energy_curve}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def ensure_shot_boundaries(
    reference_asset_id: str, reference_metadata: dict, storage_key: str, fps: float = 30.0
) -> dict:
    """Return cached shot boundaries or detect them from the reference video."""
    from ingest_worker.shot_detect import detect_shot_boundaries

    existing = (reference_metadata or {}).get("shotBoundaries")
    if existing:
        return {"shot_boundaries": existing}

    local_path = download_asset(storage_key)
    try:
        shots = detect_shot_boundaries(local_path, fps=fps)
        metadata = {"shotBoundaries": [s.model_dump(by_alias=True) for s in shots]}
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{settings.api_base}/internal/assets/{reference_asset_id}/metadata",
                json={"metadata": metadata},
                headers=_internal_headers(),
                timeout=30,
            )
        resp.raise_for_status()
        return {"shot_boundaries": metadata["shotBoundaries"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def generate_cutlist_activity(
    beat_grid_raw: dict,
    shot_boundaries_raw: List[dict],
    style_analysis: Optional[dict],
    energy_curve: List[float],
    total_duration: float,
    style_tier: str = "full_remix",
    song_asset_id: Optional[str] = None,
) -> dict:
    """Generate a cutlist from beats, shots, and style analysis."""
    beat_grid = BeatGrid(**beat_grid_raw)
    shot_boundaries = [ShotBoundary(**s) for s in shot_boundaries_raw]
    available_shot_types = [
        "extreme_wide",
        "wide",
        "medium_wide",
        "medium",
        "medium_close_up",
        "close_up",
        "extreme_close_up",
        "insert",
        "establishing",
    ]
    style_analysis = style_analysis or {}

    cutlist = generate_cutlist(
        beat_grid,
        shot_boundaries,
        style_analysis,
        energy_curve,
        available_shot_types,
        total_duration=total_duration,
        style_tier=style_tier,
        song_asset_id=song_asset_id,
    )
    return cutlist.model_dump(by_alias=True)


@activity.defn
async def rank_clips_activity(
    cutlist_raw: dict,
    clip_asset_ids: List[str],
    clip_metadata: Dict[str, dict],
    fallback_policy: str = "round_robin",
) -> dict:
    """Rank user clips for each slot in the cutlist.

    Falls back to ``fallback_policy`` if a slot receives no ranking, so the
    generated cutlist is always renderable as long as at least one clip exists.
    """
    if not clip_asset_ids:
        raise ValueError("MISSING_CLIPS: at least one clip is required to generate a renderable cutlist")

    cutlist = CutList(**cutlist_raw)

    # Ensure every clip has a metadata entry with sensible defaults.
    populated_metadata: Dict[str, dict] = {}
    for clip_id in clip_asset_ids:
        meta = clip_metadata.get(clip_id) or {}
        populated_metadata[clip_id] = {
            "shot_type": meta.get("shotType") or meta.get("shot_type") or "medium",
            "motion_energy": meta.get("motionEnergy") or meta.get("motion_energy") or 0.5,
            "aesthetic_score": meta.get("aestheticScore") or meta.get("aesthetic_score") or 0.5,
            "duration_sec": meta.get("durationSec") or meta.get("duration_sec") or 5.0,
        }

    rankings = rank_clips_for_slots(
        cutlist.slots,
        populated_metadata,
        fallback_policy=fallback_policy,
    )

    confidences = compute_confidence(rankings)
    for slot in cutlist.slots:
        scores = rankings.get(slot.index, [])
        if scores:
            slot.selected_clip_id = scores[0].clip_id
            slot.ranked_clip_ids = [s.clip_id for s in scores[:3]]
            # Clamp confidence to the valid API range [0, 0.99].
            slot.confidence = max(0.0, min(0.99, confidences.get(slot.index, 0.5)))

    return cutlist.model_dump(by_alias=True)


@activity.defn
async def save_generated_cutlist(
    project_id: str, generation_job_id: str, cutlist: dict, completion_token: str
) -> dict:
    """Persist the generated cut-list and mark the generation job complete."""
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{settings.api_base}/internal/projects/{project_id}/generated-cutlist",
            json={
                "cutList": cutlist,
                "generationJobId": generation_job_id,
                "completionToken": completion_token,
            },
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()


@activity.defn
async def fail_generation_job(generation_job_id: str, error_message: str, completion_token: str) -> dict:
    """Mark the generation job as failed."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.api_base}/internal/generation-jobs/{generation_job_id}/fail",
            json={"errorMessage": error_message, "completionToken": completion_token},
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()
