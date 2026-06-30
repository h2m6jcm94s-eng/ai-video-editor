# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ingest_worker import clip_emotion as emotion_mod
from ingest_worker.clip_emotion import (
    cache_path_for_clip,
    compute_clip_emotion_profile,
    compute_clip_emotion_profiles,
)
from shared_py.models import ClipEmotionProfile


def test_cache_path_for_clip():
    assert cache_path_for_clip("/tmp/clip.mp4") == "/tmp/clip.mp4.emotion.json"


def test_distribution_to_primary():
    distribution = {"anger": 0.1, "joy": 0.6, "calm": 0.3}
    assert emotion_mod._distribution_to_primary(distribution) == "joy"


def test_distribution_to_primary_empty():
    assert emotion_mod._distribution_to_primary({}) == "calm"


def test_vad_from_distribution():
    distribution = {"joy": 1.0}
    valence, arousal, dominance = emotion_mod._vad_from_distribution(distribution)
    assert valence > 0.5
    assert arousal > 0.5


def test_vad_from_distribution_empty():
    valence, arousal, dominance = emotion_mod._vad_from_distribution({})
    assert valence == 0.0
    assert arousal == 0.3
    assert dominance == 0.3


def test_neutral_profile():
    profile = emotion_mod._neutral_profile("test_reason")
    assert profile.primary_emotion == "calm"
    assert profile.confidence == 0.0


def test_compute_profile_uses_cache(tmp_path, monkeypatch):
    clip_path = str(tmp_path / "clip.mp4")
    cache_path = cache_path_for_clip(clip_path)

    cached = ClipEmotionProfile(
        primary_emotion="anger",
        valence=-0.5,
        arousal=0.8,
        dominance=0.6,
        confidence=0.9,
    )
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cached.model_dump(by_alias=False, mode="json"), f)

    monkeypatch.setattr(emotion_mod, "_sample_frames_uniform", lambda *a, **kw: [])
    result = compute_clip_emotion_profile(clip_path)
    assert result.primary_emotion == "anger"
    assert result.confidence == pytest.approx(0.9)


def test_compute_profile_without_cv2_returns_neutral(tmp_path, monkeypatch):
    clip_path = str(tmp_path / "clip.mp4")
    monkeypatch.setattr(emotion_mod, "_CV2", False)
    result = compute_clip_emotion_profile(clip_path)
    assert result.primary_emotion == "calm"
    assert result.confidence == 0.0


def test_compute_profiles_for_multiple_clips(tmp_path, monkeypatch):
    clip_paths = {
        "c1": str(tmp_path / "clip1.mp4"),
        "c2": str(tmp_path / "clip2.mp4"),
    }

    def fake_profile(path, sample_fps=0.5):
        return ClipEmotionProfile(
            primary_emotion="joy",
            valence=0.7,
            arousal=0.6,
            dominance=0.5,
            confidence=0.8,
        )

    monkeypatch.setattr(emotion_mod, "compute_clip_emotion_profile", fake_profile)
    results = compute_clip_emotion_profiles(clip_paths)
    assert set(results.keys()) == {"c1", "c2"}
    assert results["c1"].primary_emotion == "joy"
    assert results["c2"].primary_emotion == "joy"


def test_profile_to_vector_length():
    profile = ClipEmotionProfile(
        face_emotion_distribution={k: 0.0 for k in emotion_mod.EMOTION_ORDER},
        valence=0.0,
        arousal=0.3,
        dominance=0.3,
    )
    vector = profile.to_vector()
    assert len(vector) == 12  # 9 emotions + VAD
