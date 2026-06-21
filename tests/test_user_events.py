"""Tests for shared_py.user_events reporting helpers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared_py.user_events import UserEventReporter, areport_user_event, report_user_event


def _make_async_client_mock(status_code=200, text=""):
    """Return a patch target for ``httpx.AsyncClient`` that yields an async client mock."""
    client = AsyncMock()
    client.post.return_value.status_code = status_code
    client.post.return_value.text = text

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=cm), client


@pytest.mark.asyncio
async def test_areport_user_event_success():
    reporter = UserEventReporter(api_url="http://api", token="test-token")
    mock_client_class, mock_client = _make_async_client_mock(status_code=200)

    with patch("shared_py.user_events.httpx.AsyncClient", mock_client_class):
        result = await reporter.areport("user-1", "test.code", "hello")

    assert result is True
    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["headers"]["x-internal-token"] == "test-token"
    assert call_kwargs["json"]["userId"] == "user-1"


@pytest.mark.asyncio
async def test_areport_user_event_rejected():
    reporter = UserEventReporter(api_url="http://api", token="test-token")
    mock_client_class, mock_client = _make_async_client_mock(status_code=403, text="forbidden")

    with patch("shared_py.user_events.httpx.AsyncClient", mock_client_class):
        result = await reporter.areport("user-1", "test.code", "hello")

    assert result is False


@pytest.mark.asyncio
async def test_areport_user_event_convenience_function(monkeypatch):
    monkeypatch.setattr("shared_py.user_events._INTERNAL_TOKEN", "env-token")
    mock_client_class, mock_client = _make_async_client_mock(status_code=200)

    with patch("shared_py.user_events.httpx.AsyncClient", mock_client_class):
        result = await areport_user_event("user-2", "code", "msg", route="/test")

    assert result is True
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["json"]["route"] == "/test"
    assert call_kwargs["headers"]["x-internal-token"] == "env-token"


def test_report_user_event_no_token_returns_false():
    reporter = UserEventReporter(api_url="http://api", token="")
    assert reporter.report("user-1", "code", "msg") is False


def test_report_user_event_success_sync():
    reporter = UserEventReporter(api_url="http://api", token="test-token")
    with patch("shared_py.user_events.httpx.Client") as mock_client_class:
        mock_client = mock_client_class.return_value.__enter__.return_value
        mock_client.post.return_value.status_code = 200
        result = reporter.report("user-1", "code", "msg")
    assert result is True
