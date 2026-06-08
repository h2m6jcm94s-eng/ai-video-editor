"""Pytest configuration and shared fixtures."""

import os
import shutil
import pytest


# Auto-skip tests marked with @pytest.mark.ffmpeg when ffmpeg is not available
def pytest_runtest_setup(item):
    if item.get_closest_marker("ffmpeg"):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available on this system")


def pytest_collection_modifyitems(config, items):
    """Skip tests that require external API keys when keys are not present."""
    key_markers = {
        "requires_anthropic": "ANTHROPIC_API_KEY",
        "requires_google": "GOOGLE_API_KEY",
        "requires_groq": "GROQ_API_KEY",
        "requires_openai": "OPENAI_API_KEY",
        "requires_kimi": "KIMI_API_KEY",
        "requires_qwen": "QWEN_API_KEY",
        "requires_openrouter": "OPENROUTER_API_KEY",
    }
    for item in items:
        for marker_name, env_var in key_markers.items():
            if marker_name in item.keywords and not os.environ.get(env_var):
                item.add_marker(
                    pytest.mark.skip(reason=f"{env_var} not set — skipping key-required test")
                )
