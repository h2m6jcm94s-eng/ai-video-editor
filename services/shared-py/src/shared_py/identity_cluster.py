# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Identity clustering and protagonist selection for face detections."""

from __future__ import annotations

import dataclasses
import logging
import math
from typing import Dict, List

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dep
    np = None  # type: ignore[assignment]

try:
    from sklearn.cluster import DBSCAN
except Exception:  # pragma: no cover - optional dep
    DBSCAN = None  # type: ignore[assignment,misc]

from shared_py.tuning import IDENTITY

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Identity:
    """A cluster of face detections representing one subject."""

    id: int
    label: str
    centroid_embedding: List[float]
    face_detections: List[object]
    avg_confidence: float
    screen_time_s: float
    avg_face_size: float


def cluster_project_identities(
    all_face_detections: Dict[str, List[object]],
    clip_frame_durations: Dict[str, float],
    eps: float = IDENTITY.DBSCAN_EPS,
    min_samples: int = IDENTITY.DBSCAN_MIN_SAMPLES,
) -> List[Identity]:
    """Cluster face detections across clips into identities using DBSCAN.

    Args:
        all_face_detections: Mapping from clip_id to list of FaceDetection objects.
        clip_frame_durations: Mapping from clip_id to clip duration in seconds.
            Used to estimate the screen time contributed by each clip to an identity.
        eps: Maximum cosine distance for DBSCAN neighbourhood.
        min_samples: Minimum samples to form a cluster.

    Returns:
        A list of Identity objects.  The DBSCAN noise cluster (-1) is excluded.
    """
    if DBSCAN is None or np is None:
        logger.warning("scikit-learn or numpy not available; cannot cluster identities")
        return []

    detections: List[object] = []
    for clip_id, fds in all_face_detections.items():
        for fd in fds:
            detections.append(fd)

    if len(detections) < min_samples:
        return []

    embeddings = np.array([fd.embedding for fd in detections])
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit(embeddings)
    labels = clustering.labels_

    identities: List[Identity] = []
    unique_labels = sorted({label for label in labels if label != -1})
    for label in unique_labels:
        cluster_dets = [d for d, lbl in zip(detections, labels) if lbl == label]
        if not cluster_dets:
            continue
        centroid = np.mean(np.array([d.embedding for d in cluster_dets]), axis=0).tolist()
        avg_confidence = float(np.mean([d.confidence for d in cluster_dets]))
        avg_face_size = float(np.mean([d.face_area_ratio for d in cluster_dets]))
        unique_clips = {d.clip_id for d in cluster_dets}
        screen_time_s = sum(clip_frame_durations.get(cid, 0.0) for cid in unique_clips)
        identities.append(
            Identity(
                id=int(label),
                label=f"identity_{label}",
                centroid_embedding=centroid,
                face_detections=cluster_dets,
                avg_confidence=avg_confidence,
                screen_time_s=screen_time_s,
                avg_face_size=avg_face_size,
            )
        )

    return identities


def pick_protagonists(identities: List[Identity], top_n: int = 2) -> List[Identity]:
    """Return the top-N identities by screen-time weighted score.

    Score = screen_time_s * avg_confidence * sqrt(avg_face_size).
    The noise cluster is never passed in because ``cluster_project_identities``
    filters it out.
    """
    if not identities:
        return []

    def score(identity: Identity) -> float:
        size_factor = math.sqrt(max(0.0, identity.avg_face_size))
        return identity.screen_time_s * identity.avg_confidence * size_factor

    ranked = sorted(identities, key=score, reverse=True)
    return ranked[:top_n]
