# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

try:
    import cv2  # noqa: F401

    _CV2 = True
except ImportError:
    cv2 = None  # type: ignore[assignment]
    _CV2 = False

from ingest_worker import identity as identity_mod
from ingest_worker.identity import (
    FaceDetection,
    cache_path_for_clip,
    ensure_faces,
    ensure_faces_for_clips,
    extract_faces_from_clip,
    extract_faces_from_clips,
)


def test_cache_path_for_clip():
    assert cache_path_for_clip("/tmp/clip.mp4") == "/tmp/clip.mp4.faces.json"


def test_face_detection_dataclass():
    fd = FaceDetection(
        clip_id="c1",
        frame_idx=5,
        t_s=0.25,
        bbox=[10.0, 20.0, 30.0, 40.0],
        bbox_norm=[0.1, 0.2, 0.3, 0.4],
        embedding=[0.1] * 512,
        confidence=0.95,
        face_area_ratio=0.05,
    )
    assert fd.clip_id == "c1"
    assert fd.confidence == pytest.approx(0.95)


@pytest.mark.skipif(not _CV2, reason="cv2 not available")
def test_ensure_faces_uses_cache(tmp_path, monkeypatch):
    clip_path = str(tmp_path / "clip.mp4")
    cache_path = cache_path_for_clip(clip_path)

    cached = [
        FaceDetection(
            clip_id="c1",
            frame_idx=0,
            t_s=0.0,
            bbox=[0.0, 0.0, 10.0, 10.0],
            bbox_norm=[0.0, 0.0, 1.0, 1.0],
            embedding=[0.1] * 512,
            confidence=0.9,
            face_area_ratio=0.1,
        )
    ]
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump([identity_mod._detection_to_dict(fd) for fd in cached], f)

    monkeypatch.setattr(identity_mod, "extract_faces_from_clip", lambda *a, **kw: [])
    result = ensure_faces(clip_path, "c1")
    assert len(result) == 1
    assert result[0].clip_id == "c1"


@pytest.mark.skipif(not _CV2, reason="cv2 not available")
def test_ensure_faces_extracts_when_cache_missing(tmp_path, monkeypatch):
    clip_path = str(tmp_path / "clip.mp4")

    fake = [
        FaceDetection(
            clip_id="c1",
            frame_idx=0,
            t_s=0.0,
            bbox=[0.0, 0.0, 10.0, 10.0],
            bbox_norm=[0.0, 0.0, 1.0, 1.0],
            embedding=[0.1] * 512,
            confidence=0.9,
            face_area_ratio=0.1,
        )
    ]

    def fake_extract(path, clip_id, sample_fps=2.0):
        assert path == clip_path
        assert clip_id == "c1"
        return fake

    monkeypatch.setattr(identity_mod, "extract_faces_from_clip", fake_extract)
    result = ensure_faces(clip_path, "c1")
    assert result == fake
    assert os.path.exists(cache_path_for_clip(clip_path))


def test_extract_faces_from_clip_without_insightface_returns_empty(monkeypatch):
    monkeypatch.setattr(identity_mod, "_INSIGHTFACE", False)
    result = extract_faces_from_clip("/tmp/clip.mp4", "c1")
    assert result == []


def test_extract_faces_from_clip_without_cv2_returns_empty(monkeypatch):
    monkeypatch.setattr(identity_mod, "_CV2", False)
    result = extract_faces_from_clip("/tmp/clip.mp4", "c1")
    assert result == []


class _FakeFace:
    def __init__(self, bbox, embedding, det_score):
        self.bbox = np.array(bbox, dtype=np.float32)
        self.embedding = np.array(embedding, dtype=np.float32)
        self.det_score = det_score


class _FakeFaceApp:
    def __init__(self, faces_per_frame=1):
        self.faces_per_frame = faces_per_frame
        self.calls = 0

    def get(self, frame):
        self.calls += 1
        return [
            _FakeFace(
                bbox=[10.0, 10.0, 30.0, 30.0],
                embedding=[0.1] * 512,
                det_score=0.95,
            )
            for _ in range(self.faces_per_frame)
        ]


class _FakeCapture:
    def __init__(self, total_frames=30, fps=30.0, width=64, height=64):
        self.total_frames = total_frames
        self.fps = fps
        self.width = width
        self.height = height
        self._idx = 0
        self._opened = True

    def isOpened(self):
        return self._opened

    def get(self, prop):
        mapping = {
            cv2.CAP_PROP_FPS: self.fps,
            cv2.CAP_PROP_FRAME_COUNT: self.total_frames,
            cv2.CAP_PROP_FRAME_WIDTH: self.width,
            cv2.CAP_PROP_FRAME_HEIGHT: self.height,
        }
        return mapping.get(prop, 0.0)

    def read(self):
        if self._idx >= self.total_frames:
            return False, None
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._idx += 1
        return True, frame

    def release(self):
        self._opened = False


