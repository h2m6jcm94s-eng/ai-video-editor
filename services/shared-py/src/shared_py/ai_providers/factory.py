"""Factory for creating AIProvider instances based on env config."""

import os
from typing import Optional

from shared_py.ai_providers.base import AIProvider


def get_ai_provider(provider_name: Optional[str] = None) -> AIProvider:
    """Get an AI provider by name. Defaults to AI_PROVIDER env var, then 'programmatic'."""
    name = (provider_name or os.environ.get("AI_PROVIDER", "programmatic")).lower().strip()

    if name == "programmatic":
        from shared_py.ai_providers.programmatic_provider import ProgrammaticProvider
        return ProgrammaticProvider()

    if name == "claude":
        try:
            from shared_py.ai_providers.claude_provider import ClaudeProvider
            return ClaudeProvider()
        except ImportError as e:
            raise ImportError(f"anthropic package not installed. Run: pip install anthropic") from e

    if name == "gemini":
        try:
            from shared_py.ai_providers.gemini_provider import GeminiProvider
            return GeminiProvider()
        except ImportError as e:
            raise ImportError(f"google-generativeai not installed. Run: pip install google-generativeai") from e

    if name == "kimi":
        try:
            from shared_py.ai_providers.kimi_provider import KimiProvider
            return KimiProvider()
        except ImportError as e:
            raise ImportError(f"openai package not installed. Run: pip install openai") from e

    if name == "groq":
        try:
            from shared_py.ai_providers.groq_provider import GroqProvider
            return GroqProvider()
        except ImportError as e:
            raise ImportError(f"openai package not installed. Run: pip install openai") from e

    if name == "openrouter":
        try:
            from shared_py.ai_providers.openrouter_provider import OpenRouterProvider
            return OpenRouterProvider()
        except ImportError as e:
            raise ImportError(f"openai package not installed. Run: pip install openai") from e

    if name == "openai":
        try:
            from shared_py.ai_providers.openai_provider import OpenAIProvider
            return OpenAIProvider()
        except ImportError as e:
            raise ImportError(f"openai package not installed. Run: pip install openai") from e

    if name == "qwen":
        try:
            from shared_py.ai_providers.qwen_provider import QwenProvider
            return QwenProvider()
        except ImportError as e:
            raise ImportError(f"openai package not installed. Run: pip install openai") from e

    raise ValueError(f"Unknown AI provider: {name}. Supported: claude, gemini, kimi, groq, openrouter, openai, qwen, programmatic")
