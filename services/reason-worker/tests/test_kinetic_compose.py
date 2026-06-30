# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import Slot
from reason_worker import kinetic_compose as kt_mod
from reason_worker.kinetic_compose import (
    compose_kinetic_text_for_slot,
    assign_kinetic_text_to_slots,
    _clean_llm_json,
    _parse_kt3_result,
    STYLE_PRESETS,
)


def make_slot(**kwargs):
    defaults = {
        "index": 0,
        "start_s": 0.0,
        "duration_s": 2.0,
        "beat_index": 0,
        "section": "chorus",
        "target_shot_type": "close_up",
        "subject_hint": "test",
        "motion_hint": "static",
        "energy_level": 0.9,
    }
    defaults.update(kwargs)
    return Slot(**defaults)


def test_clean_llm_json_strips_fences():
    raw = '```json\n{"text": "RISE", "style_preset": "anime_impact", "rationale": "climax moment"}\n```'
    assert _clean_llm_json(raw) == {"text": "RISE", "style_preset": "anime_impact", "rationale": "climax moment"}


def test_clean_llm_json_returns_none_for_invalid():
    assert _clean_llm_json("not json") is None


def test_parse_kt3_result_clamps_size_pct():
    slot = make_slot()
    result = {"text": "TOO BIG", "style_preset": "anime_impact", "size_pct": 0.99}
    kt = _parse_kt3_result(result, slot)
    assert kt.size_pct == pytest.approx(0.60)


def test_parse_kt3_result_rejects_invalid_preset():
    slot = make_slot()
    result = {"text": "RISE", "style_preset": "invalid_preset", "rationale": "test"}
    kt = _parse_kt3_result(result, slot)
    assert kt.style_preset == "anime_impact"


def test_compose_skips_low_energy_non_peak_slots():
    slot = make_slot(energy_level=0.3, section="verse", story_beat=None)
    assert compose_kinetic_text_for_slot(slot, use_llm=False) is None


def test_compose_uses_iconic_quote():
    slot = make_slot(story_beat="CLIMAX")
    kt = compose_kinetic_text_for_slot(slot, iconic_text="I really want to stay", previous_texts=[])
    assert kt is not None
    assert kt.text == "I REALLY WANT TO STAY"
    assert kt.tier == "KT2"


def test_assign_kinetic_text_respects_max_count():
    slots = [make_slot(index=i, story_beat="CLIMAX") for i in range(10)]
    
    def fake_compose(slot, **kwargs):
        from reason_worker.kinetic_compose import KineticText
        return KineticText(
            text=f"TEXT{slot.index}",
            tier="KT3",
            style_preset="anime_impact",
            color_hex="#FFFFFF",
            outline=True,
            size_pct=0.5,
            animation="pop",
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(kt_mod, "compose_kinetic_text_for_slot", fake_compose)
    try:
        assign_kinetic_text_to_slots(slots, max_text_count=2)
        enabled = [s for s in slots if s.enable_kinetic_text]
        assert len(enabled) == 2
    finally:
        monkeypatch.undo()


def test_assign_kinetic_text_with_llm_disabled_marks_no_text():
    slots = [make_slot(index=i, story_beat="CLIMAX") for i in range(3)]
    assign_kinetic_text_to_slots(slots, use_llm=False)
    assert not any(s.enable_kinetic_text for s in slots)
