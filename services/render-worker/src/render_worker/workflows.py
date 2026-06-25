# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal workflow definitions for the render worker."""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass
class VideoRenderInput:
    project_id: str
    song_asset_id: str
    clip_asset_ids: List[str]
    style_tier: str
    mode: str
    user_id: str
    asset_key_map: Dict[str, str]
    reference_asset_id: Optional[str] = None
    completion_token: Optional[str] = None
    style_analysis: Optional[dict] = None
    mask_asset_ids: List[str] = field(default_factory=list)
    mask_source_map: Dict[str, str] = field(default_factory=dict)


@workflow.defn
class VideoRenderWorkflow:
    """Render a video from the project's existing cut-list."""

    @workflow.run
    async def run(self, input: VideoRenderInput) -> str:
        # 1. Fetch project details (cut-list, asset IDs, active render job)
        project_info = await workflow.execute_activity(
            "fetch_project",
            args=(input.project_id,),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )

        project = project_info["project"]
        active_render = project_info.get("activeRender")
        if not active_render:
            raise RuntimeError(f"No active render job for project {input.project_id}")

        render_id = active_render["id"]
        cutlist = project.get("cutList")
        if not cutlist:
            raise RuntimeError(f"Project {input.project_id} has no cut-list")

        # Build asset key map from API response, falling back to workflow input
        asset_key_map = {a["id"]: a["storageKey"] for a in project_info.get("assets", [])}
        asset_key_map.update(input.asset_key_map)

        # Gather clip, audio-track, song, and reference asset IDs needed for the render.
        slot_clip_ids = {
            slot.get("selectedClipId")
            for slot in cutlist.get("slots", [])
            if slot.get("selectedClipId")
        }
        audio_track_ids = {
            track.get("assetId") or track.get("asset_id")
            for track in cutlist.get("audioTracks", [])
            if track.get("assetId") or track.get("asset_id")
        }
        required_asset_ids = sorted(slot_clip_ids | audio_track_ids)
        if project.get("songAssetId"):
            required_asset_ids.append(project["songAssetId"])
        if project.get("referenceAssetId"):
            required_asset_ids.append(project["referenceAssetId"])

        # 2. Download required assets
        download_result = await workflow.execute_activity(
            "download_render_assets",
            args=(required_asset_ids, asset_key_map),
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        output_path: Optional[str] = None
        try:
            # Resolve export preset from the active render row (preset wins over cut-list aspect ratio)
            active_render = project_info.get("activeRender") or {}
            export_preset = (active_render.get("options") or {}).get("exportPreset")

            # 3. Compile the final video
            output_path = await workflow.execute_activity(
                "compile_render",
                args=(
                    cutlist,
                    download_result,
                    input.song_asset_id,
                    input.reference_asset_id,
                    input.style_analysis,
                    input.mask_source_map,
                    export_preset,
                    input.style_tier,
                ),
                start_to_close_timeout=timedelta(seconds=600),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            # 4. Upload output to R2 and create asset row
            upload_result = await workflow.execute_activity(
                "upload_render",
                args=(output_path, input.project_id, render_id),
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            # 5. Mark render job complete
            await workflow.execute_activity(
                "complete_render",
                args=(render_id, upload_result["asset_id"], input.completion_token),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )

            return upload_result["storage_key"]
        finally:
            # Always remove locally downloaded assets and the rendered scratch file.
            await workflow.execute_activity(
                "cleanup_render_assets",
                args=(download_result, output_path),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
