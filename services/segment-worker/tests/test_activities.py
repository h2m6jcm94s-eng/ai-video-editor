# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"""Tests for segmentation worker activity helpers."""

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from segment_worker import activities


class TestPersistMasksValidation:
    def test_persist_masks_rejects_invalid_base64(self, monkeypatch):
        calls = []

        def fake_create_mask_asset(project_id, source_asset_id, index):
            calls.append((project_id, source_asset_id, index))
            return {"assetId": f"asset-{index}", "storageKey": f"key-{index}"}

        monkeypatch.setattr(activities, "_create_mask_asset", fake_create_mask_asset)
        monkeypatch.setattr(activities, "_complete_mask_asset", lambda *_a, **_kw: None)
        monkeypatch.setattr(
            activities, "_patch_source_segment_metadata", lambda *_a, **_kw: None
        )

        with pytest.raises(ValueError, match="Invalid base64"):
            activities._persist_masks_as_assets(
                "proj-1", "src-1", "person", ["not-valid-b64!!!"], None, None
            )

    def test_persist_masks_rejects_too_many_masks(self, monkeypatch):
        monkeypatch.setattr(activities, "_MAX_MASK_COUNT", 2)
        monkeypatch.setattr(
            activities, "_create_mask_asset", lambda *_a, **_kw: {"assetId": "x", "storageKey": "y"}
        )
        monkeypatch.setattr(activities, "_complete_mask_asset", lambda *_a, **_kw: None)
        monkeypatch.setattr(
            activities, "_patch_source_segment_metadata", lambda *_a, **_kw: None
        )

        valid_mask = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        too_many = [valid_mask] * 3

        with pytest.raises(ValueError, match="Too many masks"):
            activities._persist_masks_as_assets(
                "proj-1", "src-1", "person", too_many, None, None
            )

    def test_persist_masks_rejects_oversized_total_payload(self, monkeypatch):
        monkeypatch.setattr(activities, "_MAX_TOTAL_MASK_BYTES", 100)
        monkeypatch.setattr(
            activities, "_create_mask_asset", lambda *_a, **_kw: {"assetId": "x", "storageKey": "y"}
        )
        monkeypatch.setattr(activities, "_complete_mask_asset", lambda *_a, **_kw: None)
        monkeypatch.setattr(
            activities, "_patch_source_segment_metadata", lambda *_a, **_kw: None
        )

        # Two small masks whose combined decoded size exceeds the lowered total limit.
        mask = base64.b64encode(b"x" * 60).decode()

        with pytest.raises(ValueError, match="Total mask payload exceeds"):
            activities._persist_masks_as_assets(
                "proj-1", "src-1", "person", [mask, mask], None, None
            )

    def test_persist_masks_accepts_valid_payload(self, monkeypatch):
        calls = []

        def fake_create_mask_asset(project_id, source_asset_id, index):
            calls.append(index)
            return {"assetId": f"asset-{index}", "storageKey": f"key-{index}"}

        monkeypatch.setattr(activities, "_create_mask_asset", fake_create_mask_asset)
        monkeypatch.setattr(activities, "_complete_mask_asset", lambda *_a, **_kw: None)
        monkeypatch.setattr(
            activities, "_patch_source_segment_metadata", lambda *_a, **_kw: None
        )

        valid = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        result = activities._persist_masks_as_assets(
            "proj-1", "src-1", "person", [valid, valid], None, None
        )

        assert result == ["asset-0", "asset-1"]
