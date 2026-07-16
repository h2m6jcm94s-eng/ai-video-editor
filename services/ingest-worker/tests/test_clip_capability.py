# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ingest_worker import clip_capability as cap_mod
from shared_py.models import ClipCapabilityProfile, ClipEmotionProfile


def test_cache_path_for_clip(tmp_path):
    cache_dir = tmp_path / "caps"
    path = cap_mod.cache_path_for_clip("/tmp/clip.mp4", cache_dir=cache_dir)
    assert path == str(cache_dir / "clip.json")


def test_aggregate_features_empty():
    features = cap_mod._aggregate_features(
        duration_sec=3.0,
        windows=[],
        emotion_profile=None,
        semantic_embedding=None,
        faces=[],
    )
    assert features["duration_sec"] == 3.0
    # Anti-decoration: missing raw signals must not pretend to be average.
    assert features["mean_motion"] == 0.0
    assert features["stability"] == 0.0
    assert features["aesthetic"] == 0.0
    assert features["sharpness"] == 0.0
    assert features["audio_arousal"] == 0.0
    assert features["motion_trend"] == "static"
    assert features["face_count_mode"] == 0
    assert features["heatmap_missing"]
    assert features["emotion_missing"]
    assert features["semantic_missing"]
    assert features["face_missing"]


def test_aggregate_features_with_heatmap():
    windows = [
        {"motion": 0.1, "aesthetic": 0.6, "sharpness": 0.5, "stability": 0.8, "dominant_motion": "still"},
        {"motion": 0.2, "aesthetic": 0.6, "sharpness": 0.5, "stability": 0.8, "dominant_motion": "still"},
        {"motion": 0.3, "aesthetic": 0.6, "sharpness": 0.5, "stability": 0.8, "dominant_motion": "right"},
        {"motion": 0.4, "aesthetic": 0.6, "sharpness": 0.5, "stability": 0.8, "dominant_motion": "right"},
        {"motion": 0.35, "aesthetic": 0.6, "sharpness": 0.5, "stability": 0.8, "dominant_motion": "right"},
    ]
    features = cap_mod._aggregate_features(
        duration_sec=5.0,
        windows=windows,
        emotion_profile=None,
        semantic_embedding=None,
        faces=[],
    )
    assert features["mean_motion"] == pytest.approx(0.27, abs=0.02)
    assert features["motion_trend"] == "increasing"
    assert features["dominant_motion"] == "right"
    assert not features["heatmap_missing"]


def test_face_count_mode():
    faces = [
        {"t_s": 0.0, "bbox_norm": [0, 0, 0.1, 0.1]},
        {"t_s": 0.0, "bbox_norm": [0.2, 0.2, 0.3, 0.3]},
        {"t_s": 1.0, "bbox_norm": [0, 0, 0.1, 0.1]},
    ]
    assert cap_mod._face_count_mode(faces) == 2


def test_face_area_ratio():
    face = {"bbox_norm": [0.1, 0.1, 0.5, 0.6]}
    assert cap_mod._face_area_ratio(face) == pytest.approx(0.2, abs=0.001)


def test_shot_type_classification():
    assert cap_mod._shot_type(0.35, 3.0, 0.1) == "close_up"
    assert cap_mod._shot_type(0.12, 3.0, 0.1) == "medium"
    assert cap_mod._shot_type(0.01, 4.0, 0.1) == "wide"
    assert cap_mod._shot_type(0.05, 1.0, 0.5) == "medium"


def test_intent_scores_cover_all_labels():
    features = {
        "duration_sec": 2.0,
        "mean_motion": 0.3,
        "motion_trend": "static",
        "dominant_motion": "still",
        "stability": 0.7,
        "aesthetic": 0.5,
        "sharpness": 0.5,
        "face_area_ratio": 0.05,
        "face_count_mode": 1,
        "dino_sim": 0.6,
        "audio_arousal": 0.4,
        "shot_type": "medium",
    }
    scores = cap_mod._score_intents(features)
    assert set(scores.keys()) == set(cap_mod.EDIT_INTENT_LABELS)
    for value in scores.values():
        assert 0.0 <= value <= 1.0


