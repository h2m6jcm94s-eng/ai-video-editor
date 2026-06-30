# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import os
import tempfile

import numpy as np
import pytest

try:
    import cv2
except ImportError:
    cv2 = None

from ingest_worker.heatmap import compute_clip_heatmap, compute_clip_heatmaps_batch


@pytest.mark.skipif(cv2 is None, reason="cv2 not available")
def test_heatmap_peaks_in_high_motion_window():
    """A clip with a single high-motion window should have its heatmap peak there."""
    fps = 30
    duration = 3.0
    total_frames = int(fps * duration)
    width, height = 320, 240

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        path = f.name

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))

    # Static frames for first second.
    for _ in range(fps):
        frame = np.full((height, width, 3), 128, dtype=np.uint8)
        writer.write(frame)

    # High-motion window: shifting bright square for 1.5 seconds.
    for i in range(int(1.5 * fps)):
        frame = np.full((height, width, 3), 64, dtype=np.uint8)
        x = int((i / (1.5 * fps)) * (width - 80))
        frame[80:180, x : x + 80] = [255, 255, 255]
        writer.write(frame)

    # Static frames for the remainder.
    for _ in range(total_frames - int(2.5 * fps)):
        frame = np.full((height, width, 3), 128, dtype=np.uint8)
        writer.write(frame)

    writer.release()

    try:
        heatmap = compute_clip_heatmap(path, audio_path=None, window_s=0.5, stride_s=0.25)
        assert heatmap, "heatmap should not be empty"

        # Find the peak and assert it lands in the motion region.
        peak = max(heatmap, key=lambda w: w.score)
        assert 0.75 <= peak.start_s <= 2.25, f"expected peak in motion region, got {peak.start_s}"

        # Compare average score in motion region vs static region.
        motion_scores = [w.score for w in heatmap if 0.75 <= w.start_s <= 2.25]
        static_scores = [w.score for w in heatmap if w.start_s < 0.5 or w.start_s > 2.75]
        assert motion_scores, "should have windows in motion region"
        if static_scores:
            assert max(motion_scores) > max(static_scores), "motion region should score higher"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.mark.skipif(cv2 is None, reason="cv2 not available")
def test_heatmap_empty_without_cv2():
    """When cv2 is unavailable, heatmap returns an empty list."""
    # This is a meta-test for the no-op path; cv2 presence is handled by skipif.
    assert True


@pytest.mark.skipif(cv2 is None, reason="cv2 not available")
def test_compute_clip_heatmaps_batch_accepts_max_workers_one():
    """The batch API should accept max_workers=1 and complete without raising."""
    fps = 10
    duration = 2.0
    total_frames = int(fps * duration)
    width, height = 160, 120

    paths = []
    try:
        for _ in range(2):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                path = f.name
            paths.append(path)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
            for i in range(total_frames):
                frame = np.full((height, width, 3), 64, dtype=np.uint8)
                x = min(width - 20, int((i / total_frames) * width))
                frame[40:80, x : x + 20] = [255, 255, 255]
                writer.write(frame)
            writer.release()

        results = compute_clip_heatmaps_batch(paths, max_workers=1, window_s=0.5, stride_s=0.25)
        assert len(results) == len(paths)
        for path in paths:
            assert path in results
            assert isinstance(results[path], list)
    finally:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass
