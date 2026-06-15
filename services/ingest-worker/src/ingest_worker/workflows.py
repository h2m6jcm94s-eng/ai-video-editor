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


@workflow.defn
class ProbeAssetWorkflow:
    """One-shot workflow to probe a single asset after upload."""

    @workflow.run
    async def run(self, input: ProbeAssetInput) -> dict:
        return await workflow.execute_activity(
            "probe_asset",
            args=(input.asset_id, input.storage_key),
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