def test_breathe_scores_high_for_calm_wide_clip():
    features = {
        "duration_sec": 5.0,
        "mean_motion": 0.05,
        "motion_trend": "static",
        "dominant_motion": "still",
        "stability": 0.9,
        "aesthetic": 0.5,
        "sharpness": 0.5,
        "face_area_ratio": 0.0,
        "face_count_mode": 0,
        "dino_sim": 0.9,
        "audio_arousal": 0.2,
        "shot_type": "wide",
    }
    scores = cap_mod._score_intents(features)
    assert scores["BREATHE"] > scores["JAB"]
    assert scores["BREATHE"] > scores["SHOCK"]


def test_jab_scores_high_for_short_spike():
    features = {
        "duration_sec": 0.5,
        "mean_motion": 0.9,
        "motion_trend": "increasing",
        "dominant_motion": "right",
        "stability": 0.2,
        "aesthetic": 0.5,
        "sharpness": 0.8,
        "face_area_ratio": 0.05,
        "face_count_mode": 0,
        "dino_sim": 0.3,
        "audio_arousal": 0.8,
        "shot_type": "medium",
    }
    scores = cap_mod._score_intents(features)
    assert scores["JAB"] > scores["LINGER"]
    assert scores["SHOCK"] > scores["BREATHE"]


def test_withhold_scores_high_for_close_static_face():
    features = {
        "duration_sec": 3.0,
        "mean_motion": 0.1,
        "motion_trend": "static",
        "dominant_motion": "still",
        "stability": 0.8,
        "aesthetic": 0.5,
        "sharpness": 0.5,
        "face_area_ratio": 0.4,
        "face_count_mode": 1,
        "dino_sim": 0.5,
        "audio_arousal": 0.3,
        "shot_type": "close_up",
    }
    scores = cap_mod._score_intents(features)
    assert scores["WITHHOLD"] > scores["RELEASE"]
    assert scores["ISOLATE"] > scores["CONNECT"]


def test_compute_profile_uses_cache(tmp_path, monkeypatch):
    clip_path = str(tmp_path / "clip.mp4")
    cache_path = cap_mod.cache_path_for_clip(clip_path, cache_dir=tmp_path)

    cached = ClipCapabilityProfile(
        clip_id="clip",
        duration_sec=2.5,
        intent_scores={label: 0.1 for label in cap_mod.EDIT_INTENT_LABELS},
        confidence=0.9,
    )
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cached.model_dump(by_alias=False, mode="json"), f)

    monkeypatch.setattr(cap_mod, "_probe_duration", lambda *a, **kw: 0.0)
    result = cap_mod.compute_clip_capability_profile(clip_path, cache_path=cache_path)
    assert result.duration_sec == pytest.approx(2.5)
    assert result.confidence == pytest.approx(0.9)


def test_compute_profile_without_cv2_returns_fallback(tmp_path, monkeypatch):
    clip_path = str(tmp_path / "clip.mp4")
    monkeypatch.setattr(cap_mod, "_CV2", False)
    monkeypatch.setattr(cap_mod, "_load_heatmap_windows", lambda *a, **kw: [])
    monkeypatch.setattr(cap_mod, "_load_emotion_profile", lambda *a, **kw: None)
    monkeypatch.setattr(cap_mod, "_load_semantic_embedding", lambda *a, **kw: None)
    monkeypatch.setattr(cap_mod, "_load_face_detections", lambda *a, **kw: [])

    result = cap_mod.compute_clip_capability_profile(clip_path, clip_id="clip")
    assert result.clip_id == "clip"
    assert result.duration_sec == 0.0
    assert result.confidence < 1.0
    assert set(result.intent_scores.keys()) == set(cap_mod.EDIT_INTENT_LABELS)
