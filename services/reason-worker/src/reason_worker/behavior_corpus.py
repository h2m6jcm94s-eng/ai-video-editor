# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Ingest successful renders into the behavior corpus.

The API is the single source of truth for anti-spam / anti-poisoning guards:
  * Per-user 7-day contribution cap (default 10/week).
  * Anomaly detection against the existing public corpus (>3σ from centroid).
  * Quarantine path for anomalous entries instead of poisoning global KNN.

This module now delegates ingestion to
``POST /api/internal/renders/{render_id}/ingest-to-corpus`` and only keeps the
shared math helpers for local use/tests.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from shared_py.config import settings

WEEKLY_CONTRIBUTION_CAP = 10
ANOMALY_Z_THRESHOLD = 3.0


def _internal_token() -> str:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return token


def _headers() -> Dict[str, str]:
    return {"x-internal-token": _internal_token()}


def _api_base() -> str:
    return settings.api_base


def _numeric_vector(signals: Dict[str, Any], feature_keys: List[str]) -> List[float]:
    return [
        float(signals.get(k)) if isinstance(signals.get(k), (int, float)) else (1.0 if signals.get(k) is True else 0.0)
        for k in feature_keys
    ]


def _euclidean(a: List[float], b: List[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _signal_feature_keys() -> List[str]:
    # Same dimensions used by BehaviorEngine for distance computation.
    return [
        "speech_ratio",
        "avg_speech_segment_duration_s",
        "multi_speaker_ratio",
        "song_present",
        "song_energy_mean",
        "song_tempo_bpm",
        "song_section_count",
        "clip_count",
        "clip_avg_duration_s",
        "motion_density",
        "motion_variance",
        "aesthetic_score_mean",
        "face_screentime_ratio",
        "multi_face_ratio",
        "shot_diversity",
        "reference_present",
    ]


def _compute_corpus_centroid(entries: List[Dict[str, Any]]) -> Optional[List[float]]:
    """Mean signal vector across a set of corpus entries."""
    if not entries:
        return None
    keys = _signal_feature_keys()
    vectors = [_numeric_vector(e.get("signals") or {}, keys) for e in entries]
    n = len(vectors)
    dim = len(keys)
    return [sum(v[i] for v in vectors) / n for i in range(dim)]


def is_anomalous_corpus_entry(signals: Dict[str, Any], public_entries: list) -> bool:
    """Return True if the new entry is >3σ away from the existing corpus centroid."""
    if len(public_entries) < 2:
        return False

    centroid = _compute_corpus_centroid(public_entries)
    if centroid is None:
        return False

    keys = _signal_feature_keys()
    new_vector = _numeric_vector(signals, keys)

    distances = [_euclidean(_numeric_vector(e.get("signals") or {}, keys), centroid) for e in public_entries]
    new_distance = _euclidean(new_vector, centroid)

    mean_dist = _mean(distances)
    std_dist = _std(distances)
    if std_dist == 0:
        return new_distance > mean_dist

    z = (new_distance - mean_dist) / std_dist
    return abs(z) > ANOMALY_Z_THRESHOLD


def can_user_contribute(entries_last_7d: List[Dict[str, Any]]) -> bool:
    """Per-user weekly cap to prevent one user from shaping the global model."""
    return len(entries_last_7d) < WEEKLY_CONTRIBUTION_CAP


async def ingest_render_to_corpus(
    render_id: str,
    quality_weight: float = 0.5,
) -> Dict[str, Any]:
    """Ask the API to ingest a render's signals/behavior into the corpus.

    The API enforces the weekly cap, anomaly detection, and quarantine logic so
    all guards live in one place.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_api_base()}/internal/renders/{render_id}/ingest-to-corpus",
            json={"qualityWeight": quality_weight},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return await resp.json()
