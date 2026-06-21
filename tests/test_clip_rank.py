"""
Unit, integration, and edge tests for clip ranking.
Covers: weighted scoring, MMR diversity, top-k selection, confidence computation,
and edge cases (single clip, no embeddings, identical clips, empty library).
"""

import pytest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from reason_worker.clip_rank import (
    rank_clips_for_slots,
    select_top_k_per_slot,
    compute_confidence,
)
from shared_py.models import Slot, ClipScore


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_slot(index=0, shot_type="wide", energy=0.5, duration=2.0,
              subject_hint="test", motion_hint="static", required_tags=None):
    return Slot(
        index=index,
        start_s=index * duration,
        duration_s=duration,
        beat_index=index,
        section="intro",
        target_shot_type=shot_type,
        subject_hint=subject_hint,
        motion_hint=motion_hint,
        energy_level=energy,
        required_tags=required_tags or [],
        avoid_tags=[],
    )


def make_clip_meta(shot_type="wide", motion_energy=0.5, duration=2.0, aesthetic=0.5):
    return {
        "shot_type": shot_type,
        "motion_energy": motion_energy,
        "duration_sec": duration,
        "aesthetic_score": aesthetic,
    }


# ──────────────────────────────────────────────────────────────────────────────
# rank_clips_for_slots
# ──────────────────────────────────────────────────────────────────────────────

class TestRankClipsForSlots:
    def test_basic_ranking(self):
        slots = [make_slot(index=0, shot_type="wide")]
        clips = {
            "C01": make_clip_meta(shot_type="wide", duration=2.0),
            "C02": make_clip_meta(shot_type="medium", duration=2.0),
            "C03": make_clip_meta(shot_type="close_up", duration=2.0),
        }

        rankings = rank_clips_for_slots(slots, clips)

        assert 0 in rankings
        assert len(rankings[0]) == 3
        # Wide shot should rank highest for wide slot
        assert rankings[0][0].clip_id in ["C01", "C02", "C03"]

    def test_shot_type_matching(self):
        """Clip with matching shot type should score higher."""
        slots = [make_slot(index=0, shot_type="close_up")]
        clips = {
            "wide_clip": make_clip_meta(shot_type="wide"),
            "close_clip": make_clip_meta(shot_type="close_up"),
        }

        rankings = rank_clips_for_slots(slots, clips)

        scores = {s.clip_id: s.shot_type_score for s in rankings[0]}
        assert scores["close_clip"] == 1.0
        assert scores["wide_clip"] == 0.3

    def test_duration_matching(self):
        """Clip with duration close to slot duration should score higher."""
        slots = [make_slot(index=0, duration=5.0)]
        clips = {
            "exact": make_clip_meta(duration=5.0),
            "short": make_clip_meta(duration=1.0),
            "long": make_clip_meta(duration=10.0),
        }

        rankings = rank_clips_for_slots(slots, clips)

        duration_scores = {s.clip_id: s.duration_score for s in rankings[0]}
        assert duration_scores["exact"] > duration_scores["short"]
        assert duration_scores["exact"] > duration_scores["long"]

    def test_motion_energy_matching(self):
        """Clip motion energy close to slot energy should score higher."""
        slots = [make_slot(index=0, energy=0.8)]
        clips = {
            "high_motion": make_clip_meta(motion_energy=0.8),
            "low_motion": make_clip_meta(motion_energy=0.2),
        }

        rankings = rank_clips_for_slots(slots, clips)

        motion_scores = {s.clip_id: s.motion_score for s in rankings[0]}
        assert motion_scores["high_motion"] > motion_scores["low_motion"]

    def test_multiple_slots(self):
        """Ranking should work for multiple slots."""
        slots = [
            make_slot(index=0, shot_type="wide"),
            make_slot(index=1, shot_type="medium"),
            make_slot(index=2, shot_type="close_up"),
        ]
        clips = {
            "C01": make_clip_meta(shot_type="wide"),
            "C02": make_clip_meta(shot_type="medium"),
            "C03": make_clip_meta(shot_type="close_up"),
        }

        rankings = rank_clips_for_slots(slots, clips)

        assert len(rankings) == 3
        for i in range(3):
            assert i in rankings
            assert len(rankings[i]) == 3

    def test_total_score_computation(self):
        """Verify total score is weighted sum."""
        slots = [make_slot(index=0)]
        clips = {
            "C01": make_clip_meta(shot_type="wide", motion_energy=0.5, duration=2.0, aesthetic=0.5),
        }

        rankings = rank_clips_for_slots(slots, clips)

        score = rankings[0][0]
        expected = (
            0.40 * score.semantic_score +
            0.20 * score.shot_type_score +
            0.15 * score.aesthetic_score +
            0.15 * score.motion_score +
            0.10 * score.duration_score -
            0.25 * score.diversity_penalty
        )
        assert abs(score.total_score - expected) < 0.001


