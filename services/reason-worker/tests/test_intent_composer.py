# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reason_worker import intent_composer as composer
from shared_py.models import EDIT_INTENT_LABELS, Slot, SongMeaning, SongNarrative, SectionMoodTags


def _slot(start_s: float, duration_s: float, section: str = "verse", energy: float = 0.5) -> Slot:
    return Slot(
        index=0,
        start_s=start_s,
        duration_s=duration_s,
        beat_index=0,
        section=section,
        target_shot_type="medium",
        subject_hint="",
        motion_hint="static",
        energy_level=energy,
    )


def test_reference_intent_lookup():
    ref = {
        "intentTrajectory": [
            {"intent": "BREATHE", "start_s": 0.0, "end_s": 2.0},
            {"intent": "RAMP_UP", "start_s": 2.0, "end_s": 5.0},
        ]
    }
    assert composer._reference_intent_at(ref, 1.0) == "BREATHE"
    assert composer._reference_intent_at(ref, 3.0) == "RAMP_UP"
    assert composer._reference_intent_at(ref, 6.0) is None


def test_reference_intent_lookup_tuple_form():
    ref = {"intent_trajectory": [("CARRY", 0.0, 4.0), ("RELEASE", 4.0, 8.0)]}
    assert composer._reference_intent_at(ref, 2.0) == "CARRY"
    assert composer._reference_intent_at(ref, 5.0) == "RELEASE"


def test_energy_section_intent():
    assert composer._energy_section_intent(0.8, "drop") == "RELEASE"
    assert composer._energy_section_intent(0.2, "verse") == "BREATHE"
    assert composer._energy_section_intent(0.5, "verse") == "CARRY"


def test_mood_intent():
    assert composer._mood_intent("aggressive") == "SHOCK"
    assert composer._mood_intent("peaceful") == "BREATHE"
    assert composer._mood_intent("unknown") is None


def test_break_runs():
    intents = ["CARRY", "CARRY", "CARRY", "RELEASE", "RELEASE", "RELEASE"]
    result = composer._break_runs(intents)
    assert result[0] == "CARRY"
    assert result[1] == "CARRY"
    assert result[2] != "CARRY"
    assert result[3] == "RELEASE"
    assert result[4] == "RELEASE"
    assert result[5] != "RELEASE"


def test_assign_intents_to_empty_slots():
    composer.assign_intents_to_slots([])


def test_assign_intents_basic():
    slots = [
        _slot(0.0, 2.0, "intro", 0.2),
        _slot(2.0, 2.0, "verse", 0.4),
        _slot(4.0, 2.0, "chorus", 0.8),
        _slot(6.0, 2.0, "outro", 0.2),
    ]
    composer.assign_intents_to_slots(slots, energy_curve=[0.2, 0.4, 0.8, 0.2])
    for slot in slots:
        assert slot.intent in EDIT_INTENT_LABELS
    assert slots[0].intent in {"BREATHE", "LINGER"}
    assert slots[2].intent in {"RELEASE", "AMPLIFY", "PUNCTUATE"}


def test_assign_intents_prefers_reference():
    slots = [_slot(0.5, 1.0, "verse", 0.8)]
    ref = {"intentTrajectory": [{"intent": "LINGER", "start_s": 0.0, "end_s": 2.0}]}
    composer.assign_intents_to_slots(slots, reference_intent_profile=ref, energy_curve=[0.8])
    assert slots[0].intent == "LINGER"


def test_assign_intents_uses_song_mood():
    slots = [_slot(1.0, 2.0, "bridge", 0.2)]
    song_meaning = SongMeaning(
        song_hash="test",
        section_moods=[
            SectionMoodTags(start_s=0.0, end_s=3.0, section_label="bridge", top_moods=[("sad", 0.9)])
        ],
    )
    composer.assign_intents_to_slots(slots, song_meaning=song_meaning, energy_curve=[0.2])
    assert slots[0].intent == "WITHHOLD"


def test_assign_intents_uses_arc():
    slots = [_slot(1.0, 2.0, "verse", 0.5)]

    class FakeAnchor:
        name = "climax"
        start_s = 0.0
        end_s = 3.0

    class FakeArc:
        name = "trailer"

    composer.assign_intents_to_slots(slots, arc_template=FakeArc(), arc_anchors=[FakeAnchor()], energy_curve=[0.5])
    assert slots[0].intent == "RELEASE"
