# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.identity_cluster import Identity, cluster_project_identities, pick_protagonists


@dataclass
class _FakeFace:
    clip_id: str
    frame_idx: int
    t_s: float
    bbox: list
    bbox_norm: list
    embedding: list
    confidence: float
    face_area_ratio: float


def _make_faces(clip_id: str, centroid: list, count: int, noise: float = 0.0) -> list:
    return [
        _FakeFace(
            clip_id=clip_id,
            frame_idx=i,
            t_s=i / 2.0,
            bbox=[10.0, 10.0, 20.0, 20.0],
            bbox_norm=[0.1, 0.1, 0.2, 0.2],
            embedding=(np.array(centroid) + np.random.normal(0, noise, len(centroid))).tolist(),
            confidence=0.9,
            face_area_ratio=0.05,
        )
        for i in range(count)
    ]


def test_dbscan_same_face_same_cluster():
    centroid = [1.0] * 128
    all_faces = {
        "clip-a": _make_faces("clip-a", centroid, 6, noise=0.02),
        "clip-b": _make_faces("clip-b", centroid, 6, noise=0.02),
    }
    durations = {"clip-a": 3.0, "clip-b": 3.0}

    identities = cluster_project_identities(all_faces, durations, eps=0.4, min_samples=5)
    assert len(identities) == 1
    assert identities[0].id != -1


def test_dbscan_different_faces_different_clusters():
    all_faces = {
        "clip-a": _make_faces("clip-a", [1.0, 0.0] * 64, 6, noise=0.02),
        "clip-b": _make_faces("clip-b", [0.0, 1.0] * 64, 6, noise=0.02),
        "clip-c": _make_faces("clip-c", [-1.0, 0.0] * 64, 6, noise=0.02),
    }
    durations = {cid: 3.0 for cid in all_faces}

    identities = cluster_project_identities(all_faces, durations, eps=0.4, min_samples=5)
    assert len(identities) == 3
    ids = {identity.id for identity in identities}
    assert -1 not in ids


def test_pick_protagonists_by_screen_time():
    identity_a = Identity(
        id=0,
        label="identity_0",
        centroid_embedding=[1.0] * 128,
        face_detections=[],
        avg_confidence=0.95,
        screen_time_s=10.0,
        avg_face_size=0.05,
    )
    identity_b = Identity(
        id=1,
        label="identity_1",
        centroid_embedding=[-1.0] * 128,
        face_detections=[],
        avg_confidence=0.95,
        screen_time_s=1.0,
        avg_face_size=0.05,
    )

    protagonists = pick_protagonists([identity_a, identity_b], top_n=1)
    assert len(protagonists) == 1
    assert protagonists[0].id == 0