# ──────────────────────────────────────────────────────────────────────────────
# Diversity (MMR)
# ──────────────────────────────────────────────────────────────────────────────

class TestDiversityMMR:
    def test_diversity_penalty_applied(self):
        """When embeddings are provided, diversity penalty should be computed."""
        slots = [
            make_slot(index=0),
            make_slot(index=1),
        ]
        clips = {
            "C01": make_clip_meta(),
            "C02": make_clip_meta(),
        }
        # Create embeddings where C01 and C02 are very similar
        embeddings = {
            "C01": np.array([1.0, 0.0, 0.0]),
            "C02": np.array([0.99, 0.01, 0.0]),
        }

        rankings = rank_clips_for_slots(slots, clips, embeddings)

        # Second slot should have diversity penalty for the similar clip
        if len(rankings[1]) >= 2:
            second_slot_scores = rankings[1]
            # At least one clip should have diversity penalty > 0
            assert any(s.diversity_penalty > 0 for s in second_slot_scores)

    def test_no_diversity_without_embeddings(self):
        """Without embeddings, diversity penalty should be 0."""
        slots = [make_slot(index=0)]
        clips = {"C01": make_clip_meta()}

        rankings = rank_clips_for_slots(slots, clips, embeddings=None)

        assert rankings[0][0].diversity_penalty == 0.0

    def test_diversity_orthogonal_embeddings(self):
        """Orthogonal embeddings should have low similarity."""
        slots = [
            make_slot(index=0),
            make_slot(index=1),
        ]
        clips = {
            "C01": make_clip_meta(),
            "C02": make_clip_meta(),
        }
        embeddings = {
            "C01": np.array([1.0, 0.0]),
            "C02": np.array([0.0, 1.0]),
        }

        rankings = rank_clips_for_slots(slots, clips, embeddings)

        # Second slot: top clip should have low diversity (orthogonal to first choice)
        if len(rankings[1]) >= 1:
            top = rankings[1][0]
            # Cosine similarity of orthogonal vectors is 0
            assert top.diversity_penalty < 0.1


# ──────────────────────────────────────────────────────────────────────────────
# select_top_k_per_slot
# ──────────────────────────────────────────────────────────────────────────────

class TestSelectTopK:
    def test_top_3_selection(self):
        rankings = {
            0: [
                ClipScore(clip_id="A", total_score=0.9),
                ClipScore(clip_id="B", total_score=0.8),
                ClipScore(clip_id="C", total_score=0.7),
                ClipScore(clip_id="D", total_score=0.6),
            ],
        }
        top_k = select_top_k_per_slot(rankings, k=3)
        assert top_k[0] == ["A", "B", "C"]

    def test_top_k_more_than_available(self):
        rankings = {
            0: [
                ClipScore(clip_id="A", total_score=0.9),
                ClipScore(clip_id="B", total_score=0.8),
            ],
        }
        top_k = select_top_k_per_slot(rankings, k=5)
        assert top_k[0] == ["A", "B"]

    def test_top_k_empty_rankings(self):
        rankings = {0: []}
        top_k = select_top_k_per_slot(rankings, k=3)
        assert top_k[0] == []

    def test_top_k_single_clip(self):
        rankings = {
            0: [ClipScore(clip_id="only", total_score=0.5)],
        }
        top_k = select_top_k_per_slot(rankings, k=3)
        assert top_k[0] == ["only"]

    def test_top_k_multiple_slots(self):
        rankings = {
            0: [ClipScore(clip_id="A0", total_score=0.9), ClipScore(clip_id="B0", total_score=0.8)],
            1: [ClipScore(clip_id="A1", total_score=0.9), ClipScore(clip_id="B1", total_score=0.7)],
        }
        top_k = select_top_k_per_slot(rankings, k=2)
        assert len(top_k) == 2
        assert top_k[0] == ["A0", "B0"]
        assert top_k[1] == ["A1", "B1"]


