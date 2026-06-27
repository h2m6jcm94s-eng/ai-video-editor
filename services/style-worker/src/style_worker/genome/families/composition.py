# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Composition feature family for the Style Genome."""

from __future__ import annotations

from typing import List

try:
    import cv2
except Exception:  # pragma: no cover - optional dep
    cv2 = None  # type: ignore[assignment]

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dep
    np = None  # type: ignore[assignment]

from shared_py.logging_config import StructuredLogger
from shared_py.models import CompositionFamily, ShotBoundary, StyleAnalysis

logger = StructuredLogger("style_worker.genome.families.composition")


def _classify_shot_size(corners, width: int, height: int) -> str:
    """Heuristic shot-size guess from feature-point spread and centrality."""
    if np is None:
        return "medium"

    xs = corners[:, 0]
    ys = corners[:, 1]
    centroid = np.array([xs.mean(), ys.mean()])
    center = np.array([width / 2.0, height / 2.0])
    centroid_dist = np.linalg.norm(centroid - center) / max(width, height)

    spread_x = np.std(xs) / max(1, width)
    spread_y = np.std(ys) / max(1, height)
    spread = max(spread_x, spread_y)

    if centroid_dist < 0.15 and spread < 0.12:
        return "close_up"
    if spread > 0.25:
        return "wide"
    return "medium"


def _rule_of_thirds_score(corners, width: int, height: int) -> float:
    """Fraction of feature points near rule-of-thirds lines."""
    if np is None:
        return 0.0

    margin = min(width, height) * 0.1
    v_lines = [width / 3.0, 2.0 * width / 3.0]
    h_lines = [height / 3.0, 2.0 * height / 3.0]

    on_thirds = 0
    for x, y in corners:
        near_v = any(abs(x - line) < margin for line in v_lines)
        near_h = any(abs(y - line) < margin for line in h_lines)
        if near_v or near_h:
            on_thirds += 1

    return on_thirds / len(corners)


def extract_composition_genome(
    video_path: str,
    shot_boundaries: List[ShotBoundary],
    style_analysis: StyleAnalysis,
    video_info: dict,
) -> CompositionFamily:
    """Extract the 5 composition features."""
    del style_analysis  # reserved for future shot-analysis integration

    size_labels: List[str] = []
    thirds_scores: List[float] = []

    if cv2 is not None and np is not None and shot_boundaries:
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            for shot in shot_boundaries:
                mid = max(shot.start_frame, min((shot.start_frame + shot.end_frame) // 2, total_frames - 1))
                cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
                ret, frame = cap.read()
                if not ret:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                height, width = gray.shape
                corners = cv2.goodFeaturesToTrack(
                    gray, maxCorners=100, qualityLevel=0.01, minDistance=10
                )
                if corners is None or len(corners) < 5:
                    size_labels.append("medium")
                    thirds_scores.append(0.5)
                    continue
                corners = corners.reshape(-1, 2)
                size_labels.append(_classify_shot_size(corners, width, height))
                thirds_scores.append(_rule_of_thirds_score(corners, width, height))
            cap.release()

    if not size_labels:
        # Fallback distribution keeps the feature vector finite and normalized.
        size_labels = ["medium"] * max(1, len(shot_boundaries))
        thirds_scores = [0.5] * len(size_labels)

    n = len(size_labels)
    pct_close = size_labels.count("close_up") / n
    pct_medium = size_labels.count("medium") / n
    pct_wide = size_labels.count("wide") / n

    dominant = "medium"
    if pct_close >= pct_medium and pct_close >= pct_wide:
        dominant = "close_up"
    elif pct_wide >= pct_medium and pct_wide >= pct_close:
        dominant = "wide"

    rule_of_thirds = sum(thirds_scores) / len(thirds_scores) if thirds_scores else 0.0

    return CompositionFamily(
        dominant_shot_size=dominant,
        pct_close_up=pct_close,
        pct_medium_shot=pct_medium,
        pct_wide_shot=pct_wide,
        rule_of_thirds_ratio=rule_of_thirds,
    )
