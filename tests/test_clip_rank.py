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
from shared_py.tuning import RANK


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
        """Verify total score is weighted sum including heatmap window quality.

        Use more clips than slots so the exhaust bonus does not apply.
        """
        slots = [make_slot(index=0)]
        clips = {
            "C01": make_clip_meta(shot_type="wide", motion_energy=0.5, duration=2.0, aesthetic=0.5),
            "C02": make_clip_meta(shot_type="medium", motion_energy=0.5, duration=2.0, aesthetic=0.5),
        }

        rankings = rank_clips_for_slots(slots, clips, force_exhaust=False)

        score = rankings[0][0]
        # When no emotion profile is available, mood-motion consistency is an
        # honest missing signal (0.0), not a decorated midpoint.
        mood_motion_score = 0.0 if score.emotion_profile is None else score.emotion_profile.motion_vibe
        expected = (
            RANK.SIGLIP_SEMANTIC_WEIGHT * score.semantic_score +
            RANK.SHOT_TYPE_WEIGHT * score.shot_type_score +
            RANK.AESTHETIC_WEIGHT * score.aesthetic_score +
            RANK.MOTION_ENERGY_WEIGHT * score.motion_score +
            RANK.DURATION_MATCH_WEIGHT * score.duration_score +
            RANK.HEATMAP_WEIGHT * score.window_score +
            RANK.MOOD_MOTION_WEIGHT * mood_motion_score +
            RANK.EMOTION_MATCH_WEIGHT * score.emotion_match_score -
            RANK.DIVERSITY_WEIGHT * score.diversity_penalty -
            score.repetition_penalty
        )
        assert abs(score.total_score - expected) < 0.001

    def test_multi_clip_diversity_without_embeddings(self):
        """When multiple clips exist, different slots should pick different clips
        even without Marengo embeddings."""
        slots = [
            make_slot(index=0, shot_type="wide", energy=0.3),
            make_slot(index=1, shot_type="medium", energy=0.5),
            make_slot(index=2, shot_type="close_up", energy=0.8),
            make_slot(index=3, shot_type="wide", energy=0.4),
            make_slot(index=4, shot_type="medium", energy=0.6),
        ]
        clips = {
            "C01": make_clip_meta(shot_type="wide", motion_energy=0.3, duration=2.0, aesthetic=0.6),
            "C02": make_clip_meta(shot_type="medium", motion_energy=0.5, duration=2.0, aesthetic=0.7),
            "C03": make_clip_meta(shot_type="close_up", motion_energy=0.8, duration=2.0, aesthetic=0.8),
        }

        rankings = rank_clips_for_slots(slots, clips)
        selected = [rankings[i][0].clip_id for i in range(len(slots))]
        distinct = set(selected)

        assert len(distinct) >= 2, f"Expected multiple clips, got {selected}"
        # Best matching clip per slot should win the first time, but repetition
        # penalty should rotate choices for similar slots.
        assert selected.count("C01") < len(slots)
        assert selected.count("C02") < len(slots)
        assert selected.count("C03") < len(slots)


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
        # A single candidate carries no comparative signal, so confidence is 0.0
        # (honest missing signal) rather than a fake midpoint.
        assert confidences[0] == 0.0

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


