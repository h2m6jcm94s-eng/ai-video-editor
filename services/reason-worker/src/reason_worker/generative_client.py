# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Multi-provider generative video client for filler/transition clips.

Preferred provider is Gemini/Veo ("Omni").  Seedance and Kling are used as
configurable fallbacks.  The client is intentionally defensive: if a provider
is unavailable or the key is invalid, it returns a failed result and the
composite provider tries the next option.
"""

from __future__ import annotations

import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import httpx


@dataclass
class GenerationResult:
    """Outcome of a single generative video request."""

    provider: str
    status: str = "pending"  # pending, succeeded, failed
    video_url: Optional[str] = None
    local_path: Optional[str] = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "succeeded" and (self.video_url or self.local_path)


class VideoProvider(ABC):
    """Abstract generative video provider."""

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def generate(
        self, prompt: str, duration_s: float, aspect_ratio: str = "16:9"
    ) -> GenerationResult:
        ...


class GeminiVeoProvider(VideoProvider):
    """Google Veo via the google-genai SDK or direct REST fallback.

    Expects ``GEMINI_API_KEY`` (or legacy ``GOOGLE_API_KEY``) in the environment.
    Uses model ``veo-3.0-generate-preview`` when available.
    """

    DEFAULT_MODEL = "veo-3.0-generate-preview"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.model = model or os.environ.get("GEMINI_VEO_MODEL") or self.DEFAULT_MODEL
        self._client = None
        self._sdk_error: Optional[str] = None
        self._init_sdk()

    def _init_sdk(self):
        try:
            from google import genai

            if self.api_key:
                self._client = genai.Client(api_key=self.api_key)
        except Exception as exc:  # pragma: no cover - import failures
            self._sdk_error = str(exc)
            self._client = None

    def name(self) -> str:
        return "gemini_veo"

    def available(self) -> bool:
        return self._client is not None

    def generate(
        self, prompt: str, duration_s: float, aspect_ratio: str = "16:9"
    ) -> GenerationResult:
        if not self._client:
            return GenerationResult(
                provider=self.name(),
                status="failed",
                error=f"google-genai SDK not available: {self._sdk_error or 'no api key'}",
            )

        try:
            # New SDK shape for video generation.  This is a best-effort call;
            # exact arguments vary by SDK version and model availability.
            operation = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "response_modalities": ["VIDEO"],
                    "aspect_ratio": aspect_ratio,
                    "duration_seconds": str(int(max(1, duration_s))),
                },
            )
            # Some SDK versions return a polled operation; others return the
            # generated Content directly.  Try both shapes.
            candidate = operation
            if hasattr(operation, "result"):
                candidate = operation.result()
            elif hasattr(operation, "candidates"):
                candidate = operation.candidates[0]

            if candidate is None:
                return GenerationResult(
                    provider=self.name(),
                    status="failed",
                    error="empty response from Gemini/Veo",
                )

            parts = getattr(candidate, "content", candidate)
            parts = getattr(parts, "parts", parts)
            if not isinstance(parts, (list, tuple)):
                parts = [parts]

            for part in parts:
                video_data = getattr(part, "video", None) or getattr(part, "inline_data", None)
                if video_data is None:
                    continue
                data = getattr(video_data, "data", None)
                if data:
                    local_path = os.path.join(
                        os.environ.get("TEMP", "/tmp"),
                        f"ave_gen_{uuid.uuid4().hex}.mp4",
                    )
                    with open(local_path, "wb") as f:
                        f.write(data)
                    return GenerationResult(
                        provider=self.name(),
                        status="succeeded",
                        local_path=local_path,
                        metadata={"model": self.model, "aspect_ratio": aspect_ratio},
                    )

            return GenerationResult(
                provider=self.name(),
                status="failed",
                error="no video part in Gemini/Veo response",
            )
        except Exception as exc:
            return GenerationResult(
                provider=self.name(),
                status="failed",
                error=f"Gemini/Veo generation failed: {exc}",
            )


class _OpenAICompatibleVideoProvider(VideoProvider):
    """Generic OpenAI-compatible video generation provider.

    Subclasses provide env-var defaults for base URL and model name.  The
    provider submits a ``POST {base_url}/videos/generations`` request and polls
    ``GET {base_url}/videos/generations/{id}`` until completion or timeout.
    """

    POLL_INTERVAL_S = 5
    MAX_POLL_S = 600

    def __init__(
        self,
        name: str,
        api_key: Optional[str],
        base_url: Optional[str],
        model: Optional[str],
        default_model: str,
    ):
        self._name = name
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = model or default_model

    def name(self) -> str:
        return self._name

    def available(self) -> bool:
        return bool(self.api_key)

    def _post(self, path: str, json_body: dict) -> dict:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{self.base_url}{path}",
                json=json_body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    def _get(self, path: str) -> dict:
        with httpx.Client(timeout=60) as client:
            resp = client.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return resp.json()

    def generate(
        self, prompt: str, duration_s: float, aspect_ratio: str = "16:9"
    ) -> GenerationResult:
        if not self.api_key:
            return GenerationResult(
                provider=self.name(),
                status="failed",
                error="API key not configured",
            )

        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "size": self._aspect_to_size(aspect_ratio),
                "duration": int(max(1, duration_s)),
            }
            submit = self._post("/videos/generations", payload)
            task_id = submit.get("id") or submit.get("task_id")
            if not task_id:
                return GenerationResult(
                    provider=self.name(),
                    status="failed",
                    error=f"provider did not return a task id: {submit}",
                )

            deadline = time.time() + self.MAX_POLL_S
            while time.time() < deadline:
                status = self._get(f"/videos/generations/{task_id}")
                state = status.get("status", "pending").lower()
                if state in ("succeeded", "completed", "done"):
                    output = status.get("output", status)
                    if isinstance(output, list):
                        url = output[0] if output else None
                    elif isinstance(output, dict):
                        url = output.get("video_url") or output.get("url")
                    else:
                        url = output
                    if url:
                        return GenerationResult(
                            provider=self.name(),
                            status="succeeded",
                            video_url=str(url),
                            metadata={"model": self.model, "task_id": task_id},
                        )
                    return GenerationResult(
                        provider=self.name(),
                        status="failed",
                        error=f"completed response missing video URL: {status}",
                    )
                if state in ("failed", "error"):
                    return GenerationResult(
                        provider=self.name(),
                        status="failed",
                        error=f"generation failed: {status.get('error', status)}",
                    )
                time.sleep(self.POLL_INTERVAL_S)

            return GenerationResult(
                provider=self.name(),
                status="failed",
                error=f"polling timed out after {self.MAX_POLL_S}s",
            )
        except Exception as exc:
            return GenerationResult(
                provider=self.name(),
                status="failed",
                error=f"{self.name()} generation failed: {exc}",
            )

    @staticmethod
    def _aspect_to_size(aspect_ratio: str) -> str:
        mapping = {
            "16:9": "1280x720",
            "9:16": "720x1280",
            "1:1": "1024x1024",
            "4:3": "1024x768",
            "3:4": "768x1024",
        }
        return mapping.get(aspect_ratio, "1280x720")


class SeedanceProvider(_OpenAICompatibleVideoProvider):
    """Seedance via an OpenAI-compatible gateway (fal, Replicate, etc.)."""

    DEFAULT_MODEL = "seedance-2.0"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(
            name="seedance",
            api_key=api_key or os.environ.get("SEEDANCE_API_KEY"),
            base_url=base_url or os.environ.get("SEEDANCE_BASE_URL"),
            model=model or os.environ.get("SEEDANCE_MODEL"),
            default_model=self.DEFAULT_MODEL,
        )


class KlingProvider(_OpenAICompatibleVideoProvider):
    """Kling via an OpenAI-compatible gateway."""

    DEFAULT_MODEL = "kling-video-v1"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(
            name="kling",
            api_key=api_key or os.environ.get("KLING_API_KEY"),
            base_url=base_url or os.environ.get("KLING_BASE_URL"),
            model=model or os.environ.get("KLING_MODEL"),
            default_model=self.DEFAULT_MODEL,
        )


class MockProvider(VideoProvider):
    """Deterministic provider for tests and local dry-runs."""

    def __init__(self, result: Optional[GenerationResult] = None):
        self._result = result or GenerationResult(
            provider="mock", status="succeeded", video_url="https://example.com/mock.mp4"
        )

    def name(self) -> str:
        return "mock"

    def available(self) -> bool:
        return True

    def generate(
        self, prompt: str, duration_s: float, aspect_ratio: str = "16:9"
    ) -> GenerationResult:
        return GenerationResult(
            provider=self.name(),
            status=self._result.status,
            video_url=self._result.video_url,
            local_path=self._result.local_path,
            error=self._result.error,
            metadata={"prompt": prompt, "duration_s": duration_s, "aspect_ratio": aspect_ratio},
        )


class CompositeProvider(VideoProvider):
    """Try multiple providers in order until one succeeds."""

    DEFAULT_ORDER = ["gemini_veo", "seedance", "kling"]

    def __init__(
        self,
        providers: Optional[list] = None,
        order: Optional[list] = None,
    ):
        self.providers = providers or self._build_default_providers(order)

    @classmethod
    def _build_default_providers(cls, order: Optional[list]) -> list:
        order = order or [p.strip() for p in os.environ.get("GENERATIVE_PROVIDER_ORDER", "").split(",") if p.strip()] or cls.DEFAULT_ORDER
        mapping = {
            "gemini_veo": GeminiVeoProvider,
            "seedance": SeedanceProvider,
            "kling": KlingProvider,
            "mock": MockProvider,
        }
        providers = []
        for name in order:
            factory = mapping.get(name)
            if factory:
                providers.append(factory())
        return providers

    def name(self) -> str:
        return "composite"

    def available(self) -> bool:
        return any(p.available() for p in self.providers)

    def generate(
        self, prompt: str, duration_s: float, aspect_ratio: str = "16:9"
    ) -> GenerationResult:
        last_error = "no providers configured"
        for provider in self.providers:
            if not provider.available():
                continue
            result = provider.generate(prompt, duration_s, aspect_ratio)
            if result.ok:
                return result
            last_error = result.error or f"{provider.name()} failed"
        return GenerationResult(
            provider=self.name(),
            status="failed",
            error=last_error,
        )


def download_video_url(url: str, local_path: Optional[str] = None) -> str:
    """Download a remote video URL to a local path."""
    if local_path is None:
        local_path = os.path.join(
            os.environ.get("TEMP", "/tmp"),
            f"ave_gen_dl_{uuid.uuid4().hex}.mp4",
        )
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
    return local_path


def get_generative_provider(
    provider: Optional[str] = None,
    order: Optional[list] = None,
) -> VideoProvider:
    """Factory for generative video providers.

    Args:
        provider: Specific provider name (``gemini_veo``, ``seedance``, ``kling``,
            ``mock``, or ``composite``).  Defaults to ``composite``.
        order: Provider order for composite mode.
    """
    name = (provider or os.environ.get("GENERATIVE_PROVIDER", "composite")).lower()
    if name == "gemini_veo":
        return GeminiVeoProvider()
    if name == "seedance":
        return SeedanceProvider()
    if name == "kling":
        return KlingProvider()
    if name == "mock":
        return MockProvider()
    return CompositeProvider(order=order)
