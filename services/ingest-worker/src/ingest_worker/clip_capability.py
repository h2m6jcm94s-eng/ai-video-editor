# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Per-clip capability map for the intent-first editing architecture.

Maps each user clip to the 15 edit intents it can serve, based on low-cost
signals already extracted during ingest: motion, faces, shot type, semantic
similarity, and emotion. The result is a JSON-serializable profile consumed
by the downstream intent composer and ranker.
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from shared_py.feature_tracer import FeatureTracer
from shared_py.logging_config import StructuredLogger
from shared_py.models import EDIT_INTENT_LABELS, ClipCapabilityProfile, ClipEmotionProfile

try:
    import cv2

    _CV2 = True
except Exception:  # pragma: no cover - optional dep
    _CV2 = False

logger = StructuredLogger("ingest_worker.clip_capability")


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "clip_capability"


def cache_path_for_clip(
    clip_path: str,
    cache_dir: Optional[Path] = None,
) -> str:
    """Return the JSON cache path for a given clip file."""
    return str((cache_dir or _default_cache_dir()) / f"{Path(clip_path).stem}.json")


def _load_capability_cache(cache_path: str) -> Optional[ClipCapabilityProfile]:
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ClipCapabilityProfile.model_validate(data)
    except Exception as exc:
        logger.warning("capability_cache_load_failed", path=cache_path, error=str(exc))
        return None


def _write_capability_cache(cache_path: str, profile: ClipCapabilityProfile) -> None:
    try:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(by_alias=True, mode="json"), f, indent=2)
    except Exception as exc:
        logger.warning("capability_cache_write_failed", path=cache_path, error=str(exc))


# ---------------------------------------------------------------------------
# Low-level signal loaders
# ---------------------------------------------------------------------------


def _probe_duration(clip_path: str) -> float:
    """Return video duration via OpenCV, falling back to 0.0."""
    if not _CV2:
        return 0.0
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return 0.0
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        return float(frames / fps) if fps > 0 else 0.0
    finally:
        cap.release()


def _load_heatmap_windows(clip_path: str) -> List[Dict[str, Any]]:
    """Load per-window motion/aesthetic/sharpness/stability from heatmap cache."""
    from ingest_worker.heatmap import compute_clip_heatmap_cached

    try:
        windows = compute_clip_heatmap_cached(clip_path)
        return [
            {
                "start_s": w.start_s,
                "end_s": w.end_s,
                "score": w.score,
                "motion": w.components.get("motion", 0.0),
                "aesthetic": w.components.get("aesthetic", 0.0),
                "sharpness": w.components.get("sharpness", 0.0),
                "stability": w.components.get("stability", 0.5),
                "dominant_motion": w.dominant_motion,
            }
            for w in windows
        ]
    except Exception as exc:
        logger.warning("heatmap_load_failed", path=clip_path, error=str(exc))
        return []


def _load_emotion_profile(clip_path: str) -> Optional[ClipEmotionProfile]:
    """Load the fused emotion profile from cache or compute it."""
    from ingest_worker.clip_emotion import (
        cache_path_for_clip as emotion_cache_path,
        compute_clip_emotion_profile,
    )

    try:
        return compute_clip_emotion_profile(clip_path, cache_path=emotion_cache_path(clip_path))
    except Exception as exc:
        logger.warning("emotion_load_failed", path=clip_path, error=str(exc))
        return None


def _load_semantic_embedding(clip_path: str, clip_id: Optional[str] = None):
    """Load DINO-v2 first/last/sample embeddings from cache or compute them."""
    from ingest_worker.clip_semantic import embed_clip

    try:
        return embed_clip(clip_path, clip_id=clip_id)
    except Exception as exc:
        logger.warning("semantic_load_failed", path=clip_path, error=str(exc))
        return None


