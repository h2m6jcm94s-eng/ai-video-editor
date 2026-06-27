# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Motion feature family for the Style Genome."""

from __future__ import annotations

import math
from typing import List

try:
    import cv2
except Exception:  # pragma: no cover - optional dep
    cv2 = None  # type: ignore[assignment]

from shared_py.logging_config import StructuredLogger
from shared_py.models import MotionFamily, ShotBoundary, StyleAnalysis

logger = StructuredLogger("style_worker.genome.families.motion")


def _sample_motion_energy(
    video_path: str,
    shot_boundaries: List[ShotBoundary],
    video_info: dict,
) -> List[float]:
    """Return a per-shot mean inter-frame difference energy (0..1)."""
    if cv2 is None or not shot_boundaries:
        return [0.0] * len(shot_boundaries)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning("Could not open video for motion energy: %s", video_path)
        return [0.0] * len(shot_boundaries)

    fps = video_info.get("fps") or float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_interval = max(1, int(round(fps / 4.0)))

    energies = []
    for shot in shot_boundaries:
        prev_gray = None
        diffs = []
        start = max(0, shot.start_frame)
        end = min(shot.end_frame, total_frames)
        for frame_idx in range(start, end, sample_interval):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray).mean()
                diffs.append(float(diff) / 255.0)
            prev_gray = gray
        energies.append(sum(diffs) / len(diffs) if diffs else 0.0)

    cap.release()
    return energies


def extract_motion_genome(
    video_path: str,
    shot_boundaries: List[ShotBoundary],
    style_analysis: StyleAnalysis,
) -> MotionFamily:
    """Extract the 12 motion features."""
    labels = list(style_analysis.camera_motions or [])
    n = len(labels)

    # Ensure labels line up with shots so percentages are well-defined.
    if n == 0:
        labels = ["static"] * len(shot_boundaries)
        n = len(labels)
    elif n != len(shot_boundaries):
        if n < len(shot_boundaries):
            labels.extend(["static"] * (len(shot_boundaries) - n))
        else:
            labels = labels[: len(shot_boundaries)]
        n = len(labels)

    energies = _sample_motion_energy(video_path, shot_boundaries, {})
    if len(energies) != n:
        energies = energies[:n] if len(energies) > n else energies + [0.0] * (n - len(energies))

    avg_energy = sum(energies) / n if n else 0.0
    max_energy = max(energies) if energies else 0.0
    std_energy = 0.0
    if len(energies) > 1:
        mean_e = avg_energy
        variance = sum((e - mean_e) ** 2 for e in energies) / (len(energies) - 1)
        std_energy = math.sqrt(variance)

    def pct(label: str) -> float:
        return labels.count(label) / n if n else 0.0

    return MotionFamily(
        avg_motion_energy=avg_energy,
        max_motion_energy=max_energy,
        motion_energy_std=std_energy,
        pct_still_shots=pct("static"),
        pct_pan_left=pct("pan_left"),
        pct_pan_right=pct("pan_right"),
        pct_tilt_up=pct("tilt_up"),
        pct_tilt_down=pct("tilt_down"),
        pct_zoom_in=pct("zoom_in"),
        pct_zoom_out=pct("zoom_out"),
        pct_handheld=pct("handheld"),
        pct_gimbal=pct("gimbal"),
    )
