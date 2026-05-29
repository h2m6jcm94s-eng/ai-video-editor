# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""AI Provider abstraction layer for swappable LLM backends."""

from shared_py.ai_providers.base import AIProvider
from shared_py.ai_providers.factory import get_ai_provider

__all__ = ["AIProvider", "get_ai_provider"]
