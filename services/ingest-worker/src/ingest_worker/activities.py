# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the ingest worker."""

from temporalio import activity

from ingest_worker.probe import probe_asset_remote


@activity.defn
async def probe_asset(asset_id: str, storage_key: str) -> dict:
    """Probe a single asset and report metadata back to the API."""
    return probe_asset_remote(asset_id, storage_key)
