# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Async HTTP client for the SAM3 segmentation server."""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

SAM3_URL = os.environ.get("SAM3_SERVER_URL", "http://localhost:8189")
SAM3_MASK_CACHE_DIR = Path(os.environ.get("SAM3_MASK_CACHE_DIR", r"E:\ai-video-editor-storage\sam3_masks"))
DEFAULT_SAM_VERSION = "sam3.1"


class Sam3UnavailableError(RuntimeError):
    """Raised when the SAM3 server is unreachable or unhealthy."""


@dataclass
class SegmentationResult:
    """Container for SAM3 segmentation output.

    Attributes:
        masks: Binary masks, usually as a list of base64-encoded PNG strings or
            paths to per-frame mask files depending on the caller's contract.
        boxes: Bounding boxes in [x1, y1, x2, y2] format.
        scores: Confidence scores for each detected mask.
        prompt_type: One of ``text``, ``box``, ``point``.
        prompt: The original prompt value sent to SAM3.
        cache_path: Optional path to a locally cached ``.npz`` result.
    """

    masks: list[Any]
    boxes: list[list[float]]
    scores: list[float]
    prompt_type: str
    prompt: Any
    cache_path: Optional[str] = None


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _result_cache_key(clip_path: str, prompt: Any, prompt_type: str, version: str) -> str:
    """Stable cache key derived from clip, prompt, and SAM version."""
    clip_hash = _sha256(clip_path.encode("utf-8"))
    prompt_hash = _sha256(str(prompt).encode("utf-8"))
    combined = f"{clip_hash}:{prompt_hash}:{prompt_type}:{version}".encode("utf-8")
    return _sha256(combined)


def _cache_path(clip_path: str, prompt: Any, prompt_type: str, version: str) -> Path:
    key = _result_cache_key(clip_path, prompt, prompt_type, version)
    SAM3_MASK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return SAM3_MASK_CACHE_DIR / f"{key}.npz"


def _load_cached_result(cache_path: Path) -> Optional[SegmentationResult]:
    """Load a cached result from disk if available."""
    try:
        import numpy as np
    except Exception:  # pragma: no cover - optional dep
        return None

    if not cache_path.exists():
        return None

    try:
        data = np.load(cache_path, allow_pickle=True)
        return SegmentationResult(
            masks=list(data.get("masks", [])),
            boxes=[list(b) for b in data.get("boxes", [])],
            scores=list(data.get("scores", [])),
            prompt_type=str(data.get("prompt_type", "text")),
            prompt=data.get("prompt"),
            cache_path=str(cache_path),
        )
    except Exception as exc:
        logger.warning("Failed to load cached SAM3 result from %s: %s", cache_path, exc)
        return None


def _save_cached_result(cache_path: Path, result: SegmentationResult) -> None:
    """Save a result to disk cache."""
    try:
        import numpy as np
    except Exception:  # pragma: no cover - optional dep
        return

    try:
        np.savez(
            cache_path,
            masks=np.asarray(result.masks, dtype=object),
            boxes=np.asarray(result.boxes, dtype=object) if result.boxes else np.asarray([]),
            scores=np.asarray(result.scores),
            prompt_type=result.prompt_type,
            prompt=result.prompt,
        )
    except Exception as exc:
        logger.warning("Failed to cache SAM3 result to %s: %s", cache_path, exc)


def _sam3_endpoint(prompt_type: str) -> str:
    """Map prompt type to the SAM3 server endpoint path."""
    mapping = {
        "text": "/segment_video_text",
        "box": "/segment_video_box",
        "point": "/segment_video_point",
    }
    endpoint = mapping.get(prompt_type)
    if endpoint is None:
        raise ValueError(
            f"Unsupported prompt_type {prompt_type!r}; must be one of {set(mapping)}"
        )
    return endpoint


def _build_request_payload(prompt_type: str, prompt: Any, clip_path: str) -> dict[str, Any]:
    """Build the JSON payload for a SAM3 video segmentation request."""
    payload: dict[str, Any] = {"video_path": clip_path}
    if prompt_type == "text":
        payload["text"] = str(prompt)
    elif prompt_type == "box":
        payload["box"] = list(prompt)
    elif prompt_type == "point":
        payload["point"] = list(prompt)
    return payload


async def sam3_available(base_url: Optional[str] = None, client: Optional[httpx.AsyncClient] = None) -> bool:
    """Check whether the SAM3 server is reachable and healthy.

    Returns True if the health endpoint responds with a 2xx status. Raises
    ``Sam3UnavailableError`` when the server cannot be reached.
    """
    url = (base_url or SAM3_URL).rstrip("/") + "/health"
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=5.0)
    try:
        response = await c.get(url)
        if response.status_code >= 500:
            raise Sam3UnavailableError(f"SAM3 server reported unhealthy status {response.status_code}")
        return response.is_success
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise Sam3UnavailableError(f"SAM3 server not reachable at {url}") from exc
    finally:
        if own_client:
            await c.aclose()


async def segment_object_in_clip(
    clip_path: str,
    prompt: Any,
    prompt_type: str = "text",
    *,
    base_url: Optional[str] = None,
    version: str = DEFAULT_SAM_VERSION,
    use_cache: bool = True,
    client: Optional[httpx.AsyncClient] = None,
) -> SegmentationResult:
    """Segment an object in a video clip using the SAM3 HTTP server.

    Args:
        clip_path: Absolute path to the source video clip.
        prompt: Text string, bounding box ``[x1, y1, x2, y2]``, or point ``[x, y]``.
        prompt_type: ``text`` | ``box`` | ``point``.
        base_url: Optional override for ``SAM3_SERVER_URL``.
        version: SAM model version used as part of the cache key.
        use_cache: Whether to read/write per-result ``.npz`` cache files.
        client: Optional shared ``httpx.AsyncClient``.

    Returns:
        A ``SegmentationResult`` with masks, boxes, scores, and metadata.

    Raises:
        Sam3UnavailableError: If the SAM3 server is unreachable.
        ValueError: If ``prompt_type`` is not supported.
    """
    cache_path = _cache_path(clip_path, prompt, prompt_type, version)

    if use_cache:
        cached = _load_cached_result(cache_path)
        if cached is not None:
            logger.debug("SAM3 cache hit for %s", clip_path)
            return cached

    url = (base_url or SAM3_URL).rstrip("/") + _sam3_endpoint(prompt_type)
    payload = _build_request_payload(prompt_type, prompt, clip_path)
    payload["version"] = version

    own_client = client is None
    c = client or httpx.AsyncClient(timeout=300.0)
    try:
        response = await c.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise Sam3UnavailableError(f"SAM3 server not reachable at {url}") from exc
    finally:
        if own_client:
            await c.aclose()

    result = SegmentationResult(
        masks=data.get("masks", []),
        boxes=data.get("boxes", []),
        scores=data.get("scores", []),
        prompt_type=prompt_type,
        prompt=prompt,
    )

    if use_cache:
        _save_cached_result(cache_path, result)
        result.cache_path = str(cache_path)

    return result
