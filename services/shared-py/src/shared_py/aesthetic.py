# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Lazy-loaded LAION aesthetic predictor for scoring image frames."""

import os
from typing import Optional

import numpy as np

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("shared_py.aesthetic")

# LAION aesthetic predictor is a simple MLP on CLIP embeddings.  We ship a
# lightweight wrapper that falls back to a simple contrast/saturation heuristic
# when the predictor is unavailable, so heatmap generation never crashes.
_AESTHETIC_MODEL = None


def _load_aesthetic_model():
    global _AESTHETIC_MODEL
    if _AESTHETIC_MODEL is not None:
        return _AESTHETIC_MODEL

    try:
        import clip

        model_path = os.environ.get("AVE_AESTHETIC_MODEL_PATH")
        if model_path and os.path.exists(model_path):
            logger.info("Loading LAION aesthetic predictor", path=model_path)
            # The LAION predictor is a shallow MLP; load it as a numpy dict.
            _AESTHETIC_MODEL = dict(np.load(model_path, allow_pickle=True))
            return _AESTHETIC_MODEL
    except Exception as e:
        logger.warning("Could not load LAION aesthetic predictor", error=str(e))

    _AESTHETIC_MODEL = False
    return _AESTHETIC_MODEL


def _heuristic_score(bgr_frame: np.ndarray) -> float:
    """Fallback aesthetic score based on contrast, saturation, and composition."""
    try:
        import cv2
    except ImportError:
        return 0.5

    lab = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    contrast = float(l.std()) / 128.0

    hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV).astype(np.float32) / 255.0
    saturation = float(hsv[:, :, 1].mean())

    # Slight center-bias (rule of thirds / subject in center is generally pleasing).
    h, w = bgr_frame.shape[:2]
    center_crop = bgr_frame[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
    center_brightness = float(cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY).mean()) / 255.0

    score = 0.45 * contrast + 0.35 * saturation + 0.20 * center_brightness
    return float(np.clip(score, 0.0, 1.0))


def score_image(bgr_frame: np.ndarray) -> float:
    """Return a 0..1 aesthetic score for a BGR frame.

    Uses the LAION aesthetic predictor if available and configured; otherwise
    falls back to a fast heuristic.
    """
    model = _load_aesthetic_model()
    if not model:
        return _heuristic_score(bgr_frame)

    try:
        import clip
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        clip_model, preprocess = clip.load("ViT-B/32", device=device)

        import cv2
        from PIL import Image

        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        image_tensor = preprocess(pil).unsqueeze(0).to(device)

        with torch.no_grad():
            image_features = clip_model.encode_image(image_tensor)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # Predict with a simple linear head if weights are present.
        weights = model.get("weights")
        bias = model.get("bias")
        if weights is not None and bias is not None:
            score = float(np.dot(image_features.cpu().numpy(), weights.T) + bias)
            # LAION predictor is roughly in [0, 10]; normalize to [0, 1].
            return float(np.clip(score / 10.0, 0.0, 1.0))
    except Exception as e:
        logger.warning("Aesthetic model inference failed, using heuristic", error=str(e))

    return _heuristic_score(bgr_frame)
