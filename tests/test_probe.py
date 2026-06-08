"""
Unit and edge tests for video probing.
Covers: metadata extraction, stream parsing, error handling, edge cases.
"""

import pytest
import os
import sys
import tempfile
import subprocess
import shutil
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ingest-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from ingest_worker.probe import probe_video


def create_test_video(path: str, duration: float = 5.0, fps: int = 30,
                      resolution: tuple = (640, 480), with_audio: bool = True):
    """Create a synthetic test video using FFmpeg."""
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    width, height = resolution
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
    ]
    if with_audio:
        cmd.extend(["-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}"])
    cmd.extend(["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", path])
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestProbeVideo:
    def test_probe_basic_video(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=5.0, fps=30, resolution=(640, 480))
            info = probe_video(path)
            assert info.duration_s > 4.0
            assert info.width == 640
            assert info.height == 480
            assert info.fps > 0
        finally:
            os.unlink(path)

    def test_probe_with_audio(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=3.0, with_audio=True)
            info = probe_video(path)
            assert info.sample_rate is not None
            assert info.channels is not None
        finally:
            os.unlink(path)


class TestProbeEdgeCases:
    def test_probe_nonexistent_file(self):
        with pytest.raises(Exception):
            probe_video("/nonexistent/file.mp4")

    def test_probe_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"")
            path = f.name
        try:
            with pytest.raises(Exception):
                probe_video(path)
        finally:
            os.unlink(path)


class TestProbeMocked:
    @pytest.mark.skipif(__import__("ingest_worker.probe", fromlist=["av"]).av is None, reason="av not installed")
    @patch("ingest_worker.probe.av.open")
    def test_probe_mocked_video_stream(self, mock_av_open):
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.type = "video"
        mock_stream.duration = 150000
        mock_stream.time_base = MagicMock()
        mock_stream.time_base.__float__ = MagicMock(return_value=1/30)
        mock_stream.width = 1920
        mock_stream.height = 1080
        mock_stream.average_rate = 30.0
        mock_stream.frames = 150
        mock_stream.pix_fmt = "yuv420p"
        mock_stream.codec = MagicMock()
        mock_stream.codec.name = "h264"
        mock_container.streams = [mock_stream]
        mock_container.duration = 5000000
        mock_container.format = MagicMock()
        mock_container.format.name = "mp4"
        mock_av_open.return_value = mock_container

        info = probe_video("fake.mp4")
        video_stream = [s for s in info["streams"] if s["type"] == "video"][0]
        assert video_stream["width"] == 1920
        assert video_stream["height"] == 1080
        assert video_stream["fps"] == 30.0
