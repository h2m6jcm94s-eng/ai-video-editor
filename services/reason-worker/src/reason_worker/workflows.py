# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal workflow definitions for the reason worker."""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from reason_worker.aspect_detect import detect_aspect_preset
    from shared_py.models import AdaptiveFeatures


def _extract_content_signals(
    project: dict,
    assets: List[dict],
    beat_grid: dict,
    energy_curve: List[float],
    clip_asset_ids: List[str],
    reference_asset_id: Optional[str],
) -> dict:
    """Build a minimal ContentSignals snapshot from available project context."""
    song_asset_id = project.get("songAssetId") or project.get("song_asset_id")
    song_metadata = next((a.get("metadata") or {} for a in assets if a.get("id") == song_asset_id), {})

    clip_assets = [a for a in assets if a.get("id") in clip_asset_ids]
    durations = [a.get("durationSec") or a.get("duration_sec") for a in clip_assets if a.get("durationSec") or a.get("duration_sec")]
    avg_clip_duration = sum(durations) / len(durations) if durations else 0.0

    motion_scores = []
    aesthetic_scores = []
    for meta in [a.get("metadata") or {} for a in clip_assets]:
        if isinstance(meta, dict):
            # B4 anti-decoration: only average real values.  The old ``or 0.5``
            # chain both fabricated medium scores for missing metadata and
            # swallowed legitimately-measured 0.0 values.
            motion_val = meta.get("motion_energy", meta.get("motionEnergy"))
            aesthetic_val = meta.get("aesthetic_score", meta.get("aestheticScore"))
            if motion_val is not None:
                motion_scores.append(float(motion_val))
            if aesthetic_val is not None:
                aesthetic_scores.append(float(aesthetic_val))

    return {
        "speech_ratio": 0.0,
        "avg_speech_segment_duration_s": 0.0,
        "multi_speaker_ratio": 0.0,
        "song_present": bool(song_asset_id),
        "song_energy_mean": float(sum(energy_curve) / len(energy_curve)) if energy_curve else 0.5,
        "song_tempo_bpm": beat_grid.get("bpm") or 120.0,
        "song_section_count": len(beat_grid.get("segments") or []),
        "clip_count": len(clip_asset_ids),
        "clip_avg_duration_s": avg_clip_duration,
        "motion_density": float(sum(motion_scores) / len(motion_scores)) if motion_scores else 0.5,
        "motion_variance": 0.0,
        "aesthetic_score_mean": float(sum(aesthetic_scores) / len(aesthetic_scores)) if aesthetic_scores else 0.5,
        "face_screentime_ratio": 0.0,
        "multi_face_ratio": 0.0,
        "shot_diversity": 0.0,
        "reference_present": bool(reference_asset_id),
        "reference_genome_hash": None,
        "content_embedding": None,
    }


@dataclass
class GenerateFromReferenceInput:
    project_id: str
    generation_job_id: str
    user_id: str
    song_asset_id: str
    clip_asset_ids: List[str] = field(default_factory=list)
    reference_asset_id: Optional[str] = None
    style_tier: str = "full_remix"
    style_analysis: Optional[dict] = None
    asset_key_map: Dict[str, str] = field(default_factory=dict)
    completion_token: str = ""
    options: Optional[dict] = field(default_factory=dict)
    render_id: Optional[str] = None  # When provided, persist signals/behavior for this render.


