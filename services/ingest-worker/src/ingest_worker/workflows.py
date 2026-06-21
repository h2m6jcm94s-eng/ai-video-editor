# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal workflow definitions for the ingest worker."""

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

        results = await workflow.gather(*futures) if futures else []
        return {"probe": probe, "analysis": results}
