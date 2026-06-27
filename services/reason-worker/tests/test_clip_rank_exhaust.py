# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import pytest

from reason_worker.clip_rank import rank_clips_for_slots
from shared_py.models import Slot


def _make_slot(index: int, start_s: float = 0.0, duration_s: float = 1.0) -> Slot:
    return Slot(
        index=index,
        start_s=start_s,
        duration_s=duration_s,
        beat_index=index,
        section="verse",
        transition_in="hard_cut",
        transition_out="hard_cut",
        target_shot_type="wide",
        subject_hint="person",
        motion_hint="static",
        energy_level=0.5,
    )


def test_exhaust_then_reuse_with_three_clips_nine_slots():
    """With 3 clips and 9 slots, each clip should be used at least once before repeats."""
    slots = [_make_slot(i, start_s=i * 1.0) for i in range(9)]
    clip_metadata = {
        "clip-a": {"shot_type": "wide", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0},
        "clip-b": {"shot_type": "wide", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0},
        "clip-c": {"shot_type": "wide", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0},
    }

    rankings = rank_clips_for_slots(slots, clip_metadata, force_exhaust=True)

    selected = [rankings[i][0].clip_id for i in range(len(slots))]
    first_three = set(selected[:3])
    assert len(first_three) == 3, f"first three slots should use all clips, got {first_three}"
    assert first_three == {"clip-a", "clip-b", "clip-c"}


def test_heatmap_window_influences_selection():
    """A clip with a high heatmap window should win over an otherwise equal clip."""
    slots = [_make_slot(0, start_s=0.5, duration_s=1.0)]
    clip_metadata = {
        "boring": {
            "shot_type": "wide",
            "motion_energy": 0.5,
            "aesthetic_score": 0.5,
            "duration_sec": 5.0,
            "heatmap": [
                {"start_s": 0.0, "end_s": 1.0, "score": 0.2, "components": {}},
            ],
        },
        "exciting": {
            "shot_type": "wide",
            "motion_energy": 0.5,
            "aesthetic_score": 0.5,
            "duration_sec": 5.0,
            "heatmap": [
                {"start_s": 0.0, "end_s": 1.0, "score": 0.9, "components": {}},
            ],
        },
    }

    rankings = rank_clips_for_slots(slots, clip_metadata, force_exhaust=False)
    top = rankings[0][0]
    assert top.clip_id == "exciting"
    assert top.window_start_s == 0.0
    assert top.window_score == 0.9


def test_source_window_start_set_on_selected_clip():
    """The best heatmap window start is carried through to the ranking."""
    slots = [_make_slot(0, start_s=0.5, duration_s=1.0)]
    clip_metadata = {
        "clip-1": {
            "shot_type": "wide",
            "motion_energy": 0.5,
            "aesthetic_score": 0.5,
            "duration_sec": 5.0,
            "heatmap": [
                {"start_s": 2.0, "end_s": 3.0, "score": 0.9, "components": {}},
            ],
        },
    }

    rankings = rank_clips_for_slots(slots, clip_metadata, force_exhaust=False)
    top = rankings[0][0]
    assert top.window_start_s == 2.0
