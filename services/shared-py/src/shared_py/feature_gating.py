# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Universal embedding-gating helper for expensive or content-sensitive features.

Every feature that is expensive, could produce artifacts, or only applies to a
specific content cluster must be routed through ``should_run_feature``. The gate
is continuous (cosine similarity to a relevance centroid), never a hardcoded
archetype enum. Budgets for LLM/cloud calls scale linearly with relevance so we
spend less on edge cases and more on high-likelihood content.

Phase 1 centroids are hand-anchored signal vectors. Phase 4 replaces them with
data-driven cluster centroids learned from accepted projects in the corpus.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Tuple

# Phase 1 hand-anchored content-cluster centroids.
# These are not hard categories; each cluster is a point in the continuous signal
# space and ``classify_content_cluster`` returns the closest one (or ``general``
# when no cluster is close enough). Phase 4 will learn data-driven centroids from
# accepted projects in the corpus.
CONTENT_CLUSTER_CENTROIDS: dict[str, dict[str, float]] = {
    "dialogue": {
        "speech_ratio": 0.8,
        "avg_speech_segment_duration_s": 3.0,
        "song_present": 0.0,
        "face_screentime_ratio": 0.7,
        "motion_density": 0.2,
    },
    "music_video": {
        "speech_ratio": 0.05,
        "song_present": 1.0,
        "song_has_vocals": 1.0,
        "motion_density": 0.7,
        "face_screentime_ratio": 0.3,
    },
    "vlog": {
        "speech_ratio": 0.4,
        "song_present": 0.0,
        "face_screentime_ratio": 0.6,
        "motion_density": 0.4,
        "multi_face_ratio": 0.2,
    },
    "tutorial": {
        "screen_capture": 1.0,
        "speech_ratio": 0.7,
        "song_present": 0.0,
        "face_screentime_ratio": 0.1,
        "motion_density": 0.1,
    },
    "trailer": {
        "speech_ratio": 0.2,
        "song_present": 1.0,
        "song_energy_mean": 0.8,
        "motion_density": 0.8,
        "motion_variance": 0.5,
        "shot_diversity": 0.6,
    },
}

DEFAULT_CLUSTER_THRESHOLD = 0.25

# Phase 1 hand-anchored relevance centroids.
# Keys are the signal dimensions currently emitted by the pipeline. Missing keys
# in either the centroid or the runtime signals are treated as 0.0 so the gate
# degrades gracefully as new signals are added.
FEATURE_RELEVANCE_CENTROIDS: dict[str, dict[str, float]] = {
    # Iconic dialogue lines only make sense in MV/AMV-like content where speech
    # is sparse, music carries the track, and motion is high.
    "iconic_quotes": {
        "speech_ratio": 0.05,
        "motion_density": 0.7,
        "song_present": 1.0,
        "song_has_vocals": 1.0,
    },
    # Sidechain ducking is relevant when a song bed coexists with speech.
    "audio_ducking": {
        "song_present": 1.0,
        "speech_ratio": 0.3,
    },
    # Identity matting only helps when a single protagonist dominates the frame.
    "identity_matting": {
        "face_screentime_ratio": 0.6,
        "multi_face_ratio": 0.3,
    },
    # Anticipation cutting needs enough motion to shift cuts around peaks.
    "anticipation": {
        "motion_density": 0.5,
        "motion_variance": 0.3,
    },
    # Persistence-of-vision inserts belong in high-energy, music-driven content.
    "pov_inserts": {
        "motion_density": 0.6,
        "song_energy_mean": 0.6,
        "song_present": 1.0,
    },
    # Auto-LUT transfer only makes sense when a reference exists and its color
    # treatment is distinct enough to be worth copying.
    "auto_lut": {
        "reference_present": 1.0,
        "reference_color_variance": 0.3,
    },
    # Pegasus per-shot labels are only useful when a reference is being analyzed.
    "pegasus_labels": {
        "reference_present": 1.0,
    },
    # Demucs stem separation is only relevant for songs with vocals.
    "demucs_stems": {
        "song_present": 1.0,
        "song_has_vocals": 1.0,
    },
    # Aesthetic scoring is trained on natural images and can mis-rank screen
    # recordings; gate it against screen-capture-like content.
    "aesthetic_scoring": {
        "screen_capture": 0.0,
    },
    # Z-index / behind-subject text requires a song with lyrics/vocals and a
    # subject matte to place text behind.
    "zindex_text": {
        "song_present": 1.0,
        "song_has_vocals": 1.0,
        "face_screentime_ratio": 0.4,
    },
    # Save-the-Cat assembler always runs in narrative mode; the *mode* (speech
    # coherent vs trailer style) is decided separately. Empty centroid means
    # ``should_run_feature`` returns True by default.
    "save_the_cat": {},
}

