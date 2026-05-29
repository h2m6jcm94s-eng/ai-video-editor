# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class CutListGlobals(BaseModel):
    total_duration_s: float
    tempo_bpm: float
    time_signature: str = "4/4"
    key: Optional[str] = None
    energy_curve: List[float] = Field(default_factory=list)
    section_markers: List["SectionMarker"] = Field(default_factory=list)
    color_grade_ref: Optional[str] = None
    aspect_ratio: str = "9:16"


class SectionMarker(BaseModel):
    name: str
    start_s: float
    end_s: float


class Slot(BaseModel):
    index: int
    start_s: float
    duration_s: float
    beat_index: int
    section: str
    transition_in: str = "hard_cut"
    transition_out: str = "hard_cut"
    target_shot_type: str
    subject_hint: str
    motion_hint: str
    energy_level: float = Field(ge=0.0, le=1.0)
    required_tags: List[str] = Field(default_factory=list)
    avoid_tags: List[str] = Field(default_factory=list)
    selected_clip_id: Optional[str] = None
    ranked_clip_ids: Optional[List[str]] = None
    confidence: Optional[float] = None


class Overlay(BaseModel):
    text: str
    start_s: float
    end_s: float
    position: str = "center"
    font: str = "Inter"
    font_size_px: int = 48
    color: str = "#FFFFFF"
    stroke: Optional[str] = "#000000"
    animation: str = "none"


class CutList(BaseModel):
    globals: CutListGlobals
    slots: List[Slot]
    overlays: List[Overlay] = Field(default_factory=list)


class ShotBoundary(BaseModel):
    start_frame: int
    end_frame: int
    start_s: float
    end_s: float
    is_gradual: bool = False
    confidence: float = 1.0


class BeatSegment(BaseModel):
    start: float
    end: float
    label: str


class BeatGrid(BaseModel):
    bpm: float
    beats: List[float]
    downbeats: List[float]
    beat_positions: List[float]
    segments: List[BeatSegment]


class ShotAnalysis(BaseModel):
    shot_size: str
    motion: str
    subject_type: str
    lighting: str
    dominant_color: str
    camera_move: str


class StyleAnalysis(BaseModel):
    color_palette: List[str] = Field(default_factory=list)
    contrast_level: float = 1.0
    saturation_level: float = 1.0
    brightness_level: float = 1.0
    lut_extracted: bool = False
    lut_storage_key: Optional[str] = None
    detected_transitions: List[str] = Field(default_factory=list)
    detected_overlays: List[Overlay] = Field(default_factory=list)
    camera_motions: List[str] = Field(default_factory=list)
    pacing: str = "medium"
    mood: str = "neutral"


class ClipScore(BaseModel):
    clip_id: str
    semantic_score: float = 0.0
    shot_type_score: float = 0.0
    aesthetic_score: float = 0.0
    motion_score: float = 0.0
    duration_score: float = 0.0
    diversity_penalty: float = 0.0
    total_score: float = 0.0


class RenderConfig(BaseModel):
    output_path: str
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    video_codec: str = "libx264"
    video_preset: str = "slow"
    video_crf: int = 18
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    pix_fmt: str = "yuv420p"
    lut_path: Optional[str] = None
    song_path: Optional[str] = None
