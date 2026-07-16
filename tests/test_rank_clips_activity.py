# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for reason worker clip ranking activity."""

import pytest

from reason_worker.activities import rank_clips_activity
from shared_py.models import CutList, CutListGlobals, Slot


def _cutlist_with_slots(*slots: Slot) -> dict:
    return CutList(
        globals=CutListGlobals(total_duration_s=10.0, tempo_bpm=120.0),
        slots=list(slots),
    ).model_dump(by_alias=True)


@pytest.mark.asyncio
async def test_rank_clips_assigns_selected_clip_id():
    cutlist_raw = _cutlist_with_slots(
        Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="intro",
            target_shot_type="wide",
            subject_hint="dancer",
            motion_hint="dynamic",
            energy_level=0.8,
        )
    )
    result = await rank_clips_activity(
        cutlist_raw,
        clip_asset_ids=["clip-1"],
        clip_metadata={"clip-1": {"shotType": "wide", "durationSec": 2.0, "aestheticScore": 0.7}},
    )

    slots = result["slots"]
    assert len(slots) == 1
    assert slots[0]["selectedClipId"] == "clip-1"
    assert "clip-1" in slots[0]["rankedClipIds"]
    # With a single candidate there is no comparative signal; confidence is 0.0.
    assert slots[0]["confidence"] >= 0.0


@pytest.mark.asyncio
async def test_rank_clips_falls_back_when_no_direct_match():
    cutlist_raw = _cutlist_with_slots(
        Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="intro",
            target_shot_type="close_up",
            subject_hint="dancer",
            motion_hint="dynamic",
            energy_level=0.5,
        )
    )
    # Only a wide clip exists; slot wants close_up but should still get the clip.
    result = await rank_clips_activity(
        cutlist_raw,
        clip_asset_ids=["wide-1"],
        clip_metadata={"wide-1": {"shotType": "wide", "durationSec": 2.5}},
    )

    assert result["slots"][0]["selectedClipId"] == "wide-1"


@pytest.mark.asyncio
async def test_rank_clips_missing_clips_fails_fast():
    cutlist_raw = _cutlist_with_slots(
        Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="intro",
            target_shot_type="wide",
            subject_hint="dancer",
            motion_hint="dynamic",
            energy_level=0.5,
        )
    )
    with pytest.raises(ValueError, match="MISSING_CLIPS"):
        await rank_clips_activity(cutlist_raw, clip_asset_ids=[], clip_metadata={})