@workflow.defn
class GenerateFromReferenceWorkflow:
    """Generate a cutlist from a reference video, song, and user clips."""

    async def _publish(self, job_id: str, stage: str, progress: float, message: str) -> None:
        await workflow.execute_activity(
            "publish_progress_activity",
            args=(job_id, stage, progress, message),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

    @workflow.run
    async def run(self, input: GenerateFromReferenceInput) -> Optional[dict]:
        retry = RetryPolicy(maximum_attempts=3)
        job_id = input.generation_job_id

        try:
            await self._publish(job_id, "fetching_context", 5, "Fetching project context")
            context = await workflow.execute_activity(
                "fetch_project_context",
                args=(input.project_id,),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry,
            )

            project = context.get("project") or {}
            assets_by_id = {a["id"]: a for a in context.get("assets", [])}

            reference_asset_id = input.reference_asset_id or project.get("referenceAssetId")
            song_asset_id = input.song_asset_id or project.get("songAssetId")

            if not reference_asset_id or not song_asset_id:
                raise RuntimeError("Project is missing reference video or song asset")

            reference_asset = assets_by_id.get(reference_asset_id, {})
            song_asset = assets_by_id.get(song_asset_id, {})

            reference_storage_key = input.asset_key_map.get(reference_asset_id) or reference_asset.get("storageKey")
            song_storage_key = input.asset_key_map.get(song_asset_id) or song_asset.get("storageKey")

            if not reference_storage_key or not song_storage_key:
                raise RuntimeError("Storage keys missing for reference or song asset")

            # Resolve total duration. Explicit user option wins; otherwise default
            # to the song length (most natural), then reference length. No upper cap
            # — the user controls output length via durationSec or by uploading a
            # shorter song/reference. Floor at 5s to avoid degenerate renders.
            target_duration = (input.options or {}).get("durationSec")
            song_duration = song_asset.get("durationSec")
            reference_duration = reference_asset.get("durationSec")
            if target_duration is not None:
                total_duration = float(target_duration)
            elif song_duration is not None:
                total_duration = float(song_duration)
            elif reference_duration is not None:
                total_duration = float(reference_duration)
            else:
                total_duration = 30.0
            total_duration = max(total_duration, 5.0)

            # Resolve export preset. If the user didn't pick one, infer from the
            # reference video's aspect ratio so a YouTube reference doesn't render
            # as a cropped portrait video.
            options = input.options or {}
            if not options.get("exportPreset"):
                ref_width = reference_asset.get("width")
                ref_height = reference_asset.get("height")
                options = {**options, "exportPreset": detect_aspect_preset(ref_width, ref_height)}
                input.options = options

            await self._publish(job_id, "analyzing_audio", 15, "Detecting beat grid")
            beat_result = await workflow.execute_activity(
                "ensure_beat_grid",
                args=(
                    song_asset_id,
                    song_asset.get("metadata") or {},
                    song_storage_key,
                ),
                start_to_close_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            await self._publish(job_id, "analyzing_video", 30, "Detecting shot boundaries")
            shot_result = await workflow.execute_activity(
                "ensure_shot_boundaries",
                args=(
                    reference_asset_id,
                    reference_asset.get("metadata") or {},
                    reference_storage_key,
                    reference_asset.get("fps") or 30.0,
                ),
                start_to_close_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            await self._publish(job_id, "analyzing_song_meaning", 35, "Loading song meaning")
            meaning_result = await workflow.execute_activity(
                "ensure_song_meaning",
                args=(
                    song_asset_id,
                    song_asset.get("metadata") or {},
                    song_storage_key,
                ),
                start_to_close_timeout=timedelta(seconds=1200),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            clip_asset_ids = input.clip_asset_ids or project.get("clipAssetIds") or []

            signals = _extract_content_signals(
                project=context.get("project", {}),
                assets=context.get("assets", []),
                beat_grid=beat_result["beat_grid"],
                energy_curve=beat_result["energy_curve"],
                clip_asset_ids=clip_asset_ids,
                reference_asset_id=input.reference_asset_id,
            )

            # Optionally override the behavior vector via KNN + per-user bias.
            options = input.options or {}
            features_raw = options.get("adaptiveFeatures") or {}
            predictor_confidence = 0.0
            predictor_reasoning = "heuristic fallback"
            if features_raw.get("useCorpusKnn") or features_raw.get("usePerUserBias"):
                prediction = await workflow.execute_activity(
                    "predict_behavior_activity",
                    args=(signals, input.user_id, features_raw, None),
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                options = {**options, "behaviorVector": prediction["behavior"]}
                input.options = options
                predictor_confidence = prediction.get("predictorConfidence", 0.0)
                predictor_reasoning = prediction.get("predictorReasoning", "")

            await self._publish(job_id, "generating_cutlist", 50, "Generating cutlist from analysis")
            song_meaning_raw = meaning_result.get("song_meaning") or {}
            music_event_grid_raw = song_meaning_raw.get("musicEventGrid")
            loudness_measurement_raw = song_meaning_raw.get("loudness")
            reference_metadata = reference_asset.get("metadata") or {}
            reference_analysis = reference_metadata.get("referenceAnalysis") or reference_metadata.get("reference_analysis") or {}
            reference_intent_profile_raw = reference_analysis.get("intentProfile") or reference_analysis.get("intent_profile")
            generation_result = await workflow.execute_activity(
                "generate_cutlist_activity",
                args=(
                    beat_result["beat_grid"],
                    shot_result["shot_boundaries"],
                    input.style_analysis,
                    beat_result["energy_curve"],
                    total_duration,
                    input.style_tier,
                    song_asset_id,
                    clip_asset_ids,
                    options,
                    music_event_grid_raw,
                    loudness_measurement_raw,
                    song_meaning_raw,
                    reference_intent_profile_raw,
                ),
                start_to_close_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            cutlist_raw = generation_result["cutlist"]
            behavior_raw = generation_result.get("behavior") or {}

            text_edits = options.get("textEdits") or options.get("text_edits")
            if text_edits:
                await self._publish(job_id, "applying_text_edits", 55, "Applying text-based edits")
                edit_result = await workflow.execute_activity(
                    "apply_text_edits_activity",
                    args=(cutlist_raw, text_edits if isinstance(text_edits, list) else [text_edits]),
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                cutlist_raw = edit_result["cutlist"]

            # Persist signals + behavior when this generation is tied to a render.
            if input.render_id:
                await workflow.execute_activity(
                    "save_render_signals_activity",
                    args=(input.render_id, signals),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                await workflow.execute_activity(
                    "save_render_behavior_activity",
                    args=(
                        input.render_id,
                        behavior_raw,
                        "knn-v1",
                        predictor_confidence,
                        {"reasoning": predictor_reasoning},
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                # Corpus ingestion is intentionally deferred to the render worker
                # so the 7-day outcome labeling window can close first.

            await self._publish(job_id, "ranking_clips", 75, "Ranking clips for each slot")
            clip_metadata = {
                clip_id: (assets_by_id.get(clip_id) or {}).get("metadata") or {}
                for clip_id in clip_asset_ids
            }
            clip_storage_keys = {
                clip_id: (input.asset_key_map.get(clip_id) or (assets_by_id.get(clip_id) or {}).get("storageKey"))
                for clip_id in clip_asset_ids
            }
            song_meaning_raw = meaning_result.get("song_meaning") or {}
            music_event_grid_raw = song_meaning_raw.get("musicEventGrid")
            ranked_cutlist = await workflow.execute_activity(
                "rank_clips_activity",
                args=(
                    cutlist_raw,
                    clip_asset_ids,
                    clip_metadata,
                    clip_storage_keys,
                    music_event_grid_raw,
                    song_meaning_raw,
                ),
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=retry,
            )

            features = AdaptiveFeatures(**{k: v for k, v in (options.get("adaptiveFeatures") or {}).items()})
            if features.use_jl_cuts or features.use_stem_aware_audio:
                await self._publish(job_id, "building_audio_mix", 80, "Applying J-cuts, L-cuts, and stem-aware ducking")
                mix_result = await workflow.execute_activity(
                    "build_audio_mix_activity",
                    args=(
                        ranked_cutlist,
                        clip_asset_ids,
                        clip_storage_keys,
                        song_meaning_raw,
                        options,
                        beat_result["beat_grid"],
                        song_asset_id,
                    ),
                    start_to_close_timeout=timedelta(seconds=300),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                ranked_cutlist = mix_result["cutlist"]

            await self._publish(job_id, "saving", 95, "Saving generated cutlist")
            await workflow.execute_activity(
                "save_generated_cutlist",
                args=(input.project_id, job_id, ranked_cutlist, input.completion_token),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry,
            )

            return ranked_cutlist
        except Exception as e:
            error_message = str(e) or "Generation workflow failed"
            await workflow.execute_activity(
                "fail_generation_job",
                args=(job_id, error_message, input.completion_token),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            raise