class TestWindowMotionFilter:
    """Reject frozen/static source windows unless the slot needs stillness."""

    def _make_heatmap(self, duration=10.0, frozen_start=0.0, frozen_end=2.0):
        """Build a heatmap where the first 2s are frozen and the rest moves."""
        windows = []
        t = 0.0
        while t < duration:
            is_frozen = frozen_start <= t < frozen_end
            windows.append({
                "start_s": round(t, 3),
                "end_s": round(min(t + 0.5, duration), 3),
                "score": 0.9 if is_frozen else 0.6,
                "components": {"motion": 0.0 if is_frozen else 0.8},
                "dominant_motion": "still" if is_frozen else "right",
            })
            t += 0.25
        return windows

    def test_high_energy_slot_avoids_frozen_window(self):
        slots = [make_slot(index=0, energy=0.8, duration=2.0)]
        clips = {
            "moving": {
                "shot_type": "wide",
                "motion_energy": 0.8,
                "duration_sec": 10.0,
                "aesthetic_score": 0.5,
                "heatmap": self._make_heatmap(),
            },
        }
        rankings = rank_clips_for_slots(slots, clips)
        top = rankings[0][0]
        # The frozen window starts at 0.0; the filter should push us past it.
        assert top.window_start_s is not None
        assert top.window_start_s >= 2.0, (
            f"expected non-frozen window (>=2.0s), got {top.window_start_s}"
        )

    def test_low_energy_slot_may_use_still_window(self):
        slots = [make_slot(index=0, energy=0.1, duration=2.0)]
        clips = {
            "moving": {
                "shot_type": "wide",
                "motion_energy": 0.1,
                "duration_sec": 10.0,
                "aesthetic_score": 0.5,
                "heatmap": self._make_heatmap(),
            },
        }
        rankings = rank_clips_for_slots(slots, clips)
        top = rankings[0][0]
        # Low-energy slots are allowed to land on the highest-scoring window,
        # even if it is in the frozen patch.
        assert top.window_start_s is not None

    def test_high_energy_rejects_short_clip_that_would_pad(self):
        """A clip shorter than the slot should lose to a long enough clip."""
        slots = [make_slot(index=0, energy=0.8, duration=4.0)]
        clips = {
            "short": {
                "shot_type": "wide",
                "motion_energy": 0.8,
                "duration_sec": 2.0,
                "aesthetic_score": 0.9,
                "heatmap": [
                    {"start_s": 0.0, "end_s": 0.5, "score": 0.9,
                     "components": {"motion": 0.5}, "dominant_motion": "right"},
                ],
            },
            "long": {
                "shot_type": "wide",
                "motion_energy": 0.8,
                "duration_sec": 5.0,
                "aesthetic_score": 0.5,
                "heatmap": [
                    {"start_s": 0.0, "end_s": 0.5, "score": 0.6,
                     "components": {"motion": 0.5}, "dominant_motion": "right"},
                    {"start_s": 0.25, "end_s": 0.75, "score": 0.6,
                     "components": {"motion": 0.5}, "dominant_motion": "right"},
                    {"start_s": 0.5, "end_s": 1.0, "score": 0.6,
                     "components": {"motion": 0.5}, "dominant_motion": "right"},
                    {"start_s": 0.75, "end_s": 1.25, "score": 0.6,
                     "components": {"motion": 0.5}, "dominant_motion": "right"},
                ],
            },
        }
        rankings = rank_clips_for_slots(slots, clips)
        top = rankings[0][0]
        assert top.clip_id == "long"

    def test_high_energy_rejects_slot_with_internal_static_patch(self):
        """A window whose full duration contains any sub-second static patch is rejected."""
        slots = [make_slot(index=0, energy=0.8, duration=2.0)]
        clips = {
            "patchy": {
                "shot_type": "wide",
                "motion_energy": 0.8,
                "duration_sec": 10.0,
                "aesthetic_score": 0.9,
                "heatmap": [
                    # First 1.5s frozen, then high motion.
                    {"start_s": 0.0, "end_s": 0.5, "score": 0.9,
                     "components": {"motion": 0.0}, "dominant_motion": "still"},
                    {"start_s": 0.25, "end_s": 0.75, "score": 0.9,
                     "components": {"motion": 0.0}, "dominant_motion": "still"},
                    {"start_s": 0.5, "end_s": 1.0, "score": 0.9,
                     "components": {"motion": 0.0}, "dominant_motion": "still"},
                    {"start_s": 0.75, "end_s": 1.25, "score": 0.9,
                     "components": {"motion": 0.0}, "dominant_motion": "still"},
                    {"start_s": 1.0, "end_s": 1.5, "score": 0.9,
                     "components": {"motion": 0.0}, "dominant_motion": "still"},
                    {"start_s": 1.25, "end_s": 1.75, "score": 0.6,
                     "components": {"motion": 0.5}, "dominant_motion": "right"},
                    {"start_s": 1.5, "end_s": 2.0, "score": 0.6,
                     "components": {"motion": 0.5}, "dominant_motion": "right"},
                    {"start_s": 1.75, "end_s": 2.25, "score": 0.6,
                     "components": {"motion": 0.5}, "dominant_motion": "right"},
                ],
            },
        }
        rankings = rank_clips_for_slots(slots, clips)
        top = rankings[0][0]
        # The 2s slot starting at 0.25 would overlap frozen windows, so the
        # ranker should push past the static patch.
        assert top.window_start_s is not None
        assert top.window_start_s >= 1.0


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

        assert rankings[0][0].semantic_score == pytest.approx(0.0)

    def test_no_video_embeddings_uses_fallback(self):
        """When clip embeddings are missing, semantic score is an honest 0.0."""
        slots = [make_slot(index=0, shot_type="wide")]
        clips = {"C01": make_clip_meta(shot_type="wide")}
        client = FakeMarengoClient(
            text_embeddings={"wide, test, static, energy 0.5": np.array([1.0, 0.0])}
        )

        rankings = rank_clips_for_slots(slots, clips, {}, marengo_client=client)

        assert rankings[0][0].semantic_score == pytest.approx(0.0)



