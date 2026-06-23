# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal workflow definitions for the segmentation worker."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass
class SegmentSubjectInput:
    """Input for the segment-subject workflow."""

    asset_id: str
    project_id: str
    storage_key: str
    prompt: str
    mode: str = "image"
    frame_index: int = 0


@workflow.defn
class SegmentSubjectWorkflow:
    """Run SAM3 segmentation on an asset and expose the result via query."""

    def __init__(self) -> None:
        self._result: Optional[dict[str, Any]] = None
        self._error: Optional[str] = None

    @workflow.run
    async def run(self, input: SegmentSubjectInput) -> dict[str, Any]:
        retry = RetryPolicy(maximum_attempts=3)
        try:
            self._result = await workflow.execute_activity(
                "segment_subject",
                args=(
                    input.asset_id,
                    input.storage_key,
                    input.prompt,
                    input.mode,
                    input.frame_index,
                    input.project_id,
                ),
                start_to_close_timeout=timedelta(seconds=600),
                retry_policy=retry,
            )
        except Exception as exc:
            self._error = str(exc)
            raise
        return self._result

    @workflow.query
    def get_result(self) -> Optional[dict[str, Any]]:
        """Return the current segmentation result, or None if still running."""
        if self._error is not None:
            return {"error": self._error}
        return self._result