DEFAULT_RELEVANCE_THRESHOLD = 0.3


def _numeric_value(value: Any) -> float:
    """Normalize a runtime signal value to a float for vector math."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def cosine_similarity(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """Cosine similarity between two sparse signal dictionaries.

    Missing keys are treated as 0.0. Values are coerced with ``_numeric_value``
    so booleans and ``None`` survive without raising.
    """
    keys = set(a) | set(b)
    if not keys:
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for key in keys:
        av = _numeric_value(a.get(key, 0.0))
        bv = _numeric_value(b.get(key, 0.0))
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (math.sqrt(norm_a) * math.sqrt(norm_b))))


def _feature_relevance(signals: Mapping[str, Any], centroid: Mapping[str, float]) -> float:
    """Bounded per-dimension relevance between signals and a feature centroid.

    For each dimension in the centroid we reward the runtime signal being close
    to the target value. This works for both positive centroids
    (``song_present: 1.0``) and anti-features (``screen_capture: 0.0``) where
    raw cosine similarity would collapse to 0/0.
    """
    if not centroid:
        return 1.0

    total_weight = 0.0
    weighted_score = 0.0
    for key, target in centroid.items():
        value = _numeric_value(signals.get(key, 0.0))
        target_v = _numeric_value(target)
        # Weight dimensions by how strongly the centroid specifies them.
        weight = max(0.01, abs(target_v))
        match = 1.0 - min(1.0, abs(value - target_v))
        weighted_score += weight * match
        total_weight += weight

    if total_weight == 0.0:
        return 1.0
    return max(0.0, min(1.0, weighted_score / total_weight))


def should_run_feature(
    name: str,
    signals: Mapping[str, Any],
    threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
) -> Tuple[bool, float]:
    """Return (should_run, relevance_score) for a named feature.

    Relevance is a bounded per-dimension similarity between the runtime signals
    and the feature's centroid. An empty centroid means the feature is always
    considered relevant (e.g. ``save_the_cat`` dispatcher).
    """
    centroid = FEATURE_RELEVANCE_CENTROIDS.get(name, {})
    if not centroid:
        return True, 1.0

    relevance = _feature_relevance(signals, centroid)
    return relevance > threshold, relevance


def gated_budget(relevance: float, min_budget: int, max_budget: int) -> int:
    """Scale a feature's LLM/cloud budget linearly with relevance.

    Relevance at or below the default gate threshold (0.3) yields a budget of
    zero. Relevance at 1.0 yields ``max_budget``.
    """
    if relevance <= DEFAULT_RELEVANCE_THRESHOLD:
        return 0
    if max_budget <= min_budget:
        return max(0, max_budget)
    ratio = (relevance - DEFAULT_RELEVANCE_THRESHOLD) / (1.0 - DEFAULT_RELEVANCE_THRESHOLD)
    budget = min_budget + (max_budget - min_budget) * ratio
    return int(max(0, min(max_budget, budget)))


def reason_to_skip(name: str, signals: Mapping[str, Any]) -> str:
    """Human-readable reason why a feature was gated off."""
    centroid = FEATURE_RELEVANCE_CENTROIDS.get(name, {})
    if not centroid:
        return ""
    relevance = _feature_relevance(signals, centroid)
    return (
        f"{name} gated off (relevance={relevance:.2f} <= threshold="
        f"{DEFAULT_RELEVANCE_THRESHOLD:.2f})"
    )


def classify_content_cluster(
    signals: Mapping[str, Any],
    threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> Tuple[str, float, Dict[str, float]]:
    """Return the closest content cluster for a set of signals.

    The result is continuous: every cluster receives a relevance score and the
    function returns the best-scoring label. If the best score is below
    ``threshold`` the content is treated as ``general`` so we do not force a
    weak cluster assignment.
    """
    if not CONTENT_CLUSTER_CENTROIDS:
        return "general", 0.0, {}

    scores = {
        name: _feature_relevance(signals, centroid)
        for name, centroid in CONTENT_CLUSTER_CENTROIDS.items()
    }
    label = max(scores, key=scores.get)  # type: ignore[arg-type]
    score = scores[label]
    if score < threshold:
        return "general", score, scores
    return label, score, scores