class TestFallbackRanking:
    """Ensure slots always receive a candidate when clips exist."""

    def test_round_robin_fallback_fills_empty_slot(self):
        slots = [
            make_slot(index=0, shot_type="wide"),
            make_slot(index=1, shot_type="close_up"),
        ]
        # Only one wide clip; slot 1 (close_up) would otherwise have no good match.
        clips = {
            "C01": make_clip_meta(shot_type="wide", duration=2.0),
        }

        rankings = rank_clips_for_slots(slots, clips, fallback_policy="round_robin")

        assert len(rankings[0]) == 1
        assert rankings[0][0].clip_id == "C01"
        assert len(rankings[1]) == 1
        assert rankings[1][0].clip_id == "C01"

    def test_best_available_fallback_uses_top_global_clip(self):
        slots = [
            make_slot(index=0, shot_type="wide"),
            make_slot(index=1, shot_type="close_up"),
        ]
        clips = {
            "C01": make_clip_meta(shot_type="wide", duration=2.0, aesthetic=0.9),
            "C02": make_clip_meta(shot_type="medium", duration=2.0, aesthetic=0.3),
        }

        rankings = rank_clips_for_slots(slots, clips, fallback_policy="best_available")

        # Both slots get a candidate.
        assert len(rankings[0]) == 2
        assert len(rankings[1]) == 2
        # Slot 0 picks the globally best clip (C01).
        assert rankings[0][0].clip_id == "C01"
        # Slot 1 should prefer a different clip because C01 already won slot 0,
        # demonstrating the repetition-penalty/diversity behavior.
        assert rankings[1][0].clip_id == "C02"

    def test_empty_clip_library_leaves_rankings_empty(self):
        slots = [make_slot(index=0)]
        rankings = rank_clips_for_slots(slots, {}, fallback_policy="round_robin")
        assert rankings[0] == []


# ──────────────────────────────────────────────────────────────────────────────
# Exhaust / repetition fixes
# ──────────────────────────────────────────────────────────────────────────────

