# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for ``Sam3Segmenter``.

These tests never require SAM3 or CUDA to be installed. They verify the
graceful fallback paths and the happy-path serialization logic with mocks.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from segment_worker import client as client_mod
from segment_worker.client import Sam3Segmenter


class TestAvailability:
    def test_not_available_without_image_libs(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", False)
        monkeypatch.setattr(client_mod, "_TORCH", True)
        segmenter = Sam3Segmenter()
        assert not segmenter.available()

    def test_not_available_without_torch(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", True)
        monkeypatch.setattr(client_mod, "_TORCH", False)
        segmenter = Sam3Segmenter()
        assert not segmenter.available()

    def test_not_available_without_sam3_modules(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", True)
        monkeypatch.setattr(client_mod, "_TORCH", True)
        monkeypatch.setattr(client_mod, "_load_sam3_modules", lambda: {})
        segmenter = Sam3Segmenter()
        assert not segmenter.available()

    def test_not_available_without_hf_token_or_checkpoint(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", True)
        monkeypatch.setattr(client_mod, "_TORCH", True)
        monkeypatch.setattr(client_mod, "_load_sam3_modules", lambda: {"build": object})
        monkeypatch.delenv("HF_TOKEN", raising=False)
        segmenter = Sam3Segmenter(checkpoint_path="")
        assert not segmenter.available()

    def test_available_with_checkpoint_path(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", True)
        monkeypatch.setattr(client_mod, "_TORCH", True)
        monkeypatch.setattr(client_mod, "_load_sam3_modules", lambda: {"build": object})
        segmenter = Sam3Segmenter(checkpoint_path="/opt/sam3/sam3.pt")
        assert segmenter.available()

    def test_available_with_hf_token(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", True)
        monkeypatch.setattr(client_mod, "_TORCH", True)
        monkeypatch.setattr(client_mod, "_load_sam3_modules", lambda: {"build": object})
        monkeypatch.setenv("HF_TOKEN", "hf_xxx")
        segmenter = Sam3Segmenter(checkpoint_path="")
        assert segmenter.available()


class TestSegmentImage:
    def test_skips_when_unavailable(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", False)
        segmenter = Sam3Segmenter()
        result = segmenter.segment_image("/tmp/img.jpg", "person")
        assert result["available"] is False
        assert result["skipped"] is True
        assert "SAM3" in result["skipped_reason"]

    def test_returns_masks_boxes_scores(self, monkeypatch, tmp_path):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", True)
        monkeypatch.setattr(client_mod, "_TORCH", True)
        monkeypatch.setattr(client_mod, "_load_sam3_modules", lambda: {"build": object})
        monkeypatch.setenv("HF_TOKEN", "hf_xxx")

        fake_mask = pytest.importorskip("numpy").array([[0.0, 1.0], [1.0, 1.0]])
        fake_box = pytest.importorskip("numpy").array([10, 20, 30, 40])
        fake_score = pytest.importorskip("numpy").array([0.95])

        class FakeProcessor:
            def set_image(self, image):
                return {"image": image}

            def set_text_prompt(self, state, prompt):
                return {
                    "masks": [fake_mask],
                    "boxes": [fake_box],
                    "scores": [fake_score],
                }

        segmenter = Sam3Segmenter()
        segmenter._image_model = object()
        segmenter._processor = FakeProcessor()

        img_path = tmp_path / "test.png"
        pytest.importorskip("PIL").Image.new("RGB", (64, 64), "red").save(img_path)

        result = segmenter.segment_image(str(img_path), "person")
        assert result["available"] is True
        assert result["skipped"] is False
        assert len(result["masks"]) == 1
        assert result["masks"][0] is not None
        assert result["boxes"] == [[10, 20, 30, 40]]
        assert result["scores"] == [[0.95]]


class TestSegmentVideo:
    def test_skips_when_unavailable(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", False)
        segmenter = Sam3Segmenter()
        result = segmenter.segment_video("/tmp/vid.mp4", "person")
        assert result["available"] is False
        assert result["skipped"] is True

    def test_returns_masks_by_frame(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_IMAGE_LIBS", True)
        monkeypatch.setattr(client_mod, "_TORCH", True)
        monkeypatch.setattr(client_mod, "_load_sam3_modules", lambda: {"build": object})
        monkeypatch.setenv("HF_TOKEN", "hf_xxx")

        fake_mask = pytest.importorskip("numpy").array([[1.0, 0.0], [0.0, 1.0]])

        class FakePredictor:
            def __init__(self):
                self.session_id = "sess-123"

            def handle_request(self, request):
                if request["type"] == "start_session":
                    return {"session_id": self.session_id}
                return {}

            def handle_stream_request(self, request):
                yield {
                    "frame_index": 0,
                    "outputs": {"out_binary_masks": [fake_mask]},
                }
                yield {
                    "frame_index": 1,
                    "outputs": {"out_binary_masks": [fake_mask]},
                }

        segmenter = Sam3Segmenter()
        segmenter._video_predictor = FakePredictor()

        result = segmenter.segment_video("/tmp/vid.mp4", "person", frame_index=3)
        assert result["available"] is True
        assert result["skipped"] is False
        assert len(result["masks_by_frame"]) == 2
        assert all(len(v) == 1 for v in result["masks_by_frame"].values())
