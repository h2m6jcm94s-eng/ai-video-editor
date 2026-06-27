# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import os
import tempfile

import numpy as np
import cv2
import pytest

from reason_worker.anticipation import (
    find_motion_peaks_in_window,
    compute_anticipation_offset,
    precompute_clip_motion_curve,
)


def _write_synthetic_video_with_bump(path: str, fps: float = 8.0):
    """Write a video with low motion then a strong motion bump in the middle."""
    width, height = 256, 144
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height), isColor=True)
    if not writer.isOpened():
        pytest.skip("VideoWriter unavailable for synthetic clip")

    n_frames = 48
    x, y = 20, height // 2 - 16
    for i in range(n_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Still for first third, fast motion in middle, still at end.
        dx = 0
        if 16 <= i < 32:
            dx = 5
        x = max(0, min(width - 32, x + dx))
        cv2.rectangle(frame, (x, y), (x + 32, y + 32), (200, 200, 200), -1)
        writer.write(frame)
    writer.release()


def test_anticipation_shifts_cut_before_peak():
    # Motion curve: low, then a peak, then low.
    fps = 8.0
    curve = np.concatenate([
        np.full(10, 0.05),
        np.linspace(0.05, 1.0, 8),
        np.linspace(1.0, 0.05, 8),
        np.full(10, 0.05),
    ]).astype(np.float32)

    window_start_s = 0.0
    window_duration_s = len(curve) / fps
    offset = compute_anticipation_offset(
        window_start_s, window_duration_s, curve, fps, target_offset_ms=333
    )
    # Peak is around frame 14 (0.05 -> 1.0 -> 0.05). At 8 fps, peak time ~14/8 = 1.75s.
    # Desired start = 1.75 - 0.333 = 1.417s. Offset = 1.417 - 0 = 1.417s (positive,
    # moving the start forward to just before the peak).
    assert 1.0 < offset < 2.0


def test_precompute_motion_curve_cached():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bump.avi")
        _write_synthetic_video_with_bump(path, fps=8.0)

        cache_path = f"{path}.motion.npz"
        assert not os.path.exists(cache_path)

        curve1 = precompute_clip_motion_curve(path, fps_sample=8.0)
        assert os.path.exists(cache_path)
        assert len(curve1) > 0

        curve2 = precompute_clip_motion_curve(path, fps_sample=8.0)
        np.testing.assert_array_equal(curve1, curve2)


def test_find_motion_peaks_finds_dominant_peak():
    fps = 8.0
    curve = np.zeros(40, dtype=np.float32)
    curve[10:20] = np.linspace(0, 1, 10)
    curve[20:30] = np.linspace(1, 0, 10)
    peaks = find_motion_peaks_in_window(curve, fps, min_prominence=0.3)
    assert len(peaks) >= 1
    assert peaks[0] == 19
