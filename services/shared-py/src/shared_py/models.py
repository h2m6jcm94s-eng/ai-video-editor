# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
from datetime import datetime, timezone
from typing import List, Optional, Literal, Any, Dict, Tuple
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel

from shared_py.feature_tracer import FeaturePathReport


TextZLayer = Literal["on_top", "behind_subject"]
TextDensity = Literal["low", "medium", "high"]

EmotionLabel = Literal[
    "joy",
    "calm",
    "intrigue",
    "tension",
    "grief",
    "triumph",
    "fear",
    "anger",
    "awe",
]


class BaseModelCamel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class EmotionSample(BaseModelCamel):
    """A single emotion measurement at a point in time."""

    t_s: float
    primary_emotion: EmotionLabel = "calm"
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.0, ge=0.0, le=1.0)
    dominance: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SectionMoodTags(BaseModelCamel):
    """CLAP mood tags for one song section."""

    start_s: float
    end_s: float
    section_label: str
    top_moods: List[Tuple[str, float]] = Field(default_factory=list)


class SongMoodProfile(BaseModelCamel):
    """Per-section and global mood/genre tags for a song."""

    song_hash: str
    genre_tags: List[Tuple[str, float]] = Field(default_factory=list)
    section_moods: List[SectionMoodTags] = Field(default_factory=list)


class VocalEmotionSample(BaseModelCamel):
    """Emotion distribution for one vocal window."""

    t_center_s: float
    dominant_emotion: str
    distribution: Dict[str, float] = Field(default_factory=dict)
    rms: float


class VocalEmotionCurve(BaseModelCamel):
    """Time-indexed vocal emotion trajectory from a song's vocals stem."""

    song_hash: str
    samples: List[VocalEmotionSample] = Field(default_factory=list)
    silent_ratio: float = 0.0


class MusicEvent(BaseModelCamel):
    """A single detected music event."""

    time_s: float
    intensity: float
    stem: str


class MusicEventGrid(BaseModelCamel):
    """Detected music events across all stems."""

    song_hash: str
    kick_times: List[float] = Field(default_factory=list)
    snare_times: List[float] = Field(default_factory=list)
    hihat_times: List[float] = Field(default_factory=list)
    bass_drop_times: List[float] = Field(default_factory=list)
    vocal_onset_times: List[float] = Field(default_factory=list)
    phrase_boundary_times: List[float] = Field(default_factory=list)
    sweep_peak_times: List[float] = Field(default_factory=list)

    def events_in_window(self, t: float, window_s: float = 0.1) -> List[MusicEvent]:
        """Return all events within ``±window_s`` of ``t``.

        Sorted by a simple priority (drum > bass > vocals > other).
        """
        priority = {
            "snare": 100,
            "kick": 90,
            "bass_drop": 85,
            "vocal_onset": 70,
            "phrase_boundary": 60,
            "sweep_peak": 55,
        }
        events: List[MusicEvent] = []
        for event_type, times in [
            ("snare", self.snare_times),
            ("kick", self.kick_times),
            ("bass_drop", self.bass_drop_times),
            ("vocal_onset", self.vocal_onset_times),
            ("phrase_boundary", self.phrase_boundary_times),
            ("sweep_peak", self.sweep_peak_times),
        ]:
            for time_s in times:
                if abs(time_s - t) <= window_s:
                    events.append(
                        MusicEvent(
                            time_s=time_s,
                            intensity=1.0,
                            stem=event_type,
                        )
                    )
        events.sort(key=lambda e: (-priority.get(e.stem, 0), abs(e.time_s - t)))
        return events


class SongMeaning(BaseModelCamel):
    """Unified song analysis produced by the ingest worker.

    Aggregates mood tags, vocal emotion, and per-stem music events into a single
    artifact that the reason worker can load in one lookup.
    """

    song_hash: str
    genre_tags: List[Tuple[str, float]] = Field(default_factory=list)
    section_moods: List[SectionMoodTags] = Field(default_factory=list)
    vocal_emotion_curve: VocalEmotionCurve = Field(
        default_factory=lambda: VocalEmotionCurve(song_hash="")
    )
    music_event_grid: MusicEventGrid = Field(
        default_factory=lambda: MusicEventGrid(song_hash="")
    )


class ClipEmotionProfile(BaseModelCamel):
    """Fused emotion profile for a user clip.

    Used by the narrative arc ranker to match clips to arc beats.
    """

    primary_emotion: EmotionLabel = "calm"
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.0, ge=0.0, le=1.0)
    dominance: float = Field(default=0.0, ge=0.0, le=1.0)
    face_emotion_distribution: Dict[str, float] = Field(default_factory=dict)
    audio_prosody_emotion: EmotionLabel = "calm"
    audio_prosody_arousal: float = Field(default=0.0, ge=0.0, le=1.0)
    color_warmth: float = Field(default=0.0, ge=-1.0, le=1.0)
    motion_vibe: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timeline: List[EmotionSample] = Field(default_factory=list)

    def to_vector(self) -> List[float]:
        """Return a fixed-length vector usable for cosine-similarity scoring."""
        order = ["joy", "calm", "intrigue", "tension", "grief", "triumph", "fear", "anger", "awe"]
        return (
            [self.face_emotion_distribution.get(k, 0.0) for k in order]
            + [self.valence, self.arousal, self.dominance]
        )


