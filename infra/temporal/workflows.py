# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal workflow definitions for the AI video editor pipeline."""

from temporalio import workflow
from temporalio.common import RetryPolicy
from dataclasses import dataclass
from typing import List, Dict
from enum import Enum

with workflow.unsafe.imports_passed_through():
    from shared_py.models import CutList, BeatGrid, ShotBoundary


class RenderStage(str, Enum):
    INITIALIZED = "initialized"
    PROBING = "probing"
    BEAT_DETECTION = "beat_detection"
    SHOT_DETECTION = "shot_detection"
    STYLE_ANALYSIS = "style_analysis"
    EMBEDDING = "embedding"
    CUTLIST_GENERATION = "cutlist_generation"
    RANKING = "ranking"
    AWAITING_REVIEW = "awaiting_review"
    RENDERING = "rendering"
    UPLOADING = "uploading"
    COMPLETED = "completed"


@dataclass
class VideoRenderInput:
    project_id: str
    reference_asset_id: str
    song_asset_id: str
    clip_asset_ids: List[str]
    style_tier: str
    mode: str
    user_id: str
    asset_key_map: Dict[str, str]


@dataclass
class AnalysisResult:
    probe: dict
    shots: List[dict]
    beats: dict
    energy_curve: List[float]
    style_analysis: dict
    lut_path: str = ""


@dataclass
class ProbeAssetInput:
    asset_id: str
    storage_key: str


@workflow.defn
class ProbeAssetWorkflow:
    """One-shot workflow to probe a single asset after upload."""

    @workflow.run
    async def run(self, input: ProbeAssetInput) -> dict:
        result = await workflow.execute_activity(
            "probe_asset",
            args=(input.asset_id, input.storage_key),
            start_to_close_timeout=120,
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return result


@workflow.defn
class VideoRenderWorkflow:
    """Main workflow for rendering a video with reference style matching."""

    def __init__(self) -> None:
        self._progress = 0
        self._stage = RenderStage.INITIALIZED

    @workflow.run
    async def run(self, input: VideoRenderInput) -> str:
        # Build per-asset key maps for activities
        clip_key_map = {cid: input.asset_key_map.get(cid, "") for cid in input.clip_asset_ids}

        # 1. Probe inputs
        self._stage = RenderStage.PROBING
        self._progress = 5
        probe = await workflow.execute_activity(
            "probe_inputs",
            args=(input.reference_asset_id, input.song_asset_id, input.clip_asset_ids, input.asset_key_map),
            start_to_close_timeout=60,
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # 2. Detect beats
        self._stage = RenderStage.BEAT_DETECTION
        self._progress = 15
        beats = await workflow.execute_activity(
            "detect_beats",
            args=(input.song_asset_id, input.asset_key_map),
            start_to_close_timeout=120,
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # 3. Detect shots
        self._stage = RenderStage.SHOT_DETECTION
        self._progress = 25
        shots = await workflow.execute_activity(
            "detect_shots",
            args=(input.reference_asset_id, input.asset_key_map),
            start_to_close_timeout=180,
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # 4. Analyze style
        self._stage = RenderStage.STYLE_ANALYSIS
        self._progress = 40
        style = await workflow.execute_activity(
            "analyze_reference_style",
            args=(input.reference_asset_id, input.style_tier, input.asset_key_map),
            start_to_close_timeout=300,
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # 5. Embed clips
        self._stage = RenderStage.EMBEDDING
        self._progress = 55
        await workflow.execute_activity(
            "embed_user_clips",
            args=(input.clip_asset_ids, input.asset_key_map),
            start_to_close_timeout=300,
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # Compute energy curve from beats (placeholder)
        energy_curve = []

        # 6. Generate cut-list
        self._stage = RenderStage.CUTLIST_GENERATION
        self._progress = 70
        cutlist = await workflow.execute_activity(
            "generate_cutlist_claude",
            args=(beats, shots, style, input.style_tier, energy_curve),
            start_to_close_timeout=120,
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # 7. Rank clips
        self._stage = RenderStage.RANKING
        self._progress = 75
        clip_metadata = {}
        for cid, meta in probe.get("clips", {}).items():
            if isinstance(meta, dict) and "error" not in meta:
                clip_metadata[cid] = {
                    "duration_sec": meta.get("duration_sec", 5.0),
                    "shot_type": meta.get("shot_type", "medium"),
                    "aesthetic_score": 0.5,
                    "motion_energy": 0.5,
                }

        await workflow.execute_activity(
            "rank_clips_per_slot",
            args=(cutlist, input.clip_asset_ids, clip_metadata, None),
            start_to_close_timeout=60,
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # If assisted mode, wait for user signal
        if input.mode == "assisted":
            self._stage = RenderStage.AWAITING_REVIEW
            self._progress = 80
            cutlist = await workflow.wait_for_external_signal(
                "cutlist_approved",
                dict,
                timeout=3600 * 24,  # 24 hours
            )

        # 8. Render
        self._stage = RenderStage.RENDERING
        self._progress = 85
        output_path = await workflow.execute_activity(
            "render_720p",
            args=(cutlist, input.clip_asset_ids, clip_key_map, style.get("lut_path"), input.song_asset_id, input.asset_key_map),
            start_to_close_timeout=600,
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # 9. Upload
        self._stage = RenderStage.UPLOADING
        self._progress = 95
        await workflow.execute_activity(
            "upload_to_r2",
            args=(output_path, input.project_id),
            start_to_close_timeout=120,
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # 10. Notify
        self._stage = RenderStage.COMPLETED
        self._progress = 100
        await workflow.execute_activity(
            "notify_user",
            args=(input.user_id, input.project_id),
            start_to_close_timeout=30,
        )

        return output_path

    @workflow.signal
    async def update_progress(self, stage: str, progress: int) -> None:
        self._stage = stage
        self._progress = progress

    @workflow.query
    def get_progress(self) -> dict:
        return {"stage": self._stage, "progress": self._progress}
