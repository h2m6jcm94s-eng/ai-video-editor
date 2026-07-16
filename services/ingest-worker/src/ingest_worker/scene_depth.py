# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Scene grouping and monocular depth estimation for video assets."""

import json
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np

from shared_py.logging_config import StructuredLogger
from shared_py.models import DepthAnalysis, DepthSample, Scene, SceneDepthAnalysis, ShotBoundary

logger = StructuredLogger("ingest_worker.scene_depth")

_DEPTH_MODEL: Optional[Tuple[Any, Any]] = None


def _cache_dir() -> Path:
    return Path(os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")) / "scene_depth"


def _analysis_cache_path(asset_id: str) -> Path:
    return _cache_dir() / f"{asset_id}_scene_depth.json"


def _load_depth_model():
    """Lazy-load MiDaS small; return (model, transform) or None on failure."""
    global _DEPTH_MODEL
    if _DEPTH_MODEL is not None:
        return _DEPTH_MODEL
    try:
        import torch
        import cv2

        model = torch.hub.load("intel-isl/MiDaS", "MiDaS_small", trust_repo=True)
        model.eval()
        if torch.cuda.is_available():
            model = model.cuda()
        transform = torch.hub.load("intel-isl/MiDaS", "transforms").small_transform
        _DEPTH_MODEL = (model, transform)
        return _DEPTH_MODEL
    except Exception as exc:
        logger.warning("depth_model_load_failed", error=str(exc))
        return None


def _fallback_depth_for_frame(frame: np.ndarray) -> np.ndarray:
    """Return a pseudo-depth map when MiDaS is unavailable.

    Uses local Laplacian variance as a rough relative-depth proxy: out-of-focus
    regions tend to have lower variance.  The result is inverted and normalized.
    """
    import cv2

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    # Block-wise variance to keep some spatial structure.
    h, w = gray.shape
    block_h, block_w = max(1, h // 8), max(1, w // 8)
    blocks = []
    for y in range(0, h, block_h):
        for x in range(0, w, block_w):
            patch = lap[y : y + block_h, x : x + block_w]
            blocks.append(np.var(patch))
    arr = np.array(blocks, dtype=np.float32)
    if arr.max() > arr.min():
        arr = (arr.max() - arr) / (arr.max() - arr.min())
    return arr


def _estimate_depth_for_frame(frame: np.ndarray) -> Tuple[np.ndarray, str]:
    """Return a normalized depth map and the model name used."""
    model_tuple = _load_depth_model()
    if model_tuple is None:
        return _fallback_depth_for_frame(frame), "fallback_laplacian"

    import torch
    import cv2

    model, transform = model_tuple
    try:
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        input_batch = transform(img)
        if torch.cuda.is_available():
            input_batch = input_batch.cuda()
        with torch.no_grad():
            prediction = model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()
        depth = prediction.cpu().numpy()
        depth = (depth - depth.min()) / max(depth.max() - depth.min(), 1e-6)
        return depth, "midas_v2.1_small"
    except Exception as exc:
        logger.warning("midas_inference_failed", error=str(exc))
        return _fallback_depth_for_frame(frame), "fallback_laplacian"


def _sample_frames(
    video_path: str, sample_fps: float = 2.0
) -> Iterator[Tuple[float, np.ndarray, int]]:
    """Yield (t_s, frame_bgr, frame_index) samples from a video."""
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    native_fps = cap.get(cv2.CAP_PROP_FPS) or sample_fps
    if native_fps <= 0:
        native_fps = sample_fps
    interval = max(1.0, native_fps / sample_fps)
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % max(1, int(round(interval))) == 0:
            t_s = frame_idx / native_fps
            yield t_s, frame, frame_idx
        frame_idx += 1
    cap.release()


def _depth_stats(depth_map: np.ndarray) -> Dict[str, float]:
    """Return mean/variance/near/far ratios for a normalized depth map."""
    flat = depth_map.flatten()
    mean = float(np.mean(flat))
    var = float(np.var(flat))
    near_ratio = float(np.mean(flat < 0.25))
    far_ratio = float(np.mean(flat > 0.75))
    return {
        "mean_depth": mean,
        "depth_variance": var,
        "near_ratio": near_ratio,
        "far_ratio": far_ratio,
    }


def _estimate_depths(
    video_path: str, sample_fps: float = 2.0
) -> Tuple[List[DepthSample], str]:
    """Sample the video and return depth samples + model name."""
    samples: List[DepthSample] = []
    model_name = "unknown"
    for t_s, frame, frame_idx in _sample_frames(video_path, sample_fps):
        depth_map, model_name = _estimate_depth_for_frame(frame)
        stats = _depth_stats(depth_map)
        samples.append(
            DepthSample(
                t_s=t_s,
                mean_depth=stats["mean_depth"],
                depth_variance=stats["depth_variance"],
                near_ratio=stats["near_ratio"],
                far_ratio=stats["far_ratio"],
            )
        )
    return samples, model_name


def _aggregate_depth(samples: List[DepthSample]) -> DepthAnalysis:
    """Summarize a list of depth samples."""
    if not samples:
        return DepthAnalysis()
    means = [s.mean_depth for s in samples]
    variances = [s.depth_variance for s in samples]
    return DepthAnalysis(
        sampled_fps=2.0,
        global_mean_depth=float(np.mean(means)),
        global_depth_variance=float(np.mean(variances)),
        samples=samples,
    )


def _group_shots_into_scenes(
    shot_boundaries: Optional[List[ShotBoundary]],
    depth_samples: List[DepthSample],
    fps: float,
) -> List[Scene]:
    """Merge adjacent shots into scenes using depth continuity.

    If no shot boundaries are provided, fall back to fixed 2-second windows.
    """
    import cv2

    scenes: List[Scene] = []
    if not depth_samples:
        return scenes

    if not shot_boundaries:
        # Fixed windows when no shot detection data is available.
        window_s = 2.0
        max_t = max(s.t_s for s in depth_samples)
        boundaries: List[Tuple[float, float]] = []
        start = 0.0
        while start < max_t:
            end = min(max_t, start + window_s)
            boundaries.append((start, end))
            start = end
    else:
        boundaries = [(s.start_s, s.end_s) for s in shot_boundaries]

    sample_by_t = {s.t_s: s for s in depth_samples}
    for scene_id, (start_s, end_s) in enumerate(boundaries):
        samples = [s for s in depth_samples if start_s <= s.t_s < end_s]
        if not samples:
            samples = [min(depth_samples, key=lambda s: abs(s.t_s - (start_s + end_s) / 2))]
        mean_depth = float(np.mean([s.mean_depth for s in samples]))
        depth_var = float(np.mean([s.depth_variance for s in samples]))
        rep_s = float(np.median([s.t_s for s in samples]))
        scenes.append(
            Scene(
                scene_id=scene_id,
                start_s=start_s,
                end_s=end_s,
                start_frame=int(round(start_s * fps)),
                end_frame=int(round(end_s * fps)),
                representative_frame_s=rep_s,
                dominant_motion="still",
                avg_depth=mean_depth,
                depth_variance=depth_var,
                visual_tag="",
                confidence=1.0,
            )
        )
    return scenes


def analyze_scenes_and_depth(
    video_path: str,
    asset_id: str,
    fps: float = 30.0,
    shot_boundaries: Optional[List[ShotBoundary]] = None,
    cache_dir: Optional[Path] = None,
) -> SceneDepthAnalysis:
    """Analyze scenes and depth for a video asset, reading from cache if present."""
    cache = cache_dir or _cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    cache_path = cache / f"{asset_id}_scene_depth.json"
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            logger.info("scene_depth_cache_hit", asset_id=asset_id)
            return SceneDepthAnalysis(**data)
        except Exception as exc:
            logger.warning("scene_depth_cache_load_failed", asset_id=asset_id, error=str(exc))

    samples, model_name = _estimate_depths(video_path)
    depth = _aggregate_depth(samples)
    depth.model_name = model_name
    scenes = _group_shots_into_scenes(shot_boundaries, samples, fps)
    analysis = SceneDepthAnalysis(
        asset_id=asset_id,
        scenes=scenes,
        depth=depth,
        extractor="scene_depth_v1",
    )
    try:
        cache_path.write_text(analysis.model_dump_json(), encoding="utf-8")
    except Exception as exc:
        logger.warning("scene_depth_cache_write_failed", asset_id=asset_id, error=str(exc))
    return analysis
