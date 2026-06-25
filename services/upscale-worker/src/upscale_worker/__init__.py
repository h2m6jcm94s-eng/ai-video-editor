# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
from shared_py.logging_config import configure_logging

configure_logging(service_name="upscale-worker")

from upscale_worker.realesrgan import upscale_with_realesrgan
from upscale_worker.topaz import upscale_with_topaz

__all__ = ["upscale_with_realesrgan", "upscale_with_topaz"]
