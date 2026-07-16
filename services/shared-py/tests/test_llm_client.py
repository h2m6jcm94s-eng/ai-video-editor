# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for the unified LLM client."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import httpx

from shared_py.llm_client import LLMClient, LLMTask


PROMPT = "Rate how iconic this line is: 'I want to be a legend'"


def _fake_ollama_response(text: str):
    """Build a minimal httpx.Response-like object for Ollama /api/chat."""
    resp = MagicMock()
    resp.json.return_value = {"message": {"role": "assistant", "content": text}}
    resp.raise_for_status.return_value = None
    return resp


def test_cache_path_is_stable():
    client = LLMClient(cache_root=Path("/tmp/cache"))
    p1 = client._cache_path(LLMTask.ICONIC_QUOTE_SCORE, PROMPT, "gemma4:12b")
    p2 = client._cache_path(LLMTask.ICONIC_QUOTE_SCORE, PROMPT, "gemma4:12b")
    assert p1 == p2
    assert p1.parent.name == "iconic_quote_score"
    assert p1.suffix == ".json"


def test_cache_path_differs_by_task():
    client = LLMClient(cache_root=Path("/tmp/cache"))
    p1 = client._cache_path(LLMTask.ICONIC_QUOTE_SCORE, PROMPT, "gemma4:12b")
    p2 = client._cache_path(LLMTask.EDIT_INTENT_CLASSIFY, PROMPT, "gemma4:12b")
    assert p1 != p2


def test_complete_returns_ollama_response(tmp_path):
    client = LLMClient(cache_root=tmp_path)
    with patch.object(httpx, "post", return_value=_fake_ollama_response("0.85")) as mock_post:
        result = client.complete(
            task=LLMTask.ICONIC_QUOTE_SCORE,
            prompt=PROMPT,
            max_tokens=10,
            temperature=0.0,
        )
    assert result == "0.85"
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["model"] == "gemma4:12b"
    assert call_kwargs["json"]["options"]["temperature"] == 0.0


def test_complete_caches_ollama_response(tmp_path):
    client = LLMClient(cache_root=tmp_path)
    with patch.object(httpx, "post", return_value=_fake_ollama_response("0.91")) as mock_post:
        r1 = client.complete(
            task=LLMTask.ICONIC_QUOTE_SCORE,
            prompt=PROMPT,
            max_tokens=10,
            temperature=0.0,
        )
        r2 = client.complete(
            task=LLMTask.ICONIC_QUOTE_SCORE,
            prompt=PROMPT,
            max_tokens=10,
            temperature=0.0,
        )
    assert r1 == "0.91"
    assert r2 == "0.91"
    assert mock_post.call_count == 1

    cache_path = client._cache_path(LLMTask.ICONIC_QUOTE_SCORE, PROMPT, "gemma4:12b")
    assert cache_path.exists()


def test_complete_falls_back_to_anthropic(tmp_path):
    client = LLMClient(cache_root=tmp_path, anthropic_api_key="fake-key")
    ollama_error = RuntimeError("connection refused")

    fake_anthropic = MagicMock()
    fake_messages = fake_anthropic.Anthropic.return_value.messages
    fake_messages.create.return_value.content = [MagicMock(text="0.77")]

    with patch.object(httpx, "post", side_effect=ollama_error):
        with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
            result = client.complete(
                task=LLMTask.ICONIC_QUOTE_SCORE,
                prompt=PROMPT,
                max_tokens=10,
                temperature=0.0,
            )
    assert result == "0.77"


def test_complete_returns_fallback_when_backends_unavailable(tmp_path):
    client = LLMClient(cache_root=tmp_path, anthropic_api_key="")
    with patch.object(httpx, "post", side_effect=RuntimeError("ollama down")):
        result = client.complete(
            task=LLMTask.ICONIC_QUOTE_SCORE,
            prompt=PROMPT,
            max_tokens=10,
            fallback_response="0.5",
        )
    assert result == "0.5"


def test_complete_raises_when_no_fallback(tmp_path):
    client = LLMClient(cache_root=tmp_path, anthropic_api_key="")
    with patch.object(httpx, "post", side_effect=RuntimeError("ollama down")):
        try:
            client.complete(
                task=LLMTask.ICONIC_QUOTE_SCORE,
                prompt=PROMPT,
                max_tokens=10,
            )
        except RuntimeError as e:
            assert "no fallback_response" in str(e)
        else:
            raise AssertionError("Expected RuntimeError")


def test_complete_parses_json_schema(tmp_path):
    client = LLMClient(cache_root=tmp_path)
    schema = {
        "type": "object",
        "properties": {"intent": {"type": "string"}},
        "required": ["intent"],
    }
    with patch.object(httpx, "post", return_value=_fake_ollama_response('{"intent": "color_shift"}')):
        result = client.complete(
            task=LLMTask.EDIT_INTENT_CLASSIFY,
            prompt=PROMPT,
            json_schema=schema,
        )
    assert result == {"intent": "color_shift"}


def test_anthropic_system_user_split(tmp_path):
    client = LLMClient(cache_root=tmp_path, anthropic_api_key="fake-key")
    prompt = "SYSTEM: You are a scorer.\nUSER: Rate this line"

    fake_anthropic = MagicMock()
    fake_messages = fake_anthropic.Anthropic.return_value.messages
    fake_messages.create.return_value.content = [MagicMock(text="0.66")]

    with patch.object(httpx, "post", side_effect=RuntimeError("ollama down")):
        with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
            client.complete(
                task=LLMTask.ICONIC_QUOTE_SCORE,
                prompt=prompt,
                max_tokens=10,
            )

    _, kwargs = fake_messages.create.call_args
    assert kwargs["system"] == "You are a scorer."
    assert kwargs["messages"][0]["content"] == "Rate this line"
