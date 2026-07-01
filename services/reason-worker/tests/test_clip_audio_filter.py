# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for clip audio inclusion filter."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import BehaviorVector
from reason_worker.clip_audio_filter import AudioSegment, filter_clip_audio_for_inclusion


def _make_seg(text=None, is_speech=True, importance=0.5, iconic_score=0.0):
    return AudioSegment(
        start_s=0.0,
        end_s=1.0,
        text=text,
        is_speech=is_speech,
        importance=importance,
        iconic_score=iconic_score,
    )


def test_iconic_only_keeps_high_iconic_quote():
    behavior = BehaviorVector(
        clip_audio_inclusion_strategy="iconic_only",
        clip_audio_min_importance=0.85,
        sfx_mute_aggressiveness=0.9,
    )
    segments = [
        _make_seg("I want to be a legend", is_speech=True, importance=0.95, iconic_score=0.9),
        _make_seg("random grunt", is_speech=True, importance=0.4, iconic_score=0.2),
    ]
    survivors = filter_clip_audio_for_inclusion(segments, behavior)
    assert len(survivors) == 1
    assert survivors[0].text == "I want to be a legend"


def test_speech_only_drops_non_speech_when_mute_aggressive():
    behavior = BehaviorVector(
        clip_audio_inclusion_strategy="speech_only",
        clip_audio_min_importance=0.3,
        sfx_mute_aggressiveness=0.9,
    )
    segments = [
        _make_seg("I want to be a legend", is_speech=True, importance=0.95),
        _make_seg(None, is_speech=False, importance=0.6),  # explosion / SFX
    ]
    survivors = filter_clip_audio_for_inclusion(segments, behavior)
    assert len(survivors) == 1
    assert survivors[0].is_speech is True


def test_never_mutes_everything():
    behavior = BehaviorVector(
        clip_audio_inclusion_strategy="never",
        clip_audio_min_importance=0.0,
        sfx_mute_aggressiveness=0.0,
    )
    segments = [
        _make_seg("important line", is_speech=True, importance=0.99),
    ]
    survivors = filter_clip_audio_for_inclusion(segments, behavior)
    assert len(survivors) == 0


def test_importance_gate_drops_low_score():
    behavior = BehaviorVector(
        clip_audio_inclusion_strategy="always",
        clip_audio_min_importance=0.7,
        sfx_mute_aggressiveness=0.0,
    )
    segments = [
        _make_seg("loud clear line", is_speech=True, importance=0.8),
        _make_seg("mumble", is_speech=True, importance=0.3),
    ]
    survivors = filter_clip_audio_for_inclusion(segments, behavior)
    assert len(survivors) == 1
    assert survivors[0].text == "loud clear line"
