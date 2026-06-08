"""
Unit, integration, and edge tests for AI provider abstraction layer.
Covers: factory instantiation, schema consistency, prompt building, all provider
implementations, and edge cases (missing API keys, invalid provider, rate limiting).
"""

import pytest
import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from shared_py.models import BeatGrid, ShotBoundary, StyleAnalysis, BeatSegment, Overlay
from shared_py.ai_providers.factory import get_ai_provider
from shared_py.ai_providers.base import AIProvider
from reason_worker.cutlist_gen import generate_cutlist_programmatic


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

class TestProviderFactory:
    def test_returns_provider_for_valid_name(self):
        valid_names = ["programmatic", "claude", "gemini", "kimi", "groq", "openrouter", "openai", "qwen"]
        for name in valid_names:
            try:
                provider = get_ai_provider(name)
            except ImportError:
                continue  # Skip providers with missing optional deps
            except ValueError:
                continue  # Skip providers whose API key is not set in this environment
            assert provider is not None
            assert hasattr(provider, "generate_cutlist")
            assert hasattr(provider, "classify_shot")
            assert hasattr(provider, "analyze_style")

    def test_default_provider(self):
        provider = get_ai_provider()
        assert provider is not None
        assert isinstance(provider, AIProvider)

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown AI provider"):
            get_ai_provider("nonexistent_provider_xyz")

    def test_case_insensitive(self):
        try:
            provider_lower = get_ai_provider("groq")
            provider_upper = get_ai_provider("GROQ")
            assert type(provider_lower) == type(provider_upper)
        except ImportError:
            pytest.skip("openai package not installed")
        except ValueError:
            pytest.skip("GROQ_API_KEY not set")


# ──────────────────────────────────────────────────────────────────────────────
# Base class / shared behavior
# ──────────────────────────────────────────────────────────────────────────────

class TestProviderBase:
    def test_build_cutlist_context(self):
        provider = get_ai_provider("programmatic")

        beat_grid = BeatGrid(
            bpm=120.0,
            time_signature="4/4",
            segments=[
                BeatSegment(start=0, end=4, label="intro"),
                BeatSegment(start=4, end=12, label="verse"),
            ],
            beats=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            beat_positions=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            downbeats=[0, 4, 8],
        )

        shots = [
            ShotBoundary(start_s=0.0, end_s=2.0, start_frame=0, end_frame=60),
            ShotBoundary(start_s=2.0, end_s=5.0, start_frame=60, end_frame=150),
        ]

        style = {
            "color_palette": ["#FF0000", "#00FF00", "#0000FF", "#FFFFFF", "#000000"],
            "contrast_level": 1.0,
            "saturation_level": 1.0,
            "brightness_level": 1.0,
            "pacing": "fast",
            "mood": "energetic",
            "camera_motions": [],
        }

        context = provider._build_cutlist_context(beat_grid, shots, style, [0.3, 0.6], ["wide", "close_up"])
        assert isinstance(context, str)
        assert "Reference Video Analysis" in context
        assert "120" in context
        assert "intro" in context
        assert "verse" in context
        assert "energetic" in context
        assert "wide" in context
        assert "close_up" in context

    def test_build_cutlist_context_empty_inputs(self):
        provider = get_ai_provider("programmatic")
        context = provider._build_cutlist_context(
            BeatGrid(bpm=120.0, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[]),
            [],
            {"color_palette": [], "contrast_level": 1.0, "saturation_level": 1.0,
             "brightness_level": 1.0, "pacing": "medium", "mood": "neutral", "camera_motions": []},
            [],
            ["wide"],
        )
        assert isinstance(context, str)
        assert "Reference Video Analysis" in context

    def test_system_prompts_defined(self):
        provider = get_ai_provider("programmatic")
        assert hasattr(provider, "SYSTEM_PROMPT_CUTLIST")
        assert hasattr(provider, "SYSTEM_PROMPT_SHOT")
        assert hasattr(provider, "SYSTEM_PROMPT_STYLE")
        assert len(provider.SYSTEM_PROMPT_CUTLIST) > 0
        assert "expert video editor" in provider.SYSTEM_PROMPT_CUTLIST.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Programmatic provider
# ──────────────────────────────────────────────────────────────────────────────

