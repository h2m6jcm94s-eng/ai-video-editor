# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Storage
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "ai-video-editor"

    # AI APIs
    anthropic_api_key: str = ""
    google_api_key: str = ""
    twelve_labs_api_key: str = ""

    # Infrastructure
    redis_url: str = "redis://localhost:6379"
    temporal_host: str = "localhost:7233"
    modal_token_id: str = ""
    modal_token_secret: str = ""

    # Worker settings
    max_workers: int = 4
    gpu_device: str = os.environ.get("GPU_DEVICE", "cpu")
    temp_dir: str = Field(default_factory=lambda: str(Path(tempfile.gettempdir()) / "ai-video-editor"))

    # API callback
    api_base: str = os.environ.get("API_BASE", "http://localhost:4000/api")
    api_token: str = os.environ.get("API_TOKEN", "")

    class Config:
        env_prefix = "AVE_"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


class _LazySettings:
    """Lazy proxy so callers can keep using `settings.api_base` without triggering
    instantiation during workflow module import."""

    def __getattr__(self, name: str):
        return getattr(get_settings(), name)


settings = _LazySettings()