class ClipIdentityInfo(BaseModelCamel):
    clip_id: str
    identity_ids: List[int] = Field(default_factory=list)
    screen_time_s: float = 0.0


class ProjectIdentities(BaseModelCamel):
    identities: List[Dict[str, Any]] = Field(default_factory=list)
    protagonists: List[int] = Field(default_factory=list)
    clip_identity_map: Dict[str, List[int]] = Field(default_factory=dict)


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
    identity_ids_present: List[int] = Field(default_factory=list)
    protagonist_matte_enabled: bool = True
    enable_kinetic_text: bool = False
    text_z_layer: TextZLayer = "on_top"
    text_density: TextDensity = "medium"
    kinetic_text: Optional[str] = None
    kinetic_text_style: Optional[str] = None
    kinetic_text_color: Optional[str] = None
    effects: List[Effect] = Field(default_factory=list)
    source_window_start_s: Optional[float] = None
    anticipation_offset_s: float = 0.0
    heatmap_score: Optional[float] = None
    story_beat: Optional[str] = None
    arc_beat_emotion_target: Optional[EmotionLabel] = None
    arc_beat_preferred_shots: List[str] = Field(default_factory=list)
    is_glimpse: bool = False
    emotion_match_score: float = 0.0


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
    feature_runtime_report: List[FeaturePathReport] = Field(default_factory=list)
    real_path_ratio: float = 0.0
    demo_grade: bool = False
    slot_window_fallback_count: Optional[int] = None


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
    total_cuts: int = 0
    avg_cut_duration_s: float = 0.0
    std_cut_duration_s: float = 0.0
    min_cut_duration_s: float = 0.0
    max_cut_duration_s: float = 0.0
    cut_density_per_min: float = 0.0
    verse_cut_density: float = 0.0
    chorus_cut_density: float = 0.0
    drop_cut_density: float = 0.0
    intro_cut_density: float = 0.0
    outro_cut_density: float = 0.0
    build_up_cut_density: float = 0.0
    hard_cut_ratio: float = 0.0
    gradual_transition_ratio: float = 0.0
    cuts_on_downbeat_ratio: float = 0.0


class MotionFamily(BaseModelCamel):
    avg_motion_energy: float = 0.0
    max_motion_energy: float = 0.0
    motion_energy_std: float = 0.0
    pct_still_shots: float = 0.0
    pct_pan_left: float = 0.0
    pct_pan_right: float = 0.0
    pct_tilt_up: float = 0.0
    pct_tilt_down: float = 0.0
    pct_zoom_in: float = 0.0
    pct_zoom_out: float = 0.0
    pct_handheld: float = 0.0
    pct_gimbal: float = 0.0


class DwellFamily(BaseModelCamel):
    avg_face_size_ratio: float = 0.0
    max_face_size_ratio: float = 0.0
    avg_subjects_per_shot: float = 0.0
    pct_shots_with_face: float = 0.0
    avg_face_screen_time_s: float = 0.0
    protagonist_present_ratio: float = 0.0
    avg_shot_subject_count: float = 0.0
    face_size_variance: float = 0.0


class AudioAlignFamily(BaseModelCamel):
    cut_to_beat_alignment: float = 0.0
    cut_to_downbeat_alignment: float = 0.0
    verse_cut_to_beat_ratio: float = 0.0
    chorus_cut_to_beat_ratio: float = 0.0
    drop_cut_to_beat_ratio: float = 0.0
    avg_cut_to_nearest_beat_s: float = 0.0
    music_duck_frequency: float = 0.0
    dialogue_clip_ratio: float = 0.0
    iconic_line_count: int = 0
    avg_dialogue_duration_s: float = 0.0


class CompositionFamily(BaseModelCamel):
    dominant_shot_size: Literal["close_up", "medium", "wide"] = "medium"
    pct_close_up: float = 0.0
    pct_medium_shot: float = 0.0
    pct_wide_shot: float = 0.0
    rule_of_thirds_ratio: float = 0.0


class StyleGenomeFamilies(BaseModelCamel):
    cut_rhythm: CutRhythmFamily = Field(default_factory=CutRhythmFamily)
    motion: MotionFamily = Field(default_factory=MotionFamily)
    dwell: DwellFamily = Field(default_factory=DwellFamily)
    audio_align: AudioAlignFamily = Field(default_factory=AudioAlignFamily)
    composition: CompositionFamily = Field(default_factory=CompositionFamily)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class StyleGenome(BaseModelCamel):
    version: str = "0.1.0"
    feature_count: int = 50
    families: StyleGenomeFamilies = Field(default_factory=StyleGenomeFamilies)
    extracted_at: str = Field(default_factory=_utc_now_iso)