class TestProgrammaticProvider:
    def test_generate_cutlist(self):
        provider = get_ai_provider("programmatic")
        beat_grid = BeatGrid(
            bpm=120.0,
            time_signature="4/4",
            beats=[0, 1, 2, 3, 4, 5, 6, 7, 8],
            beat_positions=[0, 1, 2, 3, 4, 5, 6, 7, 8],
            segments=[
                BeatSegment(start=0, end=4, label="intro"),
                BeatSegment(start=4, end=8, label="verse"),
            ],
            downbeats=[0, 4],
        )
        shots = [
            ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90),
            ShotBoundary(start_s=3.0, end_s=6.0, start_frame=90, end_frame=180),
        ]
        style = StyleAnalysis(
            lut_extracted=False, color_palette=["#FF0000"] * 5,
            text_overlays=[], transition_types=[],
            camera_motions=["static", "pan_right"],
            mood="energetic", pacing="fast",
        )

        result = generate_cutlist_programmatic(beat_grid, shots, [0.3, 0.7], ["wide", "close_up"])
        assert result is not None
        assert hasattr(result, "slots")
        assert len(result.slots) > 0
        assert hasattr(result, "globals")

    def test_classify_shot(self):
        provider = get_ai_provider("programmatic")
        result = provider.classify_shot(
            keyframes=[],
            schema={},
        )
        assert result is not None
        assert hasattr(result, "shot_size")

    def test_analyze_style(self):
        provider = get_ai_provider("programmatic")
        result = provider.analyze_style("fake.mp4")
        assert result is not None
        assert hasattr(result, "mood")
        assert hasattr(result, "pacing")

    def test_no_api_key_required(self):
        provider = get_ai_provider("programmatic")
        # Programmatic provider should not need any API key
        assert provider.name == "programmatic"


# ──────────────────────────────────────────────────────────────────────────────
# Groq provider (with mocked HTTP)
# ──────────────────────────────────────────────────────────────────────────────

class TestGroqProvider:
    def setup_method(self):
        try:
            get_ai_provider("groq")
            self.available = True
        except ImportError:
            self.available = False

    @patch.dict(os.environ, {"GROQ_API_KEY": "test_key"})
    def test_instantiates(self):
        if not self.available:
            pytest.skip("openai package not installed")
        provider = get_ai_provider("groq")
        assert provider is not None
        assert provider.name == "groq"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key(self):
        if not self.available:
            pytest.skip("openai package not installed")
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            get_ai_provider("groq")

    @patch.dict(os.environ, {"GROQ_API_KEY": "test_key"})
    @patch("httpx.Client")
    def test_generate_cutlist_mocked(self, MockClient):
        if not self.available:
            pytest.skip("openai package not installed")
        provider = get_ai_provider("groq")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '''{"globals": {"total_duration_s": 30, "tempo_bpm": 120, "time_signature": "4/4", "energy_curve": [0.5], "section_markers": [], "aspect_ratio": "16:9"}, "slots": [{"index": 0, "start_s": 0, "duration_s": 2, "beat_index": 0, "section": "intro", "transition_in": "hard_cut", "transition_out": "hard_cut", "target_shot_type": "wide", "subject_hint": "test", "motion_hint": "static", "energy_level": 0.5, "required_tags": [], "avoid_tags": [], "selected_clip_id": null, "ranked_clip_ids": null, "confidence": null}], "overlays": []}'''
                    }
                }
            ]
        }
        MockClient.return_value.__enter__ = MagicMock(return_value=MockClient.return_value)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        MockClient.return_value.post.return_value = mock_response

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        beat_grid = BeatGrid(
            bpm=120.0,
            time_signature="4/4",
            beats=[0, 1, 2, 3, 4],
            beat_positions=[0, 1, 2, 3, 4],
            segments=[BeatSegment(start=0, end=4, label="intro")],
            downbeats=[0],
        )
        shots = [ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90)]
        style = StyleAnalysis(
            lut_extracted=False, color_palette=[], text_overlays=[],
            transition_types=[], camera_motions=[],
            mood="energetic", pacing="fast",
        )
        result = provider.generate_cutlist(beat_grid, shots, style, [0.5], ["wide"])
        assert result is not None
        assert len(result.slots) == 1

    @patch.dict(os.environ, {"GROQ_API_KEY": "test_key"})
    @patch("httpx.Client")
    def test_rate_limit_retry(self, MockClient):
        if not self.available:
            pytest.skip("openai package not installed")
        provider = get_ai_provider("groq")
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        mock_429.headers = {"retry-after": "1"}

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "choices": [{"message": {"content": "{\"slots\": [], \"globals\": {\"total_duration_s\": 30, \"tempo_bpm\": 120, \"time_signature\": \"4/4\", \"energy_curve\": [0.5], \"section_markers\": [], \"aspect_ratio\": \"16:9\"}, \"overlays\": []}"}}]
        }

        MockClient.return_value.__enter__ = MagicMock(return_value=MockClient.return_value)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        MockClient.return_value.post.side_effect = [mock_429, mock_ok]

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        result = provider.generate_cutlist(
            BeatGrid(bpm=120, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[]),
            [],
            StyleAnalysis(lut_extracted=False, color_palette=[], text_overlays=[], transition_types=[],
                          camera_motions=[], mood="neutral", pacing="medium"),
            [],
            ["wide"],
        )
        assert result is not None


