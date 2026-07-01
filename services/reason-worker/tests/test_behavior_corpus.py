# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
from unittest.mock import AsyncMock, MagicMock, patch

import os

import pytest

from reason_worker.behavior_corpus import (
    can_user_contribute,
    ingest_render_to_corpus,
    is_anomalous_corpus_entry,
)


@pytest.fixture(autouse=True)
def _token():
    os.environ["INTERNAL_WORKER_TOKEN"] = "test-token"
    yield
    os.environ.pop("INTERNAL_WORKER_TOKEN", None)


def _json_response(payload: dict):
    resp = MagicMock()
    resp.raise_for_status = AsyncMock()
    resp.json = AsyncMock(return_value=payload)
    return resp


@pytest.mark.asyncio
async def test_ingest_render_to_corpus_delegates_to_api():
    api_response = {"ok": True, "entry": {"id": "entry-1"}}

    async_client_mock = MagicMock()
    async_client_mock.post = AsyncMock(return_value=_json_response(api_response))
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_client_mock):
        result = await ingest_render_to_corpus("render-1", 0.8)

    assert result["entry"]["id"] == "entry-1"
    async_client_mock.post.assert_awaited_once()
    url = async_client_mock.post.await_args.args[0]
    json_payload = async_client_mock.post.await_args.kwargs["json"]
    assert json_payload == {"qualityWeight": 0.8}
    assert "internal/renders/render-1/ingest-to-corpus" in url


def test_can_user_contribute_respects_cap():
    assert can_user_contribute([{}] * 9) is True
    assert can_user_contribute([{}] * 10) is False
    assert can_user_contribute([{}] * 11) is False


def test_is_anomalous_corpus_entry_detects_outlier():
    entries = [{"signals": {"clip_count": 5.0 + i * 0.1}} for i in range(20)]
    normal = {"clip_count": 5.0}
    outlier = {"clip_count": 500.0}

    assert is_anomalous_corpus_entry(normal, entries) is False
    assert is_anomalous_corpus_entry(outlier, entries) is True
