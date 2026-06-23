# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"""Tests for the segmentation workflow."""

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from segment_worker.activities import segment_subject
from segment_worker.workflows import SegmentSubjectInput, SegmentSubjectWorkflow


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_segment_subject_workflow_runs_activity_and_returns_result():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        asset_id = "11111111-1111-1111-1111-111111111111"
        project_id = "22222222-2222-2222-2222-222222222222"
        storage_key = "projects/2222/clips/1111-test.mp4"
        prompt = "person"
        mode = "image"
        frame_index = 0

        @activity.defn(name="segment_subject")
        async def _segment_subject(
            _asset_id: str,
            _storage_key: str,
            _prompt: str,
            _mode: str,
            _frame_index: int,
            _project_id: str,
        ):
            assert _asset_id == asset_id
            assert _storage_key == storage_key
            assert _prompt == prompt
            assert _mode == mode
            assert _frame_index == frame_index
            assert _project_id == project_id
            return {"available": True, "masks": ["base64mask"], "mask_asset_ids": ["mask-1"]}

        async with Worker(
            env.client,
            task_queue="segment",
            workflows=[SegmentSubjectWorkflow],
            activities=[_segment_subject],
        ):
            result = await env.client.execute_workflow(
                SegmentSubjectWorkflow.run,
                SegmentSubjectInput(
                    asset_id=asset_id,
                    project_id=project_id,
                    storage_key=storage_key,
                    prompt=prompt,
                    mode=mode,
                    frame_index=frame_index,
                ),
                id=f"segment-{asset_id}-{project_id}",
                task_queue="segment",
            )

            # Query should surface the same result.
            handle = env.client.get_workflow_handle(f"segment-{asset_id}-{project_id}")
            queried = await handle.query("get_result")

    assert result["available"] is True
    assert result["mask_asset_ids"] == ["mask-1"]
    assert queried == result


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_segment_subject_workflow_query_returns_none_while_running():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        asset_id = "33333333-3333-3333-3333-333333333333"
        project_id = "44444444-4444-4444-4444-444444444444"

        @activity.defn(name="segment_subject")
        async def _segment_subject(*_args, **_kwargs):
            return {"available": False, "skipped": True}

        async with Worker(
            env.client,
            task_queue="segment",
            workflows=[SegmentSubjectWorkflow],
            activities=[_segment_subject],
        ):
            handle = await env.client.start_workflow(
                SegmentSubjectWorkflow.run,
                SegmentSubjectInput(
                    asset_id=asset_id,
                    project_id=project_id,
                    storage_key="key",
                    prompt="person",
                ),
                id=f"segment-{asset_id}-{project_id}",
                task_queue="segment",
            )

            # Query before completion should return None (activity hasn't finished).
            queried = await handle.query("get_result")
            await handle.result()

    assert queried is None
