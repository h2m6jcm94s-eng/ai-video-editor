"""Tests for Wav2Vec2 vocal emotion analysis."""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared-py" / "src"))

import ingest_worker.vocal_emotion as vocal_module
from ingest_worker.vocal_emotion import analyze_vocal_stem
from shared_py.models import VocalEmotionCurve


def _fake_classifier(dominant: str = "sad"):
    """Return a classifier that always predicts the same distribution."""

    def classify(audio):
        scores = {label: 0.05 for label in vocal_module.EMOTION_CLASSES}
        scores[dominant] = 0.85
        return [{"label": label, "score": score} for label, score in scores.items()]

    return classify


class TestAnalyzeVocalStem:
    def test_silent_vocals_return_empty_curve(self, tmp_path):
        vocals_path = str(tmp_path / "vocals.wav")
        sf.write(vocals_path, np.zeros(16000 * 4, dtype=np.float32), 16000)

        with patch.object(vocal_module, "_load_classifier", lambda: _fake_classifier("neutral")):
            curve = analyze_vocal_stem(vocals_path, song_hash="abc", cache_dir=tmp_path / "cache")

        assert isinstance(curve, VocalEmotionCurve)
        assert curve.samples == []
        assert curve.silent_ratio == 1.0

    def test_voiced_vocals_return_samples(self, tmp_path):
        vocals_path = str(tmp_path / "vocals.wav")
        # Sine wave loud enough to pass RMS floor.
        t = np.linspace(0, 4.0, 16000 * 4)
        y = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        sf.write(vocals_path, y, 16000)

        with patch.object(vocal_module, "_load_classifier", lambda: _fake_classifier("happy")):
            curve = analyze_vocal_stem(vocals_path, song_hash="abc", cache_dir=tmp_path / "cache")

        assert len(curve.samples) > 0
        assert all(s.dominant_emotion == "happy" for s in curve.samples)
        assert 0.0 <= curve.silent_ratio < 1.0

    def test_missing_vocals_raise(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            analyze_vocal_stem(str(tmp_path / "missing.wav"))

    def test_cache_round_trip(self, tmp_path):
        vocals_path = str(tmp_path / "vocals.wav")
        t = np.linspace(0, 4.0, 16000 * 4)
        y = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        sf.write(vocals_path, y, 16000)

        cache_dir = tmp_path / "cache"
        with patch.object(vocal_module, "_load_classifier", lambda: _fake_classifier("angry")):
            first = analyze_vocal_stem(vocals_path, song_hash="abc", cache_dir=cache_dir)

        # Without mocking classifier, second call should load cache.
        second = analyze_vocal_stem(vocals_path, song_hash="abc", cache_dir=cache_dir)
        assert second.samples == first.samples
