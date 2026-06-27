# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal workflow definitions for the style-analysis worker."""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass
class AnalyzeStyleInput:
    """Input for the standalone style-analysis workflow.

    The workflow downloads the reference video from object storage, then runs
    LUT extraction, motion analysis, transition classification, and text
    overlay detection in parallel.
    """

    asset_id: str
    storage_key: str
    project_id: str = ""
    shot_boundaries: List[dict] = field(default_factory=list)
    lut_strength: float = 0.5
    text_sample_fps: float = 5.0


@dataclass
class AnalyzeStyleOutput:
    color_palette: List[str] = field(default_factory=list)
    contrast_level: float = 1.0
    saturation_level: float = 1.0
    brightness_level: float = 1.0
    lut_extracted: bool = False
    lut_storage_key: Optional[str] = None
    detected_transitions: List[str] = field(default_factory=list)
    detected_overlays: List[dict] = field(default_factory=list)
    camera_motions: List[str] = field(default_factory=list)
    pacing: str = "medium"
    mood: str = "neutral"


@workflow.defn
class AnalyzeStyleWorkflow:
    """Analyze a reference video for color grade, motion, transitions and text."""

    def __init__(self) -> None:
        self._output: Optional[AnalyzeStyleOutput] = None

    @workflow.run
    async def run(self, input: AnalyzeStyleInput) -> AnalyzeStyleOutput:
        retry = RetryPolicy(maximum_attempts=3)
        timeout = timedelta(seconds=300)

        # Download the reference video from R2/S3 to a local temp path.
        reference_video_path = await workflow.execute_activity(
            "download_reference_video",
            args=(input.asset_id, input.storage_key),
            start_to_close_timeout=timeout,
            retry_policy=retry,
        )

        try:
            # LUT extraction is independent of motion/transitions/text — run in parallel
            lut_future = workflow.execute_activity(
                "extract_lut",
                args=(reference_video_path, "", input.lut_strength, input.project_id),
                start_to_close_timeout=timeout,
                retry_policy=retry,
            )

            motion_future = workflow.execute_activity(
                "analyze_motion",
                args=(reference_video_path, input.shot_boundaries),
                start_to_close_timeout=timeout,
                retry_policy=retry,
            )

            transitions_future = workflow.execute_activity(
                "classify_shot_transitions",
                args=(reference_video_path, input.shot_boundaries),
                start_to_close_timeout=timeout,
                retry_policy=retry,
            )

            text_future = workflow.execute_activity(
                "detect_text_overlays",
                args=(reference_video_path, input.text_sample_fps),
                start_to_close_timeout=timeout,
                retry_policy=retry,
            )

            lut_result, motions, transitions, overlays = await asyncio.gather(
                lut_future, motion_future, transitions_future, text_future
            )

            transitions_list = transitions or []
            detected_transitions = [s.get("transition_in", "hard_cut") for s in transitions_list]

            self._output = AnalyzeStyleOutput(
                color_palette=lut_result.get("color_palette", []),
                contrast_level=lut_result.get("contrast_level", 1.0),
                saturation_level=lut_result.get("saturation_level", 1.0),
                brightness_level=lut_result.get("brightness_level", 1.0),
                lut_extracted=lut_result.get("lut_extracted", False),
                lut_storage_key=lut_result.get("lut_storage_key"),
                detected_transitions=detected_transitions,
                detected_overlays=overlays or [],
                camera_motions=motions or [],
            )
            return self._output
        finally:
            await workflow.execute_activity(
                "cleanup_style_assets",
                args=(reference_video_path, ""),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

    @workflow.query
    def get_analysis(self) -> Optional[AnalyzeStyleOutput]:
        """Return the current analysis result, or None if still running."""
        return self._output


@dataclass
class AnalyzeGenomeInput:
    """Input for the standalone Style Genome extraction workflow."""

    asset_id: str
    storage_key: str
    project_id: str = ""
    beat_grid: Optional[dict] = None
    shot_boundaries: List[dict] = field(default_factory=list)
    style_analysis: Optional[dict] = None
    project_clips: Optional[Dict[str, dict]] = None


@workflow.defn
class AnalyzeGenomeWorkflow:
    """Extract a 50-feature Style Genome fingerprint from a reference video."""

    def __init__(self) -> None:
        self._output: Optional[dict] = None

    @workflow.run
    async def run(self, input: AnalyzeGenomeInput) -> dict:
        retry = RetryPolicy(maximum_attempts=3)
        timeout = timedelta(seconds=300)

        reference_video_path = await workflow.execute_activity(
            "download_reference_video",
            args=(input.asset_id, input.storage_key),
            start_to_close_timeout=timeout,
            retry_policy=retry,
        )

        try:
            genome = await workflow.execute_activity(
                "extract_genome_activity",
                args=(
                    reference_video_path,
                    input.beat_grid,
                    input.shot_boundaries,
                    input.style_analysis,
                    input.project_clips,
                ),
                start_to_close_timeout=timeout,
                retry_policy=retry,
            )
            self._output = genome
            return genome
        finally:
            await workflow.execute_activity(
                "cleanup_style_assets",
                args=(reference_video_path, ""),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

    @workflow.query
    def get_genome(self) -> Optional[dict]:
        """Return the current genome result, or None if still running."""
        return self._output