class BehaviorVector(BaseModelCamel):
    """Continuous output parameters that drive cutlist generation and audio policy.

    This model is intentionally minimal for Phase 1 and will grow as adaptive
    features are added. All values are normalized and unit-agnostic where
    possible so the same interface can be served by heuristics, KNN, or an MLP.
    """

    # Cut rhythm
    cut_density_per_sec: float = Field(default=0.16, ge=0.01, le=2.0)
    slot_duration_mean_s: float = Field(default=2.5, ge=0.25, le=30.0)
    slot_duration_std_s: float = Field(default=0.8, ge=0.0, le=10.0)

    # Audio policy (placeholders; wired in PR-2)
    clip_audio_inclusion_strategy: str = "speech_only"
    clip_audio_min_importance: float = Field(default=0.3, ge=0.0, le=1.0)
    sfx_mute_aggressiveness: float = Field(default=0.3, ge=0.0, le=1.0)
    song_background_mode: str = "ambient"

    # Transition / effects (placeholders; expanded later)
    hard_cut_ratio: float = Field(default=0.7, ge=0.0, le=1.0)
    duck_aggressiveness: float = Field(default=0.5, ge=0.0, le=1.0)
    text_density_per_sec: float = Field(default=0.0, ge=0.0, le=5.0)
    effect_intensity: float = Field(default=0.5, ge=0.0, le=1.0)

    @classmethod
    def default_for_music_video(cls) -> "BehaviorVector":
        return cls(
            cut_density_per_sec=0.16,
            slot_duration_mean_s=2.5,
            slot_duration_std_s=0.8,
            clip_audio_inclusion_strategy="iconic_only",
            clip_audio_min_importance=0.85,
            sfx_mute_aggressiveness=0.9,
            song_background_mode="dominant",
            hard_cut_ratio=0.7,
            duck_aggressiveness=0.5,
            text_density_per_sec=0.0,
            effect_intensity=0.6,
        )

    @classmethod
    def default_for_speech_forward(cls) -> "BehaviorVector":
        return cls(
            cut_density_per_sec=0.08,
            slot_duration_mean_s=4.0,
            slot_duration_std_s=1.2,
            clip_audio_inclusion_strategy="speech_only",
            clip_audio_min_importance=0.3,
            sfx_mute_aggressiveness=0.95,
            song_background_mode="ambient",
            hard_cut_ratio=0.8,
            duck_aggressiveness=0.9,
            text_density_per_sec=0.0,
            effect_intensity=0.3,
        )


class AdaptiveFeatures(BaseModelCamel):
    """Independent toggles for adaptive features. Each is safe to disable."""

    use_adaptive_slot_density: bool = True
    use_adaptive_audio_policy: bool = False
    use_iconic_quote_detection: bool = False
    use_emotion_led_cuts: bool = False
    use_corpus_knn: bool = False
    use_per_user_bias: bool = False


class ContentSignals(BaseModelCamel):
    """Continuous measurements extracted from project content.

    Expanded in PR-A1 to include the signal dimensions required by the universal
    feature-gating helper. Missing fields default to zero/false so telemetry
    records written before this PR still validate.
    """

    speech_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_speech_segment_duration_s: float = Field(default=0.0, ge=0.0)
    multi_speaker_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    song_present: bool = False
    song_has_vocals: bool = False
    song_energy_mean: float = Field(default=0.5, ge=0.0, le=1.0)
    song_tempo_bpm: float = Field(default=120.0, ge=20.0, le=300.0)
    song_section_count: int = Field(default=0, ge=0)
    clip_count: int = Field(default=0, ge=0)
    clip_avg_duration_s: float = Field(default=0.0, ge=0.0)
    motion_density: float = Field(default=0.5, ge=0.0, le=1.0)
    motion_variance: float = Field(default=0.0, ge=0.0, le=1.0)
    aesthetic_score_mean: float = Field(default=0.0, ge=0.0, le=1.0)
    face_screentime_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    multi_face_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    shot_diversity: float = Field(default=0.0, ge=0.0, le=1.0)
    screen_capture: bool = False
    reference_present: bool = False
    reference_color_variance: float = Field(default=0.0, ge=0.0, le=1.0)
    reference_genome_hash: Optional[str] = None


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
    emotion_match_score: float = 0.0
    arc_beat_name: Optional[str] = None
    emotion_profile: Optional[ClipEmotionProfile] = None


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
    # Hardware-acceleration flags.  These are hints: the compiler falls back to
    # software encode/decode automatically if the requested path fails.
    use_nvenc: bool = False
    nvenc_preset: str = "p5"
    nvenc_cq: int = 19
    use_hwaccel: bool = False

    clip_order_fallback: str = "smart"
    clip_order_smart_threshold: float = 0.15
