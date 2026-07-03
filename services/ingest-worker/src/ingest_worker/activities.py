# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the ingest worker."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict

import httpx
from shared_py.config import settings
from shared_py.storage import download_asset
from temporalio import activity

from ingest_worker.beat_detect import compute_energy_curve, detect_beats
from ingest_worker.heatmap import compute_clip_heatmap, heatmap_to_metadata
from ingest_worker.loudness import analyze_loudness
from ingest_worker.song_lyrics import transcribe_song_lyrics
from ingest_worker.song_meaning import aggregate_song_meaning
from ingest_worker.song_mood import analyze_song
from ingest_worker.stem_events import detect_music_events
from ingest_worker.stem_separate import separate_song_stems
from ingest_worker.vocal_emotion import analyze_vocal_stem
from ingest_worker.clip_emotion import compute_clip_emotion_profile
from ingest_worker.clip_semantic import embed_clip
from ingest_worker.probe import probe_asset_remote
from style_worker.siglip2 import embed_video_frames as siglip2_embed_video_frames
from ingest_worker.shot_detect import detect_shot_boundaries


def _internal_headers() -> Dict[str, str]:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return {"x-internal-token": token}


def _local_clip_path(asset_id: str, storage_key: str) -> str:
    """Return a deterministic local path for a downloaded clip.

    Uses ``asset_id`` as the file stem so downstream embedding caches are keyed
    consistently regardless of the temporary filename assigned by ``download_asset``.
    """
    ext = os.path.splitext(storage_key)[1] or ".mp4"
    local_dir = Path(tempfile.gettempdir()) / "ave_ingest" / asset_id
    local_dir.mkdir(parents=True, exist_ok=True)
    return str(local_dir / f"clip{ext}")


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
async def detect_music_events_activity(asset_id: str, storage_key: str) -> dict:
    """Download a song asset, separate stems, transcribe lyrics, and detect per-stem music events."""
    local_path = download_asset(storage_key)
    try:
        stems = separate_song_stems(local_path)
        stems_dir = Path(stems.get("drums", "")).parent
        if not stems_dir.exists():
            raise FileNotFoundError(f"stems directory missing for asset {asset_id}")
        words = transcribe_song_lyrics(local_path)
        grid = detect_music_events(stems_dir, words, cache_dir=None)
        metadata = {"musicEventGrid": grid.model_dump(by_alias=True)}
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "music_event_grid": metadata["musicEventGrid"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def analyze_loudness_activity(asset_id: str, storage_key: str) -> dict:
    """Download a song asset and measure EBU R128 loudness."""
    local_path = download_asset(storage_key)
    try:
        measurement = analyze_loudness(local_path)
        metadata = {"loudness": measurement.model_dump(by_alias=True)}
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "loudness": metadata["loudness"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def analyze_song_meaning_activity(asset_id: str, storage_key: str) -> dict:
    """Download a song asset, run all song analyses, and persist unified SongMeaning."""
    local_path = download_asset(storage_key)
    try:
        meaning = aggregate_song_meaning(local_path)
        metadata = {"songMeaning": meaning.model_dump(by_alias=True)}
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "song_meaning": metadata["songMeaning"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def compute_clip_heatmap_activity(asset_id: str, storage_key: str) -> dict:
    """Download a clip asset, compute an interestingness heatmap, and persist metadata."""
    local_path = download_asset(storage_key, _local_clip_path(asset_id, storage_key))
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


@activity.defn
async def compute_clip_semantic_activity(asset_id: str, storage_key: str) -> dict:
    """Download a clip asset, compute DINO-v2 semantic embeddings, and persist metadata."""
    local_path = download_asset(storage_key, _local_clip_path(asset_id, storage_key))
    try:
        embedding = embed_clip(local_path, clip_id=asset_id)
        cache_dir = Path(os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")) / "clip_semantic"
        cache_path = str(cache_dir / f"{asset_id}.npz")
        metadata = {
            "dinoEmbeddingPath": cache_path,
            "dinoFirstFramePath": cache_path,
            "dinoLastFramePath": cache_path,
        }
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "dino_embedding": metadata}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def analyze_clip_emotion_activity(asset_id: str, storage_key: str) -> dict:
    """Download a clip asset, compute a fused emotion profile, and persist metadata."""
    local_path = download_asset(storage_key, _local_clip_path(asset_id, storage_key))
    try:
        cache_dir = Path(os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")) / "clip_emotion"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = str(cache_dir / f"{asset_id}.json")
        profile = compute_clip_emotion_profile(local_path, cache_path=cache_path)
        metadata = {"emotionProfile": profile.model_dump(by_alias=True)}
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "emotion_profile": metadata["emotionProfile"]}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


@activity.defn
async def compute_siglip2_embedding_activity(asset_id: str, storage_key: str) -> dict:
    """Download a clip asset, compute SigLIP-2 video embedding, and persist metadata."""
    local_path = download_asset(storage_key, _local_clip_path(asset_id, storage_key))
    try:
        siglip2_embed_video_frames(local_path, clip_id=asset_id)
        cache_dir = Path(os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")) / "siglip2_clip"
        cache_path = str(cache_dir / f"{asset_id}.npy")
        metadata = {"siglip2EmbeddingPath": cache_path}
        await _patch_asset_metadata(asset_id, metadata)
        return {"asset_id": asset_id, "siglip2_embedding": metadata}
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass
