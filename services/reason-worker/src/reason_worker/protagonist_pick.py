# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Load cached face detections and select project protagonists."""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Tuple

from ingest_worker.identity import FaceDetection, cache_path_for_clip
from shared_py.identity_cluster import Identity, cluster_project_identities, pick_protagonists

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_FPS = 2.0


def load_faces_for_project(clip_paths: Dict[str, str]) -> Dict[str, List[FaceDetection]]:
    """Load cached ``.faces.json`` files for a set of clips.

    Args:
        clip_paths: Mapping from clip_id to local file path.

    Returns:
        Mapping from clip_id to list of FaceDetection objects.
    """
    all_faces: Dict[str, List[FaceDetection]] = {}
    for clip_id, clip_path in clip_paths.items():
        cache_path = cache_path_for_clip(clip_path)
        if not os.path.exists(cache_path):
            continue
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            all_faces[clip_id] = [FaceDetection(**item) for item in data]
        except Exception as exc:
            logger.warning("Failed to load face cache for %s: %s", clip_id, exc)
    return all_faces


def select_protagonists(
    clip_paths: Dict[str, str],
    sample_fps: float = DEFAULT_SAMPLE_FPS,
    top_n: int = 2,
    eps: float = 0.4,
    min_samples: int = 5,
) -> Tuple[List[Identity], List[int]]:
    """Cluster faces across clips and pick the top protagonists.

    Args:
        clip_paths: Mapping from clip_id to local file path.
        sample_fps: Frame sampling rate used during face extraction.
        top_n: Number of protagonists to return.
        eps: DBSCAN cosine-distance threshold.
        min_samples: DBSCAN minimum cluster size.

    Returns:
        Tuple of (protagonist identities, selected identity ids).
    """
    all_faces = load_faces_for_project(clip_paths)
    if not all_faces:
        return [], []

    clip_frame_durations: Dict[str, float] = {}
    for clip_id, fds in all_faces.items():
        if fds:
            clip_frame_durations[clip_id] = max(fd.t_s for fd in fds) + (1.0 / sample_fps)
        else:
            clip_frame_durations[clip_id] = 0.0

    identities = cluster_project_identities(
        all_faces,
        clip_frame_durations,
        eps=eps,
        min_samples=min_samples,
    )
    protagonists = pick_protagonists(identities, top_n=top_n)
    return protagonists, [p.id for p in protagonists]
