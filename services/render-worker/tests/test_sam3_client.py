# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import httpx
import pytest

from render_worker.sam3_client import (
    SAM3_URL,
    Sam3UnavailableError,
    SegmentationResult,
    sam3_available,
    segment_object_in_clip,
)


@pytest.fixture
def mock_env(monkeypatch, tmp_path):
    """Isolate SAM3 client from real environment and disk cache."""
    monkeypatch.setenv("SAM3_SERVER_URL", "http://sam3.test")
    monkeypatch.setenv("SAM3_MASK_CACHE_DIR", str(tmp_path))
    # Reload module-level constants inside the fixture scope is tricky; tests
    # pass explicit base_url and ignore the module constant.


@pytest.mark.asyncio
async def test_sam3_available_success(mock_env, monkeypatch):
    called = {}

    class FakeResponse:
        status_code = 200
        is_success = True

    class FakeClient:
        async def get(self, url):
            called["url"] = url
            return FakeResponse()

        async def aclose(self):
            pass

    assert await sam3_available("http://sam3.test", client=FakeClient()) is True
    assert called["url"] == "http://sam3.test/health"


@pytest.mark.asyncio
async def test_sam3_available_unhealthy(mock_env):
    class FakeResponse:
        status_code = 503
        is_success = False

    class FakeClient:
        async def get(self, url):
            return FakeResponse()

        async def aclose(self):
            pass

    with pytest.raises(Sam3UnavailableError):
        await sam3_available("http://sam3.test", client=FakeClient())


@pytest.mark.asyncio
async def test_sam3_available_connection_error(mock_env):
    class FakeClient:
        async def get(self, url):
            raise httpx.ConnectError("nope")

        async def aclose(self):
            pass

    with pytest.raises(Sam3UnavailableError):
        await sam3_available("http://sam3.test", client=FakeClient())


@pytest.mark.asyncio
async def test_segment_object_text_prompt(mock_env, tmp_path, monkeypatch):
    sent = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "masks": ["mask1", "mask2"],
                "boxes": [[0, 0, 10, 10]],
                "scores": [0.95],
            }

    class FakeClient:
        async def post(self, url, json=None):
            sent["url"] = url
            sent["json"] = json
            return FakeResponse()

        async def aclose(self):
            pass

    clip = str(tmp_path / "clip.mp4")
    Path(clip).touch()
    result = await segment_object_in_clip(
        clip,
        "a red car",
        prompt_type="text",
        base_url="http://sam3.test",
        version="sam3.1",
        client=FakeClient(),
    )

    assert isinstance(result, SegmentationResult)
    assert result.masks == ["mask1", "mask2"]
    assert result.boxes == [[0, 0, 10, 10]]
    assert result.scores == [0.95]
    assert result.prompt_type == "text"
    assert result.prompt == "a red car"
    assert sent["url"] == "http://sam3.test/segment_video_text"
    assert sent["json"]["video_path"] == clip
    assert sent["json"]["text"] == "a red car"
    assert sent["json"]["version"] == "sam3.1"
    assert result.cache_path is not None
    assert Path(result.cache_path).exists()


@pytest.mark.asyncio
async def test_segment_object_box_prompt(mock_env, tmp_path):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"masks": [], "boxes": [], "scores": []}

    class FakeClient:
        async def post(self, url, json=None):
            self.last_url = url
            self.last_json = json
            return FakeResponse()

        async def aclose(self):
            pass

    clip = str(tmp_path / "clip.mp4")
    Path(clip).touch()
    client = FakeClient()
    await segment_object_in_clip(
        clip,
        [10, 20, 30, 40],
        prompt_type="box",
        base_url="http://sam3.test",
        client=client,
    )
    assert client.last_url == "http://sam3.test/segment_video_box"
    assert client.last_json["box"] == [10, 20, 30, 40]


@pytest.mark.asyncio
async def test_segment_object_point_prompt(mock_env, tmp_path):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"masks": [], "boxes": [], "scores": []}

    class FakeClient:
        async def post(self, url, json=None):
            self.last_url = url
            self.last_json = json
            return FakeResponse()

        async def aclose(self):
            pass

    clip = str(tmp_path / "clip.mp4")
    Path(clip).touch()
    client = FakeClient()
    await segment_object_in_clip(
        clip,
        [100, 200],
        prompt_type="point",
        base_url="http://sam3.test",
        client=client,
    )
    assert client.last_url == "http://sam3.test/segment_video_point"
    assert client.last_json["point"] == [100, 200]


@pytest.mark.asyncio
async def test_segment_object_unsupported_prompt_type(mock_env, tmp_path):
    clip = str(tmp_path / "clip.mp4")
    Path(clip).touch()
    with pytest.raises(ValueError):
        await segment_object_in_clip(clip, "x", prompt_type="audio")


@pytest.mark.asyncio
async def test_segment_object_uses_cache(mock_env, tmp_path, monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"masks": ["cached"], "boxes": [], "scores": []}

    class FakeClient:
        calls = 0

        async def post(self, url, json=None):
            FakeClient.calls += 1
            return FakeResponse()

        async def aclose(self):
            pass

    clip = str(tmp_path / "clip.mp4")
    Path(clip).touch()
    first = await segment_object_in_clip(
        clip,
        "prompt",
        base_url="http://sam3.test",
        client=FakeClient(),
    )
    assert FakeClient.calls == 1

    second = await segment_object_in_clip(
        clip,
        "prompt",
        base_url="http://sam3.test",
        client=FakeClient(),
    )
    assert FakeClient.calls == 1
    assert first.masks == second.masks == ["cached"]


def test_default_sam3_url_documented():
    # The module constant is read at import time; this smoke-test documents the
    # expected default when SAM3_SERVER_URL is not set in the environment.
    assert isinstance(SAM3_URL, str) and SAM3_URL.startswith("http")
