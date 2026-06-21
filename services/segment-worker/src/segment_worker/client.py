# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Optional SAM3 segmentation client with lazy imports and graceful fallback."""

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


def _load_sam3_modules() -> dict[str, Any]:
    """Lazy-load SAM3 modules; returns {} if the package is not installed."""
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


def _resolve_device(preferred: Optional[str] = None) -> str:
    if preferred:
        return preferred
    if not _TORCH:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


class Sam3Segmenter:
    """Optional SAM3 client for text-prompted image/video segmentation.

    The class is designed to be importable and instantiable even when SAM3,
    PyTorch, or CUDA are missing. Inference only runs when ``available()`` is
    ``True``; otherwise the segmentation methods return a skipped result dict.
    """

    def __init__(
        self,
        checkpoint_path: Optional[str] = None,
        device: Optional[str] = None,
    ) -> None:
        self._modules: Optional[dict[str, Any]] = None
        self._image_model: Optional[Any] = None
        self._processor: Optional[Any] = None
        self._video_predictor: Optional[Any] = None
        self._checkpoint_path = checkpoint_path or os.environ.get("SAM3_CHECKPOINT_PATH") or ""
        self._device = _resolve_device(device)

    @property
    def device(self) -> str:
        return self._device

    def _ensure_modules(self) -> dict[str, Any]:
        if self._modules is None:
            self._modules = _load_sam3_modules()
        return self._modules

    def available(self) -> bool:
        """Return True if SAM3 inference can be attempted on this machine."""
        if not _IMAGE_LIBS or not _TORCH:
            return False
        modules = self._ensure_modules()
        if not modules:
            return False
        # Gated checkpoints need HF_TOKEN unless a local checkpoint is provided.
        if not self._checkpoint_path and not os.environ.get("HF_TOKEN"):
            return False
        return True

    # ------------------------------------------------------------------
    # Model singletons
    # ------------------------------------------------------------------
    def _get_image_model(self) -> Optional[tuple[Any, Any]]:
        """Return (image_model, processor) tuple, loading lazily."""
        if self._image_model is not None and self._processor is not None:
            return self._image_model, self._processor

        modules = self._ensure_modules()
        if not modules:
            return None

        try:
            build = modules["build_sam3_image_model"]
            processor_cls = modules["Sam3Processor"]
            model = build()
            if _TORCH and hasattr(model, "to"):
                model = model.to(self._device)
            self._image_model = model
            self._processor = processor_cls(model)
            return self._image_model, self._processor
        except Exception:
            return None

    def _get_video_predictor(self) -> Optional[Any]:
        """Return the video predictor singleton, loading lazily."""
        if self._video_predictor is not None:
            return self._video_predictor

        modules = self._ensure_modules()
        if not modules:
            return None

        try:
            build = modules["build_sam3_video_predictor"]
            self._video_predictor = build()
            return self._video_predictor
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Inference helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_list(value: Any) -> list:
        """Normalize tensor/array/list values to plain Python lists."""
        if value is None:
            return []
        if hasattr(value, "detach"):
            value = value.detach().cpu()
        if hasattr(value, "tolist"):
            value = value.tolist()
        return list(value)

    @staticmethod
    def _mask_to_base64(mask: Any) -> Optional[str]:
        """Convert a SAM3 mask tensor/array to a base64 PNG string."""
        try:
            if hasattr(mask, "detach"):
                mask = mask.detach().cpu().numpy()
            if not isinstance(mask, np.ndarray):
                mask = np.asarray(mask)
            # Guard against empty or degenerate masks before Image.fromarray crashes.
            if mask.size == 0 or mask.ndim < 2:
                return None
            # SAM3 masks are often boolean or float in [0, 1].
            if mask.dtype != np.uint8:
                mask = (mask > 0).astype(np.uint8) * 255
            if mask.ndim == 3 and mask.shape[0] in (1, 3):
                mask = mask.transpose(1, 2, 0)
            if mask.ndim == 3 and mask.shape[-1] == 1:
                mask = mask.squeeze(-1)
            if mask.ndim != 2:
                return None
            img = Image.fromarray(mask)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:  # pragma: no cover - serialization best-effort
            return None

    @staticmethod
    def _skip(reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "skipped": True,
            "skipped_reason": reason,
            "masks": [],
            "boxes": [],
            "scores": [],
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def segment_image(self, image_path: str, prompt: str) -> dict[str, Any]:
        """Run open-vocabulary segmentation on a single image.

        Returns a serializable dict. If SAM3 is unavailable the dict contains
        a ``skipped_reason`` field and ``available=False``.
        """
        if not self.available():
            return self._skip("SAM3 is not installed or HF_TOKEN/SAM3_CHECKPOINT_PATH is missing")

        model_proc = self._get_image_model()
        if model_proc is None:
            return self._skip("Failed to load SAM3 image model")

        _, processor = model_proc
        try:
            image = Image.open(image_path).convert("RGB")
            state = processor.set_image(image)
            output = processor.set_text_prompt(state=state, prompt=prompt)

            masks = output.get("masks", [])
            boxes = output.get("boxes", [])
            scores = output.get("scores", [])

            return {
                "available": True,
                "skipped": False,
                "masks": [m for m in (self._mask_to_base64(mask) for mask in masks) if m],
                "boxes": [self._to_list(b) for b in boxes],
                "scores": [self._to_list(s) for s in scores],
            }
        except Exception as exc:  # pragma: no cover - SAM3 runtime errors
            return self._skip(f"SAM3 image inference failed: {exc}")

    def segment_video(
        self,
        video_path: str,
        prompt: str,
        frame_index: int = 0,
    ) -> dict[str, Any]:
        """Run open-vocabulary segmentation + tracking on a video.

        Returns a serializable dict with base64-encoded PNG masks per frame.
        """
        if not self.available():
            return self._skip("SAM3 is not installed or HF_TOKEN/SAM3_CHECKPOINT_PATH is missing")

        predictor = self._get_video_predictor()
        if predictor is None:
            return self._skip("Failed to load SAM3 video predictor")

        try:
            start = predictor.handle_request(
                {"type": "start_session", "resource_path": video_path}
            )
            session_id = start.get("session_id")
            if not session_id:
                return self._skip("SAM3 video predictor did not return a session id")

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
                    m for m in (self._mask_to_base64(mask) for mask in masks) if m
                ]

            return {
                "available": True,
                "skipped": False,
                "masks_by_frame": masks_by_frame,
            }
        except Exception as exc:  # pragma: no cover - SAM3 runtime errors
            return self._skip(f"SAM3 video inference failed: {exc}")
