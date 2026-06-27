# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Face detection and embedding extraction using InsightFace.

The module is designed to be importable even when InsightFace, ONNXRuntime or
CUDA are missing.  Inference only runs when dependencies are present; otherwise
it logs a warning and returns empty results.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from typing import Dict, List, Optional

try:
    import cv2

    _CV2 = True
except Exception:  # pragma: no cover - optional dep
    _CV2 = False

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dep
    np = None  # type: ignore[assignment]

try:
    from insightface.app import FaceAnalysis

    _INSIGHTFACE = True
except Exception:  # pragma: no cover - optional dep
    _INSIGHTFACE = False

logger = logging.getLogger(__name__)

FACE_APP_PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]
DEFAULT_SAMPLE_FPS = 2.0


@dataclasses.dataclass
class FaceDetection:
    """A single face detected in a clip."""

    clip_id: str
    frame_idx: int
    t_s: float
    bbox: List[float]
    bbox_norm: List[float]
    embedding: List[float]
    confidence: float
    face_area_ratio: float


_face_app: Optional[object] = None


def _get_face_app() -> Optional[object]:
    """Return a cached InsightFace FaceAnalysis instance, or None if unavailable."""
    global _face_app
    if _face_app is not None:
        return _face_app
    if not _INSIGHTFACE:
        logger.warning("insightface not available; face extraction disabled")
        return None
    try:
        app = FaceAnalysis(name="buffalo_l", providers=FACE_APP_PROVIDERS)
        app.prepare(ctx_id=0, det_size=(640, 640))
        _face_app = app
        return app
    except Exception as exc:  # pragma: no cover - model/load failure
        logger.warning("Failed to initialize InsightFace: %s", exc)
        return None


def cache_path_for_clip(clip_path: str) -> str:
    """Return the JSON cache path for a given clip file."""
    return f"{clip_path}.faces.json"


def _process_frame_batch(
    app: object,
    frames: List[tuple[int, object, float]],
    clip_id: str,
    width: int,
    height: int,
    frame_area: float,
) -> List[FaceDetection]:
    """Run InsightFace on a buffered batch of frames and return detections."""
    detections: List[FaceDetection] = []
    for frame_idx, frame, t_s in frames:
        try:
            faces = app.get(frame)
        except Exception as exc:  # pragma: no cover - runtime inference failure
            logger.warning("InsightFace inference failed at frame %d: %s", frame_idx, exc)
            faces = []
        for face in faces:
            bbox = [float(v) for v in face.bbox.flatten().tolist()]
            x1, y1, x2, y2 = bbox
            face_area = max(0.0, (x2 - x1) * (y2 - y1))
            face_area_ratio = face_area / frame_area
            bbox_norm = [
                x1 / max(1, width),
                y1 / max(1, height),
                x2 / max(1, width),
                y2 / max(1, height),
            ]
            embedding = [float(v) for v in face.embedding.flatten().tolist()]
            confidence = float(face.det_score)
            detections.append(
                FaceDetection(
                    clip_id=clip_id,
                    frame_idx=frame_idx,
                    t_s=t_s,
                    bbox=bbox,
                    bbox_norm=bbox_norm,
                    embedding=embedding,
                    confidence=confidence,
                    face_area_ratio=face_area_ratio,
                )
            )
    return detections


def _open_clip(clip_path: str):
    """Open a video capture and return metadata, or None on failure."""
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        logger.warning("Could not open video for face extraction: %s", clip_path)
        return None
    video_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return cap, video_fps, total_frames, width, height


def extract_faces_from_clip(
    clip_path: str,
    clip_id: str,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
) -> List[FaceDetection]:
    """Sample frames from a clip and extract face embeddings.

    Frames are sampled at ``sample_fps`` to keep compute reasonable while still
    capturing the subject across the clip duration.
    """
    results = extract_faces_from_clips(
        {clip_id: clip_path},
        sample_fps=sample_fps,
    )
    return results.get(clip_id, [])


