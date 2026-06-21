# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from reason_worker.activities import (
    ensure_beat_grid,
    ensure_shot_boundaries,
    fetch_project_context,
    generate_cutlist_activity,
    publish_progress_activity,
    rank_clips_activity,
    save_generated_cutlist,
)
from reason_worker.workflows import GenerateFromReferenceInput, GenerateFromReferenceWorkflow


@pytest.fixture(scope="module")
def minimal_cutlist():
    return {
        "globals": {
            "totalDurationS": 10.0,
            "tempoBpm": 120.0,
            "timeSignature": "4/4",
            "aspectRatio": "9:16",
        },
        "slots": [
            {
                "index": 0,
                "startS": 0.0,
                "durationS": 2.0,
                "beatIndex": 0,
                "section": "intro",
                "targetShotType": "wide",
                "subjectHint": "person",
                "motionHint": "static",
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_generate_from_reference_workflow_success(minimal_cutlist):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        project_id = "11111111-1111-1111-1111-111111111111"
        job_id = "22222222-2222-2222-2222-222222222222"
        ref_id = "33333333-3333-3333-3333-333333333333"
        song_id = "44444444-4444-4444-4444-444444444444"
        clip_id = "55555555-5555-5555-5555-555555555555"

        @activity.defn(name="fetch_project_context")
        async def _fetch_project_context(_project_id: str):
            assert _project_id == project_id
            return {
                "project": {
                    "id": project_id,
                    "referenceAssetId": ref_id,
                    "songAssetId": song_id,
                    "clipAssetIds": [clip_id],
                },
                "assets": [
                    {"id": ref_id, "storageKey": "ref.mp4", "durationSec": 10.0, "fps": 30.0, "metadata": {}},
                    {"id": song_id, "storageKey": "song.mp3", "durationSec": 10.0, "metadata": {}},
                    {"id": clip_id, "storageKey": "clip.mp4", "metadata": {"shotType": "wide"}},
                ],
            }

        @activity.defn(name="ensure_beat_grid")
        async def _ensure_beat_grid(_song_asset_id: str, _metadata: dict, _storage_key: str):
            return {
                "beat_grid": {
                    "bpm": 120.0,
                    "beats": [0.0, 0.5],
                    "downbeats": [0.0],
                    "beat_positions": [0.0, 0.5],
                    "segments": [{"start": 0.0, "end": 10.0, "label": "verse"}],
                },
                "energy_curve": [0.5, 0.5],
            }

        @activity.defn(name="ensure_shot_boundaries")
        async def _ensure_shot_boundaries(_reference_asset_id: str, _metadata: dict, _storage_key: str, _fps: float):
            return {
                "shot_boundaries": [
                    {
                        "startFrame": 0,
                        "endFrame": 30,
                        "startS": 0.0,
                        "endS": 1.0,
                        "confidence": 1.0,
                    }
                ]
            }

        @activity.defn(name="generate_cutlist_activity")
        async def _generate_cutlist_activity(*_args, **_kwargs):
            return minimal_cutlist

        @activity.defn(name="rank_clips_activity")
        async def _rank_clips_activity(cutlist_raw: dict, clip_asset_ids: list, clip_metadata: dict):
            cutlist_raw["slots"][0]["selectedClipId"] = clip_id
            cutlist_raw["slots"][0]["rankedClipIds"] = [clip_id]
            cutlist_raw["slots"][0]["confidence"] = 0.95
            return cutlist_raw

        @activity.defn(name="save_generated_cutlist")
        async def _save_generated_cutlist(_project_id: str, _generation_job_id: str, cutlist: dict, _token: str):
            return {"project": {"id": _project_id, "cutList": cutlist}, "job": {"id": _generation_job_id, "status": "complete"}}

        @activity.defn(name="publish_progress_activity")
        async def _publish_progress_activity(*_args, **_kwargs):
            return None

        @activity.defn(name="fail_generation_job")
        async def _fail_generation_job(_generation_job_id: str, _error_message: str, _token: str):
            return {"job": {"id": _generation_job_id, "status": "failed"}}

        async with Worker(
            env.client,
            task_queue="generate",
            workflows=[GenerateFromReferenceWorkflow],
            activities=[
                _fetch_project_context,
                _ensure_beat_grid,
                _ensure_shot_boundaries,
                _generate_cutlist_activity,
                _rank_clips_activity,
                _save_generated_cutlist,
                _publish_progress_activity,
                _fail_generation_job,
            ],
        ):
            result = await env.client.execute_workflow(
                GenerateFromReferenceWorkflow.run,
                GenerateFromReferenceInput(
                    project_id=project_id,
                    generation_job_id=job_id,
                    user_id="user-1",
                    reference_asset_id=ref_id,
                    song_asset_id=song_id,
                    clip_asset_ids=[clip_id],
                    style_analysis={"color_palette": ["#000000"]},
                    asset_key_map={ref_id: "ref.mp4", song_id: "song.mp3"},
                    completion_token="token-123",
                ),
                id=f"generate-{project_id}-{job_id}",
                task_queue="generate",
            )

    assert result["slots"][0]["selectedClipId"] == clip_id
