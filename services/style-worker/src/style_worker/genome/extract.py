# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Style Genome extraction entry point."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

try:
    import cv2
except Exception:  # pragma: no cover - optional dep
    cv2 = None  # type: ignore[assignment]

from shared_py.logging_config import StructuredLogger
from shared_py.models import (
    BeatGrid,
    ShotBoundary,
    StyleAnalysis,
    StyleGenome,
    StyleGenomeFamilies,
)
from style_worker.camera_motion import analyze_camera_motion
from style_worker.genome.families.audio_align import extract_audio_align_genome
from style_worker.genome.families.composition import extract_composition_genome
from style_worker.genome.families.cut_rhythm import extract_cut_rhythm
from style_worker.genome.families.dwell import extract_dwell_genome
from style_worker.genome.families.motion import extract_motion_genome
from style_worker.transition_type import classify_transitions

logger = StructuredLogger("style_worker.genome.extract")


def _video_info(video_path: str) -> dict:
    """Return cheap video metadata using OpenCV."""
    if cv2 is None:
        return {
            "fps": 30.0,
            "total_frames": 0,
            "duration_s": 0.0,
            "width": 0,
            "height": 0,
        }

    cap = cv2.VideoCapture(video_path)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    duration_s = total_frames / fps if fps > 0 else 0.0
    return {
        "fps": fps,
        "total_frames": total_frames,
        "duration_s": duration_s,
        "width": width,
        "height": height,
    }


def _detect_shot_boundaries(video_path: str, info: dict) -> List[ShotBoundary]:
    """Fall back to simple inter-frame difference cut detection."""
    total_frames = int(info.get("total_frames") or 0)
    fps = float(info.get("fps") or 30.0)
    duration_s = float(info.get("duration_s") or 0.0)

    if cv2 is None or total_frames < 2:
        return [
            ShotBoundary(
                start_frame=0,
                end_frame=total_frames,
                start_s=0.0,
                end_s=duration_s,
                is_gradual=False,
                confidence=1.0,
                transition_in="hard_cut",
                transition_out="hard_cut",
            )
        ]

    cap = cv2.VideoCapture(video_path)
    sample_fps = 2.0
    sample_interval = max(1, int(round(fps / sample_fps)))

    diffs: List[float] = []
    frame_indices: List[int] = []
    prev_gray = None

    for idx in range(0, total_frames, sample_interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diffs.append(float(cv2.absdiff(gray, prev_gray).mean()))
            frame_indices.append(idx)
        prev_gray = gray

    cap.release()

    if not diffs:
        return [
            ShotBoundary(
                start_frame=0,
                end_frame=total_frames,
                start_s=0.0,
                end_s=duration_s,
                is_gradual=False,
                confidence=1.0,
                transition_in="hard_cut",
                transition_out="hard_cut",
            )
        ]

    mean = sum(diffs) / len(diffs)
    std = 0.0
    if len(diffs) > 1:
        std = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1))
    threshold = mean + 2.0 * std

    cut_sample_indices = [i for i, d in enumerate(diffs) if d > threshold]
    cut_frames: List[int] = []
    if cut_sample_indices:
        group = [cut_sample_indices[0]]
        for i in cut_sample_indices[1:]:
            if frame_indices[i] - frame_indices[group[-1]] > sample_interval * 2:
                cut_frames.append(frame_indices[group[0]])
                group = [i]
            else:
                group.append(i)
        cut_frames.append(frame_indices[group[-1]])

    boundary_frames = [0] + sorted(set(cut_frames)) + [total_frames]
    shots: List[ShotBoundary] = []
    for i in range(len(boundary_frames) - 1):
        start = boundary_frames[i]
        end = boundary_frames[i + 1]
        if end <= start:
            continue
        shots.append(
            ShotBoundary(
                start_frame=start,
                end_frame=end,
                start_s=start / fps,
                end_s=end / fps,
                is_gradual=False,
                confidence=1.0,
                transition_in="hard_cut",
                transition_out="hard_cut",
            )
        )

    if not shots:
        shots = [
            ShotBoundary(
                start_frame=0,
                end_frame=total_frames,
                start_s=0.0,
                end_s=duration_s,
                is_gradual=False,
                confidence=1.0,
                transition_in="hard_cut",
                transition_out="hard_cut",
            )
        ]

    return shots


def _normalize_style_analysis(
    style_analysis: Optional[StyleAnalysis],
    video_path: str,
    shots: List[ShotBoundary],
) -> StyleAnalysis:
    """Ensure camera motions and transition labels are populated."""
    if style_analysis is None:
        style_analysis = StyleAnalysis()

    if not style_analysis.camera_motions and shots and cv2 is not None:
        try:
            style_analysis.camera_motions = analyze_camera_motion(video_path, shots)
        except Exception as exc:
            logger.warning("Failed to analyze camera motion for genome: %s", exc)
            style_analysis.camera_motions = ["static"] * len(shots)

    if not style_analysis.camera_motions:
        style_analysis.camera_motions = ["static"] * len(shots)

    if not style_analysis.detected_transition_types and shots and cv2 is not None:
        try:
            classified = classify_transitions(video_path, shots)
            style_analysis.detected_transition_types = [b.transition_in for b in classified]
        except Exception as exc:
            logger.warning("Failed to classify transitions for genome: %s", exc)

    if not style_analysis.detected_transition_types:
        style_analysis.detected_transition_types = ["hard_cut"] * len(shots)

    return style_analysis


def extract_genome(
    reference_video_path: str,
    beat_grid: Optional[BeatGrid] = None,
    shot_boundaries: Optional[List[ShotBoundary]] = None,
    style_analysis: Optional[StyleAnalysis] = None,
    project_clips: Optional[Dict[str, Any]] = None,
) -> dict:
    """Extract a 50-feature Style Genome fingerprint from a reference video.

    Optional analysis inputs are computed cheaply when missing so callers can
    obtain a complete genome from the video path alone.
    """
    info = _video_info(reference_video_path)

    if shot_boundaries is None:
        shot_boundaries = _detect_shot_boundaries(reference_video_path, info)

    style_analysis = _normalize_style_analysis(style_analysis, reference_video_path, shot_boundaries)

    families = StyleGenomeFamilies(
        cut_rhythm=extract_cut_rhythm(reference_video_path, beat_grid, shot_boundaries, info),
        motion=extract_motion_genome(reference_video_path, shot_boundaries, style_analysis),
        dwell=extract_dwell_genome(reference_video_path, project_clips, shot_boundaries, info),
        audio_align=extract_audio_align_genome(reference_video_path, beat_grid, shot_boundaries),
        composition=extract_composition_genome(
            reference_video_path, shot_boundaries, style_analysis, info
        ),
    )

    genome = StyleGenome(families=families)
    return genome.model_dump(by_alias=True)
