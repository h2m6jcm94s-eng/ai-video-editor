# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Vocal-anticipation offsets and motion-peak anticipation for cut timing."""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from shared_py.logging_config import StructuredLogger
from shared_py.models import MusicEventGrid, Slot
from shared_py.tuning import ANTICIPATION

logger = StructuredLogger("reason_worker.anticipation")

_VOCAL_WINDOW_S = 0.5
_MAX_OFFSET_S = 0.5


try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]


def _frame_energy(frame: np.ndarray, prev_gray: Optional[np.ndarray]) -> float:
    if cv2 is None or prev_gray is None:
        return 0.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray, prev_gray)
    return float(np.mean(diff))


def compute_motion_curve(
    clip_path: str,
    start_s: float,
    duration_s: float,
    fps: float = 24.0,
) -> List[Tuple[float, float]]:
    """Return a list of ``(time_rel_s, motion_energy)`` for a clip window.

    ``time_rel_s`` is relative to ``start_s``.  Motion energy is computed from
    the mean absolute frame difference in the window.
    """
    samples: List[Tuple[float, float]] = []
    if cv2 is None:
        return samples
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return samples
    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS) or fps
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        start_frame = int(start_s * video_fps)
        end_frame = min(total_frames, int((start_s + duration_s) * video_fps) + 1)
        if start_frame >= end_frame:
            return samples

        prev_gray = None
        for f in range(start_frame, end_frame):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ret, frame = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                energy = float(np.mean(diff))
                rel_s = (f - start_frame) / video_fps
                samples.append((rel_s, energy))
            prev_gray = gray
    finally:
        cap.release()
    return samples


def precompute_clip_motion_curve(clip_path: str, fps_sample: float = 2.0) -> np.ndarray:
    """Return a 1-D motion-energy curve sampled evenly over the whole clip.

    This is the legacy API used by ``clip_rank.apply_anticipation_offsets``.
    """
    if cv2 is None:
        return np.array([])
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return np.array([])
    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return np.array([])
        sample_step = max(1, int(video_fps / fps_sample))
        energies: List[float] = []
        prev_gray = None
        for f in range(0, total_frames, sample_step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ret, frame = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                energies.append(float(np.mean(diff)))
            prev_gray = gray
        return np.array(energies, dtype=np.float32)
    finally:
        cap.release()


def compute_anticipation_offset(
    source_window_start_s: float,
    source_window_duration_s: float,
    clip_motion_curve: np.ndarray,
    fps: float = 24.0,
    target_offset_ms: float = 333.0,
) -> float:
    """Return the source-window shift so the cut lands before the motion peak.

    The dominant motion peak in ``clip_motion_curve`` is located, and the offset
    moves the source window so that peak occurs ``target_offset_ms`` after the
    slot start.  The result is clamped to a safe ±0.5s window.
    """
    if clip_motion_curve is None or len(clip_motion_curve) == 0:
        return 0.0
    peak_index = int(np.argmax(clip_motion_curve))
    peak_rel_s = peak_index / max(1.0, fps)
    target_s = target_offset_ms / 1000.0
    # Shift the source window so the motion peak occurs ``target_s`` after the
    # slot start: new_start = old_start + peak_rel_s - target_s.
    offset = peak_rel_s - target_s
    # Clamp to the source window so we never ask FFmpeg to seek outside the clip.
    return max(-source_window_duration_s, min(source_window_duration_s, offset))


def apply_vocal_anticipation(
    slot: Slot,
    clip_motion_curve: List[Tuple[float, float]],
    music_events: MusicEventGrid,
    fps: float = 24.0,
) -> None:
    """Shift the source window so a nearby vocal onset lands on a motion peak.

    If the slot start is within 500ms of a vocal onset, find the highest motion
    energy inside the slot window and set ``anticipation_offset_s`` so that the
    peak aligns with the vocal onset.
    """
    if not music_events or not clip_motion_curve:
        return
    slot_start = float(slot.start_s)
    nearest_vocal: Optional[float] = None
    nearest_dist = float("inf")
    for t in music_events.vocal_onset_times:
        dist = abs(t - slot_start)
        if dist <= _VOCAL_WINDOW_S and dist < nearest_dist:
            nearest_dist = dist
            nearest_vocal = t
    if nearest_vocal is None:
        return

    peak_rel, peak_energy = max(clip_motion_curve, key=lambda x: x[1])
    if peak_energy <= 0.0:
        return

    offset = nearest_vocal - (slot_start + peak_rel)
    # Clamp to a safe window so we don't seek past the source clip.
    offset = max(-_MAX_OFFSET_S, min(_MAX_OFFSET_S, offset))
    slot.anticipation_offset_s = offset
    logger.info(
        "vocal_anticipation_offset_set",
        slot_index=slot.index,
        vocal_onset=nearest_vocal,
        peak_rel=peak_rel,
        offset=offset,
    )
