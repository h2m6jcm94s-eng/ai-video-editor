# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
from unittest.mock import patch
import tempfile

import pytest

from shared_py.models import Slot, RenderConfig
from render_worker.compiler import _extract_segment


def _make_slot(**overrides) -> Slot:
    defaults = {
        "index": 0,
        "start_s": 0.0,
        "duration_s": 1.0,
        "beat_index": 0,
        "section": "verse",
        "transition_in": "hard_cut",
        "transition_out": "hard_cut",
        "target_shot_type": "wide",
        "subject_hint": "person",
        "motion_hint": "static",
        "energy_level": 0.5,
    }
    defaults.update(overrides)
    return Slot(**defaults)


def _make_config() -> RenderConfig:
    return RenderConfig(output_path="/tmp/out.mp4", width=720, height=1280, fps=30.0)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


def test_compiler_uses_anticipation_offset_in_seek(temp_dir):
    """The compiler adds anticipation_offset_s when calculating segment seek."""
    slot = _make_slot(
        source_window_start_s=5.0,
        anticipation_offset_s=-0.333,
        selected_clip_id="clip-a",
    )
    config = _make_config()

    captured_cmd = []

    def _fake_probe(path: str) -> float:
        return 10.0

    def _fake_run_ffmpeg(cmd, context, cwd=None):
        captured_cmd.append(cmd)

    with patch("render_worker.compiler._probe_duration", side_effect=_fake_probe), \
         patch("render_worker.compiler._run_ffmpeg", side_effect=_fake_run_ffmpeg):
        _extract_segment((slot, "/tmp/clip-a.mp4", 1.0, config, temp_dir, "", "full_remix", []))

    assert captured_cmd, "ffmpeg command was not captured"
    cmd = captured_cmd[0]
    ss_idx = cmd.index("-ss")
    seek_value = float(cmd[ss_idx + 1])
    # base_start 5.0 + anticipation -0.333 = 4.667
    assert abs(seek_value - 4.667) < 0.001
