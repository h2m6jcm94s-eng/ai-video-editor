# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for DINO-v2 clip semantic embeddings."""

from __future__ import annotations

import numpy as np
from pathlib import Path

import pytest

from ingest_worker.clip_semantic import (
    ClipSemanticEmbedding,
    cosine_first_to_last,
    embed_clip,
    load_clip_embedding,
)


def _make_embedding(clip_id: str, value: float) -> ClipSemanticEmbedding:
    emb = np.full((768,), value, dtype=np.float32)
    return ClipSemanticEmbedding(
        clip_id=clip_id,
        mean_embedding=emb.copy(),
        first_frame_embedding=emb.copy(),
        last_frame_embedding=emb.copy(),
        sample_frame_embeddings=np.stack([emb.copy() for _ in range(4)]),
    )


def test_cosine_first_to_last_identical():
    a = _make_embedding("a", 1.0)
    b = _make_embedding("b", 1.0)
    assert cosine_first_to_last(a, b) == pytest.approx(1.0, abs=1e-5)


def test_cosine_first_to_last_opposite():
    a = _make_embedding("a", 1.0)
    b = _make_embedding("b", -1.0)
    assert cosine_first_to_last(a, b) == pytest.approx(-1.0, abs=1e-5)


def test_load_clip_embedding_missing_returns_none(tmp_path: Path):
    assert load_clip_embedding("does_not_exist", cache_dir=tmp_path) is None


def test_load_clip_embedding_roundtrip(tmp_path: Path):
    emb = _make_embedding("round", 0.5)
    cache_file = tmp_path / "round.npz"
    np.savez_compressed(
        cache_file,
        mean_embedding=emb.mean_embedding,
        first_frame_embedding=emb.first_frame_embedding,
        last_frame_embedding=emb.last_frame_embedding,
        sample_frame_embeddings=emb.sample_frame_embeddings,
    )
    loaded = load_clip_embedding("round", cache_dir=tmp_path)
    assert loaded is not None
    assert loaded.clip_id == "round"
    assert np.allclose(loaded.mean_embedding, emb.mean_embedding)