# ──────────────────────────────────────────────────────────────────────────────
# Claude provider (mocked)
# ──────────────────────────────────────────────────────────────────────────────

class TestClaudeProvider:
    def setup_method(self):
        try:
            get_ai_provider("claude")
            self.available = True
        except ImportError:
            self.available = False

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test_key"})
    def test_instantiates(self):
        if not self.available:
            pytest.skip("anthropic package not installed")
        provider = get_ai_provider("claude")
        assert provider is not None
        assert provider.name == "claude"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key(self):
        if not self.available:
            pytest.skip("anthropic package not installed")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            get_ai_provider("claude")

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("anthropic") is None,
        reason="anthropic package not installed",
    )
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test_key"})
    @patch("shared_py.ai_providers.claude_provider.anthropic.Anthropic")
    def test_generate_cutlist_mocked(self, MockAnthropic):
        provider = get_ai_provider("claude")
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='''{"globals": {"total_duration_s": 30, "tempo_bpm": 120, "time_signature": "4/4", "energy_curve": [0.5], "section_markers": [], "aspect_ratio": "16:9"}, "slots": [{"index": 0, "start_s": 0, "duration_s": 2, "beat_index": 0, "section": "intro", "transition_in": "hard_cut", "transition_out": "hard_cut", "target_shot_type": "wide", "subject_hint": "test", "motion_hint": "static", "energy_level": 0.5, "required_tags": [], "avoid_tags": [], "selected_clip_id": null, "ranked_clip_ids": null, "confidence": null}], "overlays": []}''')]
        mock_client.messages.create.return_value = mock_message
        MockAnthropic.return_value = mock_client

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        beat_grid = BeatGrid(
            bpm=120.0, time_signature="4/4",
            beats=[0, 1, 2, 3, 4],
            beat_positions=[0, 1, 2, 3, 4],
            segments=[BeatSegment(start=0, end=4, label="intro")],
            downbeats=[0],
        )
        shots = [ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90)]
        style = StyleAnalysis(
            lut_extracted=False, color_palette=[], text_overlays=[],
            transition_types=[], camera_motions=[],
            mood="energetic", pacing="fast",
        )
        result = provider.generate_cutlist(beat_grid, shots, style, [0.5], ["wide"])
        assert result is not None
        assert len(result.slots) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Gemini provider (mocked)
# ──────────────────────────────────────────────────────────────────────────────

