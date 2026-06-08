# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
import os
import tempfile
from pathlib import Path
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
    temp_dir: str = str(Path(tempfile.gettempdir()) / "ai-video-editor")

    class Config:
        env_prefix = "AVE_"
        case_sensitive = False


settings = Settings()
