# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the reason worker."""

import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from shared_py.config import settings
from shared_py.logging_config import StructuredLogger
from shared_py.models import AudioTrack, BeatGrid, CutList, LoudnessMeasurement, MusicEventGrid, ShotBoundary, AdaptiveFeatures, BehaviorVector, ClipEmotionProfile, SongMeaning, SongMoodProfile
from shared_py.storage import download_asset
from temporalio import activity

from reason_worker.behavior_corpus import ingest_render_to_corpus
from reason_worker.behavior_engine import BehaviorEngine
from reason_worker.clip_rank import compute_confidence, rank_clips_for_slots
from reason_worker.cutlist_gen import generate_cutlist
from reason_worker.text_edit import apply_text_edits, parse_edit_command
from reason_worker.transition_select import select_xfade

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
async def ensure_song_meaning(song_asset_id: str, song_metadata: dict, storage_key: str) -> dict:
    """Return cached SongMeaning or aggregate it from the song asset."""
    from ingest_worker.song_meaning import aggregate_song_meaning

    existing = (song_metadata or {}).get("songMeaning")
    if existing:
        return {"song_meaning": existing}

    local_path = download_asset(storage_key)
    try:
        meaning = aggregate_song_meaning(local_path)
        metadata = {"songMeaning": meaning.model_dump(by_alias=True)}
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{settings.api_base}/internal/assets/{song_asset_id}/metadata",
                json={"metadata": metadata},
                headers=_internal_headers(),
                timeout=30,
            )
        resp.raise_for_status()
        return {"song_meaning": metadata["songMeaning"]}
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
    clip_asset_ids: Optional[List[str]] = None,
    options: Optional[dict] = None,
    music_event_grid_raw: Optional[dict] = None,
    loudness_measurement_raw: Optional[dict] = None,
    song_meaning_raw: Optional[dict] = None,
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

    options = options or {}
    features = AdaptiveFeatures(**{k: v for k, v in (options.get("adaptiveFeatures") or {}).items()})
    behavior_raw = options.get("behaviorVector")
    behavior = BehaviorVector(**behavior_raw) if behavior_raw else None

    music_event_grid = MusicEventGrid(**music_event_grid_raw) if music_event_grid_raw else None
    loudness_measurement = LoudnessMeasurement(**loudness_measurement_raw) if loudness_measurement_raw else None
    song_meaning = SongMeaning(**song_meaning_raw) if song_meaning_raw else None

    cutlist = generate_cutlist(
        beat_grid,
        shot_boundaries,
        style_analysis,
        energy_curve,
        available_shot_types,
        total_duration=total_duration,
        style_tier=style_tier,
        song_asset_id=song_asset_id,
        user_clip_count=len(clip_asset_ids) if clip_asset_ids else None,
        behavior=behavior,
        features=features,
        music_event_grid=music_event_grid,
        loudness_measurement=loudness_measurement,
        song_meaning=song_meaning,
    )
    return {
        "cutlist": cutlist.model_dump(by_alias=True),
        "behavior": behavior.model_dump(by_alias=True) if behavior else BehaviorVector().model_dump(by_alias=True),
    }


@activity.defn
async def build_audio_mix_activity(
    cutlist_raw: dict,
    clip_asset_ids: List[str],
    clip_storage_keys: Dict[str, str],
    song_meaning_raw: Optional[dict] = None,
    options: Optional[dict] = None,
    beat_grid_raw: Optional[dict] = None,
    song_asset_id: Optional[str] = None,
) -> dict:
    """Build dialogue/audio tracks, apply J/L cuts and stem-aware ducking.

    Falls back to the existing cutlist audio tracks if clip paths are unavailable.
    """
    from reason_worker.audio_mix import build_audio_tracks

    cutlist = CutList(**cutlist_raw)
    features = AdaptiveFeatures(**{k: v for k, v in (options.get("adaptiveFeatures") or {}).items()})

    if not clip_storage_keys or not features.use_jl_cuts and not features.use_stem_aware_audio:
        return {"cutlist": cutlist.model_dump(by_alias=True)}

    clip_paths: Dict[str, str] = {}
    downloaded: List[str] = []
    try:
        for clip_id in clip_asset_ids:
            key = clip_storage_keys.get(clip_id)
            if not key:
                continue
            local_path = download_asset(key)
            downloaded.append(local_path)
            clip_paths[clip_id] = local_path

        beat_grid = BeatGrid(**beat_grid_raw) if beat_grid_raw else None
        song_meaning = SongMeaning(**song_meaning_raw) if song_meaning_raw else None

        audio_tracks = build_audio_tracks(
            cutlist,
            beat_grid=beat_grid,
            song_asset_id=song_asset_id,
            clip_paths=clip_paths,
            behavior=BehaviorVector(),
            song_meaning=song_meaning,
            features=features,
        )
        cutlist.audio_tracks = audio_tracks
        return {"cutlist": cutlist.model_dump(by_alias=True)}
    finally:
        for path in downloaded:
            try:
                os.remove(path)
            except OSError:
                pass


