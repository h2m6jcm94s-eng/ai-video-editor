# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for reference intent extraction."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from style_worker.reference_intent import (
    ReferenceIntentProfile,
    ShotIntent,
    _parse_intent_json,
    _audio_context_at,
)


def test_parse_intent_json_valid():
    content = '{"intent": "PUNCTUATE", "confidence": 0.8, "rationale": "hard cut on beat"}'
    intent, conf, rationale = _parse_intent_json(content)
    assert intent == "PUNCTUATE"
    assert conf == 0.8
    assert "hard cut" in rationale


def test_parse_intent_json_invalid_returns_carry():
    intent, conf, _ = _parse_intent_json("not json")
    assert intent == "CARRY"
    assert conf == 0.0


def test_audio_context_at_no_grid():
    assert _audio_context_at(0.0, 1.0, None) == "no audio context"


def test_reference_intent_profile_model_dump_roundtrip():
    profile = ReferenceIntentProfile(
        shot_intents=[
            ShotIntent(
                start_s=0.0,
                end_s=2.0,
                intent="PUNCTUATE",
                confidence=0.9,
                rationale="hard cut",
            )
        ],
        intent_histogram={"PUNCTUATE": 1.0},
        reasoning="test",
    )
    data = profile.model_dump()
    restored = ReferenceIntentProfile.from_cache_dict(data)
    assert restored.shot_intents[0].intent == "PUNCTUATE"
    assert restored.reasoning == "test"
