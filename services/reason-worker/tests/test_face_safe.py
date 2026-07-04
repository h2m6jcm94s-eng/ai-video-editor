# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import Slot
from reason_worker.face_safe import (
    choose_text_z_layer,
    face_region_in_window,
    safe_zoom_center,
)


def _make_slot(tmp_path, face_data, mask_asset_id="mask", selected_clip_id="clip"):
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_text("dummy")
    if face_data is not None:
        (tmp_path / "clip.mp4.faces.json").write_text(json.dumps(face_data))
    return Slot(
        index=0,
        start_s=1.0,
        duration_s=2.0,
        beat_index=0,
        section="verse",
        target_shot_type="close_up",
        subject_hint="test",
        motion_hint="static",
        energy_level=0.5,
        selected_clip_id=selected_clip_id,
        mask_asset_id=mask_asset_id,
        mask_enabled=True,
        source_window_start_s=0.0,
    )


def test_choose_text_z_layer_behind_subject_with_face(tmp_path):
    face_data = [{"t_s": 1.5, "bbox_norm": [0.3, 0.2, 0.7, 0.8], "face_area_ratio": 0.05}]
    slot = _make_slot(tmp_path, face_data)
    assert choose_text_z_layer(slot, {"clip": str(tmp_path / "clip.mp4")}) == "behind_subject"


def test_choose_text_z_layer_on_top_without_mask(tmp_path):
    face_data = [{"t_s": 1.5, "bbox_norm": [0.3, 0.2, 0.7, 0.8], "face_area_ratio": 0.05}]
    slot = _make_slot(tmp_path, face_data)
    slot.mask_asset_id = None
    assert choose_text_z_layer(slot, {"clip": str(tmp_path / "clip.mp4")}) == "on_top"


def test_choose_text_z_layer_on_top_when_no_face_cache(tmp_path):
    slot = _make_slot(tmp_path, None)
    assert choose_text_z_layer(slot, {"clip": str(tmp_path / "clip.mp4")}) == "on_top"


def test_face_region_aggregates_area_and_center(tmp_path):
    face_data = [
        {"t_s": 0.5, "bbox_norm": [0.1, 0.1, 0.3, 0.3]},
        {"t_s": 1.5, "bbox_norm": [0.4, 0.4, 0.6, 0.6]},
    ]
    (tmp_path / "clip.mp4.faces.json").write_text(json.dumps(face_data))
    region = face_region_in_window(str(tmp_path / "clip.mp4"), 0.0, 2.0)
    assert region["count"] == 2
    assert region["center_x"] == pytest.approx(0.35)
    assert region["center_y"] == pytest.approx(0.35)


def test_safe_zoom_center_pulls_toward_face():
    region = {"center_x": 0.2, "center_y": 0.8}
    cx, cy = safe_zoom_center(region)
    assert cx < 0.5
    assert cy > 0.5
