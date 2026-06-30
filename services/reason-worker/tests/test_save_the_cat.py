# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for the Save-the-Cat assembler."""

import numpy as np

from shared_py.models import CutList, CutListGlobals, Slot
from reason_worker.save_the_cat import (
    SNYDER_BEAT_PROFILES,
    apply_save_the_cat_beats,
)


def _make_slot(index: int, start_s: float, duration_s: float = 2.0, section: str = "verse") -> Slot:
    return Slot(
        index=index,
        start_s=start_s,
        duration_s=duration_s,
        beat_index=index,
        section=section,
        transition_in="hard_cut",
        transition_out="hard_cut",
        target_shot_type="medium",
        subject_hint="",
        motion_hint="static",
        energy_level=0.5,
        required_tags=[],
        avoid_tags=[],
        effects=[],
    )


def _make_cutlist(slots: list[Slot], total_duration: float = 100.0) -> CutList:
    return CutList(
        globals=CutListGlobals(
            total_duration_s=total_duration,
            tempo_bpm=120.0,
            time_signature="4/4",
            energy_curve=[0.5] * 100,
            section_markers=[],
            aspect_ratio="9:16",
        ),
        slots=slots,
        overlays=[],
        audio_tracks=[],
    )


def test_apply_save_the_cat_trailer_style_labels_all_slots():
    slots = [_make_slot(i, i * 5.0) for i in range(20)]
    cutlist = _make_cutlist(slots, total_duration=100.0)

    result = apply_save_the_cat_beats(cutlist, total_duration=100.0, mode="trailer_style")

    assert result is cutlist
    assert all(slot.story_beat is not None for slot in result.slots)
    assert all(slot.section in {"intro", "verse", "chorus", "drop", "outro"} for slot in result.slots)
    # Ensure the extreme beats are represented somewhere.
    beat_names = {slot.story_beat for slot in result.slots}
    assert "opening_image" in beat_names
    assert "final_image" in beat_names
    assert "finale" in beat_names


def test_apply_save_the_cat_trailer_style_applies_profiles():
    slots = [_make_slot(i, i * 5.0) for i in range(20)]
    cutlist = _make_cutlist(slots, total_duration=100.0)

    apply_save_the_cat_beats(cutlist, total_duration=100.0, mode="trailer_style")

    finale_slot = next(s for s in cutlist.slots if s.story_beat == "finale")
    assert finale_slot.energy_level > 0.5
    assert "motion_scale=" in finale_slot.subject_hint

    # Find a low-energy beat (e.g. opening_image or all_is_lost) and verify damping.
    low_energy_slot = next(
        s for s in cutlist.slots if s.story_beat in {"opening_image", "all_is_lost"}
    )
    assert low_energy_slot.energy_level < 0.5


def test_apply_save_the_cat_trailer_style_with_real_signals():
    duration = 100.0
    motion = np.zeros(1000)
    motion[350:370] = 2.0  # fun and games
    motion[650:670] = 1.5  # bad guys close in
    motion[880:900] = 2.5  # finale
    dialogue = [(6.0, 8.0, "theme")]
    chord_seq = [(0.0, 78.0, "C"), (78.0, 100.0, "F")]

    slots = [_make_slot(i, i * 5.0) for i in range(20)]
    cutlist = _make_cutlist(slots, total_duration=duration)

    result = apply_save_the_cat_beats(
        cutlist,
        total_duration=duration,
        mode="trailer_style",
        motion_curve=motion,
        dialogue_segments=dialogue,
        chord_seq=chord_seq,
    )

    fun = next(b for b in result.slots if b.story_beat == "fun_and_games")
    assert 30.0 <= fun.start_s <= 49.0
    break3 = next(b for b in result.slots if b.story_beat == "break_into_three")
    assert break3.start_s >= 75.0


def test_apply_save_the_cat_speech_coherent_groups_into_thirds():
    slots = [_make_slot(i, i * 2.0) for i in range(20)]
    cutlist = _make_cutlist(slots, total_duration=40.0)

    result = apply_save_the_cat_beats(cutlist, total_duration=40.0, mode="speech_coherent")

    labels = [slot.story_beat for slot in result.slots]
    sections = [slot.section for slot in result.slots]
    assert set(labels) <= {"intro", "body", "climax", "outro"}
    assert set(sections) <= {"intro", "verse", "chorus", "outro"}
    assert labels[0] == "intro"
    assert labels[-1] == "outro"


def test_apply_save_the_cat_off_returns_unchanged():
    slots = [_make_slot(i, i * 2.0, section="verse") for i in range(10)]
    cutlist = _make_cutlist(slots, total_duration=20.0)

    result = apply_save_the_cat_beats(cutlist, total_duration=20.0, mode="off")

    assert result is cutlist
    assert all(slot.story_beat is None for slot in result.slots)
    assert all(slot.section == "verse" for slot in result.slots)


def test_apply_save_the_cat_backward_compatible_signature():
    """The batch2-offline-render.py path still works with two positional args."""
    slots = [_make_slot(i, i * 5.0) for i in range(20)]
    cutlist = _make_cutlist(slots, total_duration=100.0)

    result = apply_save_the_cat_beats(cutlist, 100.0)

    assert all(slot.story_beat is not None for slot in result.slots)
    # Default mode is trailer_style.
    assert any(slot.story_beat == "opening_image" for slot in result.slots)


def test_apply_save_the_cat_preserves_empty_cutlist():
    cutlist = _make_cutlist([], total_duration=100.0)
    result = apply_save_the_cat_beats(cutlist, 100.0, mode="trailer_style")
    assert result.slots == []


def test_snyder_beat_profiles_keys():
    from reason_worker.snyder_detect import SNYDER_PERCENTAGE_ANCHORS
    assert set(SNYDER_BEAT_PROFILES.keys()) == set(SNYDER_PERCENTAGE_ANCHORS.keys())
