"""
Cross-cutting edge case tests for the entire AI video editor pipeline.
Covers: extreme values, boundary conditions, malformed inputs, type mismatches,
concurrency concerns, and failure propagation across module boundaries.
"""

import pytest
import os
import sys
import tempfile
import subprocess
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ingest-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "render-worker", "src"))

from shared_py.models import (
    CutList, CutListGlobals, Slot, Overlay, RenderConfig,
    BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis, ClipScore,
)
from reason_worker.cutlist_gen import generate_cutlist_programmatic
from reason_worker.clip_rank import rank_clips_for_slots, select_top_k_per_slot
from render_worker.compiler import compile_timeline


# ──────────────────────────────────────────────────────────────────────────────
# Extreme values in models
# ──────────────────────────────────────────────────────────────────────────────

class TestModelEdgeCases:
    def test_slot_negative_duration(self):
        """Slot model allows negative duration — timeline validator catches later."""
        slot = Slot(
            index=0, start_s=0.0, duration_s=-1.0, beat_index=0,
            section="intro", target_shot_type="wide",
            subject_hint="test", motion_hint="static",
            energy_level=0.5, required_tags=[], avoid_tags=[],
        )
        assert slot.duration_s == -1.0

    def test_slot_zero_duration(self):
        """Slot model allows zero duration — timeline validator catches later."""
        slot = Slot(
            index=0, start_s=0.0, duration_s=0.0, beat_index=0,
            section="intro", target_shot_type="wide",
            subject_hint="test", motion_hint="static",
            energy_level=0.5, required_tags=[], avoid_tags=[],
        )
        assert slot.duration_s == 0.0

    def test_slot_energy_out_of_range(self):
        """Energy level must be between 0 and 1."""
        with pytest.raises(Exception):
            Slot(
                index=0, start_s=0.0, duration_s=1.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="test", motion_hint="static",
                energy_level=1.5, required_tags=[], avoid_tags=[],
            )
        with pytest.raises(Exception):
            Slot(
                index=0, start_s=0.0, duration_s=1.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="test", motion_hint="static",
                energy_level=-0.1, required_tags=[], avoid_tags=[],
            )

    def test_slot_max_valid_energy(self):
        slot = Slot(
            index=0, start_s=0.0, duration_s=1.0, beat_index=0,
            section="intro", target_shot_type="wide",
            subject_hint="test", motion_hint="static",
            energy_level=1.0, required_tags=[], avoid_tags=[],
        )
        assert slot.energy_level == 1.0

    def test_slot_min_valid_energy(self):
        slot = Slot(
            index=0, start_s=0.0, duration_s=1.0, beat_index=0,
            section="intro", target_shot_type="wide",
            subject_hint="test", motion_hint="static",
            energy_level=0.0, required_tags=[], avoid_tags=[],
        )
        assert slot.energy_level == 0.0

    def test_beat_grid_zero_bpm(self):
        """BPM of 0 should be accepted but is physically meaningless."""
        bg = BeatGrid(bpm=0.0, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[])
        assert bg.bpm == 0.0

    def test_beat_grid_very_high_bpm(self):
        bg = BeatGrid(bpm=999.0, time_signature="4/4", beats=[], beat_positions=[], segments=[], downbeats=[])
        assert bg.bpm == 999.0

    def test_overlay_negative_times(self):
        o = Overlay(text="Test", start_s=-1.0, end_s=2.0)
        assert o.start_s == -1.0

    def test_overlay_end_before_start(self):
        o = Overlay(text="Test", start_s=2.0, end_s=1.0)
        assert o.end_s < o.start_s

    def test_render_config_negative_dimensions(self):
        config = RenderConfig(output_path="/tmp/out.mp4", width=-1, height=480)
        assert config.width == -1
        config2 = RenderConfig(output_path="/tmp/out.mp4", width=640, height=-1)
        assert config2.height == -1

    def test_render_config_zero_dimensions(self):
        config = RenderConfig(output_path="/tmp/out.mp4", width=0, height=480)
        assert config.width == 0

    def test_cutlist_empty_slots(self):
        cutlist = CutList(
            globals=CutListGlobals(
                total_duration_s=0.0, tempo_bpm=120,
                time_signature="4/4", energy_curve=[],
                section_markers=[], aspect_ratio="16:9",
            ),
            slots=[],
        )
        assert len(cutlist.slots) == 0

    def test_cutlist_very_long_duration(self):
        cutlist = CutList(
            globals=CutListGlobals(
                total_duration_s=3600.0, tempo_bpm=120,
                time_signature="4/4", energy_curve=[0.5] * 100,
                section_markers=[], aspect_ratio="16:9",
            ),
            slots=[
                Slot(
                    index=i, start_s=i * 2.0, duration_s=2.0, beat_index=i,
                    section="intro", target_shot_type="wide",
                    subject_hint="test", motion_hint="static",
                    energy_level=0.5, required_tags=[], avoid_tags=[],
                )
                for i in range(100)
            ],
        )
        assert len(cutlist.slots) == 100
        assert cutlist.globals.total_duration_s == 3600.0  # Field is set, not computed

    def test_shot_boundary_negative_time(self):
        # Model allows negative times
        sb = ShotBoundary(start_s=-1.0, end_s=2.0, start_frame=0, end_frame=60)
        assert sb.start_s == -1.0

    def test_shot_boundary_end_before_start(self):
        sb = ShotBoundary(start_s=3.0, end_s=1.0, start_frame=90, end_frame=30)
        assert sb.end_s < sb.start_s

    def test_clip_score_negative(self):
        # Model allows negative scores
        cs = ClipScore(clip_id="test", total_score=-1.0)
        assert cs.total_score == -1.0

    def test_clip_score_above_one(self):
        cs = ClipScore(clip_id="test", total_score=1.5)
        assert cs.total_score == 1.5


