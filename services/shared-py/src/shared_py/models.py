# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel


class BaseModelCamel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


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
    mask_asset_id: Optional[str] = None
    mask_enabled: bool = True
    effects: List[Effect] = Field(default_factory=list)
    source_window_start_s: Optional[float] = None
    heatmap_score: Optional[float] = None


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


class Subtitle(BaseModelCamel):
    id: str
    text: str
    start_s: float
    end_s: float
    speaker: Optional[str] = None
    confidence: Optional[float] = None


class AudioTrack(BaseModelCamel):
    asset_id: str
    role: Literal["music", "dialogue", "voiceover", "sfx", "ambience"] = "music"
    gain_db: float = Field(default=0.0, ge=-60.0, le=12.0)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    fade_in_s: float = Field(default=0.0, ge=0.0)
    fade_out_s: float = Field(default=0.0, ge=0.0)
    duck_gain_db: float = Field(default=-12.0, ge=-60.0, le=0.0)
    duck_attack_ms: int = Field(default=20, ge=1, le=1000)
    duck_release_ms: int = Field(default=250, ge=10, le=2000)
    duck_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    # Source window inside the asset file (for dialogue extracted from clips).
    source_start_s: Optional[float] = None
    source_end_s: Optional[float] = None
    # Link back to the cutlist slot that produced this track.
    slot_index: Optional[int] = None
    # If True, sidechain ducking is skipped for this music track (e.g. drop).
    duck_disabled: bool = False


class CutList(BaseModelCamel):
    globals: CutListGlobals
    slots: List[Slot]
    overlays: List[Overlay] = Field(default_factory=list)
    subtitles: List[Subtitle] = Field(default_factory=list)
    audio_tracks: List[AudioTrack] = Field(default_factory=list)


class ShotBoundary(BaseModelCamel):
    start_frame: int
    end_frame: int
    start_s: float
    end_s: float
    is_gradual: bool = False
    confidence: float = 1.0
    transition_in: str = "hard_cut"
    transition_out: str = "hard_cut"


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
    detected_transition_types: List[str] = Field(default_factory=list)
    detected_overlays: List[Overlay] = Field(default_factory=list)
    camera_motions: List[str] = Field(default_factory=list)
    pacing: str = "medium"
    mood: str = "neutral"


class CutRhythmFamily(BaseModelCamel):
    total_cuts: Optional[int] = None
    avg_cut_duration_s: Optional[float] = None
    std_cut_duration_s: Optional[float] = None
    min_cut_duration_s: Optional[float] = None
    max_cut_duration_s: Optional[float] = None
    cut_density_per_min: Optional[float] = None
    verse_cut_density: Optional[float] = None
    chorus_cut_density: Optional[float] = None
    drop_cut_density: Optional[float] = None
    intro_cut_density: Optional[float] = None
    outro_cut_density: Optional[float] = None
    build_up_cut_density: Optional[float] = None
    hard_cut_ratio: Optional[float] = None
    gradual_transition_ratio: Optional[float] = None
    cuts_on_downbeat_ratio: Optional[float] = None


class MotionFamily(BaseModelCamel):
    avg_motion_energy: Optional[float] = None
    max_motion_energy: Optional[float] = None
    motion_energy_std: Optional[float] = None
    pct_still_shots: Optional[float] = None
    pct_pan_left: Optional[float] = None
    pct_pan_right: Optional[float] = None
    pct_tilt_up: Optional[float] = None
    pct_tilt_down: Optional[float] = None
    pct_zoom_in: Optional[float] = None
    pct_zoom_out: Optional[float] = None
    pct_handheld: Optional[float] = None
    pct_gimbal: Optional[float] = None


class DwellFamily(BaseModelCamel):
    avg_face_size_ratio: Optional[float] = None
    max_face_size_ratio: Optional[float] = None
    avg_subjects_per_shot: Optional[float] = None
    pct_shots_with_face: Optional[float] = None
    avg_face_screen_time_s: Optional[float] = None
    protagonist_present_ratio: Optional[float] = None
    avg_shot_subject_count: Optional[float] = None
    face_size_variance: Optional[float] = None


class AudioAlignFamily(BaseModelCamel):
    cut_to_beat_alignment: Optional[float] = None
    cut_to_downbeat_alignment: Optional[float] = None
    verse_cut_to_beat_ratio: Optional[float] = None
    chorus_cut_to_beat_ratio: Optional[float] = None
    drop_cut_to_beat_ratio: Optional[float] = None
    avg_cut_to_nearest_beat_s: Optional[float] = None
    music_duck_frequency: Optional[float] = None
    dialogue_clip_ratio: Optional[float] = None
    iconic_line_count: Optional[int] = None
    avg_dialogue_duration_s: Optional[float] = None


class CompositionFamily(BaseModelCamel):
    dominant_shot_size: Optional[Literal["close_up", "medium", "wide"]] = None
    pct_close_up: Optional[float] = None
    pct_medium_shot: Optional[float] = None
    pct_wide_shot: Optional[float] = None
    rule_of_thirds_ratio: Optional[float] = None


class StyleGenomeFamilies(BaseModelCamel):
    cut_rhythm: CutRhythmFamily = Field(default_factory=CutRhythmFamily)
    motion: MotionFamily = Field(default_factory=MotionFamily)
    dwell: DwellFamily = Field(default_factory=DwellFamily)
    audio_align: AudioAlignFamily = Field(default_factory=AudioAlignFamily)
    composition: CompositionFamily = Field(default_factory=CompositionFamily)


class StyleGenome(BaseModelCamel):
    version: str = "0.1.0"
    feature_count: int = 50
    families: StyleGenomeFamilies = Field(default_factory=StyleGenomeFamilies)
    extracted_at: Optional[str] = None


class ClipScore(BaseModelCamel):
    clip_id: str
    semantic_score: float = 0.0
    shot_type_score: float = 0.0
    aesthetic_score: float = 0.0
    motion_score: float = 0.0
    duration_score: float = 0.0
    window_score: float = 0.0
    window_start_s: Optional[float] = None
    dominant_motion: str = "still"
    diversity_penalty: float = 0.0
    repetition_penalty: float = 0.0
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
    mask_paths: Dict[str, str] = Field(default_factory=dict)
    slot_mask_paths: Dict[int, str] = Field(default_factory=dict)
    audio_tracks: List[AudioTrack] = Field(default_factory=list)
    audio_paths: Dict[str, str] = Field(default_factory=dict)
