# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import os
import tempfile

import numpy as np
import cv2
import pytest

from reason_worker.momentum import compute_mean_flow_vector, momentum_coherence


def _write_synthetic_video(path: str, n_frames: int = 30, fps: float = 24.0, motion=(2, 0)):
    """Write a tiny video with a moving grey rectangle on a black background."""
    width, height = 256, 144
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height), isColor=True)
    if not writer.isOpened():
        pytest.skip("VideoWriter unavailable for synthetic clip")

    x, y = 20, height // 2 - 16
    dx, dy = motion
    for _ in range(n_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        x = max(0, min(width - 32, x + dx))
        y = max(0, min(height - 32, y + dy))
        cv2.rectangle(frame, (x, y), (x + 32, y + 32), (200, 200, 200), -1)
        writer.write(frame)
    writer.release()


@pytest.fixture
def synthetic_clip_right():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "motion_right.avi")
        _write_synthetic_video(path, motion=(2, 0))
        yield path


@pytest.fixture
def synthetic_clip_left():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "motion_left.avi")
        _write_synthetic_video(path, motion=(-2, 0))
        yield path


@pytest.fixture
def synthetic_clip_still():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "motion_still.avi")
        _write_synthetic_video(path, motion=(0, 0))
        yield path


def test_momentum_aligned_motion_scores_high(synthetic_clip_right):
    v = compute_mean_flow_vector(synthetic_clip_right, start_s=0.0, n_frames=8)
    assert v[0] > 0.1, f"expected rightward motion, got {v}"
    score = momentum_coherence(v, v)
    assert score > 0.99


def test_momentum_opposite_motion_scores_low(synthetic_clip_right, synthetic_clip_left):
    v_right = compute_mean_flow_vector(synthetic_clip_right, start_s=0.0, n_frames=8)
    v_left = compute_mean_flow_vector(synthetic_clip_left, start_s=0.0, n_frames=8)
    score = momentum_coherence(v_right, v_left)
    assert score < 0.05, f"expected low coherence for opposite motion, got {score}"


def test_momentum_still_is_neutral(synthetic_clip_still):
    v_still = compute_mean_flow_vector(synthetic_clip_still, start_s=0.0, n_frames=8)
    assert abs(v_still[0]) < 0.1
    assert abs(v_still[1]) < 0.1
    score = momentum_coherence(v_still, v_still)
    assert 0.49 <= score <= 0.51