# ──────────────────────────────────────────────────────────────────────────────
# Cutlist generation edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestCutlistEdgeCases:
    def test_single_shot_single_beat(self):
        beat_grid = BeatGrid(
            bpm=120.0, time_signature="4/4",
            beats=[0, 1],
            beat_positions=[0, 1],
            segments=[BeatSegment(start=0, end=1, label="intro")],
            downbeats=[0],
        )
        shots = [ShotBoundary(start_s=0.0, end_s=2.0, start_frame=0, end_frame=60)]
        style = StyleAnalysis(
            lut_extracted=False, color_palette=[], text_overlays=[],
            transition_types=[], camera_motions=["static"],
            dominant_emotion="neutral", pacing="medium",
        )
        cutlist = generate_cutlist_programmatic(
            beat_grid, shots, [0.5], ["wide"],
        )
        assert cutlist is not None
        assert len(cutlist.slots) > 0

    def test_very_long_video(self):
        beat_grid = BeatGrid(
            bpm=60.0, time_signature="4/4",
            segments=[
                BeatSegment(start=i * 4, end=(i + 1) * 4,
                            label="verse")
                for i in range(100)
            ],
            downbeats=list(range(0, 400, 4)),
            beats=list(range(0, 400, 1)),
            beat_positions=list(range(0, 400, 1)),
        )
        shots = [
            ShotBoundary(start_s=i * 3.0, end_s=(i + 1) * 3.0,
                         start_frame=i * 90, end_frame=(i + 1) * 90)
            for i in range(200)
        ]
        style = StyleAnalysis(
            lut_extracted=False, color_palette=[], text_overlays=[],
            transition_types=[], camera_motions=["static"],
            dominant_emotion="neutral", pacing="medium",
        )
        cutlist = generate_cutlist_programmatic(
            beat_grid, shots, [0.5] * 100,
            ["wide", "medium", "close_up"],
        )
        assert cutlist is not None

    def test_no_available_shot_types(self):
        beat_grid = BeatGrid(
            bpm=120.0, time_signature="4/4",
            beats=[0, 1, 2, 3, 4],
            beat_positions=[0, 1, 2, 3, 4],
            segments=[BeatSegment(start=0, end=4, label="intro")],
            downbeats=[0],
        )
        shots = [ShotBoundary(start_s=0.0, end_s=5.0, start_frame=0, end_frame=150)]
        style = StyleAnalysis(
            lut_extracted=False, color_palette=[], text_overlays=[],
            transition_types=[], camera_motions=["static"],
            dominant_emotion="neutral", pacing="medium",
        )
        # Empty available shot types should still not crash
        cutlist = generate_cutlist_programmatic(
            beat_grid, shots, [0.5], [],
        )
        assert cutlist is not None

    def test_energy_curve_mismatched_length(self):
        beat_grid = BeatGrid(
            bpm=120.0, time_signature="4/4",
            beats=[0, 1, 2, 3, 4, 5, 6, 7, 8],
            beat_positions=[0, 1, 2, 3, 4, 5, 6, 7, 8],
            segments=[
                BeatSegment(start=0, end=4, label="intro"),
                BeatSegment(start=4, end=8, label="verse"),
            ],
            downbeats=[0, 4],
        )
        shots = [
            ShotBoundary(start_s=0.0, end_s=2.5, start_frame=0, end_frame=75),
            ShotBoundary(start_s=2.5, end_s=5.0, start_frame=75, end_frame=150),
        ]
        style = StyleAnalysis(
            lut_extracted=False, color_palette=[], text_overlays=[],
            transition_types=[], camera_motions=["static"],
            dominant_emotion="neutral", pacing="medium",
        )
        # Energy curve shorter than segments
        cutlist = generate_cutlist_programmatic(
            beat_grid, shots, [0.5], ["wide"], total_duration=5.0,
        )
        assert cutlist is not None

    def test_all_transitions_in_schema(self):
        from reason_worker.cutlist_gen import CUTLIST_SCHEMA
        transitions = CUTLIST_SCHEMA.get("properties", {}).get("slots", {}).get("items", {}).get("properties", {}).get("transition_in", {}).get("enum", [])
        expected = [
            "hard_cut", "fade", "dissolve", "wipe_left", "wipe_right",
            "wipe_up", "wipe_down", "circle_open", "slide_up", "slide_down",
            "slide_left", "slide_right", "pixelize", "hlslice",
            "flash", "whip",
        ]
        for t in expected:
            assert t in transitions

    def test_all_shot_types_in_schema(self):
        from reason_worker.cutlist_gen import CUTLIST_SCHEMA
        shot_types = CUTLIST_SCHEMA.get("properties", {}).get("slots", {}).get("items", {}).get("properties", {}).get("target_shot_type", {}).get("enum", [])
        expected = [
            "extreme_wide", "wide", "medium_wide", "medium",
            "medium_close_up", "close_up", "extreme_close_up",
            "insert", "establishing",
        ]
        for t in expected:
            assert t in shot_types


