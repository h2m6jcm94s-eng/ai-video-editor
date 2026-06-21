# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for the SAM3 segmentation engine facade.

These tests never require SAM3 or CUDA to be installed. They verify the
graceful fallback paths and that the engine delegates to ``Sam3Segmenter``.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from segment_worker import engine


class FakeSegmenter:
    """Stand-in for Sam3Segmenter that records calls."""

    def __init__(self, available: bool = False) -> None:
        self._available = available
        self.image_calls: list[tuple[str, str]] = []
        self.video_calls: list[tuple[str, str, int]] = []

    def available(self) -> bool:  # noqa: A003
        return self._available

    def segment_image(self, image_path: str, prompt: str) -> dict:
        self.image_calls.append((image_path, prompt))
        return {"available": self._available, "mode": "image"}

    def segment_video(self, video_path: str, prompt: str, frame_index: int = 0) -> dict:
        self.video_calls.append((video_path, prompt, frame_index))
        return {"available": self._available, "mode": "video"}


class TestEngineFacade:
    def test_is_segmentation_available_delegates(self, monkeypatch):
        fake = FakeSegmenter(available=True)
        monkeypatch.setattr(engine, "_get_segmenter", lambda: fake)
        assert engine.is_segmentation_available() is True

    def test_detect_subject_mask_image_delegates(self, monkeypatch):
        fake = FakeSegmenter(available=True)
        monkeypatch.setattr(engine, "_get_segmenter", lambda: fake)
        result = engine.detect_subject_mask_image("/tmp/img.jpg", "person")
        assert result["mode"] == "image"
        assert fake.image_calls == [("/tmp/img.jpg", "person")]

    def test_detect_subject_mask_video_delegates(self, monkeypatch):
        fake = FakeSegmenter(available=True)
        monkeypatch.setattr(engine, "_get_segmenter", lambda: fake)
        result = engine.detect_subject_mask_video("/tmp/vid.mp4", "person", frame_index=5)
        assert result["mode"] == "video"
        assert fake.video_calls == [("/tmp/vid.mp4", "person", 5)]
