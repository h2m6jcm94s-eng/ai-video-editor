# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import numpy as np
import pytest

from reason_worker.transition_select import select_xfade
from shared_py.models import MusicEventGrid, Slot


def test_whip_left_uses_hlslice():
    assert select_xfade("left", "left", "whip") == "hlslice"


def test_whip_right_uses_hrslice():
    assert select_xfade("right", "right", "whip") == "hrslice"


def test_hard_cut_with_motion_uses_hard_cut():
    assert select_xfade("left", "right", "hard_cut") == "hard_cut"


def test_hard_cut_still_uses_fade():
    assert select_xfade("still", "still", "hard_cut") == "fade"


def test_match_cut_same_motion_uses_dissolve():
    assert select_xfade("left", "left", "match_cut") == "dissolve"


def test_dissolve_archetype_uses_dissolve():
    assert select_xfade("left", "right", "dissolve") == "dissolve"


def test_fade_archetype_uses_fade():
    assert select_xfade("still", "still", "fade") == "fade"


def test_kick_event_uses_hard_cut():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="drop",
        target_shot_type="wide",
        subject_hint="s",
        motion_hint="dynamic",
        energy_level=0.8,
    )
    events = MusicEventGrid(song_hash="x", kick_times=[1.0])
    assert select_xfade("still", "still", "dissolve", slot=slot, music_events=events) == "hard_cut"


def test_bass_drop_adds_flash_frame():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="drop",
        target_shot_type="wide",
        subject_hint="s",
        motion_hint="dynamic",
        energy_level=0.9,
    )
    events = MusicEventGrid(song_hash="x", bass_drop_times=[1.0])
    extra = {}
    result = select_xfade("still", "still", "hard_cut", slot=slot, music_events=events, extra=extra)
    assert result == "hard_cut"
    assert extra.get("flash_frame") is True


def test_match_cut_bonus_on_high_dino_similarity():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="drop",
        target_shot_type="wide",
        subject_hint="s",
        motion_hint="dynamic",
        energy_level=0.8,
    )
    emb = np.ones(768, dtype=np.float32)
    extra = {}
    result = select_xfade("still", "still", "dissolve", slot=slot, out_dino=emb, in_dino=emb, extra=extra)
    assert result == "hard_cut"
    assert extra.get("match_cut_bonus") is True


def test_melancholic_mood_forces_dissolve():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="verse",
        target_shot_type="wide",
        subject_hint="s",
        motion_hint="still",
        energy_level=0.2,
    )
    assert select_xfade("still", "still", "hard_cut", slot=slot, section_mood="melancholic") == "dissolve"


def test_aggressive_mood_forces_hard_cut():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="drop",
        target_shot_type="wide",
        subject_hint="s",
        motion_hint="dynamic",
        energy_level=0.8,
    )
    assert select_xfade("still", "still", "dissolve", slot=slot, section_mood="aggressive") == "hard_cut"


def test_absolute_fallback_is_hard_cut_and_logs():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="verse",
        target_shot_type="wide",
        subject_hint="s",
        motion_hint="still",
        energy_level=0.5,
    )
    extra = {}
    # Unknown archetype with no music events triggers the absolute fallback.
    result = select_xfade("still", "still", "unknown_archetype", slot=slot, extra=extra)
    assert result == "hard_cut"
    assert extra.get("fallback_hardcut") is True
