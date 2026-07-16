# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal workflow definitions for the ingest worker."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass
class ProbeAssetInput:
    asset_id: str
    storage_key: str
    asset_type: str = ""


@workflow.defn
class ProbeAssetWorkflow:
    """One-shot workflow to probe a single asset after upload and run optional analysis."""

    @workflow.run
    async def run(self, input: ProbeAssetInput) -> dict:
        probe = await workflow.execute_activity(
            "probe_asset",
            args=(input.asset_id, input.storage_key),
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        futures = []
        asset_type = (input.asset_type or "").lower()

        if asset_type == "song":
            futures.append(
                workflow.execute_activity(
                    "detect_beats_activity",
                    args=(input.asset_id, input.storage_key),
                    start_to_close_timeout=timedelta(seconds=300),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            )
            futures.append(
                workflow.execute_activity(
                    "analyze_loudness_activity",
                    args=(input.asset_id, input.storage_key),
                    start_to_close_timeout=timedelta(seconds=300),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            )
            futures.append(
                workflow.execute_activity(
                    "analyze_song_meaning_activity",
                    args=(input.asset_id, input.storage_key),
                    start_to_close_timeout=timedelta(seconds=1200),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            )

        if asset_type in {"reference_video", "clip"}:
            fps = probe.get("fps") or 30.0
            futures.append(
                workflow.execute_activity(
                    "detect_shot_boundaries_activity",
                    args=(input.asset_id, input.storage_key, fps),
                    start_to_close_timeout=timedelta(seconds=300),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            )

        if asset_type == "clip":
            futures.append(
                workflow.execute_activity(
                    "compute_clip_heatmap_activity",
                    args=(input.asset_id, input.storage_key),
                    start_to_close_timeout=timedelta(seconds=300),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            )
            futures.append(
                workflow.execute_activity(
                    "compute_clip_semantic_activity",
                    args=(input.asset_id, input.storage_key),
                    start_to_close_timeout=timedelta(seconds=600),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            )
            futures.append(
                workflow.execute_activity(
                    "analyze_clip_emotion_activity",
                    args=(input.asset_id, input.storage_key),
                    start_to_close_timeout=timedelta(seconds=600),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            )
            futures.append(
                workflow.execute_activity(
                    "compute_clip_capability_activity",
                    args=(input.asset_id, input.storage_key),
                    start_to_close_timeout=timedelta(seconds=600),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            )

        results = await asyncio.gather(*futures) if futures else []

        # Phase 3: for reference videos, kick off style analysis as an independent
        # child workflow once shot boundaries are known. Using PARENT_CLOSE_POLICY_ABANDON
        # lets the style analysis continue even after this probe workflow finishes.
        if asset_type == "reference_video":
            shot_boundaries = []
            for result in results:
                if isinstance(result, dict) and "shot_boundaries" in result:
                    shot_boundaries = result.get("shot_boundaries", [])
                    break

            await workflow.start_child_workflow(
                "AnalyzeStyleWorkflow",
                {
                    "asset_id": input.asset_id,
                    "storage_key": input.storage_key,
                    "project_id": getattr(input, "project_id", None) or "",
                    "shot_boundaries": shot_boundaries,
                    "lut_strength": 0.5,
                    "text_sample_fps": 5.0,
                },
                id=f"style-{input.asset_id}",
                task_queue="style",
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )

        return {"probe": probe, "analysis": results}
