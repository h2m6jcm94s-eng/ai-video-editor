# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Face-aware helpers for text placement and effect safety.

All helpers fail open: if face cache is missing or unreadable, they return
safe defaults that do not block the render.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

from shared_py.models import Slot


def load_face_detections(clip_path: str) -> List[dict]:
    """Load cached InsightFace detections for a clip."""
    cache_path = f"{clip_path}.faces.json"
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _detections_in_window(
    detections: List[dict],
    window_start_s: float,
    window_end_s: float,
) -> List[dict]:
    """Return detections whose timestamp falls inside the window."""
    return [
        det
        for det in detections
        if window_start_s <= float(det.get("t_s", -1.0)) <= window_end_s
    ]


def face_region_in_window(
    clip_path: str,
    window_start_s: float,
    window_end_s: float,
) -> dict:
    """Aggregate face geometry inside a clip time window.

    Returns a dict with ``area_ratio`` (max face area), ``center_x``,
    ``center_y`` (average bbox center), and ``count``.
    """
    detections = load_face_detections(clip_path)
    in_window = _detections_in_window(detections, window_start_s, window_end_s)
    if not in_window:
        return {"area_ratio": 0.0, "center_x": 0.5, "center_y": 0.5, "count": 0}

    centers_x = []
    centers_y = []
    max_area = 0.0
    for det in in_window:
        bbox = det.get("bbox_norm") or det.get("bbox") or []
        if len(bbox) < 4:
            continue
        x1, y1, x2, y2 = bbox[:4]
        area = float(det.get("face_area_ratio", (x2 - x1) * (y2 - y1)))
        max_area = max(max_area, area)
        centers_x.append((x1 + x2) * 0.5)
        centers_y.append((y1 + y2) * 0.5)

    if not centers_x:
        return {"area_ratio": 0.0, "center_x": 0.5, "center_y": 0.5, "count": 0}

    return {
        "area_ratio": max_area,
        "center_x": sum(centers_x) / len(centers_x),
        "center_y": sum(centers_y) / len(centers_y),
        "count": len(in_window),
    }


def choose_text_z_layer(slot: Slot, clip_paths: Optional[Dict[str, str]] = None) -> str:
    """Return ``behind_subject`` only when a face + mask are available."""
    if not slot.selected_clip_id:
        return "on_top"
    if not (slot.mask_asset_id and slot.mask_enabled):
        return "on_top"
    clip_path = (clip_paths or {}).get(slot.selected_clip_id)
    if not clip_path:
        return "on_top"

    window_start = slot.source_window_start_s or 0.0
    window_end = window_start + max(0.1, slot.duration_s)
    region = face_region_in_window(clip_path, window_start, window_end)
    if region["area_ratio"] >= 0.02:
        return "behind_subject"
    return "on_top"


def safe_zoom_center(
    face_region: dict,
    default: Tuple[float, float] = (0.5, 0.5),
) -> Tuple[float, float]:
    """Compute a crop center that keeps detected faces inside a zoom window.

    The center is pulled toward the face center so small faces stay in frame,
    but clamped to keep the crop within the image.
    """
    pull = 0.6
    fx, fy = face_region.get("center_x", 0.5), face_region.get("center_y", 0.5)
    dx = default[0] + (fx - default[0]) * pull
    dy = default[1] + (fy - default[1]) * pull
    return (max(0.25, min(0.75, dx)), max(0.25, min(0.75, dy)))
