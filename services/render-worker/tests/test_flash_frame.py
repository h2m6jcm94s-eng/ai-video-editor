# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
from render_worker.edits.flash_frame import flash_frame_filter


def test_flash_frame_filter_draws_white_box():
    f = flash_frame_filter(start_s=1.0, duration_s=1 / 30.0, fps=30.0)
    assert "drawbox" in f
    assert "color=white" in f
    assert "between(t\\,1.0000\\,1.0333)" in f


def test_flash_frame_filter_defaults_to_one_frame():
    f = flash_frame_filter(start_s=0.5, duration_s=0.0, fps=24.0)
    assert "between(t\\,0.5000\\,0.5417)" in f