@activity.defn
async def apply_text_edits_activity(
    cutlist_raw: dict,
    edit_commands: List[str],
) -> dict:
    """Parse natural-language edit commands and mutate the cutlist."""
    cutlist = CutList(**cutlist_raw)
    operations = [op for cmd in edit_commands if (op := parse_edit_command(cmd)) is not None]
    apply_text_edits(cutlist, operations)
    return {"cutlist": cutlist.model_dump(by_alias=True)}


@activity.defn
async def rank_clips_activity(
    cutlist_raw: dict,
    clip_asset_ids: List[str],
    clip_metadata: Dict[str, dict],
    fallback_policy: str = "round_robin",
    style_analysis: Optional[dict] = None,
    clip_order_fallback: str = "smart",
    clip_order_smart_threshold: float = 0.15,
    clip_storage_keys: Optional[Dict[str, str]] = None,
) -> dict:
    """Rank user clips for each slot in the cutlist.

    Falls back to ``fallback_policy`` if a slot receives no ranking, so the
    generated cutlist is always renderable as long as at least one clip exists.

    When ``clip_storage_keys`` is provided, clips are downloaded locally so the
    ranker can fall back to SigLIP-2 text-to-clip embeddings and optical-flow
    momentum/anticipation signals.
    """
    if not clip_asset_ids:
        raise ValueError("MISSING_CLIPS: at least one clip is required to generate a renderable cutlist")

    cutlist = CutList(**cutlist_raw)

    # Ensure every clip has a metadata entry with sensible defaults.
    populated_metadata: Dict[str, dict] = {}
    clip_emotion_profiles: Dict[str, ClipEmotionProfile] = {}
    for clip_id in clip_asset_ids:
        meta = clip_metadata.get(clip_id) or {}
        populated_metadata[clip_id] = {
            "shot_type": meta.get("shotType") or meta.get("shot_type") or "medium",
            "motion_energy": meta.get("motionEnergy") or meta.get("motion_energy") or 0.5,
            "aesthetic_score": meta.get("aestheticScore") or meta.get("aesthetic_score") or 0.5,
            "duration_sec": meta.get("durationSec") or meta.get("duration_sec") or 5.0,
            "heatmap": meta.get("heatmap") or [],
        }
        emotion_raw = meta.get("emotionProfile") or meta.get("emotion_profile")
        if emotion_raw:
            try:
                clip_emotion_profiles[clip_id] = ClipEmotionProfile.model_validate(emotion_raw)
            except Exception:
                logger.warning("Invalid emotion_profile for clip %s", clip_id)

    # Download clips when storage keys are available so SigLIP-2 and optical-flow
    # features can run during ranking.
    clip_paths: Dict[str, str] = {}
    local_paths_to_clean: List[str] = []
    if clip_storage_keys:
        for clip_id, storage_key in clip_storage_keys.items():
            if not storage_key:
                continue
            ext = os.path.splitext(storage_key)[1] or ".mp4"
            local_dir = Path(tempfile.gettempdir()) / "ave_rank" / clip_id
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = str(local_dir / f"clip{ext}")
            try:
                download_asset(storage_key, local_path)
                clip_paths[clip_id] = local_path
                local_paths_to_clean.append(local_path)
            except Exception as exc:
                logger.warning("rank_clip_download_failed", clip_id=clip_id, error=str(exc))

    try:
        has_arc_slots = any(s.story_beat for s in cutlist.slots)
        rankings = rank_clips_for_slots(
            cutlist.slots,
            populated_metadata,
            fallback_policy=fallback_policy,
            clip_order_fallback=clip_order_fallback,
            clip_order_smart_threshold=clip_order_smart_threshold,
            clip_emotion_profiles=clip_emotion_profiles or None,
            interleave_glimpses=has_arc_slots and bool(clip_emotion_profiles),
            clip_paths=clip_paths or None,
        )

        confidences = compute_confidence(rankings)

        # Reference transition archetypes (e.g., whip, hard_cut, dissolve) from style
        # analysis, used to pick direction-aware transitions for each slot.
        style_analysis = style_analysis or {}
        ref_archetypes = (
            style_analysis.get("detected_transition_types")
            or style_analysis.get("detectedTransitionTypes")
            or []
        )

        # First pass: select clips and copy heatmap window info.
        selected_motions: dict = {}
        for slot in cutlist.slots:
            scores = rankings.get(slot.index, [])
            if scores:
                top = scores[0]
                slot.selected_clip_id = top.clip_id
                slot.ranked_clip_ids = [s.clip_id for s in scores[:3]]
                # Clamp confidence to the valid API range [0, 0.99].
                slot.confidence = max(0.0, min(0.99, confidences.get(slot.index, 0.5)))
                # Carry the heatmap-best window into the slot so the compiler seeks
                # to the interesting part of the clip instead of the reference time.
                if top.window_start_s is not None:
                    slot.source_window_start_s = top.window_start_s
                if top.window_score is not None:
                    slot.heatmap_score = top.window_score
                slot.emotion_match_score = top.emotion_match_score
                selected_motions[slot.index] = top.dominant_motion

        # Second pass: direction-aware transition selection using outgoing motion from
        # the current slot's clip and incoming motion from the next slot's clip.
        slots = cutlist.slots
        for i, slot in enumerate(slots):
            ref_archetype = ref_archetypes[i % len(ref_archetypes)] if ref_archetypes else "dissolve"
            out_motion = selected_motions.get(slot.index, "still")
            next_slot = slots[i + 1] if i + 1 < len(slots) else None
            in_motion = selected_motions.get(next_slot.index, "still") if next_slot else "still"
            slot.transition_out = select_xfade(out_motion, in_motion, ref_archetype)

        result = cutlist.model_dump(by_alias=True)
    finally:
        for local_path in local_paths_to_clean:
            try:
                os.remove(local_path)
            except OSError:
                pass

    return result


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
async def save_render_signals_activity(
    render_id: str,
    signals: dict,
) -> dict:
    """Persist content signals for a render."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.api_base}/renders/{render_id}/signals",
            json={"signals": signals},
            headers=_internal_headers(),
        )
        resp.raise_for_status()
    return {"ok": True}


@activity.defn
async def save_render_behavior_activity(
    render_id: str,
    behavior: dict,
    predictor_version: str = "heuristic-v1",
    predictor_confidence: float = 0.5,
    predictor_reasoning: Optional[dict] = None,
) -> dict:
    """Persist the behavior vector applied to a render."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.api_base}/renders/{render_id}/behavior",
            json={
                "behavior": behavior,
                "predictorVersion": predictor_version,
                "predictorConfidence": predictor_confidence,
                "predictorReasoning": predictor_reasoning or {"source": "heuristic"},
            },
            headers=_internal_headers(),
        )
        resp.raise_for_status()
    return {"ok": True}


@activity.defn
async def predict_behavior_activity(
    signals: dict,
    user_id: str,
    features_raw: Optional[dict] = None,
    reference_genome: Optional[dict] = None,
) -> dict:
    """Predict a BehaviorVector + confidence + reasoning from signals/corpus."""
    features = AdaptiveFeatures(**(features_raw or {}))
    engine = BehaviorEngine()
    behavior, confidence, reasoning = await engine.predict(
        signals, user_id, features, reference_genome
    )
    return {
        "behavior": behavior.model_dump(by_alias=True),
        "predictorConfidence": confidence,
        "predictorReasoning": reasoning,
    }


@activity.defn
async def ingest_render_to_corpus_activity(render_id: str, quality_weight: float = 0.5) -> dict:
    """Ingest a render's signals + behavior into the behavior corpus."""
    return await ingest_render_to_corpus(render_id, quality_weight)


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
