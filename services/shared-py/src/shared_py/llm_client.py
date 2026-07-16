# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Unified LLM client with local Ollama backend and Anthropic cloud fallback.

Designed for small, latency-tolerant reasoning tasks across the video editor.
Responses are cached on disk by content hash so repeated prompts are free.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx

from shared_py.config import settings
from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("shared_py.llm_client")


class LLMTask(str, Enum):
    """Reasoning tasks routed through the unified LLM client."""

    ICONIC_QUOTE_SCORE = "iconic_quote_score"
    EDIT_INTENT_CLASSIFY = "edit_intent_classify"
    REFERENCE_INTENT = "reference_intent"
    BRAND_IP_CHECK = "brand_ip_check"
    TOPIC_STRUCTURE = "topic_structure"
    PEGASUS_FALLBACK = "pegasus_fallback"
    NARRATIVE_MODE_TIEBREAK = "narrative_mode_tiebreak"
    PROMPT_EDIT_PATCH = "prompt_edit_patch"
    OBJECT_EDIT_CLARIFY = "object_edit_clarify"
    KINETIC_TEXT_COMPOSE = "kinetic_text_compose"
    NARRATIVE_SECTION_LABEL = "narrative_section_label"


def _default_local_model(task: LLMTask) -> str:  # noqa: ARG001
    """Return the local Ollama model for a task.

    Both small and large-context tasks currently use ``gemma4:12b`` because the
    deployment only has one local model available.
    """
    return "gemma4:12b"


def _default_cloud_model(task: LLMTask) -> str:  # noqa: ARG001
    """Return the cloud Anthropic model for a task."""
    return "claude-3-5-haiku-20241022"


