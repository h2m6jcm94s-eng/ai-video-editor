# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import CutList, CutListGlobals, Slot, BehaviorVector
from reason_worker.audio_mix import _dialogue_segments_for_slot
from reason_worker.audio_scoring import DialogueSegment, ScoringConfig


def _make_slot(source_window_start_s=None, duration_s=5.0, selected_clip_id="c1"):
    return Slot(
        index=0,
        start_s=120.0,
        duration_s=duration_s,
        beat_index=0,
        section="verse",
        target_shot_type="medium",
        subject_hint="person",
        motion_hint="static",
        energy_level=0.5,
        selected_clip_id=selected_clip_id,
        source_window_start_s=source_window_start_s,
    )


def test_dialogue_window_defaults_to_clip_start_when_no_source_window():
    """Regression for PR #9: missing clip audio when source_window_start_s is None.

    The window must be clip-relative (default 0.0), not timeline-relative, so a
    dialogue segment at the beginning of the clip is not discarded.
    """
    slot = _make_slot(source_window_start_s=None)
    cfg = ScoringConfig(min_dialogue_score=0.5)

    def fake_score(_path, cfg=None):
        return [
            DialogueSegment(start_s=0.2, end_s=1.5, speech_score=0.8, phrase_match_score=0.0),
            DialogueSegment(start_s=10.0, end_s=11.0, speech_score=0.8, phrase_match_score=0.0),
        ]

    original = _dialogue_segments_for_slot.__globals__["score_clip_dialogue"]
    try:
        _dialogue_segments_for_slot.__globals__["score_clip_dialogue"] = fake_score
        segs = _dialogue_segments_for_slot(slot, "dummy.mp4", cfg, BehaviorVector())
    finally:
        _dialogue_segments_for_slot.__globals__["score_clip_dialogue"] = original

    assert len(segs) == 1
    assert segs[0].start_s == 0.2
    assert segs[0].end_s == 1.5


def test_dialogue_window_respects_source_window_start():
    """Only dialogue inside the chosen source window should be kept."""
    slot = _make_slot(source_window_start_s=5.0, duration_s=4.0)
    cfg = ScoringConfig(min_dialogue_score=0.5)

    def fake_score(_path, cfg=None):
        return [
            DialogueSegment(start_s=0.5, end_s=1.5, speech_score=0.8, phrase_match_score=0.0),
            DialogueSegment(start_s=6.0, end_s=7.5, speech_score=0.8, phrase_match_score=0.0),
        ]

    original = _dialogue_segments_for_slot.__globals__["score_clip_dialogue"]
    try:
        _dialogue_segments_for_slot.__globals__["score_clip_dialogue"] = fake_score
        segs = _dialogue_segments_for_slot(slot, "dummy.mp4", cfg, BehaviorVector())
    finally:
        _dialogue_segments_for_slot.__globals__["score_clip_dialogue"] = original

    assert len(segs) == 1
    assert segs[0].start_s == 1.0  # 6.0 - 5.0
    assert segs[0].end_s == 2.5  # 7.5 - 5.0, clamped to duration 4.0 -> min(4,2.5)=2.5