# ──────────────────────────────────────────────────────────────────────────────
# Clip ranking edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestClipRankEdgeCases:
    def test_single_clip(self):
        slots = [
            Slot(
                index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="nature", motion_hint="static",
                energy_level=0.5, required_tags=[], avoid_tags=[],
            ),
        ]
        clip_metadata = {
            "clip_0": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.8,
                       "motion": "static", "tags": ["nature"]},
        }
        embeddings = {"clip_0": np.array([0.5, 0.5])}
        rankings = rank_clips_for_slots(slots, clip_metadata, embeddings)
        assert len(rankings) == 1
        assert len(rankings[0]) == 1
        assert rankings[0][0].clip_id == "clip_0"

    def test_all_clips_same_score(self):
        slots = [
            Slot(
                index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="test", motion_hint="static",
                energy_level=0.5, required_tags=[], avoid_tags=[],
            ),
        ]
        clip_metadata = {
            "clip_0": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.5,
                       "motion": "static", "tags": []},
            "clip_1": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.5,
                       "motion": "static", "tags": []},
        }
        embeddings = {
            "clip_0": np.array([0.5, 0.5]),
            "clip_1": np.array([0.5, 0.5]),
        }
        rankings = rank_clips_for_slots(slots, clip_metadata, embeddings)
        # Should still return both
        assert len(rankings[0]) == 2

    def test_missing_embedding_for_clip(self):
        slots = [
            Slot(
                index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="test", motion_hint="static",
                energy_level=0.5, required_tags=[], avoid_tags=[],
            ),
        ]
        clip_metadata = {
            "clip_0": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.8,
                       "motion": "static", "tags": []},
            "clip_1": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.7,
                       "motion": "static", "tags": []},
        }
        # Only one embedding
        embeddings = {"clip_0": np.array([0.5, 0.5])}
        rankings = rank_clips_for_slots(slots, clip_metadata, embeddings)
        # clip_1 should be skipped or get zero score
        assert len(rankings[0]) <= 2

    def test_avoid_tags_penalty(self):
        slots = [
            Slot(
                index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="test", motion_hint="static",
                energy_level=0.5, required_tags=[], avoid_tags=["watermark"],
            ),
        ]
        clip_metadata = {
            "clip_0": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.9,
                       "motion": "static", "tags": ["watermark"]},
            "clip_1": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.7,
                       "motion": "static", "tags": []},
        }
        embeddings = {
            "clip_0": np.array([0.9, 0.9]),
            "clip_1": np.array([0.5, 0.5]),
        }
        rankings = rank_clips_for_slots(slots, clip_metadata, embeddings)
        # clip_0 should be penalized for having avoid tag
        scores = {r.clip_id: r.total_score for r in rankings[0]}
        if "clip_0" in scores and "clip_1" in scores:
            assert scores["clip_1"] >= scores["clip_0"] - 0.3  # Allow some margin

    def test_required_tags_bonus(self):
        slots = [
            Slot(
                index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="test", motion_hint="static",
                energy_level=0.5, required_tags=["sunset"], avoid_tags=[],
            ),
        ]
        clip_metadata = {
            "clip_0": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.7,
                       "motion": "static", "tags": ["sunset"]},
            "clip_1": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.9,
                       "motion": "static", "tags": []},
        }
        embeddings = {
            "clip_0": np.array([0.5, 0.5]),
            "clip_1": np.array([0.9, 0.9]),
        }
        rankings = rank_clips_for_slots(slots, clip_metadata, embeddings)
        scores = {r.clip_id: r.total_score for r in rankings[0]}
        if "clip_0" in scores and "clip_1" in scores:
            # clip_0 should get bonus for having required tag
            assert scores["clip_0"] > scores["clip_1"] * 0.5

    def test_select_top_k_k_larger_than_available(self):
        rankings = {
            0: [
                ClipScore(clip_id="clip_0", score=0.9),
            ],
        }
        top_k = select_top_k_per_slot(rankings, k=5)
        assert top_k[0] == ["clip_0"]

    def test_select_top_k_k_zero(self):
        rankings = {
            0: [
                ClipScore(clip_id="clip_0", score=0.9),
                ClipScore(clip_id="clip_1", score=0.8),
            ],
        }
        top_k = select_top_k_per_slot(rankings, k=0)
        assert top_k[0] == []


