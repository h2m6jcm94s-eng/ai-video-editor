# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the style-analysis worker."""

from typing import List

from temporalio import activity

from style_worker.camera_motion import analyze_camera_motion
from style_worker.lut_extract import extract_lut_from_reference
from style_worker.text_extract import extract_text_overlays
from style_worker.transition_type import classify_transitions
from shared_py.models import Overlay, ShotBoundary, StyleAnalysis


@activity.defn
async def extract_lut(video_path: str, output_dir: str, strength: float = 0.5) -> dict:
    """Extract a .cube LUT from a reference video."""
    cube_path, analysis = extract_lut_from_reference(video_path, output_dir, strength)
    return {
        "cube_path": cube_path,
        "color_palette": analysis.color_palette,
        "contrast_level": analysis.contrast_level,
        "saturation_level": analysis.saturation_level,
        "brightness_level": analysis.brightness_level,
        "lut_extracted": analysis.lut_extracted,
        "lut_storage_key": analysis.lut_storage_key,
    }


@activity.defn
async def detect_text_overlays(video_path: str, fps_sample: float = 5.0) -> List[dict]:
    """Detect persistent text overlays in a video."""
    overlays = extract_text_overlays(video_path, fps_sample)
    return [o.model_dump() for o in overlays]


@activity.defn
async def analyze_motion(video_path: str, shot_boundaries: List[dict]) -> List[str]:
    """Classify camera motion for each shot boundary."""
    shots = [ShotBoundary(**s) for s in shot_boundaries]
    return analyze_camera_motion(video_path, shots)


@activity.defn
async def classify_shot_transitions(video_path: str, shot_boundaries: List[dict]) -> List[dict]:
    """Classify transition types for shot boundaries."""
    shots = [ShotBoundary(**s) for s in shot_boundaries]
    result = classify_transitions(video_path, shots)
    return [s.model_dump() for s in result]
