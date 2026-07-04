# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import pytest

from reason_worker.speed_ramps import apply_speed_ramp_into_hit
from shared_py.models import MusicEventGrid, Slot


def test_speed_ramp_adds_effect_on_crisis_and_kick():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="drop",
        target_shot_type="wide",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.9,
        story_beat="CRISIS",
    )
    events = MusicEventGrid(song_hash="x", kick_times=[1.0])
    apply_speed_ramp_into_hit(slot, events, arc_beat=None)
    assert len(slot.effects) == 1
    assert slot.effects[0].type == "speed_ramp"
    assert slot.effects[0].params["startSpeed"] == 1.0
    assert slot.effects[0].params["endSpeed"] == 0.5


def test_speed_ramp_skips_without_hit_arc():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="verse",
        target_shot_type="wide",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.5,
        story_beat="VERSE",
    )
    events = MusicEventGrid(song_hash="x", kick_times=[1.0])
    apply_speed_ramp_into_hit(slot, events, arc_beat=None)
    assert not slot.effects


def test_speed_ramp_skips_without_drum_event():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="drop",
        target_shot_type="wide",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.9,
        story_beat="VICTORY",
    )
    events = MusicEventGrid(song_hash="x", kick_times=[2.0])
    apply_speed_ramp_into_hit(slot, events, arc_beat=None)
    assert not slot.effects
