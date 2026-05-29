"""AI Provider abstraction layer for swappable LLM backends."""

from shared_py.ai_providers.base import AIProvider
from shared_py.ai_providers.factory import get_ai_provider

__all__ = ["AIProvider", "get_ai_provider"]
