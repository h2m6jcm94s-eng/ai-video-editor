# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.

from shared_py.models import Keyframe
from render_worker.edits.camera_motion import camera_motion_filter


class TestCameraMotionFilter:
    def test_zoom_in_contains_zoompan(self):
        f = camera_motion_filter(1080, 1920, "zoom_in", intensity=0.5, duration_s=2.0)
        assert "zoompan" in f
        assert "z=" in f
        assert "x=" in f
        assert "y=" in f
        assert "s=1080x1920" in f

    def test_preset_zoom_in_uses_end_zoom(self):
        f = camera_motion_filter(1080, 1920, "zoom_in", intensity=0.5, duration_s=2.0)
        # zoom_amp = 1.0 + 0.5*0.5 = 1.25 at t=2.0
        assert "1.25" in f

    def test_explicit_keyframes_drive_zoom(self):
        kfs = [Keyframe(t_s=0.0, value=1.0), Keyframe(t_s=2.0, value=1.5)]
        f = camera_motion_filter(1080, 1920, "zoom_in", duration_s=2.0, keyframes=kfs)
        assert "1.5" in f

    def test_pan_left_has_reach_expression(self):
        f = camera_motion_filter(1080, 1920, "pan_left", intensity=0.5, duration_s=2.0)
        assert "pan" in f or "0.3" in f