def _encode_image(path: str) -> str:
    """Read an image file and return a base64-encoded JPEG data URI payload."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


class LLMClient:
    """Ollama-first LLM client with optional Anthropic fallback and disk cache.

    The client is intentionally simple: it sends a prompt, returns text (or
    parsed JSON when a schema is supplied), and caches the result. It does not
    manage conversation history because every task is a single-turn reasoning
    call.
    """

    DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
    DEFAULT_CACHE_ROOT = Path("E:/ai-video-editor-storage/llm_cache")

    def __init__(
        self,
        ollama_base_url: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        local_model: Optional[str] = None,
        cloud_model: Optional[str] = None,
        cache_root: Optional[Path] = None,
        timeout: float = 60.0,
    ):
        self.ollama_base_url = (ollama_base_url or self.DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.local_model = local_model
        self.cloud_model = cloud_model
        self.cache_root = Path(cache_root) if cache_root else self.DEFAULT_CACHE_ROOT
        self.timeout = timeout

        resolved_key = anthropic_api_key or settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._anthropic_key = resolved_key
        self._anthropic_module: Optional[Any] = None

    def _model_for_task(self, task: LLMTask) -> str:
        """Resolve the effective local model for a task."""
        return self.local_model or _default_local_model(task)

    def _cloud_model_for_task(self, task: LLMTask) -> str:
        """Resolve the effective cloud model for a task."""
        return self.cloud_model or _default_cloud_model(task)

    def _cache_path(
        self,
        task: LLMTask,
        prompt: str,
        model: str,
        images: Optional[list[str]] = None,
    ) -> Path:
        """Stable disk location for a cached response."""
        image_key = "|".join(sorted(images or []))
        payload = f"{task.value}|{prompt}|{model}|{image_key}"
        cache_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self.cache_root / task.value / f"{cache_hash}.json"

    def _load_cache(self, path: Path) -> Optional[str]:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("response")
        except Exception as e:
            logger.debug("failed to read LLM cache", path=str(path), error=str(e))
            return None

    def _save_cache(self, path: Path, task: LLMTask, prompt: str, model: str, response: str) -> None:
        # Never cache empty responses: an empty body is a failure mode (e.g.
        # thinking-model token exhaustion), and caching it poisons every
        # future call with the same prompt.
        if not response or not response.strip():
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "task": task.value,
                "model": model,
                "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "response": response,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.debug("failed to write LLM cache", path=str(path), error=str(e))

    def _ollama_generate(
        self,
        task: LLMTask,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        json_schema: Optional[dict[str, Any]],
        images: Optional[list[str]] = None,
    ) -> str:
        """Call Ollama /api/chat and return the response text.

        Gemma 4 (vision) reliably returns empty responses via ``/api/generate``;
        the chat endpoint works for both text and vision prompts. ``keep_alive``
        is set to ``-1`` so the local model stays loaded across the many small
        calls in a render.
        """
        full_prompt = prompt
        if json_schema:
            full_prompt = (
                f"{prompt}\n\n"
                f"Respond ONLY with valid JSON matching this schema:\n{json.dumps(json_schema, indent=2)}"
            )

        # Ollama's native /api/chat endpoint expects `content` as a string and
        # optional `images` as a list of base64-encoded image strings. The
        # OpenAI-compatible content-list format is not accepted here.
        encoded_images: list[str] = [_encode_image(p) for p in images] if images else []

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": full_prompt}],
            "stream": False,
            "keep_alive": -1,
            # Disable chain-of-thought "thinking": with small num_predict budgets
            # the thinking tokens consume the entire budget and content comes
            # back empty (done_reason="length").  Ignored by models without
            # thinking support.
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if encoded_images:
            payload["messages"][0]["images"] = encoded_images
        if json_schema:
            # Constrain local models to JSON output when a schema is requested.
            payload["format"] = "json"

        url = f"{self.ollama_base_url}/api/chat"
        try:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e

        message = data.get("message") or {}
        text = message.get("content", "") if isinstance(message, dict) else ""
        if not isinstance(text, str):
            text = json.dumps(text)

        # If structured output was requested, validate it immediately. On parse
        # failure retry once with an explicit reminder so Gemma-style models that
        # emit prose or markdown still return usable JSON.
        if json_schema:
            try:
                self._maybe_parse_json(text, json_schema)
                return text
            except ValueError:
                logger.warning(
                    "ollama_json_parse_failed_retrying",
                    task=task.value,
                    model=model,
                    raw=text[:500],
                )
            stricter_prompt = (
                f"{full_prompt}\n\n"
                "REMEMBER: Return ONLY raw JSON. No markdown fences. No explanation. "
                "No prose before or after."
            )
            payload["messages"][0]["content"] = stricter_prompt
            try:
                resp = httpx.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"Ollama request failed: {e}") from e
            message = data.get("message") or {}
            text = message.get("content", "") if isinstance(message, dict) else ""
            if not isinstance(text, str):
                text = json.dumps(text)

        return text

    def _anthropic_complete(
        self,
        task: LLMTask,
        prompt: str,
        max_tokens: int,
        temperature: float,
        json_schema: Optional[dict[str, Any]],
    ) -> str:
        """Call Anthropic Messages API and return the response text."""
        if not self._anthropic_key:
            raise RuntimeError("Anthropic API key not configured")

        if self._anthropic_module is None:
            try:
                import anthropic
            except ImportError as e:
                raise RuntimeError("anthropic package not installed") from e
            self._anthropic_module = anthropic

        client = self._anthropic_module.Anthropic(api_key=self._anthropic_key)
        model = self._cloud_model_for_task(task)

        # Split a leading system block if present.
        system: Optional[str] = None
        user_prompt = prompt
        if prompt.startswith("SYSTEM:"):
            parts = prompt.split("USER:", 1)
            if len(parts) == 2:
                system = parts[0].replace("SYSTEM:", "").strip()
                user_prompt = parts[1].strip()

        messages = [{"role": "user", "content": user_prompt}]

        if json_schema:
            tool_name = "emit_response"
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
                "tools": [
                    {
                        "name": tool_name,
                        "description": "Emit the final structured response",
                        "input_schema": json_schema,
                    }
                ],
                "tool_choice": {"type": "tool", "name": tool_name},
            }
            if system:
                kwargs["system"] = system

            response = client.messages.create(**kwargs)
            for block in response.content:
                if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
                    return json.dumps(block.input)
            # Fallback to text if tool_use is missing.
            return response.content[0].text if response.content else ""

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""

    def complete(
        self,
        task: LLMTask,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.0,
        json_schema: Optional[dict[str, Any]] = None,
        fallback_response: Optional[str] = None,
        images: Optional[list[str]] = None,
    ) -> str | dict[str, Any]:
        """Complete a single-turn LLM task.

        Args:
            task: The reasoning task being performed.
            prompt: The full prompt text. A leading ``SYSTEM: ... USER: ...``
                block is supported for Anthropic fallback.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            json_schema: Optional JSON schema for structured output. When set,
                the response is parsed as JSON and returned as a dict.
            fallback_response: Value returned if both backends fail and no key
                is configured. If omitted, failures raise.
            images: Optional list of image file paths for vision prompts. Only
                supported by the Ollama backend.

        Returns:
            Response text, or parsed JSON dict when ``json_schema`` is given.
        """
        model = self._model_for_task(task)
        cache_path = self._cache_path(task, prompt, model, images=images)
        cached = self._load_cache(cache_path)
        if cached is not None:
            logger.debug("LLM cache hit", task=task.value, model=model)
            return self._maybe_parse_json(cached, json_schema)

        # Try local Ollama first.
        try:
            response_text = self._ollama_generate(
                task=task,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                json_schema=json_schema,
                images=images,
            )
            self._save_cache(cache_path, task, prompt, model, response_text)
            return self._maybe_parse_json(response_text, json_schema)
        except Exception as ollama_error:
            logger.warning(
                "Ollama LLM failed, attempting Anthropic fallback",
                task=task.value,
                model=model,
                error=str(ollama_error),
            )

        # Fall back to Anthropic cloud.
        last_error: Optional[Exception] = None
        try:
            response_text = self._anthropic_complete(
                task=task,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                json_schema=json_schema,
            )
            self._save_cache(cache_path, task, prompt, model, response_text)
            return self._maybe_parse_json(response_text, json_schema)
        except Exception as anthropic_error:
            last_error = anthropic_error
            logger.warning(
                "Anthropic LLM fallback failed",
                task=task.value,
                error=str(anthropic_error),
            )

        if fallback_response is not None:
            return self._maybe_parse_json(fallback_response, json_schema)

        raise RuntimeError(
            f"LLM completion failed for {task.value} and no fallback_response was provided"
        ) from last_error

    @staticmethod
    def _maybe_parse_json(text: str, json_schema: Optional[dict[str, Any]]) -> str | dict[str, Any]:  # noqa: ARG004
        """Parse text as JSON when a schema was requested."""
        if json_schema is None:
            return text
        text = text.strip()
        if not text:
            raise ValueError("LLM returned empty response")
        # Strip markdown code fences if present.
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to extract the first JSON object with a regex as a last resort.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"LLM returned invalid JSON.\nRaw: {text[:500]}")