class TestGeminiProvider:
    def setup_method(self):
        try:
            get_ai_provider("gemini")
            self.available = True
        except ImportError:
            self.available = False

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test_key"})
    def test_instantiates(self):
        if not self.available:
            pytest.skip("google-generativeai package not installed")
        provider = get_ai_provider("gemini")
        assert provider is not None
        assert provider.name == "gemini"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key(self):
        if not self.available:
            pytest.skip("google-generativeai package not installed")
        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            get_ai_provider("gemini")

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("google") is None,
        reason="google-generativeai package not installed",
    )
    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test_key"})
    @patch("shared_py.ai_providers.gemini_provider.genai.GenerativeModel")
    def test_generate_cutlist_mocked(self, MockModel):
        provider = get_ai_provider("gemini")
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '''{"globals": {"total_duration_s": 30, "tempo_bpm": 120, "time_signature": "4/4", "energy_curve": [0.5], "section_markers": [], "aspect_ratio": "16:9"}, "slots": [{"index": 0, "start_s": 0, "duration_s": 2, "beat_index": 0, "section": "intro", "transition_in": "hard_cut", "transition_out": "hard_cut", "target_shot_type": "wide", "subject_hint": "test", "motion_hint": "static", "energy_level": 0.5, "required_tags": [], "avoid_tags": [], "selected_clip_id": null, "ranked_clip_ids": null, "confidence": null}], "overlays": []}'''
        mock_model.generate_content.return_value = mock_response
        MockModel.return_value = mock_model

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        result = provider.generate_cutlist(
            BeatGrid(bpm=120, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[0]),
            [ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90)],
            StyleAnalysis(lut_extracted=False, color_palette=[], text_overlays=[], transition_types=[],
                          camera_motions=[], mood="neutral", pacing="medium"),
            [0.5],
            ["wide"],
        )
        assert result is not None
        assert len(result.slots) == 1


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI provider (mocked)
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenAIProvider:
    def setup_method(self):
        try:
            get_ai_provider("openai")
            self.available = True
        except ImportError:
            self.available = False

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"})
    def test_instantiates(self):
        if not self.available:
            pytest.skip("openai package not installed")
        provider = get_ai_provider("openai")
        assert provider is not None
        assert provider.name == "openai"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key(self):
        if not self.available:
            pytest.skip("openai package not installed")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            get_ai_provider("openai")

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("openai") is None,
        reason="openai package not installed",
    )
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"})
    @patch("shared_py.ai_providers.openai_provider.openai.OpenAI")
    def test_generate_cutlist_mocked(self, MockOpenAI):
        provider = get_ai_provider("openai")
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '''{"globals": {"total_duration_s": 30, "tempo_bpm": 120, "time_signature": "4/4", "energy_curve": [0.5], "section_markers": [], "aspect_ratio": "16:9"}, "slots": [{"index": 0, "start_s": 0, "duration_s": 2, "beat_index": 0, "section": "intro", "transition_in": "hard_cut", "transition_out": "hard_cut", "target_shot_type": "wide", "subject_hint": "test", "motion_hint": "static", "energy_level": 0.5, "required_tags": [], "avoid_tags": [], "selected_clip_id": null, "ranked_clip_ids": null, "confidence": null}], "overlays": []}'''
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion
        MockOpenAI.return_value = mock_client

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        result = provider.generate_cutlist(
            BeatGrid(bpm=120, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[0]),
            [ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90)],
            StyleAnalysis(lut_extracted=False, color_palette=[], text_overlays=[], transition_types=[],
                          camera_motions=[], mood="neutral", pacing="medium"),
            [0.5],
            ["wide"],
        )
        assert result is not None
        assert len(result.slots) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Qwen provider (mocked)
# ──────────────────────────────────────────────────────────────────────────────

