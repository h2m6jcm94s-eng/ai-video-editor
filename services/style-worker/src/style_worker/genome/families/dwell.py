# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Dwell / subject-presence feature family for the Style Genome."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    import cv2
except Exception:  # pragma: no cover - optional dep
    cv2 = None  # type: ignore[assignment]

from shared_py.logging_config import StructuredLogger
from shared_py.models import DwellFamily, ShotBoundary

logger = StructuredLogger("style_worker.genome.families.dwell")


def _face_area_ratio(face: dict) -> float:
    """Best-effort normalized face area from detection metadata."""
    if "face_area_ratio" in face:
        return float(face["face_area_ratio"])

    bbox = face.get("bbox") or face.get("bbox_norm") or []
    if len(bbox) >= 4:
        x1, y1, x2, y2 = bbox[:4]
        area = max(0.0, (x2 - x1) * (y2 - y1))
        # If bbox_norm, area is already normalized; otherwise unknown frame size.
        if "bbox_norm" in face:
            return min(area, 1.0)
        return min(area / 1_000_000.0, 1.0)
    return 0.0


def _faces_from_project_clips(project_clips: Optional[Dict[str, Any]]) -> List[dict]:
    faces: List[dict] = []
    if not project_clips:
        return faces
    for _clip_id, meta in project_clips.items():
        if not isinstance(meta, dict):
            continue
        for face in meta.get("faces") or []:
            if isinstance(face, dict):
                faces.append(face)
    return faces


def _sample_video_faces(video_path: str, video_info: dict) -> List[dict]:
    """Sample the reference video and run a lightweight face detector if available."""
    try:
        from ingest_worker.identity import _get_face_app
    except Exception as exc:  # pragma: no cover - cross-service dep optional
        logger.debug("ingest_worker.identity not available for dwell genome", error=str(exc))
        return []

    app = _get_face_app()
    if app is None:
        return []
    if cv2 is None:
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning("Could not open video for dwell sampling: %s", video_path)
        return []

    fps = video_info.get("fps") or float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    sample_interval = max(1, int(round(fps / 2.0)))

    faces = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample_interval == 0:
            try:
                detected = app.get(frame)
            except Exception as exc:  # pragma: no cover - runtime inference failure
                logger.warning("Face inference failed at frame %d: %s", frame_idx, exc)
                detected = []
            for face in detected:
                bbox = [float(v) for v in face.bbox.flatten().tolist()]
                x1, y1, x2, y2 = bbox
                faces.append({
                    "face_area_ratio": max(0.0, (x2 - x1) * (y2 - y1)) / max(1.0, float(frame.shape[0] * frame.shape[1])),
                    "confidence": float(face.det_score),
                })
        frame_idx += 1

    cap.release()
    return faces


def _per_shot_face_counts(
    video_path: str,
    shot_boundaries: List[ShotBoundary],
    video_info: dict,
) -> List[int]:
    """Return max face count observed in each shot, using the same InsightFace path."""
    try:
        from ingest_worker.identity import _get_face_app
    except Exception:
        return [0] * len(shot_boundaries)

    app = _get_face_app()
    if app is None or cv2 is None:
        return [0] * len(shot_boundaries)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return [0] * len(shot_boundaries)

    fps = video_info.get("fps") or float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_interval = max(1, int(round(fps / 2.0)))

    counts = []
    for shot in shot_boundaries:
        max_faces = 0
        start = max(0, shot.start_frame)
        end = min(shot.end_frame, total_frames)
        for frame_idx in range(start, end, sample_interval):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            try:
                detected = app.get(frame)
            except Exception:
                detected = []
            max_faces = max(max_faces, len(detected))
        counts.append(max_faces)

    cap.release()
    return counts


def extract_dwell_genome(
    video_path: str,
    project_clips: Optional[Dict[str, Any]],
    shot_boundaries: List[ShotBoundary],
    video_info: dict,
) -> DwellFamily:
    """Extract the 8 dwell features."""
    faces = _faces_from_project_clips(project_clips)
    if not faces:
        faces = _sample_video_faces(video_path, video_info)

    ratios = [_face_area_ratio(f) for f in faces]
    n = len(ratios)

    avg_face_size = sum(ratios) / n if n else 0.0
    max_face_size = max(ratios) if ratios else 0.0
    variance = 0.0
    if n > 1:
        variance = sum((r - avg_face_size) ** 2 for r in ratios) / (n - 1)

    shot_face_counts = _per_shot_face_counts(video_path, shot_boundaries, video_info)
    shots_with_face = sum(1 for c in shot_face_counts if c > 0)
    pct_shots_with_face = shots_with_face / len(shot_boundaries) if shot_boundaries else 0.0
    avg_subjects_per_shot = sum(shot_face_counts) / len(shot_face_counts) if shot_face_counts else 0.0
    avg_shot_subject_count = avg_subjects_per_shot

    # Without identity tracking we cannot accurately measure screen time or
    # protagonist presence; v0 returns zeros when no tracked faces are supplied.
    avg_face_screen_time_s = 0.0
    protagonist_present_ratio = 1.0 if pct_shots_with_face > 0.5 else 0.0

    return DwellFamily(
        avg_face_size_ratio=avg_face_size,
        max_face_size_ratio=max_face_size,
        avg_subjects_per_shot=avg_subjects_per_shot,
        pct_shots_with_face=pct_shots_with_face,
        avg_face_screen_time_s=avg_face_screen_time_s,
        protagonist_present_ratio=protagonist_present_ratio,
        avg_shot_subject_count=avg_shot_subject_count,
        face_size_variance=variance,
    )
