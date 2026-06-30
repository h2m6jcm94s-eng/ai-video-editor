# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Edit-intent classification and guardrails for prompt-based video edits."""

from __future__ import annotations

from typing import Any

from shared_py.llm_client import LLMClient, LLMTask


# Valid edit-intent labels returned by classify_edit_intent.
EDIT_INTENT_LABELS = {"color_shift", "texture_replace", "structural_change"}


def _client() -> LLMClient:
    return LLMClient(
        local_model="gemma4:12b",
        cloud_model="claude-3-5-haiku-20241022",
    )


def classify_edit_intent(text_prompt: str) -> str:
    """Classify a free-form edit prompt into one of three intent buckets.

    Returns one of: ``color_shift``, ``texture_replace``, ``structural_change``.
    Falls back to ``structural_change`` when the model response is ambiguous.
    """
    prompt = (
        "You are a video-edit intent classifier. "
        "Read the user's prompt and choose exactly one label from the list below. "
        "Respond with ONLY the label.\n\n"
        "Labels: color_shift, texture_replace, structural_change\n\n"
        f"Prompt: {text_prompt}\n\n"
        "Label:"
    )
    response = _client().complete(
        task=LLMTask.EDIT_INTENT_CLASSIFY,
        prompt=prompt,
        max_tokens=16,
        temperature=0.0,
        fallback_response="structural_change",
    )
    label = response.strip().lower().rstrip(".")
    for valid in EDIT_INTENT_LABELS:
        if valid in label:
            return valid
    return "structural_change"


def is_brand_ip_violation(prompt: str) -> bool:
    """Return True if the prompt appears to request a brand/IP violation."""
    full_prompt = (
        "You are a content-safety reviewer for a video editing assistant. "
        "Decide whether the following user prompt asks to create, imitate, or "
        "misuse a recognizable brand, character, logo, or protected IP in a way "
        "that would likely infringe.\n\n"
        "Respond with ONLY 'yes' or 'no'.\n\n"
        f"Prompt: {prompt}\n\n"
        "Violation:"
    )
    response = _client().complete(
        task=LLMTask.BRAND_IP_CHECK,
        prompt=full_prompt,
        max_tokens=8,
        temperature=0.0,
        fallback_response="no",
    )
    return response.strip().lower().startswith("yes")


def is_face_edit(sam_mask: Any, frame: Any) -> bool:
    """Detect whether the edit region intersects a human face.

    This is a placeholder gate. When MediaPipe is available the function
    returns True if any face bounding box overlaps the mask; otherwise it
    raises NotImplementedError so callers know explicit consent logic is
    required before proceeding.
    """
    try:
        import mediapipe as mp
    except ImportError as e:
        raise NotImplementedError(
            "Face-edit ethics gate requires mediapipe; install it or implement consent logic"
        ) from e

    # Lazy imports to avoid loading heavy vision modules at import time.
    import numpy as np

    np_mask = np.asarray(sam_mask) if not isinstance(sam_mask, np.ndarray) else sam_mask
    np_frame = np.asarray(frame) if not isinstance(frame, np.ndarray) else frame

    mp_face_detection = mp.solutions.face_detection
    detector = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    results = detector.process(np_frame)

    if not results or not results.detections:
        return False

    mask_indices = np.argwhere(np_mask > 0)
    if mask_indices.size == 0:
        return False

    height, width = np_mask.shape[:2]
    for detection in results.detections:
        bbox = detection.location_data.relative_bounding_box
        x1 = int(bbox.xmin * width)
        y1 = int(bbox.ymin * height)
        x2 = int((bbox.xmin + bbox.width) * width)
        y2 = int((bbox.ymin + bbox.height) * height)

        in_face = (
            (mask_indices[:, 1] >= x1)
            & (mask_indices[:, 1] <= x2)
            & (mask_indices[:, 0] >= y1)
            & (mask_indices[:, 0] <= y2)
        )
        if np.any(in_face):
            return True

    return False
