# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""SAM3 segmentation engine with lazy imports and graceful fallback.

The engine is designed to be importable even when SAM3, CUDA, or the HF
checkpoints are missing.  Heavy dependencies are only loaded on first use.
"""

from __future__ import annotations

import base64
import io
import os
from typing import Any, Optional

try:
    import numpy as np
    from PIL import Image

    _IMAGE_LIBS = True
except Exception:  # pragma: no cover - optional deps
    _IMAGE_LIBS = False

try:
    import torch

    _TORCH = True
except Exception:  # pragma: no cover - optional deps
    _TORCH = False

_SAM3_IMAGE_MODEL = None
_SAM3_PROCESSOR = None
_SAM3_VIDEO_PREDICTOR = None


def _load_sam3_modules() -> dict[str, Any]:
    """Lazy-load SAM3 modules; returns {} if SAM3 is not installed."""
    try:
        from sam3.model_builder import build_sam3_image_model, build_sam3_video_predictor
        from sam3.model.sam3_image_processor import Sam3Processor

        return {
            "build_sam3_image_model": build_sam3_image_model,
            "build_sam3_video_predictor": build_sam3_video_predictor,
            "Sam3Processor": Sam3Processor,
        }
    except Exception:
        return {}


def _image_model() -> Optional[tuple[Any, Any]]:
    """Singleton image model + processor."""
    global _SAM3_IMAGE_MODEL, _SAM3_PROCESSOR
    if _SAM3_IMAGE_MODEL is not None:
        return _SAM3_IMAGE_MODEL, _SAM3_PROCESSOR

    modules = _load_sam3_modules()
    if not modules:
        return None

    build = modules["build_sam3_image_model"]
    processor_cls = modules["Sam3Processor"]
    _SAM3_IMAGE_MODEL = build()
    _SAM3_PROCESSOR = processor_cls(_SAM3_IMAGE_MODEL)
    return _SAM3_IMAGE_MODEL, _SAM3_PROCESSOR


def _video_predictor() -> Optional[Any]:
    """Singleton video predictor."""
    global _SAM3_VIDEO_PREDICTOR
    if _SAM3_VIDEO_PREDICTOR is not None:
        return _SAM3_VIDEO_PREDICTOR

    modules = _load_sam3_modules()
    if not modules:
        return None

    _SAM3_VIDEO_PREDICTOR = modules["build_sam3_video_predictor"]()
    return _SAM3_VIDEO_PREDICTOR


def _skip(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "skipped": True,
        "skipped_reason": reason,
        "masks": [],
        "boxes": [],
        "scores": [],
    }


def is_segmentation_available() -> bool:
    """Return True if SAM3 image inference can be attempted."""
    if not _IMAGE_LIBS or not _TORCH:
        return False
    modules = _load_sam3_modules()
    if not modules:
        return False
    # HF_TOKEN is required to download gated checkpoints unless a local path is provided.
    if not os.environ.get("HF_TOKEN") and not os.environ.get("SAM3_CHECKPOINT_PATH"):
        return False
    return True


def _mask_to_base64(mask: Any) -> Optional[str]:
    """Convert a SAM3 mask tensor/array to a base64 PNG string."""
    try:
        if hasattr(mask, "detach"):
            mask = mask.detach().cpu().numpy()
        if not isinstance(mask, np.ndarray):
            mask = np.asarray(mask)
        # SAM3 masks are often boolean or float in [0, 1].
        if mask.dtype != np.uint8:
            mask = (mask > 0).astype(np.uint8) * 255
        if mask.ndim == 3 and mask.shape[0] in (1, 3):
            mask = mask.transpose(1, 2, 0)
        if mask.ndim == 3 and mask.shape[-1] == 1:
            mask = mask.squeeze(-1)
        img = Image.fromarray(mask)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # pragma: no cover - serialization best-effort
        return None


def detect_subject_mask_image(
    image_path: str,
    prompt: str,
    version: str = "sam3",
) -> dict[str, Any]:
    """Run open-vocabulary segmentation on a single image.

    Returns a serializable dict.  If SAM3 is unavailable the dict contains a
    ``skipped_reason`` field and ``available=False``.
    """
    if not is_segmentation_available():
        return _skip("SAM3 is not installed or HF_TOKEN/SAM3_CHECKPOINT_PATH is missing")

    model_proc = _image_model()
    if model_proc is None:
        return _skip("Failed to load SAM3 image model")

    _, processor = model_proc
    try:
        image = Image.open(image_path).convert("RGB")
        state = processor.set_image(image)
        output = processor.set_text_prompt(state=state, prompt=prompt)

        masks = output.get("masks", [])
        boxes = output.get("boxes", [])
        scores = output.get("scores", [])

        # Normalize boxes and scores to plain Python types.
        def _to_list(value: Any) -> list:
            if hasattr(value, "detach"):
                value = value.detach().cpu().tolist()
            elif hasattr(value, "tolist"):
                value = value.tolist()
            return list(value) if value is not None else []

        return {
            "available": True,
            "skipped": False,
            "masks": [_mask_to_base64(m) for m in masks],
            "boxes": [_to_list(b) for b in boxes],
            "scores": [_to_list(s) for s in scores],
        }
    except Exception as exc:  # pragma: no cover - SAM3 runtime errors
        return _skip(f"SAM3 image inference failed: {exc}")


def detect_subject_mask_video(
    video_path: str,
    prompt: str,
    frame_index: int = 0,
    version: str = "sam3.1",
) -> dict[str, Any]:
    """Run open-vocabulary segmentation + tracking on a video.

    This is a best-effort implementation that propagates a text prompt on the
    requested frame.  It returns base64-encoded PNG masks per frame.
    """
    if not is_segmentation_available():
        return _skip("SAM3 is not installed or HF_TOKEN/SAM3_CHECKPOINT_PATH is missing")

    predictor = _video_predictor()
    if predictor is None:
        return _skip("Failed to load SAM3 video predictor")

    try:
        start = predictor.handle_request(
            {"type": "start_session", "resource_path": video_path}
        )
        session_id = start.get("session_id")
        if not session_id:
            return _skip("SAM3 video predictor did not return a session id")

        predictor.handle_request(
            {
                "type": "add_prompt",
                "session_id": session_id,
                "frame_index": frame_index,
                "text": prompt,
            }
        )

        masks_by_frame: dict[int, list[str]] = {}
        for out in predictor.handle_stream_request(
            {"type": "propagate_in_video", "session_id": session_id}
        ):
            outputs = out.get("outputs", {})
            frame_idx = out.get("frame_index", 0)
            masks = outputs.get("out_binary_masks", [])
            masks_by_frame[frame_idx] = [
                m for m in (_mask_to_base64(mask) for mask in masks) if m
            ]

        return {
            "available": True,
            "skipped": False,
            "masks_by_frame": masks_by_frame,
        }
    except Exception as exc:  # pragma: no cover - SAM3 runtime errors
        return _skip(f"SAM3 video inference failed: {exc}")
