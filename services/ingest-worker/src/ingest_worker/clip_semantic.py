# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""DINO-v2 semantic embeddings for clip frames.

Used by Wave 7 match-cut detection and as a visual representation of each clip.
Embeddings are cached as compressed numpy arrays on disk.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("ingest_worker.clip_semantic")

os.environ.setdefault("HF_HOME", r"E:\hf-cache")

_DINO_MODEL_NAME = "facebook/dinov2-base"
_DINO_EMBEDDING_DIM = 768
_INPUT_SIZE = 224

# ImageNet normalization constants used by DINO-v2 training.
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Lazy singletons.
_dino_model: Optional[object] = None
_dino_device: Optional[str] = None


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "clip_semantic"


def _load_dino_model() -> Tuple[object, str]:
    """Load the DINO-v2 model and return (model, device)."""
    global _dino_model, _dino_device
    if _dino_model is not None:
        return _dino_model, _dino_device

    import torch
    from transformers import AutoModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("loading_dino_v2", model=_DINO_MODEL_NAME, device=device)
    model = AutoModel.from_pretrained(_DINO_MODEL_NAME)
    model.to(device)
    model.eval()
    _dino_model = model
    _dino_device = device
    return model, device


def _preprocess_frame(pil_image: "Image") -> np.ndarray:
    """Resize, center-crop, and normalize a PIL image for DINO-v2."""
    # Resize shorter side to _INPUT_SIZE using bicubic interpolation.
    w, h = pil_image.size
    if w < h:
        new_w = _INPUT_SIZE
        new_h = int(round(h * _INPUT_SIZE / w))
    else:
        new_h = _INPUT_SIZE
        new_w = int(round(w * _INPUT_SIZE / h))
    resized = pil_image.resize((new_w, new_h), resample=3)  # Image.BICUBIC == 3

    # Center crop to square.
    left = (new_w - _INPUT_SIZE) // 2
    top = (new_h - _INPUT_SIZE) // 2
    cropped = resized.crop((left, top, left + _INPUT_SIZE, top + _INPUT_SIZE))

    # Convert to float32 tensor in CHW order and normalize.
    arr = np.array(cropped, dtype=np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    arr = arr.transpose(2, 0, 1)
    return arr


def _read_frame_at(clip_path: str, target_s: float) -> Optional["Image"]:
    """Decode a single frame near ``target_s`` using PyAV."""
    try:
        from PIL import Image
        import av
    except Exception as exc:
        logger.warning("clip_semantic_import_failed", error=str(exc))
        return None

    try:
        container = av.open(clip_path)
        video_stream = container.streams.video[0]
        time_base = float(video_stream.time_base)

        # Seek to the nearest keyframe before target_s.
        target_tb = int(target_s / time_base)
        container.seek(target_tb, stream=video_stream)

        for frame in container.decode(video_stream):
            frame_s = float(frame.pts * time_base)
            if frame_s >= target_s - 0.1:
                return frame.to_image()
        return None
    except Exception as exc:
        logger.warning("clip_semantic_frame_read_failed", path=clip_path, target_s=target_s, error=str(exc))
        return None
    finally:
        try:
            container.close()
        except Exception:
            pass


def _compute_embeddings_for_frames(frames: List["Image"]) -> np.ndarray:
    """Return (N, 768) float32 CLS embeddings for a list of PIL images."""
    if not frames:
        return np.zeros((0, _DINO_EMBEDDING_DIM), dtype=np.float32)

    model, device = _load_dino_model()
    import torch

    batch = np.stack([_preprocess_frame(f) for f in frames], axis=0)
    tensor = torch.from_numpy(batch).to(device)

    with torch.no_grad():
        outputs = model(tensor)
        last_hidden = outputs.last_hidden_state  # (N, seq_len, dim)
        cls_embeddings = last_hidden[:, 0, :]  # CLS token is first.

    return cls_embeddings.detach().cpu().numpy().astype(np.float32)


def _clip_id_from_path(clip_path: str) -> str:
    return Path(clip_path).stem


@dataclass
class ClipSemanticEmbedding:
    clip_id: str
    mean_embedding: np.ndarray  # (768,) mean of sample frames
    first_frame_embedding: np.ndarray  # (768,)
    last_frame_embedding: np.ndarray  # (768,)
    sample_frame_embeddings: np.ndarray  # (4, 768)


def _probe_duration(clip_path: str) -> float:
    """Return video duration via ffprobe, falling back to PyAV."""
    try:
        import subprocess
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                clip_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return float(out.strip())
    except Exception:
        try:
            import av
            container = av.open(clip_path)
            dur = float(container.duration / av.time_base)
            container.close()
            return dur
        except Exception:
            return 0.0


def embed_clip(
    clip_path: str,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    clip_id: Optional[str] = None,
) -> ClipSemanticEmbedding:
    """Compute DINO-v2 embeddings for a clip and cache them on disk."""
    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()
    clip_id = clip_id if clip_id is not None else _clip_id_from_path(clip_path)
    cache_file = cache_dir / f"{clip_id}.npz"

    if not force_refresh and cache_file.exists():
        try:
            data = np.load(cache_file)
            return ClipSemanticEmbedding(
                clip_id=clip_id,
                mean_embedding=data["mean_embedding"].astype(np.float32),
                first_frame_embedding=data["first_frame_embedding"].astype(np.float32),
                last_frame_embedding=data["last_frame_embedding"].astype(np.float32),
                sample_frame_embeddings=data["sample_frame_embeddings"].astype(np.float32),
            )
        except Exception as exc:
            logger.warning("clip_semantic_cache_corrupt", clip_id=clip_id, error=str(exc))

    duration = _probe_duration(clip_path)
    if duration <= 0.05:
        raise ValueError(f"Could not determine duration for {clip_path}")

    # Target timestamps.
    sample_times = [duration * p for p in (0.10, 0.30, 0.60, 0.90)]
    first_time = 0.02
    last_time = max(0.02, duration - 0.02)

    all_times = [first_time] + sample_times + [last_time]
    frames = [_read_frame_at(clip_path, t) for t in all_times]
    if any(f is None for f in frames):
        missing = [i for i, f in enumerate(frames) if f is None]
        raise RuntimeError(f"Failed to read frames at indices {missing} for {clip_path}")

    embeddings = _compute_embeddings_for_frames(frames)
    if embeddings.shape[0] != len(frames):
        raise RuntimeError(f"DINO embedding count mismatch for {clip_path}")

    first_emb = embeddings[0]
    sample_embs = embeddings[1:5]
    last_emb = embeddings[5]
    mean_emb = sample_embs.mean(axis=0)

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            cache_file,
            mean_embedding=mean_emb,
            first_frame_embedding=first_emb,
            last_frame_embedding=last_emb,
            sample_frame_embeddings=sample_embs,
        )
        logger.info("clip_semantic_cached", clip_id=clip_id, path=str(cache_file))
    except Exception as exc:
        logger.warning("clip_semantic_cache_write_failed", clip_id=clip_id, error=str(exc))

    return ClipSemanticEmbedding(
        clip_id=clip_id,
        mean_embedding=mean_emb,
        first_frame_embedding=first_emb,
        last_frame_embedding=last_emb,
        sample_frame_embeddings=sample_embs,
    )


def load_clip_embedding(
    clip_id: str,
    cache_dir: Optional[Path] = None,
) -> Optional[ClipSemanticEmbedding]:
    """Load a cached DINO-v2 embedding without running the model."""
    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()
    cache_file = cache_dir / f"{clip_id}.npz"
    if not cache_file.exists():
        return None
    try:
        data = np.load(cache_file)
        return ClipSemanticEmbedding(
            clip_id=clip_id,
            mean_embedding=data["mean_embedding"].astype(np.float32),
            first_frame_embedding=data["first_frame_embedding"].astype(np.float32),
            last_frame_embedding=data["last_frame_embedding"].astype(np.float32),
            sample_frame_embeddings=data["sample_frame_embeddings"].astype(np.float32),
        )
    except Exception as exc:
        logger.warning("clip_semantic_load_failed", clip_id=clip_id, error=str(exc))
        return None


def cosine_first_to_last(clip_a: ClipSemanticEmbedding, clip_b: ClipSemanticEmbedding) -> float:
    """Cosine similarity between clip A's last frame and clip B's first frame."""
    a = clip_a.last_frame_embedding
    b = clip_b.first_frame_embedding
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
