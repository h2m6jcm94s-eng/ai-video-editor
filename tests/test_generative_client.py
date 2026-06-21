"""
Unit tests for the generative video client and filler prompt builder.

Live generative APIs are never called; all provider paths are exercised with
module-level mocks or deterministic fake providers.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from reason_worker.generative_client import (
    CompositeProvider,
    GeminiVeoProvider,
    GenerationResult,
    KlingProvider,
    MockProvider,
    SeedanceProvider,
    get_generative_provider,
)
from reason_worker.filler_prompt import build_filler_prompt, build_transition_prompt
from shared_py.models import Slot


class TestMockProvider:
    def test_available(self):
        provider = MockProvider()
        assert provider.available()

    def test_generate_returns_success(self):
        provider = MockProvider()
        result = provider.generate("prompt", 5.0)
        assert result.ok
        assert result.provider == "mock"

    def test_generate_honors_custom_result(self):
        failure = GenerationResult(provider="mock", status="failed", error="boom")
        provider = MockProvider(result=failure)
        assert not provider.generate("prompt", 5.0).ok


class TestGeminiVeoProvider:
    def test_unavailable_without_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        provider = GeminiVeoProvider(api_key="")
        assert not provider.available()
        result = provider.generate("prompt", 5.0)
        assert not result.ok
        assert "api key" in result.error.lower()

    def test_unavailable_when_sdk_missing(self, monkeypatch):
        """If google-genai is not importable, provider reports unavailable."""
        monkeypatch.setitem(sys.modules, "google", None)
        monkeypatch.setitem(sys.modules, "google.genai", None)
        provider = GeminiVeoProvider(api_key="fake")
        # The provider attempts import in __init__; with modules broken it stays unavailable.
        assert not provider.available()

    def test_unavailable_with_oauth_token(self):
        """OAuth/access tokens (e.g., starting with 'AQ.') are rejected with a clear error."""
        provider = GeminiVeoProvider(api_key="AQ.Ab8RN6K_...")
        assert not provider.available()
        result = provider.generate("prompt", 5.0)
        assert not result.ok
        assert "OAuth" in result.error
        assert "AIza" in result.error


class TestOpenAICompatibleProviders:
    def test_seedance_unavailable_without_key(self, monkeypatch):
        monkeypatch.delenv("SEEDANCE_API_KEY", raising=False)
        provider = SeedanceProvider()
        assert not provider.available()

    def test_kling_unavailable_without_key(self, monkeypatch):
        monkeypatch.delenv("KLING_API_KEY", raising=False)
        provider = KlingProvider()
        assert not provider.available()

    def test_seedance_happy_path(self, monkeypatch, tmp_path):
        calls = []

        class FakeResp:
            def __init__(self, json_data, status=200):
                self._json = json_data
                self.status_code = status

            def json(self):
                return self._json

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise Exception("HTTP error")

        def fake_post(url, *, json=None, headers=None, timeout=None):
            calls.append(("POST", url, json))
            return FakeResp({"id": "task-123"})

        def fake_get(url, *, headers=None, timeout=None):
            calls.append(("GET", url))
            return FakeResp({"status": "succeeded", "output": {"video_url": "https://example.com/v.mp4"}})

        provider = SeedanceProvider(api_key="sk-test", base_url="https://seedance.test/v1")
        monkeypatch.setattr(provider, "_post", lambda path, body: fake_post(f"{provider.base_url}{path}", json=body, headers=None).json())
        monkeypatch.setattr(provider, "_get", lambda path: fake_get(f"{provider.base_url}{path}", headers=None).json())

        result = provider.generate("a cat", 5.0)
        assert result.ok
        assert result.video_url == "https://example.com/v.mp4"
        assert result.provider == "seedance"

    def test_seedance_failure_state(self, monkeypatch):
        provider = SeedanceProvider(api_key="sk-test", base_url="https://seedance.test/v1")
        monkeypatch.setattr(provider, "_post", lambda path, body: {"id": "task-123"})
        monkeypatch.setattr(provider, "_get", lambda path: {"status": "failed", "error": "nsfw"})

        result = provider.generate("a cat", 5.0)
        assert not result.ok
        assert "nsfw" in result.error


class TestCompositeProvider:
    def test_uses_first_successful_provider(self):
        first = MockProvider(
            result=GenerationResult(provider="first", status="failed", error="fail")
        )
        second = MockProvider()
        composite = CompositeProvider(providers=[first, second])
        result = composite.generate("prompt", 5.0)
        assert result.ok
        assert result.provider == "mock"

    def test_fails_when_all_providers_fail(self):
        providers = [
            MockProvider(result=GenerationResult(provider=f"p{i}", status="failed", error="x"))
            for i in range(3)
        ]
        composite = CompositeProvider(providers=providers)
        result = composite.generate("prompt", 5.0)
        assert not result.ok
        assert "x" in result.error

    def test_available_if_any_provider_available(self):
        composite = CompositeProvider(providers=[GeminiVeoProvider(api_key=""), MockProvider()])
        assert composite.available()

    def test_default_factory_prefers_gemini_then_seedance_then_kling(self, monkeypatch):
        monkeypatch.setenv("GENERATIVE_PROVIDER_ORDER", "seedance,kling,mock")
        provider = get_generative_provider()
        assert provider.name() == "composite"
        names = [p.name() for p in provider.providers]
        assert names == ["seedance", "kling", "mock"]


class TestBuildFillerPrompt:
    def test_includes_shot_and_motion(self):
        slot = Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="intro",
            target_shot_type="close_up",
            subject_hint="a pianist's hands",
            motion_hint="slow_push",
            energy_level=0.8,
        )
        prompt = build_filler_prompt(slot)
        assert "close-up" in prompt.lower()
        assert "pianist" in prompt.lower()
        assert "slow gentle push in" in prompt.lower()
        assert "high energy" in prompt.lower()

    def test_includes_style_analysis(self):
        slot = Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="intro",
            target_shot_type="wide",
            subject_hint="forest",
            motion_hint="static",
            energy_level=0.2,
        )
        style = {"color_palette": "teal and orange", "contrast_level": 0.7, "saturation_level": 0.9}
        prompt = build_filler_prompt(slot, style)
        assert "teal and orange" in prompt.lower()
        assert "70% contrast" in prompt
        assert "90% saturation" in prompt


class TestBuildTransitionPrompt:
    def test_bridges_two_slots(self):
        from_slot = Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="intro",
            target_shot_type="wide",
            subject_hint="forest trail",
            motion_hint="static",
            energy_level=0.5,
        )
        to_slot = Slot(
            index=1,
            start_s=2.0,
            duration_s=2.0,
            beat_index=1,
            section="drop",
            target_shot_type="close_up",
            subject_hint="city rooftop",
            motion_hint="gimbal",
            energy_level=0.9,
        )
        prompt = build_transition_prompt(from_slot, to_slot)
        assert "forest trail" in prompt.lower()
        assert "city rooftop" in prompt.lower()
