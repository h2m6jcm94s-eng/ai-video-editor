# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""KNN-style behavior prediction from the behavior corpus + per-user bias."""

import math
import os
import re
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import httpx
from shared_py.config import settings
from shared_py.feature_gating import classify_content_cluster
from shared_py.feature_tracer import FeatureTracer
from shared_py.models import AdaptiveFeatures, BehaviorVector


# Features extracted from ContentSignals for distance computation.
# Each tuple is (key, min_value, max_value, weight). Weights reflect how much
# each dimension should influence nearest-neighbor matching. Phase 1 values are
# hand-anchored; Phase 2 recomputes them monthly from the accepted corpus.
_SIGNAL_FEATURES = [
    ("speech_ratio", 0.0, 1.0, 2.0),
    ("avg_speech_segment_duration_s", 0.0, 10.0, 0.5),
    ("multi_speaker_ratio", 0.0, 1.0, 0.5),
    ("song_present", 0.0, 1.0, 1.5),
    ("song_energy_mean", 0.0, 1.0, 1.0),
    ("song_tempo_bpm", 60.0, 200.0, 0.3),
    ("song_section_count", 0.0, 10.0, 0.3),
    ("clip_count", 0.0, 20.0, 0.3),
    ("clip_avg_duration_s", 0.0, 60.0, 0.3),
    ("motion_density", 0.0, 1.0, 1.5),
    ("motion_variance", 0.0, 1.0, 0.5),
    ("aesthetic_score_mean", 0.0, 1.0, 0.5),
    ("face_screentime_ratio", 0.0, 1.0, 1.0),
    ("multi_face_ratio", 0.0, 1.0, 0.5),
    ("shot_diversity", 0.0, 1.0, 0.5),
    ("reference_present", 0.0, 1.0, 0.5),
]

_BEHAVIOR_NUMERIC_FIELDS = {
    "cut_density_per_sec",
    "slot_duration_mean_s",
    "slot_duration_std_s",
    "clip_audio_min_importance",
    "sfx_mute_aggressiveness",
    "hard_cut_ratio",
    "duck_aggressiveness",
    "text_density_per_sec",
    "effect_intensity",
}


def _internal_token() -> str:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return token


def _to_snake_case(name: str) -> str:
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _feature_value(raw: Any) -> float:
    if isinstance(raw, bool):
        return 1.0 if raw else 0.0
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _normalize_signals(
    signals: Dict[str, Any],
    means: Optional[List[float]] = None,
    stds: Optional[List[float]] = None,
) -> List[float]:
    """Normalize signals using z-scores when corpus moments are available.

    Falls back to min-max normalization per dimension when the standard
    deviation is missing or zero.
    """
    vector = []
    for i, (key, lo, hi, _weight) in enumerate(_SIGNAL_FEATURES):
        value = _feature_value(signals.get(key))
        if means is not None and stds is not None and stds[i] > 0:
            norm = (value - means[i]) / stds[i]
            # Keep outliers from dominating the distance.
            vector.append(max(-3.0, min(3.0, norm)))
        else:
            denom = hi - lo
            norm = (value - lo) / denom if denom > 0 else 0.0
            vector.append(max(0.0, min(1.0, norm)))
    return vector


def _signal_weights() -> List[float]:
    return [weight for _key, _lo, _hi, weight in _SIGNAL_FEATURES]


