"""
Unit and edge tests for Settings configuration.
Covers: env var loading, defaults, prefix behavior, missing values, type coercion.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from shared_py.config import Settings


class TestSettingsDefaults:
    """Test default values when no env vars are set."""

    def test_default_redis_url(self):
        s = Settings()
        assert s.redis_url == "redis://localhost:6379"

    def test_default_temporal_host(self):
        s = Settings()
        assert s.temporal_host == "localhost:7233"

    def test_default_bucket_name(self):
        s = Settings()
        assert s.r2_bucket_name == "ai-video-editor"

    def test_default_max_workers(self):
        s = Settings()
        assert s.max_workers == 4

    def test_default_gpu_device(self):
        s = Settings()
        assert s.gpu_device == "cpu"

    def test_default_temp_dir(self):
        import tempfile
        from pathlib import Path
        s = Settings()
        assert s.temp_dir == str(Path(tempfile.gettempdir()) / "ai-video-editor")

    def test_all_api_keys_empty_by_default(self):
        s = Settings()
        assert s.anthropic_api_key == ""
        assert s.google_api_key == ""
        assert s.twelve_labs_api_key == ""


class TestSettingsEnvVars:
    """Test env var loading with AVE_ prefix."""

    def test_redis_url_from_env(self, monkeypatch):
        monkeypatch.setenv("AVE_REDIS_URL", "redis://production:6380")
        s = Settings()
        assert s.redis_url == "redis://production:6380"

    def test_r2_credentials_from_env(self, monkeypatch):
        monkeypatch.setenv("AVE_R2_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE")
        monkeypatch.setenv("AVE_R2_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
        monkeypatch.setenv("AVE_R2_BUCKET_NAME", "my-bucket")
        s = Settings()
        assert s.r2_access_key_id == "AKIAIOSFODNN7EXAMPLE"
        assert s.r2_secret_access_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert s.r2_bucket_name == "my-bucket"

    def test_api_keys_from_env(self, monkeypatch):
        monkeypatch.setenv("AVE_ANTHROPIC_API_KEY", "sk-ant-test123")
        monkeypatch.setenv("AVE_GOOGLE_API_KEY", "gemini-test456")
        monkeypatch.setenv("AVE_TWELVE_LABS_API_KEY", "tl-test789")
        s = Settings()
        assert s.anthropic_api_key == "sk-ant-test123"
        assert s.google_api_key == "gemini-test456"
        assert s.twelve_labs_api_key == "tl-test789"

    def test_max_workers_from_env(self, monkeypatch):
        monkeypatch.setenv("AVE_MAX_WORKERS", "8")
        s = Settings()
        assert s.max_workers == 8

    def test_gpu_device_from_env(self, monkeypatch):
        monkeypatch.setenv("AVE_GPU_DEVICE", "cuda:1")
        s = Settings()
        assert s.gpu_device == "cuda:1"

    def test_temp_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("AVE_TEMP_DIR", "/custom/tmp")
        s = Settings()
        assert s.temp_dir == "/custom/tmp"


class TestSettingsEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_string_env_var(self, monkeypatch):
        """Empty string should override default."""
        monkeypatch.setenv("AVE_REDIS_URL", "")
        s = Settings()
        assert s.redis_url == ""

    def test_whitespace_in_env_var(self, monkeypatch):
        """Whitespace should be preserved."""
        monkeypatch.setenv("AVE_R2_ENDPOINT", "  https://example.com  ")
        s = Settings()
        assert s.r2_endpoint == "  https://example.com  "

    def test_special_chars_in_api_key(self, monkeypatch):
        """API keys with special characters."""
        key = "sk-test/with+special=chars&more"
        monkeypatch.setenv("AVE_ANTHROPIC_API_KEY", key)
        s = Settings()
        assert s.anthropic_api_key == key

    def test_very_long_api_key(self, monkeypatch):
        """Very long API key."""
        key = "sk-" + "a" * 4096
        monkeypatch.setenv("AVE_ANTHROPIC_API_KEY", key)
        s = Settings()
        assert s.anthropic_api_key == key

    def test_negative_max_workers(self, monkeypatch):
        """Negative max_workers is allowed at model level."""
        monkeypatch.setenv("AVE_MAX_WORKERS", "-1")
        s = Settings()
        assert s.max_workers == -1

    def test_zero_max_workers(self, monkeypatch):
        """Zero max_workers."""
        monkeypatch.setenv("AVE_MAX_WORKERS", "0")
        s = Settings()
        assert s.max_workers == 0

    def test_non_numeric_max_workers(self, monkeypatch):
        """Non-numeric value should raise validation error."""
        monkeypatch.setenv("AVE_MAX_WORKERS", "invalid")
        with pytest.raises(Exception):
            Settings()

    def test_case_insensitive_env_vars(self, monkeypatch):
        """Test case-insensitive matching (Config.case_sensitive=False)."""
        monkeypatch.setenv("ave_redis_url", "redis://lowercase:6379")
        s = Settings()
        # Pydantic v2 case_sensitive=False means lowercase env vars are checked too
        assert s.redis_url == "redis://lowercase:6379"

    def test_url_with_auth(self, monkeypatch):
        """Redis URL with authentication."""
        monkeypatch.setenv("AVE_REDIS_URL", "redis://user:pass@localhost:6379/0")
        s = Settings()
        assert s.redis_url == "redis://user:pass@localhost:6379/0"

    def test_unix_socket_redis(self, monkeypatch):
        """Unix socket Redis URL."""
        monkeypatch.setenv("AVE_REDIS_URL", "unix:///var/run/redis/redis.sock")
        s = Settings()
        assert s.redis_url == "unix:///var/run/redis/redis.sock"

    def test_settings_singleton(self):
        """Verify settings module exposes a usable singleton (lazy proxy over Settings)."""
        from shared_py.config import settings, get_settings
        # `settings` is a _LazySettings proxy; verify it resolves to a Settings instance
        # and that attribute access goes through to the underlying Settings object.
        assert isinstance(get_settings(), Settings)
        assert settings.redis_url == get_settings().redis_url

    def test_settings_reinstantiation(self):
        """Fresh Settings instance picks up current env."""
        s1 = Settings()
        s2 = Settings()
        assert s1.redis_url == s2.redis_url