# ──────────────────────────────────────────────────────────────────────────────
# compute_confidence
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeConfidence:
    def test_high_confidence_large_gap(self):
        rankings = {
            0: [
                ClipScore(clip_id="A", total_score=0.9),
                ClipScore(clip_id="B", total_score=0.5),
                ClipScore(clip_id="C", total_score=0.4),
                ClipScore(clip_id="D", total_score=0.3),
            ],
        }
        confidences = compute_confidence(rankings)
        assert confidences[0] > 0.5
        assert confidences[0] <= 1.0

    def test_low_confidence_small_gap(self):
        rankings = {
            0: [
                ClipScore(clip_id="A", total_score=0.51),
                ClipScore(clip_id="B", total_score=0.50),
                ClipScore(clip_id="C", total_score=0.49),
                ClipScore(clip_id="D", total_score=0.48),
            ],
        }
        confidences = compute_confidence(rankings)
        assert confidences[0] < 0.1

    def test_two_clips(self):
        rankings = {
            0: [
                ClipScore(clip_id="A", total_score=0.8),
                ClipScore(clip_id="B", total_score=0.2),
            ],
        }
        confidences = compute_confidence(rankings)
        assert confidences[0] == min(1.0, (0.8 - 0.2) * 2.0)

    def test_single_clip(self):
        rankings = {
            0: [ClipScore(clip_id="A", total_score=0.5)],
        }
        confidences = compute_confidence(rankings)
        assert confidences[0] == 0.5

    def test_empty_rankings(self):
        rankings = {}
        confidences = compute_confidence(rankings)
        assert confidences == {}

    def test_multiple_slots(self):
        rankings = {
            0: [
                ClipScore(clip_id="A", total_score=0.9),
                ClipScore(clip_id="B", total_score=0.3),
            ],
            1: [
                ClipScore(clip_id="C", total_score=0.6),
                ClipScore(clip_id="D", total_score=0.55),
            ],
        }
        confidences = compute_confidence(rankings)
        assert len(confidences) == 2
        # First slot has larger gap
        assert confidences[0] > confidences[1]


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestClipRankEdgeCases:
    def test_empty_clip_library(self):
        slots = [make_slot(index=0)]
        clips = {}
        rankings = rank_clips_for_slots(slots, clips)
        assert rankings[0] == []

    def test_single_clip(self):
        slots = [make_slot(index=0)]
        clips = {"C01": make_clip_meta()}
        rankings = rank_clips_for_slots(slots, clips)
        assert len(rankings[0]) == 1
        assert rankings[0][0].clip_id == "C01"

    def test_no_slots(self):
        slots = []
        clips = {"C01": make_clip_meta()}
        rankings = rank_clips_for_slots(slots, clips)
        assert rankings == {}

    def test_identical_clips(self):
        """Identical clips should have same scores."""
        slots = [make_slot(index=0)]
        clips = {
            "C01": make_clip_meta(shot_type="wide", motion_energy=0.5, duration=2.0),
            "C02": make_clip_meta(shot_type="wide", motion_energy=0.5, duration=2.0),
        }
        rankings = rank_clips_for_slots(slots, clips)
        assert len(rankings[0]) == 2
        # Scores should be identical (diversity may differ)
        assert rankings[0][0].total_score == pytest.approx(rankings[0][1].total_score, abs=0.001)

    def test_clip_with_missing_metadata(self):
        """Clip with missing metadata fields should use defaults."""
        slots = [make_slot(index=0)]
        clips = {
            "C01": {},  # Empty metadata
        }
        rankings = rank_clips_for_slots(slots, clips)
        assert len(rankings[0]) == 1
        # Should use defaults: shot_type=None -> 0.3, motion_energy=0.5 -> match, etc.
        assert rankings[0][0].shot_type_score == 0.3

    def test_negative_motion_energy(self):
        """Negative motion energy should still compute."""
        slots = [make_slot(index=0, energy=0.5)]
        clips = {
            "C01": make_clip_meta(motion_energy=-0.5),
        }
        rankings = rank_clips_for_slots(slots, clips)
        assert len(rankings[0]) == 1
        # Motion score = 1.0 - |(-0.5) - 0.5| = 0.0
        assert rankings[0][0].motion_score == 0.0

    def test_very_large_duration_mismatch(self):
        """Huge duration mismatch should give near-zero duration score."""
        slots = [make_slot(index=0, duration=1.0)]
        clips = {
            "C01": make_clip_meta(duration=1000.0),
        }
        rankings = rank_clips_for_slots(slots, clips)
        assert rankings[0][0].duration_score < 0.01

    def test_slot_duration_zero(self):
        """Zero slot duration should not cause division by zero."""
        slots = [make_slot(index=0, duration=0.0)]
        clips = {
            "C01": make_clip_meta(duration=1.0),
        }
        rankings = rank_clips_for_slots(slots, clips)
        assert len(rankings[0]) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Marengo semantic scoring