def _compute_moments(signal_dicts: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    """Per-feature mean and population standard deviation across signal rows."""
    if not signal_dicts:
        return [], []

    means = []
    stds = []
    for key, _lo, _hi, _weight in _SIGNAL_FEATURES:
        values = [_feature_value(s.get(key)) for s in signal_dicts]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        means.append(mean)
        stds.append(std)
    return means, stds


def _euclidean(a: List[float], b: List[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _weighted_euclidean(a: List[float], b: List[float], weights: List[float]) -> float:
    """Weighted Euclidean distance, normalized by total weight."""
    total_weight = sum(weights)
    if total_weight == 0:
        return _euclidean(a, b)
    squared = sum(w * (x - y) ** 2 for x, y, w in zip(a, b, weights))
    return math.sqrt(squared / total_weight)


def _sigmoid(x: float) -> float:
    """Squash any real value to (0, 1)."""
    return 1.0 / (1.0 + math.exp(-x))


def _clamp(field: str, value: float) -> float:
    # Approximate clamps matching BehaviorVector Field constraints.
    clamps = {
        "cut_density_per_sec": (0.01, 2.0),
        "slot_duration_mean_s": (0.25, 30.0),
        "slot_duration_std_s": (0.0, 10.0),
        "clip_audio_min_importance": (0.0, 1.0),
        "sfx_mute_aggressiveness": (0.0, 1.0),
        "hard_cut_ratio": (0.0, 1.0),
        "duck_aggressiveness": (0.0, 1.0),
        "text_density_per_sec": (0.0, 5.0),
        "effect_intensity": (0.0, 1.0),
    }
    lo, hi = clamps.get(field, (0.0, 1.0))
    return max(lo, min(hi, value))


class BehaviorEngine:
    """Predict a BehaviorVector from content signals and historical corpus data."""

    def __init__(self, api_base: Optional[str] = None, internal_token: Optional[str] = None):
        self.api_base = api_base or settings.api_base
        self.token = internal_token or _internal_token()

    def _headers(self) -> Dict[str, str]:
        return {"x-internal-token": self.token}

    async def predict(
        self,
        signals: Dict[str, Any],
        user_id: str,
        features: AdaptiveFeatures,
        reference_genome: Optional[Dict[str, Any]] = None,
    ) -> Tuple[BehaviorVector, float, str]:
        """Return a BehaviorVector + confidence + reasoning for the signals.

        `reference_genome` is reserved for future filtering; it is intentionally
        not used in the Phase 1 KNN so the interface stays stable.

        Confidence is derived from neighbor density and query distance in the
        corpus. A low-confidence prediction triggers the UI to show alternatives.
        """
        _ = reference_genome

        cluster, cluster_score, cluster_scores = classify_content_cluster(signals)

        base = BehaviorVector()
        confidence = 0.0
        reasoning = "heuristic fallback; corpus KNN disabled"

        if features.use_corpus_knn:
            knn_result = await self._knn_predict(signals, user_id)
            if knn_result is not None:
                base, confidence, reasoning = knn_result
            else:
                reasoning = "no usable corpus entries for KNN prediction"

        if features.use_per_user_bias:
            bias = await self._fetch_user_bias(user_id, cluster)
            base = self._apply_bias(base, bias)
            reasoning += f" + per-user {cluster} bias applied"

        reasoning += f" (cluster={cluster}, score={cluster_score:.2f})"
        return base, confidence, reasoning

    async def _knn_predict(
        self, signals: Dict[str, Any], user_id: str
    ) -> Optional[Tuple[BehaviorVector, float, str]]:
        async with FeatureTracer("behavior_knn", gated_in=True) as ft:
            try:
                entries = await self._fetch_corpus(user_id)
            except Exception:
                ft.fallback("corpus_fetch_failed")
                return None

            if not entries:
                ft.fallback("no_usable_corpus_entries")
                return None

            # Use corpus moments for z-score normalization when we have enough samples.
            entry_signal_dicts = [entry.get("signals") or {} for entry in entries]
            means, stds = _compute_moments(entry_signal_dicts)
            use_z_score = len(entries) >= 2 and all(s > 0 for s in stds)
            weights = _signal_weights()

            query_vector = _normalize_signals(signals, means=means if use_z_score else None, stds=stds if use_z_score else None)

            candidates: List[Tuple[List[float], Dict[str, Any], float]] = []
            for entry in entries:
                entry_signals = entry.get("signals") or {}
                entry_behavior = entry.get("behavior") or {}
                quality_weight = float(entry.get("qualityWeight") or 0.0)

                candidate_vector = _normalize_signals(
                    entry_signals, means=means if use_z_score else None, stds=stds if use_z_score else None
                )
                distance = _weighted_euclidean(query_vector, candidate_vector, weights)
                weight = quality_weight / (1.0 + distance)

                if weight <= 0:
                    continue
                candidates.append((candidate_vector, entry_behavior, weight))

            if not candidates:
                ft.fallback("no_weighted_candidates")
                return None

            # Weighted average of behavior fields.
            weighted: Dict[str, float] = {}
            total_weight = 0.0
            for _, entry_behavior, weight in candidates:
                for field in _BEHAVIOR_NUMERIC_FIELDS:
                    raw = entry_behavior.get(field)
                    if raw is None:
                        continue
                    weighted[field] = weighted.get(field, 0.0) + float(raw) * weight
                total_weight += weight

            averaged = {field: weighted.get(field, 0.0) / total_weight for field in _BEHAVIOR_NUMERIC_FIELDS}
            averaged = {field: _clamp(field, value) for field, value in averaged.items()}

            # Carry over non-numeric defaults from BehaviorVector unless present.
            behavior_data = BehaviorVector().model_dump()
            behavior_data.update(averaged)
            behavior = BehaviorVector(**behavior_data)

            # Confidence: high when neighbors are close to each other (dense cluster)
            # AND the query is close to that cluster.
            neighbor_vectors = [c[0] for c in candidates]
            distances = [_weighted_euclidean(query_vector, v, weights) for v in neighbor_vectors]
            query_distance = min(distances) if distances else 1.0

            pairwise = [
                _weighted_euclidean(a, b, weights)
                for a, b in combinations(neighbor_vectors, 2)
            ]
            mean_pairwise = sum(pairwise) / len(pairwise) if pairwise else 0.0
            cluster_density = 1.0 / (mean_pairwise + 1e-9)

            confidence = _sigmoid(cluster_density - query_distance)
            reasoning = {
                "source": "knn",
                "neighbors": len(candidates),
                "queryDistance": round(query_distance, 4),
                "clusterDensity": round(cluster_density, 4),
                "confidence": round(confidence, 4),
            }
            ft.signature(f"neighbors={len(candidates)},confidence={round(confidence, 3)}")
            ft.real()
            return behavior, confidence, str(reasoning)

    async def _fetch_corpus(self, user_id: str) -> List[Dict[str, Any]]:
        import urllib.parse

        params = urllib.parse.urlencode({"userId": user_id, "limit": 500})
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/internal/behavior-corpus?{params}",
                headers=self._headers(),
                timeout=30,
            )
        await resp.raise_for_status()
        payload = await resp.json()
        return payload.get("entries", [])

    async def _fetch_user_bias(self, user_id: str, cluster: str = "general") -> Dict[str, float]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.api_base}/internal/user-taste-profiles/{user_id}",
                    headers=self._headers(),
                    timeout=30,
                )
            await resp.raise_for_status()
            profile = (await resp.json()).get("profile", {}) or {}
            cluster_bias_vectors = profile.get("clusterBiasVectors") or {}
            bias = (cluster_bias_vectors.get(cluster) or cluster_bias_vectors.get("general") or {})
            return {_to_snake_case(k): float(v) for k, v in bias.items()}
        except Exception:
            return {}

    def _apply_bias(self, behavior: BehaviorVector, bias: Dict[str, float]) -> BehaviorVector:
        data = behavior.model_dump()
        for key, delta in bias.items():
            if key in data:
                data[key] = _clamp(key, data[key] + delta)
        return BehaviorVector(**data)
