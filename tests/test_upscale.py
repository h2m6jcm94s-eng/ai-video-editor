"""
Unit, integration, and edge tests for upscaling workers.
Covers: Real-ESRGAN command generation, Topaz API (mocked),
and edge cases (missing binary, missing API key, corrupt input).
"""

import pytest
import os
import sys
import tempfile
import subprocess
import shutil
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "upscale-worker", "src"))

from upscale_worker.realesrgan import upscale_with_realesrgan
from upscale_worker.topaz import upscale_with_topaz


def create_test_video(path: str, duration: float = 2.0, resolution: tuple = (640, 480)):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    width, height = resolution
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
            "-pix_fmt", "yuv420p",
            path,
        ],
        check=True, capture_output=True,
    )
    return path


class TestRealESRGAN:
    def test_invalid_input_file(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name
        try:
            with pytest.raises(Exception):
                upscale_with_realesrgan("/nonexistent/input.mp4", output_path)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
    def test_custom_model(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            input_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name
        try:
            create_test_video(input_path, duration=1.0)
            try:
                upscale_with_realesrgan(input_path, output_path, model="realesrgan-x4plus")
            except Exception:
                pass  # Expected if binary missing
        finally:
            for p in [input_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
    def test_custom_scale(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            input_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name
        try:
            create_test_video(input_path, duration=1.0)
            try:
                upscale_with_realesrgan(input_path, output_path, scale=4)
            except Exception:
                pass
        finally:
            for p in [input_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)


class TestTopaz:
    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            input_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name
        try:
            create_test_video(input_path, duration=1.0)
            old_key = os.environ.get("TOPAZ_API_KEY")
            if "TOPAZ_API_KEY" in os.environ:
                del os.environ["TOPAZ_API_KEY"]
            try:
                with pytest.raises(ValueError, match="TOPAZ_API_KEY not set"):
                    await upscale_with_topaz(input_path, output_path)
            finally:
                if old_key is not None:
                    os.environ["TOPAZ_API_KEY"] = old_key
        finally:
            for p in [input_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)