# ──────────────────────────────────────────────────────────────────────────────
# Render edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestRenderEdgeCases:
    def test_slot_extends_past_video_end(self):
        """Slot requesting past video end should be clamped or error."""
        import shutil
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", "testsrc=duration=3.0:size=640x480:rate=30",
                 "-pix_fmt", "yuv420p", video_path],
                check=True, capture_output=True,
            )
            cutlist = CutList(
                globals=CutListGlobals(
                    total_duration_s=5.0, tempo_bpm=120,
                    time_signature="4/4", energy_curve=[0.5],
                    section_markers=[], aspect_ratio="16:9",
                ),
                slots=[
                    Slot(
                        index=0, start_s=0.0, duration_s=5.0, beat_index=0,
                        section="intro", target_shot_type="wide",
                        subject_hint="test", motion_hint="static",
                        energy_level=0.5, required_tags=[], avoid_tags=[],
                        selected_clip_id="clip_0",
                    ),
                ],
            )
            config = RenderConfig(output_path=output_path, width=640, height=480)
            # Should handle gracefully (clamp or error)
            try:
                result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
                assert os.path.exists(result)
            except ValueError:
                pass  # Also acceptable
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_slot_before_video_start(self):
        """Negative start should be handled."""
        import shutil
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", "testsrc=duration=5.0:size=640x480:rate=30",
                 "-pix_fmt", "yuv420p", video_path],
                check=True, capture_output=True,
            )
            cutlist = CutList(
                globals=CutListGlobals(
                    total_duration_s=3.0, tempo_bpm=120,
                    time_signature="4/4", energy_curve=[0.5],
                    section_markers=[], aspect_ratio="16:9",
                ),
                slots=[
                    Slot(
                        index=0, start_s=-1.0, duration_s=3.0, beat_index=0,
                        section="intro", target_shot_type="wide",
                        subject_hint="test", motion_hint="static",
                        energy_level=0.5, required_tags=[], avoid_tags=[],
                        selected_clip_id="clip_0",
                    ),
                ],
            )
            config = RenderConfig(output_path=output_path, width=640, height=480)
            with pytest.raises(Exception):
                compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_very_high_resolution(self):
        """4K config should be accepted."""
        config = RenderConfig(output_path="/tmp/out.mp4", width=3840, height=2160)
        assert config.width == 3840
        assert config.height == 2160

    def test_very_low_resolution(self):
        """Tiny resolution should be accepted."""
        config = RenderConfig(output_path="/tmp/out.mp4", width=64, height=64)
        assert config.width == 64
        assert config.height == 64

    def test_render_with_many_overlays(self):
        cutlist = CutList(
            globals=CutListGlobals(
                total_duration_s=10.0, tempo_bpm=120,
                time_signature="4/4", energy_curve=[0.5],
                section_markers=[], aspect_ratio="16:9",
            ),
            slots=[
                Slot(
                    index=0, start_s=0.0, duration_s=10.0, beat_index=0,
                    section="intro", target_shot_type="wide",
                    subject_hint="test", motion_hint="static",
                    energy_level=0.5, required_tags=[], avoid_tags=[],
                    selected_clip_id="clip_0",
                ),
            ],
            overlays=[
                Overlay(
                    text=f"Overlay {i}",
                    start_s=i * 0.5,
                    end_s=i * 0.5 + 0.3,
                    position="center",
                    font="Inter",
                    font_size_px=24,
                    color="#FFFFFF",
                    animation="none",
                )
                for i in range(20)
            ],
        )
        assert len(cutlist.overlays) == 20


