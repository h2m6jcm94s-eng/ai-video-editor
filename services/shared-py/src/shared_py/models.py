# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
from typing import List, Optional, Literal, Any
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel


class BaseModelCamel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class EffectParams(BaseModelCamel):
    pass


class ZoomPunchInParams(EffectParams):
    target_scale: float = Field(default=1.3, ge=1.0, le=3.0)
    duration_ms: int = Field(default=300, ge=50, le=2000)
    easing: Literal["linear", "easeIn", "easeOut", "easeInOut"] = "easeOut"


class FocusPullParams(EffectParams):
    target_blur: float = Field(default=0.0, ge=0.0, le=20.0)
    duration_ms: int = Field(default=800, ge=50, le=5000)
    easing: Literal["linear", "easeIn", "easeOut", "easeInOut"] = "easeInOut"


class FreezeFrameParams(EffectParams):
    hold_ms: int = Field(default=500, ge=50, le=5000)


class SpeedRampParams(EffectParams):
    start_speed: float = Field(default=1.0, ge=0.1, le=4.0)
    end_speed: float = Field(default=2.0, ge=0.1, le=4.0)
    curve: Literal["linear", "ramp_up", "ramp_down", "s_curve"] = "s_curve"


class ShakeParams(EffectParams):
    intensity: float = Field(default=5.0, ge=0.0, le=20.0)
    duration_ms: int = Field(default=300, ge=50, le=2000)


class GlitchParams(EffectParams):
    intensity: float = Field(default=0.3, ge=0.0, le=1.0)
    duration_ms: int = Field(default=200, ge=50, le=2000)


class VignetteParams(EffectParams):
    intensity: float = Field(default=0.4, ge=0.0, le=1.0)
    color: str = "#000000"


class FilmGrainParams(EffectParams):
    intensity: float = Field(default=0.2, ge=0.0, le=1.0)


class ColorPopParams(EffectParams):
    hue_shift: float = Field(default=0.0, ge=-180.0, le=180.0)
    saturation: float = Field(default=1.5, ge=0.0, le=3.0)


class TextKineticParams(EffectParams):
    text: str = Field(..., min_length=1, max_length=200)
    animation: Literal["fade_up", "typewriter", "pop", "slide_left"] = "fade_up"
    font_size: int = Field(default=48, ge=8, le=200)


class LowerThirdParams(EffectParams):
    text: str = Field(..., min_length=1, max_length=200)
    subtext: Optional[str] = Field(default=None, max_length=200)
    style: Literal["minimal", "bold", "news"] = "minimal"


class CalloutArrowParams(EffectParams):
    direction: Literal["up", "down", "left", "right"] = "down"
    color: str = "#f59e0b"


class SfxParams(EffectParams):
    gain_db: float = Field(default=-6.0, ge=-60.0, le=12.0)


class WhooshSfxParams(SfxParams):
    variant: Literal["short", "long", "dramatic"] = "short"


class DingSfxParams(SfxParams):
    variant: Literal["bell", "chime", "coin"] = "bell"


class RecordScratchSfxParams(SfxParams):
    pass


class Effect(BaseModelCamel):
    id: Optional[str] = None
    type: Literal[
        "zoom_punch_in",
        "focus_pull",
        "freeze_frame",
        "speed_ramp",
        "shake",
        "glitch",
        "vignette",
        "film_grain",
        "color_pop",
        "text_kinetic",
        "lower_third",
        "callout_arrow",
        "whoosh_sfx",
        "ding_sfx",
        "record_scratch_sfx",
    ]
    start_s: float = Field(ge=0.0)
    duration_s: float = Field(ge=0.0)
    params: Any


class CutListGlobals(BaseModelCamel):
    total_duration_s: float
    tempo_bpm: float
    time_signature: str = "4/4"
    key: Optional[str] = None
    energy_curve: List[float] = Field(default_factory=list)
    section_markers: List["SectionMarker"] = Field(default_factory=list)
    color_grade_ref: Optional[str] = None
    aspect_ratio: str = "9:16"


class SectionMarker(BaseModelCamel):
    name: str
    start_s: float
    end_s: float


class Slot(BaseModelCamel):
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
    effects: List[Effect] = Field(default_factory=list)


class Overlay(BaseModelCamel):
    text: str
    start_s: float
    end_s: float
    position: str = "center"
    font: str = "Inter"
    font_size_px: int = 48
    color: str = "#FFFFFF"
    stroke: Optional[str] = "#000000"
    animation: str = "none"


class AudioTrack(BaseModelCamel):
    asset_id: str
    gain_db: float = Field(default=0.0, ge=-60.0, le=12.0)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    fade_in_s: float = Field(default=0.0, ge=0.0)
    fade_out_s: float = Field(default=0.0, ge=0.0)


class CutList(BaseModelCamel):
    globals: CutListGlobals
    slots: List[Slot]
    overlays: List[Overlay] = Field(default_factory=list)
    audio_tracks: List[AudioTrack] = Field(default_factory=list)


class ShotBoundary(BaseModelCamel):
    start_frame: int
    end_frame: int
    start_s: float
    end_s: float
    is_gradual: bool = False
    confidence: float = 1.0


class BeatSegment(BaseModelCamel):
    start: float
    end: float
    label: str


class BeatGrid(BaseModelCamel):
    bpm: float
    beats: List[float]
    downbeats: List[float]
    beat_positions: List[float]
    segments: List[BeatSegment]


class ShotAnalysis(BaseModelCamel):
    shot_size: str
    motion: str
    subject_type: str
    lighting: str
    dominant_color: str
    camera_move: str


class StyleAnalysis(BaseModelCamel):
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


class ClipScore(BaseModelCamel):
    clip_id: str
    semantic_score: float = 0.0
    shot_type_score: float = 0.0
    aesthetic_score: float = 0.0
    motion_score: float = 0.0
    duration_score: float = 0.0
    diversity_penalty: float = 0.0
    total_score: float = 0.0


class RenderConfig(BaseModelCamel):
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
    audio_tracks: List[AudioTrack] = Field(default_factory=list)
