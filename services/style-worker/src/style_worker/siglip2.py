# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""SigLIP-2 cross-modal text-to-clip embeddings for semantic clip ranking.

Used as a fallback when Marengo text-to-video embeddings are unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("style_worker.siglip2")

os.environ.setdefault("HF_HOME", r"E:\hf-cache")

_MODEL_NAME = "google/siglip2-base-patch16-256"
_MAX_TEXT_LENGTH = 64

# Lazy singletons.
_siglip_processor: Optional[object] = None
_siglip_model: Optional[object] = None
_siglip_device: Optional[str] = None


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "siglip2_clip"


def _load_model() -> Tuple[object, object, str]:
    """Load the SigLIP-2 processor and model."""
    global _siglip_processor, _siglip_model, _siglip_device
    if _siglip_model is not None:
        return _siglip_processor, _siglip_model, _siglip_device

    import torch
    from transformers import AutoModel, AutoProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("loading_siglip2", model=_MODEL_NAME, device=device)
    _siglip_processor = AutoProcessor.from_pretrained(_MODEL_NAME)
    _siglip_model = AutoModel.from_pretrained(_MODEL_NAME).to(device).eval()
    _siglip_device = device
    return _siglip_processor, _siglip_model, device


def _clip_id_from_path(clip_path: str) -> str:
    return Path(clip_path).stem


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


def _read_frame_at(clip_path: str, target_s: float) -> Optional["Image"]:
    """Decode a single frame near ``target_s`` using PyAV."""
    try:
        import av
        from PIL import Image
    except Exception as exc:
        logger.warning("siglip2_import_failed", error=str(exc))
        return None

    try:
        container = av.open(clip_path)
        video_stream = container.streams.video[0]
        time_base = float(video_stream.time_base)
        target_tb = int(target_s / time_base)
        container.seek(target_tb, stream=video_stream)

        for frame in container.decode(video_stream):
            frame_s = float(frame.pts * time_base)
            if frame_s >= target_s - 0.1:
                return frame.to_image()
        return None
    except Exception as exc:
        logger.warning("siglip2_frame_read_failed", path=clip_path, target_s=target_s, error=str(exc))
        return None
    finally:
        try:
            container.close()
        except Exception:
            pass


def _normalize(emb: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(emb, axis=-1, keepdims=True)
    return emb / np.where(norm == 0, 1, norm)


def embed_text(query: str) -> np.ndarray:
    """Encode a text query into a normalized SigLIP-2 text embedding."""
    processor, model, device = _load_model()
    import torch

    text = query[:_MAX_TEXT_LENGTH]
    inputs = processor(text=[text], return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        text_embeds = model.get_text_features(**inputs).squeeze(0)

    emb = text_embeds.detach().cpu().numpy().astype(np.float32)
    return _normalize(emb)


def embed_video_frames(
    clip_path: str,
    n_frames: int = 8,
    cache_dir: Optional[Path] = None,
    clip_id: Optional[str] = None,
) -> np.ndarray:
    """Encode ``n_frames`` evenly sampled frames and return mean-pooled embedding.

    Results are cached under ``<cache_dir>/<clip_id>.npy``.
    """
    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()
    clip_id = clip_id if clip_id is not None else _clip_id_from_path(clip_path)
    cache_file = cache_dir / f"{clip_id}.npy"

    if cache_file.exists():
        try:
            return np.load(cache_file).astype(np.float32)
        except Exception as exc:
            logger.warning("siglip2_cache_corrupt", clip_id=clip_id, error=str(exc))

    duration = _probe_duration(clip_path)
    if duration <= 0.05:
        raise ValueError(f"Could not determine duration for {clip_path}")

    if n_frames <= 1:
        times = [duration / 2]
    else:
        times = [duration * i / (n_frames - 1) for i in range(n_frames)]

    frames = []
    for t in times:
        frame = _read_frame_at(clip_path, t)
        if frame is not None:
            frames.append(frame)
    if not frames:
        raise RuntimeError(f"Could not decode any frames from {clip_path}")

    processor, model, device = _load_model()
    import torch

    # Processor accepts a list of PIL images.
    inputs = processor(images=frames, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        image_embeds = model.get_image_features(**inputs)  # (n_frames, dim)

    emb = image_embeds.detach().cpu().numpy().astype(np.float32)
    mean_emb = _normalize(emb.mean(axis=0))

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(cache_file, mean_emb)
        logger.info("siglip2_cached", clip_id=clip_id, path=str(cache_file))
    except Exception as exc:
        logger.warning("siglip2_cache_write_failed", clip_id=clip_id, error=str(exc))

    return mean_emb


def cosine_text_to_clip(query: str, clip_path: str) -> float:
    """Cosine similarity between a text query and a clip's video embedding."""
    text_emb = embed_text(query)
    clip_emb = embed_video_frames(clip_path)
    return float(np.dot(text_emb, clip_emb))
