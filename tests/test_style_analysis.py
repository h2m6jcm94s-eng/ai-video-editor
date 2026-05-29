"""
Unit, integration, and edge tests for style analysis workers.
Covers: LUT extraction, text overlay extraction (OCR mocked), camera motion analysis,
transition classification, and edge cases (no frames, no text, static video).
"""

import pytest
import os
import sys
import tempfile
import subprocess
import shutil
import numpy as np
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "style-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from style_worker.lut_extract import sample_frames, extract_lut_from_reference
from style_worker.text_extract import compute_iou, extract_text_overlays
from style_worker.camera_motion import analyze_camera_motion
from style_worker.transition_type import classify_transitions
from shared_py.models import ShotBoundary


def create_test_video(path: str, duration: float = 5.0, fps: int = 30,
                      resolution: tuple = (640, 480)):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    width, height = resolution
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
            "-pix_fmt", "yuv420p",
            path,
        ],
        check=True, capture_output=True,
    )
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestSampleFrames:
    def test_samples_from_video(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=5.0)
            frames = sample_frames(path, n_samples=10)
            assert isinstance(frames, list)
            assert len(frames) > 0
            assert all(isinstance(f, np.ndarray) for f in frames)
        finally:
            os.unlink(path)

    def test_nonexistent_video(self):
        with pytest.raises(Exception):
            sample_frames("/nonexistent/video.mp4", n_samples=10)


class TestComputeIoU:
    def test_identical_boxes(self):
        bbox = [[0, 0], [10, 0], [10, 10], [0, 10]]
        assert compute_iou(bbox, bbox) == 1.0

    def test_no_overlap(self):
        bbox1 = [[0, 0], [10, 0], [10, 10], [0, 10]]
        bbox2 = [[20, 20], [30, 20], [30, 30], [20, 30]]
        assert compute_iou(bbox1, bbox2) == 0.0

    def test_partial_overlap(self):
        bbox1 = [[0, 0], [10, 0], [10, 10], [0, 10]]
        bbox2 = [[5, 5], [15, 5], [15, 15], [5, 15]]
        iou = compute_iou(bbox1, bbox2)
        assert 0.0 < iou < 1.0


class TestExtractTextOverlays:
    @patch("style_worker.text_extract.PaddleOCR")
    def test_no_text_detected(self, MockOCR):
        mock_instance = MagicMock()
        mock_instance.ocr.return_value = [None]
        MockOCR.return_value = mock_instance
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=2.0)
            overlays = extract_text_overlays(path, fps_sample=1.0)
            assert overlays == []
        finally:
            os.unlink(path)

    def test_paddleocr_not_installed(self):
        import style_worker.text_extract as te
        original = te.PaddleOCR
        te.PaddleOCR = None
        try:
            overlays = extract_text_overlays("fake_path.mp4")
            assert overlays == []
        finally:
            te.PaddleOCR = original


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestCameraMotion:
    def test_static_video(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=3.0)
            shots = [ShotBoundary(start_frame=0, end_frame=90, start_s=0.0, end_s=3.0)]
            motions = analyze_camera_motion(path, shots)
            assert len(motions) == 1
            assert motions[0] in ["static", "handheld", "gimbal"]
        finally:
            os.unlink(path)

    def test_multiple_shots(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=6.0)
            shots = [
                ShotBoundary(start_frame=0, end_frame=90, start_s=0.0, end_s=3.0),
                ShotBoundary(start_frame=90, end_frame=180, start_s=3.0, end_s=6.0),
            ]
            motions = analyze_camera_motion(path, shots)
            assert len(motions) == 2
        finally:
            os.unlink(path)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestClassifyTransitions:
    def test_hard_cuts(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=3.0)
            boundaries = [
                ShotBoundary(start_frame=0, end_frame=45, start_s=0.0, end_s=1.5, is_gradual=False),
                ShotBoundary(start_frame=45, end_frame=90, start_s=1.5, end_s=3.0, is_gradual=False),
            ]
            result = classify_transitions(path, boundaries)
            for b in result:
                assert b.transition_in == "hard_cut"
        finally:
            os.unlink(path)

    def test_empty_boundaries(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=2.0)
            result = classify_transitions(path, [])
            assert result == []
        finally:
            os.unlink(path)
