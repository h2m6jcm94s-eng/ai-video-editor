# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Direction-aware transition selection between user clips."""

from typing import List, Optional, Tuple

import numpy as np

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("reason_worker.transition_select")

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


def _quantize_direction(mean_flow: np.ndarray) -> str:
    """Quantize a mean optical-flow vector to one of 8 directions or still."""
    dx, dy = float(mean_flow[0]), float(mean_flow[1])
    magnitude = np.sqrt(dx * dx + dy * dy)
    if magnitude < 0.5:
        return "still"

    angle = np.arctan2(dy, dx) * 180 / np.pi
    directions = ["right", "down_right", "down", "down_left", "left", "up_left", "up", "up_right"]
    index = int(round(angle / 45)) % 8
    return directions[index]


def motion_direction_around_cut(
    clip_path: str,
    cut_time_s: float,
    context_s: float = 0.3,
) -> Tuple[str, str]:
    """Return (outgoing_motion, incoming_motion) for a cut at ``cut_time_s``.

    Computes mean optical flow in the last ``context_s`` of the outgoing side
    and the first ``context_s`` of the incoming side.
    """
    if cv2 is None:
        return "still", "still"

    cap = cv2.VideoCapture(clip_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0.0

    cut_frame = int(cut_time_s * fps)
    context_frames = max(1, int(context_s * fps))

    outgoing_start = max(0, cut_frame - context_frames)
    outgoing_end = max(0, cut_frame)
    incoming_start = min(total_frames, cut_frame + 1)
    incoming_end = min(total_frames, cut_frame + 1 + context_frames)

    def _mean_flow(start_frame: int, end_frame: int) -> Optional[np.ndarray]:
        flows = []
        prev_gray = None
        for f in range(start_frame, end_frame):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ret, frame = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None,
                    pyr_scale=0.5, levels=3, winsize=15,
                    iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
                )
                flows.append(flow)
            prev_gray = gray
        if not flows:
            return None
        return np.mean(np.stack(flows), axis=(0, 1, 2))

    outgoing_flow = _mean_flow(outgoing_start, outgoing_end)
    incoming_flow = _mean_flow(incoming_start, incoming_end)

    cap.release()

    out_dir = _quantize_direction(outgoing_flow) if outgoing_flow is not None else "still"
    in_dir = _quantize_direction(incoming_flow) if incoming_flow is not None else "still"
    return out_dir, in_dir


def classify_reference_transition_archetypes(
    video_path: str,
    shot_boundaries: List[dict],
) -> List[str]:
    """Classify each reference shot boundary into a transition archetype.

    Archetypes: hard_cut, dissolve, fade, whip, match_cut.
    """
    if cv2 is None:
        return ["hard_cut"] * len(shot_boundaries)

    archetypes = []
    for i, boundary in enumerate(shot_boundaries):
        transition_in = boundary.get("transition_in", "hard_cut")
        is_gradual = boundary.get("is_gradual", False)
        span = boundary.get("end_frame", 0) - boundary.get("start_frame", 0)

        if is_gradual or transition_in in {"dissolve", "fade"}:
            if transition_in == "fade":
                archetypes.append("fade")
            else:
                archetypes.append("dissolve")
            continue

        if transition_in == "whip":
            archetypes.append("whip")
            continue

        # Decide between hard_cut and match_cut based on motion continuity.
        if i > 0 and i < len(shot_boundaries):
            prev_end = shot_boundaries[i - 1].get("end_s", 0.0)
            curr_start = boundary.get("start_s", 0.0)
            cut_time = (prev_end + curr_start) / 2
            try:
                out_dir, in_dir = motion_direction_around_cut(video_path, cut_time, context_s=0.2)
                if out_dir != "still" and out_dir == in_dir:
                    archetypes.append("match_cut")
                    continue
            except Exception as e:
                logger.warning("Failed to compute motion around cut", error=str(e))

        archetypes.append("hard_cut")

    return archetypes


def select_xfade(
    out_motion: str,
    in_motion: str,
    ref_archetype: str,
) -> str:
    """Pick an xfade preset name based on outgoing/incoming motion and reference intent.

    Returned strings are keys in the compiler's XFADE_MAP.
    """
    if ref_archetype == "hard_cut":
        return "fade" if (out_motion == "still" and in_motion == "still") else "hard_cut"

    if ref_archetype == "whip":
        if out_motion in {"left", "up_left", "down_left"} and in_motion in {"left", "up_left", "down_left"}:
            return "hlslice"
        if out_motion in {"right", "up_right", "down_right"} and in_motion in {"right", "up_right", "down_right"}:
            return "hrslice"
        return "whip"

    if ref_archetype == "match_cut" and out_motion == in_motion and out_motion != "still":
        return "dissolve"

    if ref_archetype == "fade":
        return "fade"

    if ref_archetype == "dissolve":
        return "dissolve"

    return "dissolve"
