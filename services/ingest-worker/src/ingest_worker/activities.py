# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the ingest worker."""

import os
from pathlib import Path
from typing import Dict

import httpx
from shared_py.config import settings
from shared_py.storage import download_asset
from temporalio import activity

from ingest_worker.beat_detect import compute_energy_curve, detect_beats
from ingest_worker.heatmap import compute_clip_heatmap, heatmap_to_metadata
from ingest_worker.song_mood import analyze_song
from ingest_worker.stem_separate import separate_song_stems
from ingest_worker.vocal_emotion import analyze_vocal_stem
from ingest_worker.probe import probe_asset_remote
from ingest_worker.shot_detect import detect_shot_boundaries


def _internal_headers() -> Dict[str, str]:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return {"x-internal-token": token}


async def _patch_asset_metadata(asset_id: str, metadata: dict) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{settings.api_base}/internal/assets/{asset_id}/metadata",
            json={"metadata": metadata},
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()


@activity.defn
async def probe_asset(asset_id: str, storage_key: str) -> dict:
    """Probe a single asset and report metadata back to the API."""
    return await probe_asset_remote(asset_id, storage_key)


@activity.defn
async def detect_beats_activity(asset_id: str, storage_key: str) -> dict:
    """Download a song asset, detect beat grid + energy curve, and persist metadata."""
    local_path = download_asset(storage_key)
    try:
        beat_grid = detect_beats(local_path)
        energy_curve = compute_energy_curve(local_path)
        metadata = {
            "beatGrid": beat_grid.model_dump(by_alias=True),
            "energyCurve": energy_curve,
        }
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "beat_grid": metadata["beatGrid"], "energy_curve": energy_curve}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def detect_shot_boundaries_activity(asset_id: str, storage_key: str, fps: float = 30.0) -> dict:
    """Download a video asset, detect shot boundaries, and persist metadata."""
    local_path = download_asset(storage_key)
    try:
        shots = detect_shot_boundaries(local_path, fps=fps)
        metadata = {
            "shotBoundaries": [s.model_dump(by_alias=True) for s in shots],
        }
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "shot_boundaries": metadata["shotBoundaries"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def analyze_song_mood_activity(asset_id: str, storage_key: str) -> dict:
    """Download a song asset, detect beats, and run CLAP mood/genre tagging."""
    local_path = download_asset(storage_key)
    try:
        beat_grid = detect_beats(local_path)
        mood_profile = analyze_song(local_path, beat_grid)
        metadata = {"songMoodProfile": mood_profile.model_dump(by_alias=True)}
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "song_mood_profile": metadata["songMoodProfile"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def analyze_vocal_emotion_activity(asset_id: str, storage_key: str) -> dict:
    """Download a song asset, separate stems, and run Wav2Vec2 vocal emotion."""
    local_path = download_asset(storage_key)
    try:
        stems = separate_song_stems(local_path)
        vocals_path = stems.get("vocals")
        if vocals_path is None or not Path(vocals_path).exists():
            raise FileNotFoundError(f"vocals stem missing for asset {asset_id}")
        curve = analyze_vocal_stem(str(vocals_path), song_hash=asset_id)
        metadata = {"vocalEmotionCurve": curve.model_dump(by_alias=True)}
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "vocal_emotion_curve": metadata["vocalEmotionCurve"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def compute_clip_heatmap_activity(asset_id: str, storage_key: str) -> dict:
    """Download a clip asset, compute an interestingness heatmap, and persist metadata."""
    local_path = download_asset(storage_key)
    try:
        heatmap = compute_clip_heatmap(local_path, audio_path=None, window_s=0.5, stride_s=0.25)
        metadata = {"heatmap": heatmap_to_metadata(heatmap)}
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "heatmap": metadata["heatmap"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass
