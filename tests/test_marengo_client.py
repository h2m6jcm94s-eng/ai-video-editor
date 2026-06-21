"""
Unit tests for the Twelve Labs Marengo 3.0 client wrapper.

Live API calls are intentionally avoided; these tests verify fallback behavior
and the SDK integration shape using module-level mocks.
"""

import os
import sys
import tempfile
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from reason_worker.marengo_client import MarengoClient


class TestMarengoClientFallbacks:
    def test_unavailable_without_api_key(self):
        """Client reports unavailable when the API key is missing."""
        client = MarengoClient(api_key="")
        assert not client.available()
        assert client.embed_text("hello") is None

    def test_embed_text_returns_none_when_unavailable(self):
        client = MarengoClient(api_key="")
        assert client.embed_text("test query") is None

    def test_embed_video_file_returns_none_when_unavailable(self):
        client = MarengoClient(api_key="")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            assert client.embed_video_file(path) is None
        finally:
            os.unlink(path)


class TestMarengoClientWithMocks:
    @pytest.fixture(autouse=True)
    def _patch_twelvelabs(self, monkeypatch):
        """Install a fake twelvelabs module for every test in this class."""
        fake_module = types.ModuleType("twelvelabs")
        monkeypatch.setitem(sys.modules, "twelvelabs", fake_module)
        yield
        # sys.modules cleanup is handled by monkeypatch.

    def _make_fake_sdk(self, fake_embedding):
        """Build fake SDK classes and attach them to the fake twelvelabs module."""
        fake_module = sys.modules["twelvelabs"]

        class FakeAsset:
            id = "asset-123"
            status = "ready"

        class FakeResponse:
            data = [
                type(
                    "Emb",
                    (),
                    {
                        "embedding": fake_embedding,
                        "embedding_scope": "asset",
                        "embedding_option": "fused",
                    },
                )
            ]

        class FakeAssets:
            def create(self, **kwargs):
                return FakeAsset()

            def retrieve(self, asset_id):
                return FakeAsset()

        class FakeEmbedV2:
            def create(self, **kwargs):
                return FakeResponse()

        class FakeTwelveLabs:
            def __init__(self, api_key):
                self.api_key = api_key
                self.assets = FakeAssets()
                self.embed = type("Embed", (), {"v_2": FakeEmbedV2()})()

        fake_module.TwelveLabs = FakeTwelveLabs
        fake_module.TextInputRequest = lambda **kwargs: kwargs
        fake_module.VideoInputRequest = lambda **kwargs: kwargs
        fake_module.MediaSource = lambda **kwargs: kwargs

    def test_embed_text_success(self):
        """Text embedding uses the SDK and returns a numpy vector."""
        fake_embedding = [0.1] * 512
        self._make_fake_sdk(fake_embedding)

        client = MarengoClient(api_key="fake-key")
        assert client.available()
        emb = client.embed_text("ocean waves")
        assert emb is not None
        assert emb.shape == (512,)
        assert emb.dtype == np.float32

    def test_embed_video_file_uploads_and_embeds(self):
        """Video embedding uploads a file and returns the fused asset embedding."""
        fake_embedding = [0.2] * 512
        self._make_fake_sdk(fake_embedding)

        client = MarengoClient(api_key="fake-key")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            emb = client.embed_video_file(path)
            assert emb is not None
            assert emb.shape == (512,)
        finally:
            os.unlink(path)

    def test_sdk_failure_marks_unavailable(self):
        """If the SDK constructor raises, the client is unavailable."""
        fake_module = sys.modules["twelvelabs"]

        class ExplodingTwelveLabs:
            def __init__(self, api_key):
                raise RuntimeError("boom")

        fake_module.TwelveLabs = ExplodingTwelveLabs

        client = MarengoClient(api_key="fake-key")
        assert not client.available()