class TestQwenProvider:
    def setup_method(self):
        try:
            get_ai_provider("qwen")
            self.available = True
        except ImportError:
            self.available = False

    @patch.dict(os.environ, {"QWEN_API_KEY": "test_key"})
    def test_instantiates(self):
        if not self.available:
            pytest.skip("openai package not installed")
        provider = get_ai_provider("qwen")
        assert provider is not None
        assert provider.name == "qwen"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key(self):
        if not self.available:
            pytest.skip("openai package not installed")
        with pytest.raises(ValueError, match="QWEN_API_KEY"):
            get_ai_provider("qwen")

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("openai") is None,
        reason="openai package not installed",
    )
    @patch.dict(os.environ, {"QWEN_API_KEY": "test_key"})
    @patch("shared_py.ai_providers.qwen_provider.openai.OpenAI")
    def test_generate_cutlist_mocked(self, MockOpenAI):
        provider = get_ai_provider("qwen")
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '''{"globals": {"total_duration_s": 30, "tempo_bpm": 120, "time_signature": "4/4", "energy_curve": [0.5], "section_markers": [], "aspect_ratio": "16:9"}, "slots": [{"index": 0, "start_s": 0, "duration_s": 2, "beat_index": 0, "section": "intro", "transition_in": "hard_cut", "transition_out": "hard_cut", "target_shot_type": "wide", "subject_hint": "test", "motion_hint": "static", "energy_level": 0.5, "required_tags": [], "avoid_tags": [], "selected_clip_id": null, "ranked_clip_ids": null, "confidence": null}], "overlays": []}'''
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion
        MockOpenAI.return_value = mock_client

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        result = provider.generate_cutlist(
            BeatGrid(bpm=120, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[0]),
            [ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90)],
            StyleAnalysis(lut_extracted=False, color_palette=[], text_overlays=[], transition_types=[],
                          camera_motions=[], mood="neutral", pacing="medium"),
            [0.5],
            ["wide"],
        )
        assert result is not None
        assert len(result.slots) == 1

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("openai") is None,
        reason="openai package not installed",
    )
    @patch.dict(os.environ, {"QWEN_API_KEY": "test_key"})
    @patch("shared_py.ai_providers.qwen_provider.openai.OpenAI")
    def test_generate_cutlist_markdown_stripped(self, MockOpenAI):
        provider = get_ai_provider("qwen")
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '```json\n{"globals": {"total_duration_s": 30, "tempo_bpm": 120, "time_signature": "4/4", "energy_curve": [0.5], "section_markers": [], "aspect_ratio": "16:9"}, "slots": [{"index": 0, "start_s": 0, "duration_s": 2, "beat_index": 0, "section": "intro", "transition_in": "hard_cut", "transition_out": "hard_cut", "target_shot_type": "wide", "subject_hint": "test", "motion_hint": "static", "energy_level": 0.5, "required_tags": [], "avoid_tags": [], "selected_clip_id": null, "ranked_clip_ids": null, "confidence": null}], "overlays": []}\n```'
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion
        MockOpenAI.return_value = mock_client

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        result = provider.generate_cutlist(
            BeatGrid(bpm=120, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[0]),
            [ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90)],
            StyleAnalysis(lut_extracted=False, color_palette=[], text_overlays=[], transition_types=[],
                          camera_motions=[], mood="neutral", pacing="medium"),
            [0.5],
            ["wide"],
        )
        assert result is not None
        assert len(result.slots) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Fallback chain
# ──────────────────────────────────────────────────────────────────────────────

