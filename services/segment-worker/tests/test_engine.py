# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for the SAM3 segmentation engine.

These tests never require SAM3 or CUDA to be installed.  They verify the
graceful fallback paths and the happy-path serialization logic with mocks.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from segment_worker import engine


class TestAvailability:
    def test_not_available_without_sam3(self, monkeypatch):
        monkeypatch.setattr(engine, "_load_sam3_modules", lambda: {})
        assert not engine.is_segmentation_available()

    def test_not_available_without_hf_token(self, monkeypatch):
        """HF_TOKEN or SAM3_CHECKPOINT_PATH is required to download checkpoints."""
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("SAM3_CHECKPOINT_PATH", raising=False)
        # Pretend SAM3 is importable.
        monkeypatch.setattr(
            engine,
            "_load_sam3_modules",
            lambda: {"build_sam3_image_model": object, "Sam3Processor": object},
        )
        assert not engine.is_segmentation_available()

    def test_available_with_checkpoint_path(self, monkeypatch):
        monkeypatch.setenv("SAM3_CHECKPOINT_PATH", "/opt/sam3/sam3.pt")
        monkeypatch.setattr(
            engine,
            "_load_sam3_modules",
            lambda: {"build_sam3_image_model": object, "Sam3Processor": object},
        )
        assert engine.is_segmentation_available()


class TestDetectSubjectMaskImage:
    def test_skips_when_sam3_unavailable(self, monkeypatch):
        monkeypatch.setattr(engine, "is_segmentation_available", lambda: False)
        result = engine.detect_subject_mask_image("/tmp/img.jpg", "person")
        assert result["available"] is False
        assert result["skipped"] is True
        assert "SAM3" in result["skipped_reason"]

    def test_returns_masks_boxes_scores(self, monkeypatch, tmp_path):
        """Happy path with a mocked SAM3 image model."""
        monkeypatch.setattr(engine, "is_segmentation_available", lambda: True)

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

        monkeypatch.setattr(
            engine,
            "_image_model",
            lambda: (object(), FakeProcessor()),
        )

        img_path = tmp_path / "test.png"
        pytest.importorskip("PIL").Image.new("RGB", (64, 64), "red").save(img_path)

        result = engine.detect_subject_mask_image(str(img_path), "person")
        assert result["available"] is True
        assert result["skipped"] is False
        assert len(result["masks"]) == 1
        assert result["masks"][0] is not None
        assert result["boxes"] == [[10, 20, 30, 40]]
        assert result["scores"] == [[0.95]]


class TestDetectSubjectMaskVideo:
    def test_skips_when_sam3_unavailable(self, monkeypatch):
        monkeypatch.setattr(engine, "is_segmentation_available", lambda: False)
        result = engine.detect_subject_mask_video("/tmp/vid.mp4", "person")
        assert result["available"] is False
        assert result["skipped"] is True
