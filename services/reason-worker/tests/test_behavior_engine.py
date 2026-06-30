# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reason_worker.behavior_engine import (
    BehaviorEngine,
    _compute_moments,
    _normalize_signals,
    _weighted_euclidean,
)
from shared_py.models import AdaptiveFeatures


def _signals(**kwargs):
    defaults = {
        "speech_ratio": 0.0,
        "avg_speech_segment_duration_s": 0.0,
        "multi_speaker_ratio": 0.0,
        "song_present": True,
        "song_energy_mean": 0.5,
        "song_tempo_bpm": 120.0,
        "song_section_count": 2,
        "clip_count": 3,
        "clip_avg_duration_s": 5.0,
        "motion_density": 0.5,
        "motion_variance": 0.0,
        "aesthetic_score_mean": 0.5,
        "face_screentime_ratio": 0.0,
        "multi_face_ratio": 0.0,
        "shot_diversity": 0.0,
        "reference_present": True,
    }
    defaults.update(kwargs)
    return defaults


def _mock_async_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = AsyncMock()
    resp.json = AsyncMock(return_value=payload)
    return resp


@pytest.mark.asyncio
async def test_predict_returns_default_when_flags_off():
    engine = BehaviorEngine(api_base="http://test/api", internal_token="token")
    features = AdaptiveFeatures(use_corpus_knn=False, use_per_user_bias=False)
    behavior, confidence, reasoning = await engine.predict(_signals(), "user-1", features)
    assert behavior.cut_density_per_sec == pytest.approx(0.16)
    assert confidence == 0.0
    assert "heuristic" in reasoning.lower()


@pytest.mark.asyncio
async def test_knn_uses_weighted_average():
    engine = BehaviorEngine(api_base="http://test/api", internal_token="token")

    corpus_resp = _mock_async_response(
        {
            "entries": [
                {
                    "signals": _signals(clip_count=10),
                    "behavior": {"cut_density_per_sec": 0.5, "hard_cut_ratio": 0.9},
                    "qualityWeight": 1.0,
                },
                {
                    "signals": _signals(clip_count=2),
                    "behavior": {"cut_density_per_sec": 0.2, "hard_cut_ratio": 0.5},
                    "qualityWeight": 0.5,
                },
            ]
        }
    )

    async_client_mock = MagicMock()
    async_client_mock.get = AsyncMock(return_value=corpus_resp)
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_client_mock):
        features = AdaptiveFeatures(use_corpus_knn=True, use_per_user_bias=False)
        behavior, confidence, reasoning = await engine.predict(_signals(clip_count=6), "user-1", features)

    # Weighted average should be closer to the first (higher quality) entry.
    assert behavior.cut_density_per_sec > 0.16
    assert behavior.hard_cut_ratio > 0.7
    assert 0.0 <= confidence <= 1.0
    assert "knn" in reasoning.lower()


@pytest.mark.asyncio
async def test_per_user_bias_uses_cluster_specific_vector():
    engine = BehaviorEngine(api_base="http://test/api", internal_token="token")

    profile_resp = _mock_async_response(
        {"profile": {"clusterBiasVectors": {"music_video": {"cutDensityPerSec": 0.1}}}}
    )

    async_client_mock = MagicMock()
    async_client_mock.get = AsyncMock(return_value=profile_resp)
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_client_mock):
        features = AdaptiveFeatures(use_corpus_knn=False, use_per_user_bias=True)
        # Signals strongly match the music_video cluster.
        behavior, confidence, reasoning = await engine.predict(
            _signals(
                song_present=True,
                song_has_vocals=True,
                motion_density=0.8,
                speech_ratio=0.0,
                song_energy_mean=0.2,
                shot_diversity=0.0,
            ),
            "user-1",
            features,
        )

    assert behavior.cut_density_per_sec == pytest.approx(0.26)
    assert "bias" in reasoning.lower()
    assert "music_video" in reasoning


@pytest.mark.asyncio
async def test_per_user_bias_falls_back_to_general_cluster():
    engine = BehaviorEngine(api_base="http://test/api", internal_token="token")

    profile_resp = _mock_async_response(
        {"profile": {"clusterBiasVectors": {"general": {"cutDensityPerSec": 0.1}}}}
    )

    async_client_mock = MagicMock()
    async_client_mock.get = AsyncMock(return_value=profile_resp)
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_client_mock):
        features = AdaptiveFeatures(use_corpus_knn=False, use_per_user_bias=True)
        behavior, confidence, reasoning = await engine.predict(_signals(), "user-1", features)

    assert behavior.cut_density_per_sec == pytest.approx(0.26)


class TestSignalMath:
    def test_z_score_normalization_uses_corpus_moments(self):
        signals = {"clip_count": 6}
        means, stds = _compute_moments([{"clip_count": 10}, {"clip_count": 2}])
        normalized = _normalize_signals(signals, means=means, stds=stds)
        # clip_count is the 8th feature (index 7).
        assert normalized[7] == pytest.approx(0.0)

    def test_min_max_fallback_when_no_moments(self):
        normalized = _normalize_signals({"clip_count": 10})
        # clip_count range is 0-20, so 10 maps to 0.5.
        assert normalized[7] == pytest.approx(0.5)

    def test_weighted_euclidean_respects_weights(self):
        # Two unit vectors; only the first dimension differs.
        a = [1.0, 0.0]
        b = [0.0, 0.0]
        # With weight 4 on the differing dimension and weight 1 elsewhere,
        # normalized distance = sqrt(4/5) ~= 0.894.
        assert _weighted_euclidean(a, b, [4.0, 1.0]) == pytest.approx(0.8944, abs=0.001)
        # With equal weights, distance = sqrt(1/2) ~= 0.707.
        assert _weighted_euclidean(a, b, [1.0, 1.0]) == pytest.approx(0.7071, abs=0.001)