def _load_face_detections(clip_path: str, clip_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Run face detection and return lightweight per-face records."""
    from ingest_worker.identity import extract_faces_from_clip

    try:
        faces = extract_faces_from_clip(clip_path, clip_id or Path(clip_path).stem)
        return [
            {
                "bbox_norm": f.bbox_norm,
                "confidence": f.confidence,
                "t_s": f.t_s,
            }
            for f in faces
        ]
    except Exception as exc:
        logger.warning("face_extraction_failed", path=clip_path, error=str(exc))
        return []


# ---------------------------------------------------------------------------
# Feature aggregation
# ---------------------------------------------------------------------------


def _motion_trend(motions: List[float]) -> str:
    """Classify motion trajectory across the clip."""
    if len(motions) < 4:
        return "static"
    mid = len(motions) // 2
    first = float(np.mean(motions[:mid]))
    second = float(np.mean(motions[mid:]))
    if second > first + 0.1:
        return "increasing"
    if second < first - 0.1:
        return "decreasing"
    return "static"


def _dominant_motion_mode(motions: List[str]) -> str:
    """Return the most common dominant motion direction."""
    if not motions:
        return "still"
    return Counter(motions).most_common(1)[0][0]


def _face_area_ratio(face: Dict[str, Any]) -> float:
    """Compute normalized face area from a bbox_norm record."""
    bbox = face.get("bbox_norm") or [0.0, 0.0, 0.0, 0.0]
    if len(bbox) < 4:
        return 0.0
    x1, y1, x2, y2 = bbox
    return max(0.0, (x2 - x1) * (y2 - y1))


def _face_count_mode(faces: List[Dict[str, Any]]) -> int:
    """Most common number of faces detected in a sampled frame."""
    if not faces:
        return 0
    counts = Counter(round(f["t_s"], 2) for f in faces)
    return counts.most_common(1)[0][1] if counts else 0


def _first_last_similarity(semantic_embedding) -> float:
    """Cosine similarity between first and last DINO-v2 frame embeddings."""
    if semantic_embedding is None:
        return 0.0
    a = semantic_embedding.first_frame_embedding
    b = semantic_embedding.last_frame_embedding
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm == 0:
        return 0.0
    return float(np.dot(a, b) / norm)


def _shot_type(face_area_ratio: float, duration_sec: float, mean_motion: float) -> str:
    """Heuristic shot-size classification from face coverage and motion."""
    if face_area_ratio > 0.25:
        return "close_up"
    if face_area_ratio > 0.08:
        return "medium"
    if face_area_ratio < 0.03 and mean_motion < 0.3 and duration_sec > 2.0:
        return "wide"
    return "medium"


def _aggregate_features(
    duration_sec: float,
    windows: List[Dict[str, Any]],
    emotion_profile: Optional[ClipEmotionProfile],
    semantic_embedding,
    faces: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Turn raw signals into a normalized feature dict for intent scoring."""
    if windows:
        motions = [w["motion"] for w in windows]
        mean_motion = float(np.mean(motions))
        stability = float(np.mean([w["stability"] for w in windows]))
        aesthetic = float(np.mean([w["aesthetic"] for w in windows]))
        sharpness = float(np.mean([w["sharpness"] for w in windows]))
        dominant_motion = _dominant_motion_mode([w["dominant_motion"] for w in windows])
        motion_trend = _motion_trend(motions)
    else:
        # Anti-decoration: missing raw signals should not pretend to be average.
        mean_motion = emotion_profile.motion_vibe if emotion_profile else 0.0
        stability = 0.0
        aesthetic = 0.0
        sharpness = 0.0
        dominant_motion = "still"
        motion_trend = "static"

    face_areas = [_face_area_ratio(f) for f in faces]
    face_area_ratio = max(face_areas) if face_areas else 0.0
    face_count_mode = _face_count_mode(faces)
    dino_sim = _first_last_similarity(semantic_embedding)
    audio_arousal = emotion_profile.audio_prosody_arousal if emotion_profile else 0.0

    return {
        "duration_sec": duration_sec,
        "mean_motion": mean_motion,
        "motion_trend": motion_trend,
        "dominant_motion": dominant_motion,
        "stability": stability,
        "aesthetic": aesthetic,
        "sharpness": sharpness,
        "face_area_ratio": face_area_ratio,
        "face_count_mode": face_count_mode,
        "dino_sim": dino_sim,
        "audio_arousal": audio_arousal,
        "shot_type": _shot_type(face_area_ratio, duration_sec, mean_motion),
        "heatmap_missing": len(windows) == 0,
        "emotion_missing": emotion_profile is None,
        "semantic_missing": semantic_embedding is None,
        "face_missing": len(faces) == 0,
    }


# ---------------------------------------------------------------------------
# Intent scoring heuristics
# ---------------------------------------------------------------------------


def _clamp(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def _score_breathe(f: Dict[str, Any]) -> float:
    return _clamp(
        (1.0 - f["mean_motion"]) * 0.4
        + f["stability"] * 0.2
        + f["dino_sim"] * 0.2
        + max(0.0, 0.1 - f["face_area_ratio"]) * 3.0
        + min(f["duration_sec"] / 3.0, 1.0) * 0.2
    )


def _score_punctuate(f: Dict[str, Any]) -> float:
    return _clamp(
        f["mean_motion"] * 0.6
        + f["sharpness"] * 0.2
        + (1.0 - abs(f["duration_sec"] - 1.0)) * 0.2
    )


def _score_ramp_up(f: Dict[str, Any]) -> float:
    trend_weight = 0.8 if f["motion_trend"] == "increasing" else 0.2
    return _clamp(
        trend_weight * 0.5
        + f["mean_motion"] * 0.2
        + min(f["duration_sec"] / 2.0, 1.0) * 0.3
    )


def _score_release(f: Dict[str, Any]) -> float:
    return _clamp(
        f["mean_motion"] * 0.7
        + max(0.0, 0.2 - f["face_area_ratio"]) * 1.5
        + min(f["duration_sec"] / 1.5, 1.0) * 0.2
    )


def _score_reveal(f: Dict[str, Any]) -> float:
    motion_weight = 0.0 if f["dominant_motion"] == "still" else 1.0
    return _clamp(
        (1.0 - f["dino_sim"]) * 0.5
        + motion_weight * 0.3
        + min(f["mean_motion"], 1.0) * 0.2
    )


def _score_withhold(f: Dict[str, Any]) -> float:
    return _clamp(
        min(f["face_area_ratio"] * 2.0, 1.0) * 0.4
        + (1.0 - f["mean_motion"]) * 0.3
        + f["stability"] * 0.2
        + min(f["duration_sec"] / 2.0, 1.0) * 0.1
    )


def _score_connect(f: Dict[str, Any]) -> float:
    multi_face = 0.8 if f["face_count_mode"] >= 2 else 0.1
    return _clamp(
        multi_face * 0.4
        + (1.0 - abs(f["face_area_ratio"] - 0.15) * 5.0) * 0.3
        + min(f["duration_sec"] / 2.0, 1.0) * 0.3
    )


def _score_isolate(f: Dict[str, Any]) -> float:
    single_face = 0.7 if f["face_count_mode"] == 1 else 0.1
    return _clamp(
        single_face * 0.4
        + min(f["face_area_ratio"] * 2.5, 1.0) * 0.4
        + min(f["duration_sec"] / 1.5, 1.0) * 0.2
    )


def _score_shock(f: Dict[str, Any]) -> float:
    short = 1.0 if f["duration_sec"] < 1.0 else 0.0
    return _clamp(
        f["mean_motion"] * 0.4
        + (1.0 - f["stability"]) * 0.3
        + f["sharpness"] * 0.2
        + short * 0.2
    )


def _score_carry(f: Dict[str, Any]) -> float:
    return _clamp(
        (1.0 - abs(f["mean_motion"] - 0.5) * 1.5) * 0.4
        + f["stability"] * 0.2
        + f["dino_sim"] * 0.2
        + min(f["duration_sec"] / 3.0, 1.0) * 0.2
    )


def _score_linger(f: Dict[str, Any]) -> float:
    face = 1.0 if f["face_area_ratio"] > 0.1 else 0.0
    return _clamp(
        min(f["duration_sec"] / 4.0, 1.0) * 0.5
        + (1.0 - f["mean_motion"]) * 0.2
        + face * 0.3
    )


def _score_jab(f: Dict[str, Any]) -> float:
    short = 1.0 if f["duration_sec"] < 0.8 else 0.0
    return _clamp(
        short * 0.5
        + f["mean_motion"] * 0.5
    )


def _score_layer(f: Dict[str, Any]) -> float:
    return _clamp(
        f["aesthetic"] * 0.3
        + f["mean_motion"] * 0.3
        + (1.0 - f["dino_sim"]) * 0.2
        + min(f["duration_sec"] / 2.5, 1.0) * 0.2
    )


def _score_strip_down(f: Dict[str, Any]) -> float:
    return _clamp(
        (1.0 - f["mean_motion"]) * 0.3
        + max(0.0, 0.05 - f["face_area_ratio"]) * 5.0
        + f["dino_sim"] * 0.2
        + min(f["duration_sec"] / 3.0, 1.0) * 0.2
    )


def _score_amplify(f: Dict[str, Any]) -> float:
    trend_weight = 0.8 if f["motion_trend"] == "increasing" else 0.2
    return _clamp(
        f["mean_motion"] * 0.4
        + trend_weight * 0.3
        + f["audio_arousal"] * 0.2
        + min(f["duration_sec"] / 2.5, 1.0) * 0.1
    )


_INTENT_SCORERS = {
    "BREATHE": _score_breathe,
    "PUNCTUATE": _score_punctuate,
    "RAMP_UP": _score_ramp_up,
    "RELEASE": _score_release,
    "REVEAL": _score_reveal,
    "WITHHOLD": _score_withhold,
    "CONNECT": _score_connect,
    "ISOLATE": _score_isolate,
    "SHOCK": _score_shock,
    "CARRY": _score_carry,
    "LINGER": _score_linger,
    "JAB": _score_jab,
    "LAYER": _score_layer,
    "STRIP_DOWN": _score_strip_down,
    "AMPLIFY": _score_amplify,
}


def _score_intents(features: Dict[str, Any]) -> Dict[str, float]:
    """Return a score in [0, 1] for each of the 15 edit intents."""
    return {intent: _clamp(scorer(features)) for intent, scorer in _INTENT_SCORERS.items()}


def _confidence(features: Dict[str, Any]) -> float:
    """Confidence that the capability profile reflects real signal, not fallback."""
    conf = 1.0
    if features.get("heatmap_missing"):
        conf -= 0.2
    if features.get("emotion_missing"):
        conf -= 0.2
    if features.get("semantic_missing"):
        conf -= 0.15
    if features.get("face_missing"):
        conf -= 0.15
    return max(0.0, conf)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_clip_capability_profile(
    clip_path: str,
    clip_id: Optional[str] = None,
    cache_path: Optional[str] = None,
    force_refresh: bool = False,
) -> ClipCapabilityProfile:
    """Compute or load the capability map for a single clip.

    The function is safe to call repeatedly: it reads a JSON cache when
    available and writes one after real computation. Heavy signal extraction
    (DINO, heatmap, emotion, faces) is delegated to existing ingest modules
    that have their own caches.
    """
    with FeatureTracer("clip_capability", gated_in=True) as ft:
        effective_cache_path = (
            cache_path if cache_path is not None else cache_path_for_clip(clip_path)
        )
        if not force_refresh:
            cached = _load_capability_cache(effective_cache_path)
            if cached is not None:
                ft.signature("cached")
                ft.real()
                return cached

        duration_sec = _probe_duration(clip_path)
        windows = _load_heatmap_windows(clip_path)
        emotion_profile = _load_emotion_profile(clip_path)
        semantic_embedding = _load_semantic_embedding(clip_path, clip_id=clip_id)
        faces = _load_face_detections(clip_path, clip_id=clip_id)

        features = _aggregate_features(
            duration_sec, windows, emotion_profile, semantic_embedding, faces
        )
        intent_scores = _score_intents(features)

        profile = ClipCapabilityProfile(
            clip_id=clip_id or Path(clip_path).stem,
            duration_sec=round(duration_sec, 3),
            shot_type=features["shot_type"],
            motion_energy=round(features["mean_motion"], 3),
            motion_trend=features["motion_trend"],
            dominant_motion=features["dominant_motion"],
            stability=round(features["stability"], 3),
            aesthetic_score=round(features["aesthetic"], 3),
            sharpness=round(features["sharpness"], 3),
            face_area_ratio=round(features["face_area_ratio"], 3),
            face_count_mode=features["face_count_mode"],
            dino_first_last_similarity=round(features["dino_sim"], 3),
            audio_arousal=round(features["audio_arousal"], 3),
            intent_scores={k: round(v, 3) for k, v in intent_scores.items()},
            confidence=round(_confidence(features), 3),
        )

        _write_capability_cache(effective_cache_path, profile)
        top = max(intent_scores, key=intent_scores.get) if intent_scores else ""
        ft.signature(f"intents={len(intent_scores)},top={top}")
        ft.real()
        return profile


def compute_clip_capability_profiles(
    clip_paths: Dict[str, str],
    cache_dir: Optional[Path] = None,
) -> Dict[str, ClipCapabilityProfile]:
    """Compute capability maps for multiple clips keyed by clip_id."""
    results: Dict[str, ClipCapabilityProfile] = {}
    for clip_id, path in clip_paths.items():
        cache_path = None
        if cache_dir is not None:
            cache_path = str(cache_dir / f"{clip_id}.json")
        results[clip_id] = compute_clip_capability_profile(
            path, clip_id=clip_id, cache_path=cache_path
        )
    return results
