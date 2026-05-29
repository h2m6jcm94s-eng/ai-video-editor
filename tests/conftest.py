"""Pytest configuration and shared fixtures."""

import shutil
import pytest


# Auto-skip tests marked with @pytest.mark.ffmpeg when ffmpeg is not available
def pytest_runtest_setup(item):
    if item.get_closest_marker("ffmpeg"):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available on this system")