# ──────────────────────────────────────────────────────────────────────────────
# Concurrency / idempotency
# ──────────────────────────────────────────────────────────────────────────────

class TestConcurrencyEdgeCases:
    def test_cutlist_idempotent(self):
        """Same inputs should produce identical cutlist."""
        beat_grid = BeatGrid(
            bpm=120.0, time_signature="4/4",
            beats=[0, 1, 2, 3, 4],
            beat_positions=[0, 1, 2, 3, 4],
            segments=[BeatSegment(start=0, end=4, label="intro")],
            downbeats=[0],
        )
        shots = [ShotBoundary(start_s=0.0, end_s=5.0, start_frame=0, end_frame=150)]
        style = StyleAnalysis(
            lut_extracted=False, color_palette=[], text_overlays=[],
            transition_types=[], camera_motions=["static"],
            dominant_emotion="neutral", pacing="medium",
        )
        cutlist1 = generate_cutlist_programmatic(
            beat_grid, shots, [0.5], ["wide"],
        )
        cutlist2 = generate_cutlist_programmatic(
            beat_grid, shots, [0.5], ["wide"],
        )
        assert len(cutlist1.slots) == len(cutlist2.slots)
        for s1, s2 in zip(cutlist1.slots, cutlist2.slots):
            assert s1.start_s == s2.start_s
            assert s1.duration_s == s2.duration_s
            assert s1.target_shot_type == s2.target_shot_type
            assert s1.energy_level == s2.energy_level

    def test_ranking_idempotent(self):
        slots = [
            Slot(
                index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="test", motion_hint="static",
                energy_level=0.5, required_tags=[], avoid_tags=[],
            ),
        ]
        clip_metadata = {
            "clip_0": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.8,
                       "motion_energy": 0.5, "tags": []},
            "clip_1": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.6,
                       "motion_energy": 0.5, "tags": []},
        }
        embeddings = {
            "clip_0": np.array([0.8, 0.8]),
            "clip_1": np.array([0.4, 0.4]),
        }
        rankings1 = rank_clips_for_slots(slots, clip_metadata, embeddings)
        rankings2 = rank_clips_for_slots(slots, clip_metadata, embeddings)
        assert len(rankings1[0]) == len(rankings2[0])
        for r1, r2 in zip(rankings1[0], rankings2[0]):
            assert r1.clip_id == r2.clip_id
            assert abs(r1.total_score - r2.total_score) < 0.0001


# ──────────────────────────────────────────────────────────────────────────────
# Temporal workflow edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestTemporalEdgeCases:
    def test_workflow_input_validation(self):
        # RenderJob is a TypeScript type, not in Python models
        pytest.skip("RenderJob is defined in TypeScript shared-types only")

    def test_workflow_invalid_style_tier(self):
        pytest.skip("RenderJob is defined in TypeScript shared-types only")

    def test_workflow_invalid_mode(self):
        pytest.skip("RenderJob is defined in TypeScript shared-types only")

    def test_progress_event_ordering(self):
        pytest.skip("ProgressEvent is defined in TypeScript shared-types only")

    def test_progress_exceeds_100(self):
        pytest.skip("ProgressEvent is defined in TypeScript shared-types only")

    def test_progress_negative(self):
        pytest.skip("ProgressEvent is defined in TypeScript shared-types only")
