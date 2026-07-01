# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import Slot, ClipEmotionProfile
from reason_worker.clip_rank import _score_clip, _emotion_label_to_vector


def test_emotion_label_vector_shape():
    vec = _emotion_label_to_vector("anger")
    assert len(vec) == 12
    assert vec[7] == 1.0  # anger is 8th in order (0-indexed: 7)


def test_score_clip_without_arc_has_zero_emotion_match():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="verse",
        target_shot_type="medium",
        subject_hint="test",
        motion_hint="static",
        energy_level=0.5,
    )
    meta = {"shot_type": "medium", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0}
    score = _score_clip(slot, "c1", meta, {}, {}, [])
    assert score.emotion_match_score == 0.0


def test_score_clip_arc_prefers_matching_emotion():
    slot = Slot(
        index=0,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="verse",
        target_shot_type="medium",
        subject_hint="test",
        motion_hint="static",
        energy_level=0.5,
        story_beat="CRISIS",
        arc_beat_emotion_target="fear",
    )
    meta = {"shot_type": "medium", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0}

    fear_profile = ClipEmotionProfile(primary_emotion="fear", face_emotion_distribution={"fear": 1.0})
    calm_profile = ClipEmotionProfile(primary_emotion="calm", face_emotion_distribution={"calm": 1.0})

    fear_score = _score_clip(slot, "c1", meta, {}, {}, [], emotion_profile=fear_profile)
    calm_score = _score_clip(slot, "c2", meta, {}, {}, [], emotion_profile=calm_profile)

    assert fear_score.emotion_match_score > calm_score.emotion_match_score
    assert fear_score.total_score > calm_score.total_score
