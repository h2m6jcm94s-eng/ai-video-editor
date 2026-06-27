# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import Slot
from reason_worker.lyric_overlays import (
    generate_slot_text_overlay,
    should_render_behind_subject,
)


def _slot(section: str, **overrides) -> Slot:
    defaults = {
        "index": 0,
        "start_s": 0.0,
        "duration_s": 1.0,
        "beat_index": 0,
        "target_shot_type": "wide",
        "subject_hint": "person",
        "motion_hint": "static",
        "energy_level": 0.5,
    }
    defaults.update(overrides)
    return Slot(section=section, **defaults)


def test_generate_slot_text_overlay_returns_none_by_default():
    """Hard-coded section labels are disabled; no song metadata means no text."""
    assert generate_slot_text_overlay(_slot("verse")) is None
    assert generate_slot_text_overlay(_slot("chorus")) is None
    assert generate_slot_text_overlay(_slot("drop")) is None


def test_generate_slot_text_overlay_uses_lyrics_when_provided():
    """When real lyrics are supplied, pick the word in the slot window."""
    song_metadata = {
        "lyrics": [
            {"onset_s": 0.3, "text": "hello"},
            {"onset_s": 1.5, "text": "world"},
        ]
    }
    slot = _slot("chorus", start_s=0.0, duration_s=1.0)
    assert generate_slot_text_overlay(slot, song_metadata=song_metadata) == "HELLO"

    slot = _slot("chorus", start_s=1.0, duration_s=1.0)
    assert generate_slot_text_overlay(slot, song_metadata=song_metadata) == "WORLD"


def test_should_render_behind_subject_true_when_matte_present():
    slot = _slot(
        "chorus",
        enable_kinetic_text=True,
        text_z_layer="behind_subject",
        identity_ids_present=[1],
        protagonist_matte_enabled=True,
    )
    assert should_render_behind_subject(slot) is True


def test_should_render_behind_subject_false_when_disabled():
    slot = _slot(
        "chorus",
        enable_kinetic_text=False,
        text_z_layer="behind_subject",
        identity_ids_present=[1],
        protagonist_matte_enabled=True,
    )
    assert should_render_behind_subject(slot) is False


def test_should_render_behind_subject_false_when_on_top():
    slot = _slot(
        "chorus",
        enable_kinetic_text=True,
        text_z_layer="on_top",
        identity_ids_present=[1],
        protagonist_matte_enabled=True,
    )
    assert should_render_behind_subject(slot) is False


def test_should_render_behind_subject_false_when_no_identity():
    slot = _slot(
        "chorus",
        enable_kinetic_text=True,
        text_z_layer="behind_subject",
        identity_ids_present=[],
        protagonist_matte_enabled=True,
    )
    assert should_render_behind_subject(slot) is False


def test_should_render_behind_subject_false_when_matte_disabled():
    slot = _slot(
        "chorus",
        enable_kinetic_text=True,
        text_z_layer="behind_subject",
        identity_ids_present=[1],
        protagonist_matte_enabled=False,
    )
    assert should_render_behind_subject(slot) is False
