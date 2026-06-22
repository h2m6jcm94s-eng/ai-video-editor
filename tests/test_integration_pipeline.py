"""
End-to-end integration tests for the full video render pipeline.
Uses real FFmpeg where possible, mocks for heavy ML dependencies.
"""

import pytest
import os
import sys
import tempfile
import subprocess
import shutil
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ingest-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "render-worker", "src"))

from shared_py.models import (
    BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis,
    CutList, CutListGlobals, Slot, RenderConfig, ClipScore,
)
from ingest_worker.probe import probe_video
from ingest_worker.beat_detect import detect_beats_librosa, compute_energy_curve
from ingest_worker.shot_detect import detect_shot_boundaries_pyscenedetect
from reason_worker.cutlist_gen import generate_cutlist_programmatic
from reason_worker.clip_rank import rank_clips_for_slots, select_top_k_per_slot, compute_confidence
from render_worker.compiler import compile_timeline


def create_test_video(path: str, duration: float = 10.0, fps: int = 30,
                      resolution: tuple = (640, 480), with_audio: bool = True):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    width, height = resolution
    args = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
    ]
    if with_audio:
        args.extend(["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"])
    args.extend(["-pix_fmt", "yuv420p", path])
    subprocess.run(args, check=True, capture_output=True)
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestFullPipeline:
    def test_probe_video(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=5.0)
            info = probe_video(path)
            assert info["duration_sec"] > 4.0
            assert info.width == 640
            assert info.height == 480
            assert info.fps > 0
        finally:
            os.unlink(path)

    def test_detect_beats(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            audio_path = f.name
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
                 "-ar", "44100", audio_path],
                check=True, capture_output=True,
            )
            beat_grid = detect_beats_librosa(audio_path)
            assert beat_grid is not None
            assert beat_grid.bpm > 0
            assert len(beat_grid.segments) > 0
        finally:
            os.unlink(audio_path)

    def test_energy_curve(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            audio_path = f.name
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=5",
                 "-ar", "44100", audio_path],
                check=True, capture_output=True,
            )
            curve = compute_energy_curve(audio_path, n_points=10)
            assert len(curve) == 10
            assert all(isinstance(v, float) for v in curve)
            assert all(0 <= v <= 1 for v in curve)
        finally:
            os.unlink(audio_path)

    def test_generate_cutlist(self):
        beat_grid = BeatGrid(
            bpm=120.0, time_signature="4/4",
            beats=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            beat_positions=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            segments=[
                BeatSegment(start=0, end=4, label="intro"),
                BeatSegment(start=4, end=12, label="verse"),
                BeatSegment(start=12, end=16, label="chorus"),
            ],
            downbeats=[0, 4, 8, 12],
        )
        shots = [
            ShotBoundary(start_s=0.0, end_s=2.5, start_frame=0, end_frame=75),
            ShotBoundary(start_s=2.5, end_s=5.0, start_frame=75, end_frame=150),
            ShotBoundary(start_s=5.0, end_s=7.5, start_frame=150, end_frame=225),
            ShotBoundary(start_s=7.5, end_s=10.0, start_frame=225, end_frame=300),
        ]
        energy_curve = [0.3, 0.5, 0.7, 0.9]
        available_types = ["wide", "medium", "close_up", "extreme_close_up", "insert"]

        cutlist = generate_cutlist_programmatic(
            beat_grid, shots, energy_curve, available_types, total_duration=10.0,
        )
        assert cutlist is not None
        assert isinstance(cutlist, CutList)
        assert len(cutlist.slots) > 0
        assert cutlist.globals.total_duration_s <= 10.0

    def test_rank_clips(self):
        slots = [
            Slot(index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                 section="intro", target_shot_type="wide",
                 subject_hint="nature", motion_hint="static",
                 energy_level=0.3, required_tags=[], avoid_tags=[]),
            Slot(index=1, start_s=2.0, duration_s=2.0, beat_index=2,
                 section="verse", target_shot_type="close_up",
                 subject_hint="person", motion_hint="handheld",
                 energy_level=0.7, required_tags=[], avoid_tags=[]),
        ]
        clip_metadata = {
            "clip_0": {"shot_type": "wide", "duration_s": 2.0, "aesthetic_score": 0.8,
                       "motion_energy": 0.5, "tags": ["nature", "landscape"]},
            "clip_1": {"shot_type": "close_up", "duration_s": 2.0, "aesthetic_score": 0.9,
                       "motion_energy": 0.7, "tags": ["person", "portrait"]},
        }
        embeddings = {"clip_0": np.array([0.9, 0.1]), "clip_1": np.array([0.1, 0.9])}
        rankings = rank_clips_for_slots(slots, clip_metadata, embeddings)
        assert len(rankings) == 2
        for slot_idx, scores in rankings.items():
            assert isinstance(scores, list)
            assert len(scores) > 0
            for score in scores:
                assert isinstance(score, ClipScore)
                assert score.clip_id in clip_metadata

    def test_select_top_k(self):
        rankings = {
            0: [ClipScore(clip_id="clip_0", total_score=0.9), ClipScore(clip_id="clip_1", total_score=0.8)],
            1: [ClipScore(clip_id="clip_3", total_score=0.95), ClipScore(clip_id="clip_4", total_score=0.5)],
        }
        top_k = select_top_k_per_slot(rankings, k=2)
        assert top_k[0] == ["clip_0", "clip_1"]
        assert top_k[1] == ["clip_3", "clip_4"]

    def test_compute_confidence(self):
        rankings = {
            0: [
                ClipScore(clip_id="clip_0", total_score=0.9),
                ClipScore(clip_id="clip_1", total_score=0.85),
                ClipScore(clip_id="clip_2", total_score=0.5),
                ClipScore(clip_id="clip_3", total_score=0.3),
            ],
        }
        confidence = compute_confidence(rankings)
        assert confidence[0] < 1.0
        assert confidence[0] > 0.0