def extract_faces_from_clips(
    clip_paths: Dict[str, str],
    sample_fps: float = DEFAULT_SAMPLE_FPS,
    max_batch_frames: int = 64,
) -> Dict[str, List[FaceDetection]]:
    """Sample frames from multiple clips and extract face embeddings.

    Frames are sampled at ``sample_fps`` for each clip.  The implementation
    buffers sampled frames into chunks of ``max_batch_frames`` so that future
    backends (TensorRT / FastAPI) can process a chunk as a single GPU batch.
    With the current InsightFace ``FaceAnalysis.get`` API each frame is still
    submitted individually, but all clips share one model session and cache
    writes are batched per clip.
    """
    results: Dict[str, List[FaceDetection]] = {clip_id: [] for clip_id in clip_paths}
    if not _CV2:
        logger.warning("cv2 not available; cannot extract faces")
        return results
    if np is None:
        logger.warning("numpy not available; cannot extract faces")
        return results

    app = _get_face_app()
    if app is None:
        return results

    for clip_id, clip_path in clip_paths.items():
        opened = _open_clip(clip_path)
        if opened is None:
            continue
        cap, video_fps, total_frames, width, height = opened
        frame_area = max(1.0, float(width * height))
        sample_interval = max(1, int(round(video_fps / sample_fps)))

        frames_buffer: List[tuple[int, object, float]] = []
        frame_idx = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % sample_interval == 0:
                    t_s = frame_idx / video_fps
                    frames_buffer.append((frame_idx, frame, t_s))
                    if len(frames_buffer) >= max_batch_frames:
                        results[clip_id].extend(
                            _process_frame_batch(
                                app, frames_buffer, clip_id, width, height, frame_area
                            )
                        )
                        frames_buffer = []
                frame_idx += 1
                if frame_idx > total_frames + 10:
                    break
            if frames_buffer:
                results[clip_id].extend(
                    _process_frame_batch(
                        app, frames_buffer, clip_id, width, height, frame_area
                    )
                )
        finally:
            cap.release()

    return results


def _detection_to_dict(fd: FaceDetection) -> dict:
    return dataclasses.asdict(fd)


def _detection_from_dict(data: dict) -> FaceDetection:
    return FaceDetection(**data)


def _load_face_cache(cache_path: str) -> Optional[List[FaceDetection]]:
    """Load cached detections if the file exists and is valid."""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [_detection_from_dict(item) for item in data]
    except Exception as exc:
        logger.warning("Failed to load face cache %s: %s", cache_path, exc)
    return None


def _write_face_cache(cache_path: str, faces: List[FaceDetection]) -> None:
    """Write detections to the JSON cache."""
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump([_detection_to_dict(fd) for fd in faces], f)
    except Exception as exc:
        logger.warning("Failed to write face cache %s: %s", cache_path, exc)


def ensure_faces(
    clip_path: str,
    clip_id: str,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
) -> List[FaceDetection]:
    """Load cached face detections for a clip, or extract and cache them."""
    cache_path = cache_path_for_clip(clip_path)
    cached = _load_face_cache(cache_path)
    if cached is not None:
        return cached

    faces = extract_faces_from_clip(clip_path, clip_id, sample_fps=sample_fps)
    _write_face_cache(cache_path, faces)
    return faces


def ensure_faces_for_clips(
    clip_paths: Dict[str, str],
    sample_fps: float = DEFAULT_SAMPLE_FPS,
) -> Dict[str, List[FaceDetection]]:
    """Load cached face detections for multiple clips, extracting missing ones.

    Extraction is performed in one batched pass so model initialization and GPU
    context setup happen once for the whole set.
    """
    results: Dict[str, List[FaceDetection]] = {}
    missing: Dict[str, str] = {}

    for clip_id, clip_path in clip_paths.items():
        cache_path = cache_path_for_clip(clip_path)
        cached = _load_face_cache(cache_path)
        if cached is not None:
            results[clip_id] = cached
        else:
            missing[clip_id] = clip_path

    if missing:
        extracted = extract_faces_from_clips(missing, sample_fps=sample_fps)
        for clip_id, faces in extracted.items():
            cache_path = cache_path_for_clip(clip_paths[clip_id])
            _write_face_cache(cache_path, faces)
            results[clip_id] = faces

    return results
