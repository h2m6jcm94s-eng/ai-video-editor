# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Load DINO-v2 clip semantic embeddings for match-cut detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np

STORAGE_ROOT = Path(r"E:\ai-video-editor-storage")


@dataclass(frozen=True)
class DinoClipEmbedding:
    clip_id: str
    mean: np.ndarray
    first_frame: np.ndarray
    last_frame: np.ndarray
    samples: np.ndarray


def _normalize(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    if norm == 0.0:
        return v
    return v / norm


def load_dino_embedding(
    clip_id: str,
    storage_root: Optional[Path] = None,
    metadata: Optional[dict] = None,
) -> Optional[DinoClipEmbedding]:
    """Load a cached DINO embedding from storage or from a metadata path.

    The metadata key ``dinoEmbeddingPath`` points to the same ``.npz`` that
    contains first/last/mean embeddings.
    """
    root = Path(storage_root) if storage_root else STORAGE_ROOT
    path: Optional[Path] = None
    if metadata:
        raw = (
            metadata.get("dinoEmbeddingPath")
            or metadata.get("dino_embedding_path")
            or metadata.get("dinoFirstFramePath")
            or metadata.get("dino_last_frame_path")
        )
        if raw:
            path = Path(raw)
    if path is None:
        path = root / "clip_semantic" / f"{clip_id}.npz"
    if not path.exists() and metadata:
        # Fall back to the original source filename so offline fixtures that use
        # synthetic clip IDs still resolve cached embeddings.
        filename = metadata.get("filename")
        if filename:
            path = root / "clip_semantic" / f"{Path(filename).stem}.npz"
    if not path.exists():
        return None
    try:
        data = np.load(path)
        return DinoClipEmbedding(
            clip_id=clip_id,
            mean=_normalize(data["mean_embedding"].astype(np.float32)),
            first_frame=_normalize(data["first_frame_embedding"].astype(np.float32)),
            last_frame=_normalize(data["last_frame_embedding"].astype(np.float32)),
            samples=data["sample_frame_embeddings"].astype(np.float32),
        )
    except Exception:
        return None


def cosine_last_to_first(a: DinoClipEmbedding, b: DinoClipEmbedding) -> float:
    """Cosine similarity between the end of clip ``a`` and start of clip ``b``."""
    x, y = a.last_frame, b.first_frame
    nx, ny = float(np.linalg.norm(x)), float(np.linalg.norm(y))
    if nx == 0.0 or ny == 0.0:
        return 0.0
    return float(np.dot(x, y) / (nx * ny))


def load_dino_embeddings_for_clips(
    clip_ids,
    clip_metadata: Optional[Dict[str, dict]] = None,
    storage_root: Optional[Path] = None,
) -> Dict[str, DinoClipEmbedding]:
    """Load DINO embeddings for a set of clip IDs."""
    result: Dict[str, DinoClipEmbedding] = {}
    meta = clip_metadata or {}
    for clip_id in clip_ids:
        emb = load_dino_embedding(
            clip_id,
            storage_root=storage_root,
            metadata=meta.get(clip_id),
        )
        if emb is not None:
            result[clip_id] = emb
    return result
