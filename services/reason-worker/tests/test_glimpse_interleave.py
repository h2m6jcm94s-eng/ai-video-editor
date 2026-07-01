# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import Slot, ClipScore, ClipEmotionProfile
from reason_worker.clip_rank import _interleave_glimpse_slots, INTERLEAVE_BEATS


def make_slot(index, start_s, duration_s, story_beat="RISING_ACTION"):
    return Slot(
        index=index,
        start_s=start_s,
        duration_s=duration_s,
        beat_index=index,
        section="chorus",
        target_shot_type="medium",
        subject_hint="test",
        motion_hint="static",
        energy_level=0.7,
        story_beat=story_beat,
    )


def make_score(clip_id, profile=None):
    score = ClipScore(
        clip_id=clip_id,
        total_score=1.0,
        emotion_profile=profile,
    )
    return score


def test_interleave_creates_glimpse_slots():
    slot = make_slot(0, 10.0, 3.0)
    profiles = {
        "primary": ClipEmotionProfile(primary_emotion="joy", valence=0.8),
        "past": ClipEmotionProfile(primary_emotion="grief", valence=-0.7),
        "future": ClipEmotionProfile(primary_emotion="triumph", valence=0.6),
    }
    clip_metadata = {
        "primary": {"duration_sec": 5.0},
        "past": {"duration_sec": 5.0},
        "future": {"duration_sec": 5.0},
    }
    rankings = {
        0: [
            make_score("primary", profiles["primary"]),
            make_score("past", profiles["past"]),
            make_score("future", profiles["future"]),
        ]
    }
    slots = [slot]
    new_rankings = _interleave_glimpse_slots(slots, rankings, clip_metadata, profiles)

    assert len(slots) >= 2
    assert any(s.is_glimpse for s in slots)
    assert sum(s.duration_s for s in slots) == pytest.approx(3.0)
    assert all(s.index == i for i, s in enumerate(slots))
    assert len(new_rankings) == len(slots)


def test_interleave_leaves_non_arc_slots_unchanged():
    slot = make_slot(0, 10.0, 3.0, story_beat="WORLD")
    profiles = {"primary": ClipEmotionProfile(primary_emotion="joy", valence=0.8)}
    rankings = {0: [make_score("primary", profiles["primary"])]}
    slots = [slot]
    new_rankings = _interleave_glimpse_slots(slots, rankings, {}, profiles)

    assert len(slots) == 1
    assert not slots[0].is_glimpse
    assert new_rankings[0][0].clip_id == "primary"


def test_interleave_requires_enough_candidates():
    slot = make_slot(0, 10.0, 3.0)
    profiles = {"primary": ClipEmotionProfile(primary_emotion="joy", valence=0.8)}
    rankings = {0: [make_score("primary", profiles["primary"])]}
    slots = [slot]
    new_rankings = _interleave_glimpse_slots(slots, rankings, {}, profiles)

    assert len(slots) == 1
    assert not slots[0].is_glimpse
