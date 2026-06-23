# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal workflow definitions for the reason worker."""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy


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

            # Resolve total duration from the song asset, falling back to reference.
            total_duration = song_asset.get("durationSec") or reference_asset.get("durationSec") or 30.0

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

            await self._publish(job_id, "generating_cutlist", 50, "Generating cutlist from analysis")
            cutlist_raw = await workflow.execute_activity(
                "generate_cutlist_activity",
                args=(
                    beat_result["beat_grid"],
                    shot_result["shot_boundaries"],
                    input.style_analysis,
                    beat_result["energy_curve"],
                    total_duration,
                    input.style_tier,
                ),
                start_to_close_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            await self._publish(job_id, "ranking_clips", 75, "Ranking clips for each slot")
            clip_asset_ids = input.clip_asset_ids or project.get("clipAssetIds") or []
            clip_metadata = {
                clip_id: (assets_by_id.get(clip_id) or {}).get("metadata") or {}
                for clip_id in clip_asset_ids
            }
            ranked_cutlist = await workflow.execute_activity(
                "rank_clips_activity",
                args=(cutlist_raw, clip_asset_ids, clip_metadata),
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=retry,
            )

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