class TestProviderFallbackChain:
    @patch.dict(os.environ, {"AI_PROVIDER": "kimi,qwen,programmatic"})
    def test_single_provider_chain(self):
        # When the first provider is programmatic, it returns immediately
        from reason_worker.cutlist_gen import generate_cutlist
        beat_grid = BeatGrid(
            bpm=120.0,
            time_signature="4/4",
            beats=[0, 1, 2, 3, 4, 5, 6, 7, 8],
            beat_positions=[0, 1, 2, 3, 4, 5, 6, 7, 8],
            segments=[BeatSegment(start=0, end=4, label="intro"), BeatSegment(start=4, end=8, label="verse")],
            downbeats=[0, 4],
        )
        shots = [ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90)]
        result = generate_cutlist(beat_grid, shots, {}, [0.3, 0.7], ["wide", "close_up"])
        assert result is not None
        assert len(result.slots) > 0

    @patch.dict(os.environ, {"AI_PROVIDER": "nonexistent_provider_xyz"})
    def test_invalid_provider_falls_back_to_programmatic(self):
        from reason_worker.cutlist_gen import generate_cutlist
        beat_grid = BeatGrid(
            bpm=120.0,
            time_signature="4/4",
            beats=[0, 1, 2, 3, 4, 5, 6, 7, 8],
            beat_positions=[0, 1, 2, 3, 4, 5, 6, 7, 8],
            segments=[BeatSegment(start=0, end=4, label="intro"), BeatSegment(start=4, end=8, label="verse")],
            downbeats=[0, 4],
        )
        shots = [ShotBoundary(start_s=0.0, end_s=3.0, start_frame=0, end_frame=90)]
        result = generate_cutlist(beat_grid, shots, {}, [0.3, 0.7], ["wide", "close_up"])
        assert result is not None
        assert len(result.slots) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestProviderEdgeCases:
    def setup_method(self):
        try:
            get_ai_provider("groq")
            self.available = True
        except ImportError:
            self.available = False

    @patch.dict(os.environ, {"GROQ_API_KEY": "test_key"})
    @patch("httpx.Client")
    def test_invalid_json_response(self, MockClient):
        if not self.available:
            pytest.skip("openai package not installed")
        provider = get_ai_provider("groq")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not valid json"}}]
        }
        MockClient.return_value.__enter__ = MagicMock(return_value=MockClient.return_value)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        MockClient.return_value.post.return_value = mock_response

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        result = provider.generate_cutlist(
            BeatGrid(bpm=120, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[]),
            [],
            StyleAnalysis(lut_extracted=False, color_palette=[], text_overlays=[], transition_types=[],
                          camera_motions=[], mood="neutral", pacing="medium"),
            [],
            ["wide"],
        )
        # Should fall back to programmatic
        assert result is not None

    @patch.dict(os.environ, {"GROQ_API_KEY": "test_key"})
    @patch("httpx.Client")
    def test_empty_slots_in_response(self, MockClient):
        if not self.available:
            pytest.skip("openai package not installed")
        provider = get_ai_provider("groq")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "{\"globals\": {\"total_duration_s\": 30, \"tempo_bpm\": 120, \"time_signature\": \"4/4\", \"energy_curve\": [0.5], \"section_markers\": [], \"aspect_ratio\": \"16:9\"}, \"slots\": [], \"overlays\": []}"}}]
        }
        MockClient.return_value.__enter__ = MagicMock(return_value=MockClient.return_value)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        MockClient.return_value.post.return_value = mock_response

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        result = provider.generate_cutlist(
            BeatGrid(bpm=120, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[]),
            [],
            StyleAnalysis(lut_extracted=False, color_palette=[], text_overlays=[], transition_types=[],
                          camera_motions=[], mood="neutral", pacing="medium"),
            [],
            ["wide"],
        )
        # Should fall back to programmatic since empty slots are invalid
        assert result is not None
        assert len(result.slots) > 0

    @patch.dict(os.environ, {"GROQ_API_KEY": "test_key"})
    @patch("httpx.Client")
    def test_malformed_json_with_backticks(self, MockClient):
        if not self.available:
            pytest.skip("openai package not installed")
        provider = get_ai_provider("groq")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "```json\n{\"globals\": {\"total_duration_s\": 30, \"tempo_bpm\": 120, \"time_signature\": \"4/4\", \"energy_curve\": [0.5], \"section_markers\": [], \"aspect_ratio\": \"16:9\"}, \"slots\": [{\"index\": 0, \"start_s\": 0, \"duration_s\": 2, \"beat_index\": 0, \"section\": \"intro\", \"transition_in\": \"hard_cut\", \"transition_out\": \"hard_cut\", \"target_shot_type\": \"wide\", \"subject_hint\": \"test\", \"motion_hint\": \"static\", \"energy_level\": 0.5, \"required_tags\": [], \"avoid_tags\": [], \"selected_clip_id\": null, \"ranked_clip_ids\": null, \"confidence\": null}], \"overlays\": []}\n```"}}]
        }
        MockClient.return_value.__enter__ = MagicMock(return_value=MockClient.return_value)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        MockClient.return_value.post.return_value = mock_response

        from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis
        result = provider.generate_cutlist(
            BeatGrid(bpm=120, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[]),
            [],
            StyleAnalysis(lut_extracted=False, color_palette=[], text_overlays=[], transition_types=[],
                          camera_motions=[], mood="neutral", pacing="medium"),
            [],
            ["wide"],
        )
        assert result is not None
        assert len(result.slots) == 1

    def test_all_providers_share_base(self):
        names = ["programmatic", "claude", "gemini", "groq", "openai", "qwen"]
        providers = []
        for n in names:
            try:
                providers.append(get_ai_provider(n))
            except ImportError:
                pass  # Skip providers with missing deps
        assert len(providers) >= 1  # At least programmatic works
        assert all(isinstance(p, AIProvider) for p in providers)
        assert all(hasattr(p, "SYSTEM_PROMPT_CUTLIST") for p in providers)
        assert all(hasattr(p, "_build_cutlist_context") for p in providers)