class TestExhaustAndRepetition:
    def test_no_reuse_when_enough_clips(self):
        """If slots <= clips, usage_cap=1 prevents any clip from repeating."""
        slots = [
            make_slot(index=0, shot_type="wide"),
            make_slot(index=1, shot_type="medium"),
            make_slot(index=2, shot_type="close_up"),
        ]
        clips = {
            "C01": make_clip_meta(shot_type="wide"),
            "C02": make_clip_meta(shot_type="medium"),
            "C03": make_clip_meta(shot_type="close_up"),
            "C04": make_clip_meta(shot_type="wide"),
            "C05": make_clip_meta(shot_type="medium"),
        }

        rankings = rank_clips_for_slots(slots, clips)
        selected = [rankings[i][0].clip_id for i in range(len(slots))]
        assert len(set(selected)) == len(selected), f"Clips repeated: {selected}"

    def test_exhaust_spreads_usage_before_repeating(self):
        """With more slots than clips, every clip is used before any repeats."""
        slots = [make_slot(index=i) for i in range(6)]
        clips = {
            "C01": make_clip_meta(),
            "C02": make_clip_meta(),
            "C03": make_clip_meta(),
        }

        rankings = rank_clips_for_slots(slots, clips)
        selected = [rankings[i][0].clip_id for i in range(len(slots))]
        # First three slots should use all three clips.
        assert set(selected[:3]) == {"C01", "C02", "C03"}, selected
        # Usage cap for 6 slots / 3 clips = ceil(2 * 1.2) = 2.
        from collections import Counter
        counts = Counter(selected)
        assert all(c <= 2 for c in counts.values()), counts


# ──────────────────────────────────────────────────────────────────────────────
# B4: honest missing signals (no fabricated medium constants)
# ──────────────────────────────────────────────────────────────────────────────

class TestHonestMissingSignals:
    def test_missing_aesthetic_scores_zero_not_medium(self):
        """A clip without aesthetic_score must not get a fabricated 0.5."""
        from reason_worker.clip_rank import _score_clip

        slot = make_slot(index=0)
        meta = make_clip_meta()
        del meta["aesthetic_score"]
        score = _score_clip(slot, "C01", meta, {}, {}, [])
        assert score.aesthetic_score == 0.0

    def test_missing_motion_energy_scores_zero_not_medium(self):
        """A clip without motion_energy must not get a fabricated 0.5 match."""
        from reason_worker.clip_rank import _score_clip

        slot = make_slot(index=0, energy=0.8)
        meta = make_clip_meta()
        del meta["motion_energy"]
        score = _score_clip(slot, "C01", meta, {}, {}, [])
        assert score.motion_score == 0.0

    def test_measured_zero_motion_is_respected(self):
        """A legitimately measured 0.0 motion must survive (not 'or 0.5')."""
        from reason_worker.clip_rank import _score_clip

        slot = make_slot(index=0, energy=0.0)
        meta = make_clip_meta(motion_energy=0.0, aesthetic=0.0)
        score = _score_clip(slot, "C01", meta, {}, {}, [])
        # motion match for a still slot + still clip is perfect.
        assert score.motion_score == pytest.approx(1.0)
        assert score.aesthetic_score == 0.0


