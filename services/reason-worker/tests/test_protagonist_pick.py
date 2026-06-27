# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ingest_worker.identity import FaceDetection
from reason_worker.protagonist_pick import load_faces_for_project, select_protagonists


@dataclass
class _FakeIdentity:
    id: int
    label: str
    centroid_embedding: list
    face_detections: list
    avg_confidence: float
    screen_time_s: float
    avg_face_size: float


def _make_face(clip_id: str, embedding: list, t_s: float = 0.0) -> FaceDetection:
    return FaceDetection(
        clip_id=clip_id,
        frame_idx=0,
        t_s=t_s,
        bbox=[10.0, 10.0, 20.0, 20.0],
        bbox_norm=[0.1, 0.1, 0.2, 0.2],
        embedding=embedding,
        confidence=0.95,
        face_area_ratio=0.05,
    )


def test_load_faces_for_project_reads_cache(tmp_path):
    clip_path = str(tmp_path / "clip.mp4")
    faces = [_make_face("clip-a", [1.0] * 128)]
    with open(f"{clip_path}.faces.json", "w", encoding="utf-8") as f:
        json.dump([{k: getattr(fd, k) for k in fd.__dataclass_fields__} for fd in faces], f)

    result = load_faces_for_project({"clip-a": clip_path})
    assert "clip-a" in result
    assert len(result["clip-a"]) == 1


def test_select_protagonists_empty_when_no_cache(tmp_path):
    result = select_protagonists({"clip-a": str(tmp_path / "missing.mp4")})
    assert result == ([], [])


def test_protagonist_picked_by_screen_time(tmp_path, monkeypatch):
    identity_a = _FakeIdentity(
        id=0,
        label="identity_0",
        centroid_embedding=[1.0] * 128,
        face_detections=[_make_face("clip-a", [1.0] * 128)],
        avg_confidence=0.95,
        screen_time_s=10.0,
        avg_face_size=0.05,
    )
    identity_b = _FakeIdentity(
        id=1,
        label="identity_1",
        centroid_embedding=[-1.0] * 128,
        face_detections=[_make_face("clip-b", [-1.0] * 128)],
        avg_confidence=0.95,
        screen_time_s=1.0,
        avg_face_size=0.05,
    )

    monkeypatch.setattr(
        "reason_worker.protagonist_pick.cluster_project_identities",
        lambda *a, **kw: [identity_a, identity_b],
    )
    monkeypatch.setattr(
        "reason_worker.protagonist_pick.load_faces_for_project",
        lambda *a, **kw: {"clip-a": []},
    )

    protagonists, ids = select_protagonists({"clip-a": str(tmp_path / "a.mp4")})
    assert ids == [0, 1]
    assert protagonists[0].screen_time_s > protagonists[1].screen_time_s
