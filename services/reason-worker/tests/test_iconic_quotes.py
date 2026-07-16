# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for iconic quote detector."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reason_worker.iconic_quotes import (
    TranscriptSegment,
    _is_latin_script,
    _language_agnostic_salience,
    _llm_cache_key,
    _repetition_score,
    _text_emotional_intensity,
    detect_iconic_quotes,
    should_detect_iconic_quotes,
)


class _FakeLLMClient:
    """Minimal fake LLM client that returns deterministic scores."""

    def __init__(self):
        self.call_count = 0

    def _score(self, prompt: str) -> float:
        self.call_count += 1
        text = prompt.lower()
        if "legend" in text:
            return 0.92
        if "forever" in text or "dream" in text:
            return 0.75
        return 0.35

    def complete(self, **kwargs):
        return f"{self._score(kwargs.get('prompt', '')):.2f}"


def _with_fake_client(func):
    """Run ``func`` while the iconic module uses a fake LLM client."""
    import reason_worker.iconic_quotes as iq

    original_client = iq._llm_client
    fake_client = _FakeLLMClient()
    iq._llm_client = lambda: fake_client
    # Clear module cache so tests are independent.
    original_cache = dict(iq._LLM_ICONIC_CACHE)
    iq._LLM_ICONIC_CACHE.clear()
    try:
        return func(fake_client)
    finally:
        iq._llm_client = original_client
        iq._LLM_ICONIC_CACHE.clear()
        iq._LLM_ICONIC_CACHE.update(original_cache)


def test_text_emotional_intensity_boosts_intense_words():
    legend = _text_emotional_intensity("I want to be a legend!")
    mumble = _text_emotional_intensity("yeah okay sure")
    assert legend > mumble


def test_text_emotional_intensity_language_agnostic_non_latin():
    """B6: non-Latin text should score for expressive punctuation/endings."""
    # Japanese exclamatory ending + repeated emphasis.
    jp_intense = _text_emotional_intensity("絶対に負けないよ！！")
    # Neutral Japanese sentence.
    jp_neutral = _text_emotional_intensity("今日はいい天気です")
    assert jp_intense > 0.3
    assert jp_intense > jp_neutral


def test_text_emotional_intensity_uses_full_width_marks():
    """B6: full-width exclamation/question marks count."""
    ascii_exclaim = _text_emotional_intensity("Run")
    fullwidth_exclaim = _text_emotional_intensity("走れ！")
    assert fullwidth_exclaim > ascii_exclaim


def test_llm_cache_key_stable():
    k1 = _llm_cache_key("I want to be a legend", "Cyberpunk")
    k2 = _llm_cache_key("I want to be a legend", "Cyberpunk")
    assert k1 == k2
    assert k1 != _llm_cache_key("different text", "Cyberpunk")


def test_detect_iconic_quotes_filters_short_lines():
    def _run(_client):
        segments = [
            TranscriptSegment(start_s=0.0, end_s=1.0, text="hi"),
            TranscriptSegment(start_s=2.0, end_s=3.0, text="I want to be a legend forever"),
        ]
        quotes = detect_iconic_quotes(segments, source_ip_hint="Cyberpunk Edgerunners")
        texts = [q.segment.text for q in quotes]
        assert "hi" not in texts
        assert any("legend" in t for t in texts)

    _with_fake_client(_run)


def test_detect_iconic_quotes_respects_top_k_guard():
    def _run(client):
        segments = [
            TranscriptSegment(start_s=i, end_s=i + 1, text=f"this is test line number {i} with some emotion")
            for i in range(30)
        ]
        detect_iconic_quotes(segments, source_ip_hint="Cyberpunk", max_llm_candidates=5)
        assert client.call_count == 5

    _with_fake_client(_run)


def test_detect_iconic_quotes_caches_llm_calls():
    def _run(client):
        segments = [
            TranscriptSegment(start_s=0.0, end_s=1.0, text="I want to be a legend"),
        ]
        detect_iconic_quotes(segments, source_ip_hint="Cyberpunk")
        detect_iconic_quotes(segments, source_ip_hint="Cyberpunk")
        assert client.call_count == 1

    _with_fake_client(_run)