def test_extract_faces_from_clips_without_insightface_returns_empty(monkeypatch):
    monkeypatch.setattr(identity_mod, "_INSIGHTFACE", False)
    result = extract_faces_from_clips({"c1": "/tmp/clip.mp4"})
    assert result == {"c1": []}


def test_extract_faces_from_clips_without_cv2_returns_empty(monkeypatch):
    monkeypatch.setattr(identity_mod, "_CV2", False)
    result = extract_faces_from_clips({"c1": "/tmp/clip.mp4"})
    assert result == {"c1": []}


@pytest.mark.skipif(not _CV2, reason="cv2 not available")
def test_extract_faces_from_clips_batches_frames(monkeypatch):
    fake_app = _FakeFaceApp(faces_per_frame=1)
    monkeypatch.setattr(identity_mod, "_get_face_app", lambda: fake_app)
    monkeypatch.setattr(identity_mod, "cv2", cv2)
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: _FakeCapture(total_frames=10, fps=30.0))

    results = extract_faces_from_clips(
        {"c1": "/tmp/clip.mp4"},
        sample_fps=10.0,
        max_batch_frames=2,
    )

    # 10 frames @ 30 fps sampled at 10 fps -> frames 0, 3, 6, 9
    assert len(results["c1"]) == 4
    assert {d.frame_idx for d in results["c1"]} == {0, 3, 6, 9}
    assert sorted([d.t_s for d in results["c1"]]) == [0.0, 0.1, 0.2, 0.3]
    assert fake_app.calls == 4
    for detection in results["c1"]:
        assert detection.clip_id == "c1"
        assert detection.confidence == pytest.approx(0.95)
        assert len(detection.embedding) == 512


@pytest.mark.skipif(not _CV2, reason="cv2 not available")
def test_extract_faces_from_clips_multiple_clips(monkeypatch):
    fake_app = _FakeFaceApp(faces_per_frame=1)
    monkeypatch.setattr(identity_mod, "_get_face_app", lambda: fake_app)
    monkeypatch.setattr(identity_mod, "cv2", cv2)
    monkeypatch.setattr(
        cv2,
        "VideoCapture",
        lambda path: _FakeCapture(total_frames=6, fps=30.0),
    )

    results = extract_faces_from_clips(
        {"c1": "/tmp/a.mp4", "c2": "/tmp/b.mp4"},
        sample_fps=15.0,
        max_batch_frames=4,
    )

    # 6 frames @ 30 fps sampled at 15 fps -> frames 0, 2, 4 per clip
    assert len(results["c1"]) == 3
    assert len(results["c2"]) == 3
    assert fake_app.calls == 6


@pytest.mark.skipif(not _CV2, reason="cv2 not available")
def test_ensure_faces_for_clips_uses_cache_and_extracts_missing(tmp_path, monkeypatch):
    # c1 has a valid cache, c2 does not.
    c1_path = str(tmp_path / "c1.mp4")
    c2_path = str(tmp_path / "c2.mp4")

    cached = [
        FaceDetection(
            clip_id="c1",
            frame_idx=0,
            t_s=0.0,
            bbox=[0.0, 0.0, 10.0, 10.0],
            bbox_norm=[0.0, 0.0, 1.0, 1.0],
            embedding=[0.1] * 512,
            confidence=0.9,
            face_area_ratio=0.1,
        )
    ]
    with open(cache_path_for_clip(c1_path), "w", encoding="utf-8") as f:
        json.dump([identity_mod._detection_to_dict(fd) for fd in cached], f)

    fake_app = _FakeFaceApp(faces_per_frame=1)
    monkeypatch.setattr(identity_mod, "_get_face_app", lambda: fake_app)
    monkeypatch.setattr(identity_mod, "cv2", cv2)
    monkeypatch.setattr(
        cv2,
        "VideoCapture",
        lambda path: _FakeCapture(total_frames=6, fps=30.0),
    )

    results = ensure_faces_for_clips(
        {"c1": c1_path, "c2": c2_path},
        sample_fps=15.0,
    )

    assert len(results["c1"]) == 1
    assert results["c1"][0].clip_id == "c1"
    assert len(results["c2"]) == 3  # frames 0, 2, 4
    assert fake_app.calls == 3  # only c2 was extracted
    assert os.path.exists(cache_path_for_clip(c2_path))
