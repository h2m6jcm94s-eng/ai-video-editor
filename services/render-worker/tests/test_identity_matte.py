# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import CutList, CutListGlobals, Slot
from render_worker.identity_matte import build_identity_masks


@dataclass
class _FakeIdentity:
    id: int
    label: str
    centroid_embedding: list
    face_detections: list
    avg_confidence: float
    screen_time_s: float
    avg_face_size: float


def _make_cutlist(clip_ids: list) -> CutList:
    return CutList(
        globals=CutListGlobals(
            total_duration_s=10.0,
            tempo_bpm=120.0,
            aspect_ratio="9:16",
        ),
        slots=[
            Slot(
                index=i,
                start_s=float(i),
                duration_s=1.0,
                beat_index=i,
                section="verse",
                target_shot_type="wide",
                subject_hint="person",
                motion_hint="static",
                energy_level=0.5,
                selected_clip_id=clip_id,
            )
            for i, clip_id in enumerate(clip_ids)
        ],
    )


@dataclass
class _FakeFaceDetection:
    clip_id: str
    frame_idx: int = 0
    t_s: float = 0.0
    bbox: list = None
    bbox_norm: list = None
    embedding: list = None
    confidence: float = 0.9
    face_area_ratio: float = 0.05

    def __post_init__(self):
        if self.bbox is None:
            self.bbox = [10.0, 10.0, 20.0, 20.0]
        if self.bbox_norm is None:
            self.bbox_norm = [0.1, 0.1, 0.2, 0.2]
        if self.embedding is None:
            self.embedding = [1.0] * 128


def test_matte_skipped_when_identity_absent(tmp_path, monkeypatch):
    cutlist = _make_cutlist(["clip-a", "clip-b"])
    clip_paths = {"clip-a": str(tmp_path / "a.mp4"), "clip-b": str(tmp_path / "b.mp4")}

    fake_identity = _FakeIdentity(
        id=0,
        label="identity_0",
        centroid_embedding=[1.0] * 128,
        face_detections=[_FakeFaceDetection(clip_id="clip-a")],
        avg_confidence=0.9,
        screen_time_s=5.0,
        avg_face_size=0.05,
    )

    monkeypatch.setattr(
        "render_worker.identity_matte.select_protagonists",
        lambda *a, **kw: ([fake_identity], [0]),
    )
    monkeypatch.setattr(
        "render_worker.identity_matte.ensure_faces",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "render_worker.identity_matte.generate_subject_mask_for_identity",
        lambda *a, **kw: {"available": True, "skipped": False, "output_path": str(tmp_path / "mask.mp4")},
    )

    mask_paths, slot_info = build_identity_masks(cutlist, clip_paths, str(tmp_path))

    assert "clip-a" in mask_paths
    assert "clip-b" not in mask_paths
    assert slot_info[0] == [0]
    assert slot_info[1] == []
