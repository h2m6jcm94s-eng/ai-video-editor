# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Conservation-of-momentum scoring for clip transitions."""

from typing import Tuple
import numpy as np
import cv2

from shared_py.tuning import FLOW, MOMENTUM


def _read_downscaled_frame(cap) -> np.ndarray | None:
    """Read the next frame from a capture and resize it for flow computation."""
    ret, frame = cap.read()
    if not ret or frame is None:
        return None
    return cv2.resize(frame, FLOW.TARGET_SIZE)


def compute_mean_flow_vector(
    clip_path: str,
    start_s: float,
    n_frames: int = FLOW.N_FRAMES,
) -> Tuple[float, float]:
    """Compute the mean optical-flow vector starting at ``start_s``.

    Uses OpenCV Farneback optical flow on 256x144 downscaled frames.  Returns
    ``(dx, dy)`` in downscaled pixel units; a zero vector is returned when the
    clip cannot be read or has too few frames.
    """
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return (0.0, 0.0)

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        frame_idx = max(0, int(round(start_s * fps)))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames > 0:
            frame_idx = min(frame_idx, max(0, total_frames - n_frames - 1))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

        prev = _read_downscaled_frame(cap)
        if prev is None:
            return (0.0, 0.0)
        prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)

        flow_accum = np.zeros((2,), dtype=np.float64)
        flow_count = 0
        for _ in range(n_frames):
            curr = _read_downscaled_frame(cap)
            if curr is None:
                break
            curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray,
                curr_gray,
                None,
                pyr_scale=FLOW.PYR_SCALE,
                levels=FLOW.LEVELS,
                winsize=FLOW.WINSIZE,
                iterations=FLOW.ITERATIONS,
                poly_n=FLOW.POLY_N,
                poly_sigma=FLOW.POLY_SIGMA,
                flags=FLOW.FLAGS,
            )
            mean_flow = np.mean(flow, axis=(0, 1))
            flow_accum += mean_flow
            flow_count += 1
            prev_gray = curr_gray

        if flow_count == 0:
            return (0.0, 0.0)
        mean = flow_accum / flow_count
        return (float(mean[0]), float(mean[1]))
    finally:
        cap.release()


def momentum_coherence(v_out: Tuple[float, float], v_in: Tuple[float, float]) -> float:
    """Return a 0-1 score for how well ``v_in`` continues ``v_out``.

    Identical directions score 1, opposite directions score 0, and still or
    missing motion is neutral (0.5).
    """
    ax, ay = v_out
    bx, by = v_in
    norm_a = float(np.hypot(ax, ay))
    norm_b = float(np.hypot(bx, by))

    if norm_a == 0.0 and norm_b == 0.0:
        return 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.5

    cos_sim = (ax * bx + ay * by) / (norm_a * norm_b)
    cos_sim = max(-1.0, min(1.0, cos_sim))
    return MOMENTUM.COHERENCE_NEUTRAL + MOMENTUM.COHERENCE_SCALE * cos_sim
