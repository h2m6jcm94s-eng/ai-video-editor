# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Direction-aware and music/semantics-aware transition selection."""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from shared_py.logging_config import StructuredLogger
from shared_py.models import MusicEventGrid, Slot

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
) -> tuple[str, str]:
    """Return (outgoing_motion, incoming_motion) for a cut at ``cut_time_s``."""
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
    """Classify each reference shot boundary into a transition archetype."""
    if cv2 is None:
        return ["hard_cut"] * len(shot_boundaries)

    archetypes = []
    for i, boundary in enumerate(shot_boundaries):
        transition_in = boundary.get("transition_in", "hard_cut")
        is_gradual = boundary.get("is_gradual", False)

        if is_gradual or transition_in in {"dissolve", "fade"}:
            archetypes.append("fade" if transition_in == "fade" else "dissolve")
            continue
        if transition_in == "whip":
            archetypes.append("whip")
            continue

        if 0 < i < len(shot_boundaries):
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


def _dino_cosine(out_dino: Optional[np.ndarray], in_dino: Optional[np.ndarray]) -> float:
    if out_dino is None or in_dino is None:
        return 0.0
    x, y = out_dino, in_dino
    nx, ny = float(np.linalg.norm(x)), float(np.linalg.norm(y))
    if nx == 0.0 or ny == 0.0:
        return 0.0
    return float(np.dot(x, y) / (nx * ny))


def _event_near(music_events: Optional[MusicEventGrid], event_list: str, t: float, window_s: float = 0.1) -> bool:
    if not music_events:
        return False
    for time_s in getattr(music_events, event_list, []):
        if abs(time_s - t) <= window_s:
            return True
    return False


def _has_sustained_vocal_ahead(music_events: Optional[MusicEventGrid], t: float, ahead_s: float = 1.0) -> bool:
    if not music_events:
        return False
    for time_s in music_events.vocal_onset_times:
        if t < time_s <= t + ahead_s:
            return True
    for time_s in music_events.phrase_boundary_times:
        if t < time_s <= t + ahead_s:
            return True
    return False


def _direction_slice(out_motion: str, in_motion: str) -> str:
    """Return a directional slice transition when motions align horizontally."""
    lefts = {"left", "up_left", "down_left"}
    rights = {"right", "up_right", "down_right"}
    if out_motion in lefts and in_motion in lefts:
        return "hlslice"
    if out_motion in rights and in_motion in rights:
        return "hrslice"
    return ""


def select_xfade(
    out_motion: str,
    in_motion: str,
    ref_archetype: str,
    slot: Optional[Slot] = None,
    music_events: Optional[MusicEventGrid] = None,
    section_mood: Optional[str] = None,
    out_dino: Optional[np.ndarray] = None,
    in_dino: Optional[np.ndarray] = None,
    extra: Optional[dict] = None,
) -> str:
    """Pick an xfade preset name based on motion, reference intent, music, and semantics.

    When ``slot`` is provided the function runs the full Wave-7 decision table
    (match cuts, music-event triggers, mood forcing).  When only the three
    legacy arguments are supplied it falls back to the previous motion-aware
    logic so existing tests stay valid.

    ``extra`` is an optional mutable dict the caller can inspect for side-band
    signals such as ``flash_frame`` or ``match_cut_bonus``.
    """
    extra = extra if extra is not None else {}

    # Legacy path: no semantic / music context available.
    if slot is None:
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
        return "hard_cut"

    cut_time = float(slot.start_s + slot.duration_s)
    energy = float(slot.energy_level or 0.5)
    mood = (section_mood or "").lower()

    # 1. Match cut (strong semantic continuity).
    dino_sim = _dino_cosine(out_dino, in_dino)
    if dino_sim > 0.85:
        extra["match_cut_bonus"] = True
        logger.info("match_cut_bonus", slot_index=slot.index, cosine=round(dino_sim, 3))
        return "hard_cut"
    if dino_sim > 0.7:
        extra["match_cut"] = True
        logger.info("match_cut_lite", slot_index=slot.index, cosine=round(dino_sim, 3))
        return "hard_cut"

    # 2. Drum / music event triggers.
    if _event_near(music_events, "kick_times", cut_time, 0.1):
        return "hard_cut"

    if _event_near(music_events, "snare_times", cut_time, 0.1):
        directional = _direction_slice(out_motion, in_motion)
        if directional:
            return directional
        return "whip"

    if _event_near(music_events, "vocal_onset_times", cut_time, 0.1):
        if _has_sustained_vocal_ahead(music_events, cut_time, ahead_s=1.0):
            return "dissolve"

    if _event_near(music_events, "sweep_peak_times", cut_time, 0.1):
        return "radial" if energy > 0.6 else "zoomblur"

    if _event_near(music_events, "bass_drop_times", cut_time, 0.1):
        extra["flash_frame"] = True
        return "hard_cut"

    # 3. Mood forcing.
    if "melancholic" in mood and energy < 0.4:
        return "dissolve"
    if "aggressive" in mood and energy > 0.7:
        return "hard_cut"

    # 4. Motion-aligned reference fallback.
    if ref_archetype == "hard_cut":
        return "fade" if (out_motion == "still" and in_motion == "still") else "hard_cut"
    if ref_archetype == "whip":
        directional = _direction_slice(out_motion, in_motion)
        if directional:
            return directional
        return "whip"
    if ref_archetype == "match_cut" and out_motion == in_motion and out_motion != "still":
        return "dissolve"
    if ref_archetype == "fade":
        return "fade"
    if ref_archetype == "dissolve":
        return "dissolve"

    # 5. Absolute fallback — never dissolve by default.
    extra["fallback_hardcut"] = True
    logger.warning(
        "xfade_fallback_hardcut",
        slot_index=slot.index,
        ref_archetype=ref_archetype,
        out_motion=out_motion,
        in_motion=in_motion,
    )
    return "hard_cut"
