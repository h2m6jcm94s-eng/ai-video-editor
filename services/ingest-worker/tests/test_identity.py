# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

try:
    import cv2  # noqa: F401

    _CV2 = True
except ImportError:
    _CV2 = False

from ingest_worker import identity as identity_mod
from ingest_worker.identity import (
    FaceDetection,
    cache_path_for_clip,
    ensure_faces,
    extract_faces_from_clip,
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