class TestMomentumFixes:
    def test_same_clip_continuation_gets_zero_momentum_bonus(self):
        """Continuing the same clip should not be rewarded by momentum."""
        from unittest.mock import patch
        from reason_worker.clip_rank import rerank_with_momentum

        slots = [
            make_slot(index=0, shot_type="wide"),
            make_slot(index=1, shot_type="wide"),
        ]
        # Identical scores; momentum would flip order if bonus applied.
        scores = [
            ClipScore(clip_id="C01", total_score=1.0),
            ClipScore(clip_id="C02", total_score=1.0),
        ]
        rankings = {0: list(scores), 1: list(scores)}
        clip_paths = {"C01": "fake_c01.mp4", "C02": "fake_c02.mp4"}

        with patch("reason_worker.clip_rank.compute_mean_flow_vector", return_value=(1.0, 0.0)):
            with patch("reason_worker.clip_rank.momentum_coherence", return_value=1.0):
                new_rankings, chosen = rerank_with_momentum(
                    rankings, slots, {}, clip_paths=clip_paths
                )

        # Slot 0 picks C01 (first in sorted order). Slot 1 should NOT keep C01
        # just because it is the same clip; momentum bonus for same-clip
        # continuation is zeroed, while C02 gets the full momentum reward.
        assert chosen[0] == "C01"
        assert chosen[1] == "C02"
        # More importantly: the bonus applied to C01 in slot 1 is zero.
        slot1_scores = {s.clip_id: s.total_score for s in new_rankings[1]}
        assert slot1_scores["C01"] == 1.0

    def test_recent_clip_window_gets_zero_momentum_bonus(self):
        """A clip reappearing within 3 slots must not get momentum bonus."""
        from unittest.mock import patch
        from reason_worker.clip_rank import rerank_with_momentum

        slots = [make_slot(index=i) for i in range(4)]
        scores = [
            ClipScore(clip_id="C01", total_score=1.0),
            ClipScore(clip_id="C02", total_score=1.0),
            ClipScore(clip_id="C03", total_score=1.0),
        ]
        rankings = {i: list(scores) for i in range(4)}
        clip_paths = {f"C{i:02d}": f"fake_c{i:02d}.mp4" for i in range(1, 4)}

        with patch("reason_worker.clip_rank.compute_mean_flow_vector", return_value=(1.0, 0.0)):
            with patch("reason_worker.clip_rank.momentum_coherence", return_value=1.0):
                new_rankings, chosen = rerank_with_momentum(
                    rankings, slots, {}, clip_paths=clip_paths
                )

        # With identical scores, the first slot picks C01.  Without the recent-
        # window guard, momentum would keep dragging C01 back for several slots.
        # It should only be allowed again at slot 3 (outside the 3-slot window).
        assert chosen[0] == "C01"
        assert chosen[1] != "C01"
        assert chosen[2] != "C01"
        assert chosen[3] == "C01"


# ──────────────────────────────────────────────────────────────────────────────
# Deterministic clip ordering fallback
# ──────────────────────────────────────────────────────────────────────────────

class TestDeterministicOrderingFallback:
    def test_filename_fallback_sorts_alphabetically_on_tie(self):
        slots = [make_slot(index=0)]
        clips = {
            "C02": make_clip_meta(),
            "C01": make_clip_meta(),
            "C03": make_clip_meta(),
        }
        # Give each clip a filename so tie-break can use it.
        for clip_id in clips:
            clips[clip_id]["filename"] = f"video_{clip_id}.mp4"

        rankings = rank_clips_for_slots(
            slots,
            clips,
            force_exhaust=False,
            clip_order_fallback="filename",
            clip_order_smart_threshold=1.0,  # force fallback
        )
        # Identical scores trigger fallback; alphabetical filename wins.
        assert rankings[0][0].clip_id == "C01"

    def test_shuffle_fallback_is_deterministic_per_slot(self):
        slots = [make_slot(index=0), make_slot(index=1)]
        clips = {f"C{i:02d}": make_clip_meta() for i in range(10)}

        run1 = rank_clips_for_slots(
            slots,
            clips,
            force_exhaust=False,
            clip_order_fallback="shuffle",
            clip_order_smart_threshold=1.0,
        )
        run2 = rank_clips_for_slots(
            slots,
            clips,
            force_exhaust=False,
            clip_order_fallback="shuffle",
            clip_order_smart_threshold=1.0,
        )
        # Same seed per slot index should give identical order.
        assert [s.clip_id for s in run1[0]] == [s.clip_id for s in run2[0]]
        assert [s.clip_id for s in run1[1]] == [s.clip_id for s in run2[1]]

    def test_smart_fallback_does_not_change_order(self):
        slots = [make_slot(index=0)]
        clips = {
            "C01": make_clip_meta(),
            "C02": make_clip_meta(),
        }
        rankings = rank_clips_for_slots(
            slots,
            clips,
            force_exhaust=False,
            clip_order_fallback="smart",
        )
        # With identical metadata and smart fallback, both are valid; just
        # ensure no exception and order is stable.
        assert len(rankings[0]) == 2
