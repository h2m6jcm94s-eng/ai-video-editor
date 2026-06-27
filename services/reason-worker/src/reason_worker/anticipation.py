# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Anticipation cutting: shift clip starts so cuts land on motion peaks."""

import os
import numpy as np
import cv2
from scipy.signal import find_peaks

from shared_py.tuning import FLOW, ANTICIPATION


def _read_downscaled_frame(cap):
    """Read and downscale the next frame from a capture."""
    ret, frame = cap.read()
    if not ret or frame is None:
        return None
    return cv2.resize(frame, FLOW.TARGET_SIZE)


def precompute_clip_motion_curve(
    clip_path: str,
    fps_sample: float = ANTICIPATION.FPS_SAMPLE,
) -> np.ndarray:
    """Compute per-frame motion magnitude for a clip and cache it.

    The cache is written next to the source clip as ``{clip_path}.motion.npz``.
    If a newer cache exists it is reused.
    """
    cache_path = f"{clip_path}.motion.npz"

    if os.path.exists(cache_path) and os.path.exists(clip_path):
        try:
            cache_mtime = os.path.getmtime(cache_path)
            src_mtime = os.path.getmtime(clip_path)
            if cache_mtime >= src_mtime:
                cached = np.load(cache_path)
                curve = cached.get("motion_curve")
                if curve is not None:
                    return np.asarray(curve, dtype=np.float32)
        except Exception:
            # Ignore corrupt cache and recompute below.
            pass

    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return np.zeros(0, dtype=np.float32)

    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 1:
            return np.zeros(0, dtype=np.float32)

        sample_interval = max(1, int(round(src_fps / fps_sample)))
        magnitudes = []

        ret, prev_frame = cap.read()
        if not ret or prev_frame is None:
            return np.zeros(0, dtype=np.float32)
        prev_gray = cv2.cvtColor(cv2.resize(prev_frame, FLOW.TARGET_SIZE), cv2.COLOR_BGR2GRAY)

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            frame_idx += 1
            if frame_idx % sample_interval != 0:
                continue
            gray = cv2.cvtColor(cv2.resize(frame, FLOW.TARGET_SIZE), cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray,
                gray,
                None,
                pyr_scale=FLOW.PYR_SCALE,
                levels=FLOW.LEVELS,
                winsize=FLOW.WINSIZE,
                iterations=FLOW.ITERATIONS,
                poly_n=FLOW.POLY_N,
                poly_sigma=FLOW.POLY_SIGMA,
                flags=FLOW.FLAGS,
            )
            mag = np.mean(np.hypot(flow[..., 0], flow[..., 1]))
            magnitudes.append(float(mag))
            prev_gray = gray

        if not magnitudes:
            return np.zeros(0, dtype=np.float32)
        curve = np.asarray(magnitudes, dtype=np.float32)
    finally:
        cap.release()

    try:
        np.savez_compressed(cache_path, motion_curve=curve, fps_sample=fps_sample)
    except Exception:
        # Cache write is best-effort; do not fail the analysis.
        pass

    return curve


def find_motion_peaks_in_window(
    motion_curve: np.ndarray,
    fps: float,
    min_prominence: float = ANTICIPATION.MIN_PROMINENCE,
) -> np.ndarray:
    """Find indices of dominant motion peaks in ``motion_curve``.

    Prominence is computed on a min-max normalized copy of the curve so the
    threshold is independent of absolute motion scale.
    """
    if motion_curve is None or len(motion_curve) == 0 or fps <= 0:
        return np.array([], dtype=int)

    min_val = float(np.min(motion_curve))
    max_val = float(np.max(motion_curve))
    if max_val <= min_val:
        return np.array([], dtype=int)

    normalized = (motion_curve - min_val) / (max_val - min_val)
    peaks, _ = find_peaks(normalized, prominence=min_prominence)
    return peaks


def compute_anticipation_offset(
    source_window_start_s: float,
    source_window_duration_s: float,
    clip_motion_curve: np.ndarray,
    fps: float,
    target_offset_ms: float = ANTICIPATION.TARGET_OFFSET_MS,
) -> float:
    """Return the seconds to shift the source window start.

    The dominant peak in the motion window is located and the start is shifted
    so the cut lands ``target_offset_ms`` before it.  The returned offset is
    added to ``source_window_start_s`` by the compiler, so negative values mean
    "start earlier".
    """
    if (
        clip_motion_curve is None
        or len(clip_motion_curve) == 0
        or fps <= 0
        or source_window_duration_s <= 0
    ):
        return 0.0

    start_frame = int(round(source_window_start_s * fps))
    end_frame = int(round((source_window_start_s + source_window_duration_s) * fps))
    start_frame = max(0, start_frame)
    end_frame = max(start_frame, min(end_frame, len(clip_motion_curve) - 1))
    if end_frame <= start_frame:
        return 0.0

    window_curve = clip_motion_curve[start_frame:end_frame]
    peaks = find_motion_peaks_in_window(window_curve, fps, min_prominence=ANTICIPATION.MIN_PROMINENCE)
    if len(peaks) == 0:
        return 0.0

    dominant_peak_rel = int(peaks[int(np.argmax(window_curve[peaks]))])
    peak_time_s = source_window_start_s + dominant_peak_rel / fps
    desired_start_s = peak_time_s - target_offset_ms / 1000.0
    offset_s = desired_start_s - source_window_start_s

    # Clamp: do not start before the beginning of the clip, and do not push
    # past the end of the source window.
    min_offset = -source_window_start_s
    max_offset = source_window_duration_s - ANTICIPATION.MAX_OFFSET_PAD_S
    return float(max(min_offset, min(offset_s, max_offset)))
