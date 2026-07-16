# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for T.9.C.3 semantic + emotion clip ranking signals."""

from __future__ import annotations

import numpy as np

import pytest

from reason_worker.clip_rank import (
    _cosine_similarity,
    _emotion_match_score,
    _mood_motion_consistency,
    _motion_vibe_label,
    _semantic_score,
)
from shared_py.models import ClipEmotionProfile, Slot


def test_emotion_match_score_high_for_matching_emotion():
    profile = ClipEmotionProfile(primary_emotion="grief", valence=-0.5, arousal=0.6, dominance=0.4)
    score = _emotion_match_score(profile, "grief")
    assert score > 0.85


def test_emotion_match_score_default_without_target():
    profile = ClipEmotionProfile(primary_emotion="joy")
    assert _emotion_match_score(profile, None) == 0.0


def test_emotion_match_score_default_without_profile():
    assert _emotion_match_score(None, "grief") == 0.0


def test_mood_motion_consistency_hits_table():
    assert _mood_motion_consistency("aggressive", "frantic") == 1.0
    assert _mood_motion_consistency("melancholic", "frantic") == 0.0
    assert _mood_motion_consistency("unknown", "fluid") == 0.0
    assert _mood_motion_consistency("uplifting", None) == 0.0


def test_motion_vibe_label_buckets():
    assert _motion_vibe_label(0.1) == "still"
    assert _motion_vibe_label(0.35) == "slow"
    assert _motion_vibe_label(0.6) == "fluid"
    assert _motion_vibe_label(0.9) == "frantic"


def test_semantic_score_marengo_tier():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="verse",
        target_shot_type="medium",
        subject_hint="",
        motion_hint="",
        energy_level=0.5,
    )
    slot_emb = np.array([1.0, 0.0], dtype=np.float32)
    clip_emb = np.array([1.0, 0.0], dtype=np.float32)
    score = _semantic_score(slot, "c1", {"c1": clip_emb}, {0: slot_emb})
    assert score == pytest.approx(1.0, abs=1e-4)


def test_semantic_score_default_when_no_embeddings_or_paths():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="verse",
        target_shot_type="medium",
        subject_hint="",
        motion_hint="",
        energy_level=0.5,
    )
    score = _semantic_score(slot, "c1", {}, {})
    assert 0.0 <= score <= 1.0
