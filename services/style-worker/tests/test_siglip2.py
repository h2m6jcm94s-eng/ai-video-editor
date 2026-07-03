# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for SigLIP-2 text-to-clip embeddings."""

from __future__ import annotations

import numpy as np
from pathlib import Path

import pytest

from style_worker import siglip2


def test_normalize_handles_zero():
    zero = np.zeros((8,), dtype=np.float32)
    out = siglip2._normalize(zero)
    assert np.allclose(out, 0.0)


def test_normalize_unit_length():
    v = np.array([3.0, 4.0], dtype=np.float32)
    out = siglip2._normalize(v)
    assert np.linalg.norm(out) == pytest.approx(1.0, abs=1e-5)


def test_embed_text_returns_normalized(monkeypatch):
    class FakeProcessor:
        def __call__(self, text=None, return_tensors=None, padding=False, truncation=False):
            import torch
            return {"input_ids": torch.zeros((1, 4), dtype=torch.long)}

    class FakeModel:
        def get_text_features(self, **kwargs):
            import torch
            return torch.tensor([[1.0, 2.0, 3.0]], dtype=torch.float32)

    monkeypatch.setattr(siglip2, "_siglip_processor", FakeProcessor())
    monkeypatch.setattr(siglip2, "_siglip_model", FakeModel())
    monkeypatch.setattr(siglip2, "_siglip_device", "cpu")

    emb = siglip2.embed_text("motorcycle at night")
    assert emb.shape == (3,)
    assert np.linalg.norm(emb) == pytest.approx(1.0, abs=1e-5)


def test_video_embedding_cache_roundtrip(tmp_path: Path):
    clip_id = "dummy_path"
    cache_file = tmp_path / f"{clip_id}.npy"
    emb = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    np.save(cache_file, emb)

    loaded = siglip2.embed_video_frames("dummy_path.mp4", cache_dir=tmp_path)
    assert np.allclose(loaded, emb)
