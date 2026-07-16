# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reason_worker import intent_technique_mapper as mapper
from shared_py.models import Slot


def _slot(intent: str) -> Slot:
    return Slot(
        index=0,
        start_s=0.0,
        duration_s=1.0,
        beat_index=0,
        section="verse",
        transition_in="hard_cut",
        transition_out="hard_cut",
        target_shot_type="medium",
        subject_hint="",
        motion_hint="static",
        energy_level=0.5,
        intent=intent,
    )


def test_empty_slots():
    mapper.apply_techniques_from_intents([])


def test_breathe_maps_to_fade_and_wide():
    slots = [_slot("BREATHE")]
    mapper.apply_techniques_from_intents(slots)
    assert slots[0].transition_in == "fade"
    assert slots[0].target_shot_type == "wide"
    assert slots[0].motion_hint == "static"
    assert slots[0].text_density == "low"


def test_release_maps_to_hard_cut_and_wide():
    slots = [_slot("RELEASE")]
    mapper.apply_techniques_from_intents(slots)
    assert slots[0].transition_in == "hard_cut"
    assert slots[0].target_shot_type == "wide"
    assert slots[0].motion_hint == "explosive"


def test_withhold_maps_to_close_up():
    slots = [_slot("WITHHOLD")]
    mapper.apply_techniques_from_intents(slots)
    assert slots[0].transition_in == "fade"
    assert slots[0].target_shot_type == "close_up"
    assert slots[0].motion_hint == "static"


def test_adjacent_transitions_align():
    slots = [_slot("BREATHE"), _slot("RELEASE")]
    mapper.apply_techniques_from_intents(slots)
    assert slots[0].transition_out == slots[1].transition_in


def test_smooth_pair_uses_dissolve():
    slots = [_slot("BREATHE"), _slot("LINGER")]
    mapper.apply_techniques_from_intents(slots)
    assert slots[0].transition_out == "dissolve"
    assert slots[1].transition_in == "dissolve"


def test_hard_pair_uses_hard_cut():
    slots = [_slot("SHOCK"), _slot("RELEASE")]
    mapper.apply_techniques_from_intents(slots)
    assert slots[0].transition_out == "hard_cut"
    assert slots[1].transition_in == "hard_cut"


def test_reference_hard_bias():
    slots = [_slot("PUNCTUATE")]
    mapper.apply_techniques_from_intents(slots, reference_transitions=["hard_cut"] * 10)
    assert slots[0].transition_in == "hard_cut"


def test_reference_hard_bias_respects_explicit_fade():
    slots = [_slot("LINGER")]
    mapper.apply_techniques_from_intents(slots, reference_transitions=["hard_cut"] * 10)
    assert slots[0].transition_in == "dissolve"


def test_unknown_intent_defaults_to_carry():
    slots = [_slot("UNKNOWN")]
    mapper.apply_techniques_from_intents(slots)
    assert slots[0].target_shot_type == "medium"