def test_should_detect_iconic_quotes_for_mv_content():
    embedding = {
        "motion_density": 0.8,
        "speech_ratio": 0.02,
        "song_present": 1.0,
        "song_has_vocals": 1.0,
    }
    should_run, score = should_detect_iconic_quotes(embedding)
    assert should_run is True
    assert score > 0.8


def test_should_skip_iconic_quotes_for_podcast_content():
    embedding = {
        "motion_density": 0.1,
        "speech_ratio": 0.9,
        "song_present": 0.0,
        "song_has_vocals": 0.0,
    }
    should_run, score = should_detect_iconic_quotes(embedding)
    assert should_run is False
    assert score < 0.3


def test_detect_iconic_quotes_returns_empty_for_non_mv():
    def _run(client):
        segments = [
            TranscriptSegment(start_s=0.0, end_s=1.0, text="I want to be a legend forever"),
        ]
        embedding = {"motion_density": 0.1, "speech_ratio": 0.9, "song_present": 0.0, "song_has_vocals": 0.0}
        quotes = detect_iconic_quotes(segments, source_ip_hint="Podcast", content_embedding=embedding)
        assert quotes == []
        assert client.call_count == 0

    _with_fake_client(_run)


def test_detect_iconic_quotes_scales_llm_budget_with_likeness():
    def _run(client):
        segments = [
            TranscriptSegment(start_s=i, end_s=i + 1, text=f"this is test line number {i} with some emotion")
            for i in range(30)
        ]
        # mv_likeness ≈ 0.6 → budget ≈ 15 candidates.
        embedding = {
            "motion_density": 0.75,
            "speech_ratio": 0.04,
            "song_present": 1.0,
            "song_has_vocals": 1.0,
        }
        detect_iconic_quotes(segments, source_ip_hint="Cyberpunk", content_embedding=embedding)
        assert client.call_count > 5
        assert client.call_count <= 20

    _with_fake_client(_run)


def test_repetition_score_boosts_repeated_phrases():
    segments = [
        TranscriptSegment(start_s=0.0, end_s=1.0, text="君の名は"),
        TranscriptSegment(start_s=1.0, end_s=2.0, text="もう一度"),
        TranscriptSegment(start_s=2.0, end_s=3.0, text="君の名は"),
        TranscriptSegment(start_s=3.0, end_s=4.0, text="君の名は"),
    ]
    assert _repetition_score("君の名は", segments) == 1.0
    assert _repetition_score("もう一度", segments) == 0.0


def test_is_latin_script_detects_japanese():
    assert _is_latin_script("I want to be a legend") is True
    assert _is_latin_script("君の名は") is False
    assert _is_latin_script("中文歌词") is False


def test_detect_iconic_quotes_non_latin_uses_llm_and_salience():
    def _run(client):
        segments = [
            TranscriptSegment(start_s=0.0, end_s=1.75, text="君の名は"),
            TranscriptSegment(start_s=1.75, end_s=3.5, text="もう一度"),
            TranscriptSegment(start_s=3.5, end_s=5.25, text="君の名は"),
            TranscriptSegment(start_s=5.25, end_s=7.0, text="君の名は"),
        ]
        # Without a clip path salience is shape/repetition only.
        quotes = detect_iconic_quotes(
            segments,
            source_ip_hint="Kimi No Nawa",
            iconic_weights={
                "emotional_intensity": 0.0,
                "loudness_normalized": 0.0,
                "iconic_llm_score": 0.0,
                "vocal_uniqueness": 0.0,
                "isolation": 0.0,
                "language_agnostic_salience": 1.0,
            },
        )
        # The language-agnostic path now calls the LLM for non-Latin text too.
        assert client.call_count > 0
        # Repeated Japanese phrase should surface.
        texts = [q.segment.text for q in quotes]
        assert any("君の名は" in t for t in texts)

    _with_fake_client(_run)


def test_language_agnostic_salience_zero_for_invalid_shape():
    segments = [
        TranscriptSegment(start_s=0.0, end_s=0.2, text="a"),
    ]
    score = _language_agnostic_salience(segments[0], segments, None, None)
    assert score == 0.0