@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestRenderability:
    """Phase 5: end-to-end check that a generated cutlist can actually compile."""

    def test_generated_cutlist_compiles_without_empty_slots(self):
        beat_grid = BeatGrid(
            bpm=120.0,
            time_signature="4/4",
            beats=[0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
            beat_positions=[1, 2, 3, 4] * 3,
            segments=[BeatSegment(start=0, end=5, label="intro")],
            downbeats=[0.0, 2.0, 4.0],
        )
        shots = [
            ShotBoundary(start_s=0.0, end_s=2.5, start_frame=0, end_frame=75),
            ShotBoundary(start_s=2.5, end_s=5.0, start_frame=75, end_frame=150),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            clip_path = os.path.join(tmpdir, "clip.mp4")
            song_path = os.path.join(tmpdir, "song.wav")
            output_path = os.path.join(tmpdir, "output.mp4")
            create_test_video(clip_path, duration=5.0, resolution=(720, 1280), with_audio=False)
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                 "-ar", "44100", song_path],
                check=True, capture_output=True,
            )

            cutlist = generate_cutlist_programmatic(
                beat_grid, shots, [0.5] * 5, ["wide", "medium", "close_up"], total_duration=5.0
            )
            assert cutlist.slots, "cutlist produced no slots"

            # Phase 1 guarantee: even a single clip must fill every slot.
            clip_metadata = {
                "clip_0": {"shot_type": "wide", "duration_sec": 5.0, "aesthetic_score": 0.6, "motion_energy": 0.5},
            }
            rankings = rank_clips_for_slots(cutlist.slots, clip_metadata, fallback_policy="round_robin")
            for slot in cutlist.slots:
                scores = rankings.get(slot.index, [])
                assert scores, f"slot {slot.index} received no ranking"
                slot.selected_clip_id = scores[0].clip_id

            config = RenderConfig(
                output_path=output_path,
                width=720,
                height=1280,
                fps=30.0,
                song_path=song_path,
            )
            compile_timeline(cutlist, {"clip_0": clip_path}, output_path, config, style_tier="full_remix")

            assert os.path.exists(output_path), "render output was not created"
            assert os.path.getsize(output_path) > 0, "render output is empty"
