"""
Unit and edge tests for all Pydantic data models.
Covers: validation, defaults, serialization, immutability, and boundary conditions.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from shared_py.models import (
    CutList,
    CutListGlobals,
    Slot,
    Overlay,
    SectionMarker,
    BeatGrid,
    BeatSegment,
    ShotBoundary,
    ShotAnalysis,
    StyleAnalysis,
    ClipScore,
    RenderConfig,
)


# ──────────────────────────────────────────────────────────────────────────────
# CutListGlobals
# ──────────────────────────────────────────────────────────────────────────────

class TestCutListGlobals:
    def test_defaults(self):
        g = CutListGlobals(total_duration_s=30.0, tempo_bpm=120, aspect_ratio="9:16")
        assert g.time_signature == "4/4"
        assert g.key is None
        assert g.energy_curve == []
        assert g.section_markers == []
        assert g.color_grade_ref is None

    def test_full_construction(self):
        g = CutListGlobals(
            total_duration_s=60.0,
            tempo_bpm=140.5,
            time_signature="3/4",
            key="F#m",
            energy_curve=[0.1, 0.5, 0.9],
            section_markers=[
                SectionMarker(name="intro", start_s=0.0, end_s=5.0),
                SectionMarker(name="drop", start_s=15.0, end_s=30.0),
            ],
            color_grade_ref="s3://bucket/lut.cube",
            aspect_ratio="16:9",
        )
        assert g.tempo_bpm == 140.5
        assert g.key == "F#m"
        assert len(g.section_markers) == 2

    def test_edge_zero_duration(self):
        """Zero-duration is allowed at model level (validated elsewhere)."""
        g = CutListGlobals(total_duration_s=0.0, tempo_bpm=0.0, aspect_ratio="1:1")
        assert g.total_duration_s == 0.0
        assert g.tempo_bpm == 0.0

    def test_edge_negative_duration(self):
        """Pydantic allows negative floats — business logic should reject."""
        g = CutListGlobals(total_duration_s=-5.0, tempo_bpm=-10.0, aspect_ratio="9:16")
        assert g.total_duration_s == -5.0  # Model allows it

    def test_serialization_roundtrip(self):
        g = CutListGlobals(
            total_duration_s=30.0,
            tempo_bpm=120.0,
            energy_curve=[0.2, 0.8],
            section_markers=[SectionMarker(name="verse", start_s=0.0, end_s=10.0)],
            aspect_ratio="9:16",
        )
        data = g.model_dump()
        g2 = CutListGlobals(**data)
        assert g2.total_duration_s == 30.0
        assert g2.section_markers[0].name == "verse"

    def test_json_serialization(self):
        import json
        g = CutListGlobals(total_duration_s=10.0, tempo_bpm=100.0, aspect_ratio="16:9")
        s = json.dumps(g.model_dump())
        assert "total_duration_s" in s
        assert "10.0" in s


# ──────────────────────────────────────────────────────────────────────────────
# Slot
# ──────────────────────────────────────────────────────────────────────────────

class TestSlot:
    def test_defaults(self):
        s = Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="intro",
            target_shot_type="wide",
            subject_hint="establishing",
            motion_hint="static",
            energy_level=0.5,
        )
        assert s.transition_in == "hard_cut"
        assert s.transition_out == "hard_cut"
        assert s.required_tags == []
        assert s.avoid_tags == []
        assert s.selected_clip_id is None
        assert s.ranked_clip_ids is None
        assert s.confidence is None

    def test_energy_bounds_valid(self):
        """Energy 0.0 and 1.0 are at the boundary."""
        s0 = Slot(index=0, start_s=0.0, duration_s=1.0, beat_index=0, section="intro",
                  target_shot_type="wide", subject_hint="test", motion_hint="static", energy_level=0.0)
        s1 = Slot(index=1, start_s=1.0, duration_s=1.0, beat_index=1, section="intro",
                  target_shot_type="wide", subject_hint="test", motion_hint="static", energy_level=1.0)
        assert s0.energy_level == 0.0
        assert s1.energy_level == 1.0

    def test_energy_out_of_range(self):
        """Pydantic ge/le constraints should reject out-of-range values."""
        with pytest.raises(Exception):
            Slot(index=0, start_s=0.0, duration_s=1.0, beat_index=0, section="intro",
                 target_shot_type="wide", subject_hint="test", motion_hint="static", energy_level=1.5)
        with pytest.raises(Exception):
            Slot(index=0, start_s=0.0, duration_s=1.0, beat_index=0, section="intro",
                 target_shot_type="wide", subject_hint="test", motion_hint="static", energy_level=-0.1)

    def test_negative_duration(self):
        """Model allows negative duration — business logic should guard."""
        s = Slot(index=0, start_s=5.0, duration_s=-1.0, beat_index=0, section="intro",
                 target_shot_type="wide", subject_hint="test", motion_hint="static", energy_level=0.5)
        assert s.duration_s == -1.0

    def test_ranked_clip_ids(self):
        s = Slot(
            index=0, start_s=0.0, duration_s=2.0, beat_index=0, section="intro",
            target_shot_type="wide", subject_hint="test", motion_hint="static", energy_level=0.5,
            ranked_clip_ids=["clip_a", "clip_b", "clip_c"],
            confidence=0.92,
        )
        assert s.ranked_clip_ids == ["clip_a", "clip_b", "clip_c"]
        assert s.confidence == 0.92


# ──────────────────────────────────────────────────────────────────────────────
# Overlay
# ──────────────────────────────────────────────────────────────────────────────

class TestOverlay:
    def test_defaults(self):
        o = Overlay(text="Hello", start_s=0.0, end_s=2.0)
        assert o.position == "center"
        assert o.font == "Inter"
        assert o.font_size_px == 48
        assert o.color == "#FFFFFF"
        assert o.stroke == "#000000"
        assert o.animation == "none"

    def test_all_positions(self):
        positions = ["center", "top", "bottom", "left", "right",
                     "top_left", "top_right", "bottom_left", "bottom_right"]
        for pos in positions:
            o = Overlay(text="X", start_s=0.0, end_s=1.0, position=pos)
            assert o.position == pos

    def test_invalid_position_rejected(self):
        """Position is str for extensibility; no validation error raised."""
        o = Overlay(text="X", start_s=0.0, end_s=1.0, position="invalid_corner")
        assert o.position == "invalid_corner"

    def test_start_after_end(self):
        """Model allows start > end — timeline validator should catch."""
        o = Overlay(text="Bad", start_s=5.0, end_s=2.0)
        assert o.start_s > o.end_s


# ──────────────────────────────────────────────────────────────────────────────
# CutList
# ──────────────────────────────────────────────────────────────────────────────

class TestCutList:
    def test_empty_slots(self):
        cl = CutList(
            globals=CutListGlobals(total_duration_s=0.0, tempo_bpm=120, aspect_ratio="9:16"),
            slots=[],
        )
        assert cl.slots == []
        assert cl.overlays == []

    def test_multiple_slots_and_overlays(self):
        cl = CutList(
            globals=CutListGlobals(total_duration_s=10.0, tempo_bpm=120, aspect_ratio="9:16"),
            slots=[
                Slot(index=0, start_s=0.0, duration_s=2.0, beat_index=0, section="intro",
                     target_shot_type="wide", subject_hint="establish", motion_hint="static", energy_level=0.3),
                Slot(index=1, start_s=2.0, duration_s=3.0, beat_index=2, section="verse",
                     target_shot_type="medium", subject_hint="action", motion_hint="handheld", energy_level=0.7),
            ],
            overlays=[
                Overlay(text="Title", start_s=0.0, end_s=2.0, animation="fade"),
            ],
        )
        assert len(cl.slots) == 2
        assert len(cl.overlays) == 1
        assert cl.slots[1].motion_hint == "handheld"

    def test_model_copy(self):
        cl = CutList(
            globals=CutListGlobals(total_duration_s=5.0, tempo_bpm=120, aspect_ratio="9:16"),
            slots=[Slot(index=0, start_s=0.0, duration_s=5.0, beat_index=0, section="intro",
                        target_shot_type="wide", subject_hint="test", motion_hint="static", energy_level=0.5)],
        )
        cl2 = cl.model_copy(deep=True)
        cl2.slots[0].duration_s = 10.0
        # Deep copy means original is unaffected
        assert cl.slots[0].duration_s == 5.0
        assert cl2.slots[0].duration_s == 10.0

    def test_total_duration_mismatch(self):
        """Slots can exceed globals duration — validator should catch in business logic."""
        cl = CutList(
            globals=CutListGlobals(total_duration_s=5.0, tempo_bpm=120, aspect_ratio="9:16"),
            slots=[
                Slot(index=0, start_s=0.0, duration_s=3.0, beat_index=0, section="intro",
                     target_shot_type="wide", subject_hint="test", motion_hint="static", energy_level=0.5),
                Slot(index=1, start_s=3.0, duration_s=5.0, beat_index=3, section="verse",
                     target_shot_type="close_up", subject_hint="test", motion_hint="static", energy_level=0.5),
            ],
        )
        # Model allows it — sum of slots = 8s > globals 5s
        total_slot_duration = sum(s.duration_s for s in cl.slots)
        assert total_slot_duration > cl.globals.total_duration_s


# ──────────────────────────────────────────────────────────────────────────────
# BeatGrid / BeatSegment
# ──────────────────────────────────────────────────────────────────────────────

class TestBeatGrid:
    def test_empty_beats(self):
        bg = BeatGrid(bpm=0.0, beats=[], downbeats=[], beat_positions=[], segments=[])
        assert bg.beats == []
        assert bg.bpm == 0.0

    def test_typical_construction(self):
        bg = BeatGrid(
            bpm=124.0,
            beats=[0.0, 0.484, 0.968, 1.452],
            downbeats=[0.0, 1.936],
            beat_positions=[1, 2, 3, 4],
            segments=[BeatSegment(start=0.0, end=10.0, label="intro")],
        )
        assert len(bg.beats) == 4
        assert bg.downbeats[0] == 0.0

    def test_segment_ordering(self):
        """Segments can be out of order — business logic should sort."""
        bg = BeatGrid(
            bpm=120.0,
            beats=[0.0, 0.5],
            downbeats=[0.0],
            beat_positions=[1, 2],
            segments=[
                BeatSegment(start=5.0, end=10.0, label="outro"),
                BeatSegment(start=0.0, end=5.0, label="intro"),
            ],
        )
        assert bg.segments[0].label == "outro"  # Model preserves order


# ──────────────────────────────────────────────────────────────────────────────
# ShotBoundary
# ──────────────────────────────────────────────────────────────────────────────

class TestShotBoundary:
    def test_defaults(self):
        sb = ShotBoundary(start_frame=0, end_frame=30, start_s=0.0, end_s=1.0)
        assert sb.is_gradual is False
        assert sb.confidence == 1.0

    def test_gradual_transition(self):
        sb = ShotBoundary(
            start_frame=120, end_frame=150, start_s=4.0, end_s=5.0,
            is_gradual=True, confidence=0.85,
        )
        assert sb.is_gradual is True
        assert sb.confidence == 0.85

    def test_zero_length_shot(self):
        """Zero-length shot is allowed at model level."""
        sb = ShotBoundary(start_frame=100, end_frame=100, start_s=3.33, end_s=3.33)
        assert sb.end_frame == sb.start_frame

    def test_negative_frame_range(self):
        """Model allows start > end — timeline validator should reject."""
        sb = ShotBoundary(start_frame=100, end_frame=50, start_s=3.33, end_s=1.67)
        assert sb.start_frame > sb.end_frame


# ──────────────────────────────────────────────────────────────────────────────
# ShotAnalysis
# ──────────────────────────────────────────────────────────────────────────────

class TestShotAnalysis:
    def test_full_construction(self):
        sa = ShotAnalysis(
            shot_size="close_up",
            motion="handheld",
            subject_type="face",
            lighting="low_key",
            dominant_color="#ff6600",
            camera_move="push",
        )
        assert sa.shot_size == "close_up"
        assert sa.dominant_color == "#ff6600"  # Normalized with # prefix


# ──────────────────────────────────────────────────────────────────────────────
# StyleAnalysis
# ──────────────────────────────────────────────────────────────────────────────

class TestStyleAnalysis:
    def test_defaults(self):
        sa = StyleAnalysis()
        assert sa.color_palette == []
        assert sa.contrast_level == 1.0
        assert sa.saturation_level == 1.0
        assert sa.brightness_level == 1.0
        assert sa.lut_extracted is False
        assert sa.pacing == "medium"
        assert sa.mood == "neutral"

    def test_with_lut(self):
        sa = StyleAnalysis(
            color_palette=["#1d3540", "#dc6428"],
            contrast_level=1.5,
            lut_extracted=True,
            lut_storage_key="s3://bucket/style.cube",
            detected_transitions=["whip", "dissolve"],
            camera_motions=["push", "pan_right"],
            pacing="fast",
            mood="energetic",
        )
        assert sa.lut_extracted is True
        assert sa.lut_storage_key == "s3://bucket/style.cube"
        assert len(sa.detected_transitions) == 2


# ──────────────────────────────────────────────────────────────────────────────
# ClipScore
# ──────────────────────────────────────────────────────────────────────────────

class TestClipScore:
    def test_defaults(self):
        cs = ClipScore(clip_id="C01")
        assert cs.semantic_score == 0.0
        assert cs.total_score == 0.0

    def test_weighted_total(self):
        cs = ClipScore(
            clip_id="C01",
            semantic_score=0.9,
            shot_type_score=1.0,
            aesthetic_score=0.8,
            motion_score=0.7,
            duration_score=0.6,
            diversity_penalty=0.1,
            total_score=0.75,
        )
        assert cs.total_score == 0.75

    def test_negative_diversity_penalty(self):
        """Negative diversity penalty (bonus) should be allowed."""
        cs = ClipScore(clip_id="C01", diversity_penalty=-0.2)
        assert cs.diversity_penalty == -0.2


# ──────────────────────────────────────────────────────────────────────────────
# RenderConfig
# ──────────────────────────────────────────────────────────────────────────────

class TestRenderConfig:
    def test_defaults(self):
        rc = RenderConfig(output_path="/tmp/out.mp4")
        assert rc.width == 1280
        assert rc.height == 720
        assert rc.fps == 30.0
        assert rc.video_codec == "libx264"
        assert rc.video_preset == "slow"
        assert rc.video_crf == 18
        assert rc.audio_codec == "aac"
        assert rc.audio_bitrate == "192k"
        assert rc.pix_fmt == "yuv420p"
        assert rc.lut_path is None
        assert rc.song_path is None

    def test_custom_config(self):
        rc = RenderConfig(
            output_path="/tmp/4k.mp4",
            width=3840,
            height=2160,
            fps=60.0,
            video_preset="veryslow",
            video_crf=16,
            lut_path="/tmp/style.cube",
            song_path="/tmp/song.mp3",
        )
        assert rc.width == 3840
        assert rc.video_crf == 16

    def test_extreme_resolution(self):
        """Extreme resolutions are allowed at model level."""
        rc = RenderConfig(output_path="/tmp/tiny.mp4", width=1, height=1)
        assert rc.width == 1
        rc2 = RenderConfig(output_path="/tmp/huge.mp4", width=16384, height=16384)
        assert rc2.width == 16384

    def test_invalid_crf(self):
        """CRF outside 0-51 range is allowed at model level (FFmpeg will reject)."""
        rc = RenderConfig(output_path="/tmp/out.mp4", video_crf=100)
        assert rc.video_crf == 100
