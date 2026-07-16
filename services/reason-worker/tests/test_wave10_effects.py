# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Unit tests for Wave 10 mood-driven effect additions."""

import pytest

from reason_worker.wave10_effects import apply_wave_10_effects
from shared_py.models import AdaptiveFeatures, CutList, CutListGlobals, MusicEventGrid, Slot


def _cutlist_with_slots(slots):
    return CutList(
        globals=CutListGlobals(total_duration_s=10.0, tempo_bpm=120.0),
        slots=slots,
    )


def test_wave10_off_by_default():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="drop",
        target_shot_type="close_up",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.9,
    )
    cutlist = _cutlist_with_slots([slot])
    apply_wave_10_effects(
        cutlist,
        music_event_grid=MusicEventGrid(song_hash="x", kick_times=[0.5]),
        features=AdaptiveFeatures(),
    )
    assert all(len(s.effects) == 0 for s in cutlist.slots)


def test_zoom_punch_added_on_kick_for_high_energy_slot():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="drop",
        target_shot_type="close_up",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.9,
    )
    cutlist = _cutlist_with_slots([slot])
    apply_wave_10_effects(
        cutlist,
        music_event_grid=MusicEventGrid(song_hash="x", kick_times=[0.5]),
        features=AdaptiveFeatures(use_wave_10_effects=True),
    )
    assert any(e.type == "zoom_punch_in" for e in slot.effects)


def test_vignette_added_on_crisis_slot():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="drop",
        target_shot_type="close_up",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.9,
        story_beat="CRISIS",
    )
    cutlist = _cutlist_with_slots([slot])
    apply_wave_10_effects(
        cutlist,
        music_event_grid=MusicEventGrid(song_hash="x"),
        features=AdaptiveFeatures(use_wave_10_effects=True),
    )
    assert any(e.type == "vignette" for e in slot.effects)


def test_hm_mvgd_hm_added_to_strongest_slot():
    slots = [
        Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="intro",
            target_shot_type="wide",
            subject_hint="subject",
            motion_hint="static",
            energy_level=0.3,
        ),
        Slot(
            index=1,
            start_s=2.0,
            duration_s=2.0,
            beat_index=1,
            section="drop",
            target_shot_type="close_up",
            subject_hint="subject",
            motion_hint="dynamic",
            energy_level=0.95,
        ),
    ]
    cutlist = _cutlist_with_slots(slots)
    apply_wave_10_effects(
        cutlist,
        music_event_grid=MusicEventGrid(song_hash="x"),
        features=AdaptiveFeatures(use_wave_10_effects=True),
    )
    assert any(e.type == "hm_mvgd_hm" for s in cutlist.slots for e in s.effects)


def test_effect_cap_respected():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="drop",
        target_shot_type="close_up",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.9,
        story_beat="VICTORY",
        arc_beat_emotion_target="triumph",
        effects=[],
    )
    cutlist = _cutlist_with_slots([slot])
    apply_wave_10_effects(
        cutlist,
        music_event_grid=MusicEventGrid(song_hash="x", kick_times=[0.5]),
        features=AdaptiveFeatures(use_wave_10_effects=True),
    )
    assert len(slot.effects) <= 2
    # Crisis/victory vignette and hm_mvgd_hm are the highest-priority additions.
    assert any(e.type == "vignette" for e in slot.effects)
    assert any(e.type == "hm_mvgd_hm" for e in slot.effects)
