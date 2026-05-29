# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Classify transition types from shot boundaries."""

from typing import List
import numpy as np

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

from shared_py.models import ShotBoundary


def classify_transitions(
    video_path: str, boundaries: List[ShotBoundary]
) -> List[ShotBoundary]:
    """Classify transition type for each boundary."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)

    for boundary in boundaries:
        if not boundary.is_gradual:
            boundary.transition_in = "hard_cut"
            continue

        # Analyze frames around boundary
        start_frame = boundary.start_frame
        end_frame = boundary.end_frame
        span = end_frame - start_frame

        if span <= 1:
            boundary.transition_in = "hard_cut"
            continue

        # Read frames around transition
        frames = []
        for f in range(max(0, start_frame - 2), min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), end_frame + 2)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ret, frame = cap.read()
            if ret:
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))

        if len(frames) < 3:
            boundary.transition_in = "dissolve"
            continue

        # Check for wipe: fit line to changed mask
        diffs = []
        for i in range(len(frames) - 1):
            diff = cv2.absdiff(frames[i], frames[i + 1])
            _, mask = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
            diffs.append(mask)

        # Dissolve/fade: smooth SSIM decay + monotonic luminance
        luminances = [f.mean() for f in frames]
        lum_diffs = np.diff(luminances)
        is_monotonic = np.all(lum_diffs >= -1) or np.all(lum_diffs <= 1)

        if is_monotonic and span > 3:
            if luminances[0] < 20 or luminances[-1] < 20:
                boundary.transition_in = "fade"
            else:
                boundary.transition_in = "dissolve"
            continue

        # Wipe: structured translating half-plane
        # Simplified: check if changes cluster along a line
        # For MVP, use a heuristic
        if span >= 2 and span <= 15:
            # Check for directional change
            first_diff = diffs[0] if diffs else None
            last_diff = diffs[-1] if diffs else None
            if first_diff is not None and last_diff is not None:
                # Compare center of mass of changes
                moments_first = cv2.moments(first_diff)
                moments_last = cv2.moments(last_diff)
                if moments_first["m00"] > 0 and moments_last["m00"] > 0:
                    cx1 = moments_first["m10"] / moments_first["m00"]
                    cx2 = moments_last["m10"] / moments_last["m00"]
                    if abs(cx1 - cx2) > frames[0].shape[1] * 0.2:
                        boundary.transition_in = "wipe_right" if cx2 > cx1 else "wipe_left"
                        continue

        # Whip pan: short span + high motion blur
        if span <= 10:
            laplacians = [cv2.Laplacian(f, cv2.CV_64F).var() for f in frames]
            if min(laplacians) < 50:  # Motion blur indicator
                boundary.transition_in = "whip"
                continue

        boundary.transition_in = "dissolve"

    cap.release()
    return boundaries
