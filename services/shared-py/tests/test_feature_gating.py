# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from shared_py.feature_gating import (
    CONTENT_CLUSTER_CENTROIDS,
    FEATURE_RELEVANCE_CENTROIDS,
    classify_content_cluster,
    cosine_similarity,
    gated_budget,
    reason_to_skip,
    should_run_feature,
)


class TestCosineSimilarity:
    def test_identical_vectors_are_one(self):
        assert cosine_similarity({"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 2.0}) == pytest.approx(1.0)

    def test_orthogonal_vectors_are_zero(self):
        assert cosine_similarity({"a": 1.0}, {"b": 1.0}) == 0.0

    def test_empty_vectors_are_zero(self):
        assert cosine_similarity({}, {}) == 0.0

    def test_booleans_and_none_are_coerced(self):
        assert cosine_similarity({"song_present": True, "speech_ratio": 0.0}, {"song_present": 1.0}) == pytest.approx(1.0)
        assert cosine_similarity({"song_present": None}, {"song_present": 1.0}) == 0.0

    def test_missing_keys_treated_as_zero(self):
        a = {"motion_density": 0.8, "speech_ratio": 0.05}
        b = {"motion_density": 0.8, "speech_ratio": 0.05, "song_present": 1.0}
        # Missing song_present in a is 0, so dot is lower but still positive.
        assert 0.0 < cosine_similarity(a, b) < 1.0


class TestShouldRunFeature:
    def test_iconic_quotes_runs_for_mv_content(self):
        signals = {
            "motion_density": 0.8,
            "speech_ratio": 0.02,
            "song_present": True,
            "song_has_vocals": True,
        }
        should_run, score = should_run_feature("iconic_quotes", signals)
        assert should_run is True
        assert score > 0.8

    def test_iconic_quotes_skips_podcast_content(self):
        signals = {
            "motion_density": 0.1,
            "speech_ratio": 0.9,
            "song_present": False,
            "song_has_vocals": False,
        }
        should_run, score = should_run_feature("iconic_quotes", signals)
        assert should_run is False
        assert score < 0.3

    def test_audio_ducking_runs_with_song_and_speech(self):
        signals = {"song_present": True, "speech_ratio": 0.5}
        should_run, score = should_run_feature("audio_ducking", signals)
        assert should_run is True
        assert score > 0.8

    def test_audio_ducking_runs_for_music_only_content(self):
        # Sidechain parameters on a music-only bed do no harm: ducking only
        # triggers when dialogue tracks exist. The gate therefore stays open for
        # any song-present signal.
        signals = {"song_present": True, "speech_ratio": 0.0}
        should_run, score = should_run_feature("audio_ducking", signals)
        assert should_run is True
        assert score > 0.7

    def test_audio_ducking_skips_when_no_song(self):
        signals = {"song_present": False, "speech_ratio": 0.5}
        should_run, score = should_run_feature("audio_ducking", signals)
        assert should_run is False
        assert score < 0.3

    def test_aesthetic_scoring_runs_for_natural_footage(self):
        signals = {"screen_capture": False}
        should_run, score = should_run_feature("aesthetic_scoring", signals)
        assert should_run is True
        assert score == pytest.approx(1.0)

    def test_aesthetic_scoring_skips_screen_recordings(self):
        signals = {"screen_capture": True}
        should_run, score = should_run_feature("aesthetic_scoring", signals)
        assert should_run is False
        assert score == pytest.approx(0.0)

    def test_save_the_cat_always_runs(self):
        should_run, score = should_run_feature("save_the_cat", {})
        assert should_run is True
        assert score == 1.0

    def test_unknown_feature_with_empty_centroid_runs(self):
        should_run, score = should_run_feature("not_a_feature", {})
        assert should_run is True
        assert score == 1.0


class TestGatedBudget:
    def test_below_threshold_is_zero(self):
        assert gated_budget(0.2, min_budget=5, max_budget=20) == 0
        assert gated_budget(0.3, min_budget=5, max_budget=20) == 0

    def test_at_threshold_is_zero(self):
        assert gated_budget(0.3, min_budget=5, max_budget=20) == 0

    def test_at_one_is_max(self):
        assert gated_budget(1.0, min_budget=5, max_budget=20) == 20

    def test_midpoint_scales_linearly(self):
        # relevance 0.65 is halfway between 0.3 and 1.0 -> budget halfway between 5 and 20.
        assert gated_budget(0.65, min_budget=5, max_budget=20) == pytest.approx(12, abs=1)

    def test_clamps_negative_max(self):
        assert gated_budget(0.9, min_budget=10, max_budget=5) == 5


class TestReasonToSkip:
    def test_includes_relevance(self):
        msg = reason_to_skip("iconic_quotes", {"speech_ratio": 0.9, "song_present": False})
        assert "iconic_quotes gated off" in msg
        assert "relevance=" in msg


class TestClassifyContentCluster:
    def test_music_video_cluster_high_motion_song(self):
        label, score, scores = classify_content_cluster(
            {"song_present": True, "song_has_vocals": True, "motion_density": 0.8, "speech_ratio": 0.0}
        )
        assert label == "music_video"
        assert score > 0.8
        assert scores["music_video"] > scores["dialogue"]

    def test_tutorial_cluster_screen_capture(self):
        label, score, _ = classify_content_cluster(
            {"screen_capture": True, "speech_ratio": 0.8, "song_present": False, "face_screentime_ratio": 0.0}
        )
        assert label == "tutorial"
        assert score > 0.7

    def test_general_when_best_score_below_threshold(self):
        # Empty signals still match low-target centroids, so raise the threshold
        # to force a "general" bucket and verify the fallback path.
        label, score, scores = classify_content_cluster({}, threshold=1.0)
        assert label == "general"
        assert score < 1.0
        assert all(s < 1.0 for s in scores.values())

    def test_returns_all_cluster_scores(self):
        _, _, scores = classify_content_cluster({"speech_ratio": 0.9})
        assert set(scores.keys()) == set(CONTENT_CLUSTER_CENTROIDS)