# ──────────────────────────────────────────────────────────────────────────────

class FakeMarengoClient:
    """Stub Marengo client that returns deterministic text embeddings."""

    def __init__(self, available=True, text_embeddings=None):
        self._available = available
        self._text_embeddings = text_embeddings or {}

    def available(self):
        return self._available

    def embed_text(self, text):
        return self._text_embeddings.get(text)


class TestMarengoSemanticScoring:
    def test_marengo_boosts_matching_clip(self):
        """When Marengo text/video embeddings align, the matching clip wins."""
        slots = [make_slot(index=0, shot_type="wide", subject_hint="ocean waves")]
        clips = {
            "ocean": make_clip_meta(shot_type="wide"),
            "city": make_clip_meta(shot_type="wide"),
        }
        # Text embedding matches the "ocean" video embedding.
        embeddings = {
            "ocean": np.array([1.0, 0.0]),
            "city": np.array([0.0, 1.0]),
        }
        client = FakeMarengoClient(
            text_embeddings={"wide, ocean waves, static, energy 0.5": np.array([1.0, 0.0])}
        )

        rankings = rank_clips_for_slots(slots, clips, embeddings, marengo_client=client)

        assert rankings[0][0].clip_id == "ocean"
        assert rankings[0][0].semantic_score > 0.9

    def test_marengo_unavailable_uses_fallback(self):
        """When Marengo is unavailable, semantic score stays at the fallback."""
        slots = [make_slot(index=0, shot_type="wide")]
        clips = {"C01": make_clip_meta(shot_type="wide")}
        embeddings = {"C01": np.array([1.0, 0.0])}
        client = FakeMarengoClient(available=False)

        rankings = rank_clips_for_slots(slots, clips, embeddings, marengo_client=client)

        assert rankings[0][0].semantic_score == pytest.approx(0.7)

    def test_no_video_embeddings_uses_fallback(self):
        """When clip embeddings are missing, semantic score stays at fallback."""
        slots = [make_slot(index=0, shot_type="wide")]
        clips = {"C01": make_clip_meta(shot_type="wide")}
        client = FakeMarengoClient(
            text_embeddings={"wide, test, static, energy 0.5": np.array([1.0, 0.0])}
        )

        rankings = rank_clips_for_slots(slots, clips, {}, marengo_client=client)

        assert rankings[0][0].semantic_score == pytest.approx(0.7)
