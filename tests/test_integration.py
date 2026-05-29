"""
Integration tests for cross-module interactions.
Covers: end-to-end pipeline, data flow, and error propagation.
"""

import pytest
import os
import sys
import tempfile
import subprocess
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ingest-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "render-worker", "src"))

from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, StyleAnalysis, Slot, RenderConfig
from ingest_worker.probe import probe_video
from ingest_worker.beat_detect import detect_beats_librosa
from reason_worker.cutlist_gen import generate_cutlist_programmatic
from render_worker.compiler import compile_timeline


def create_test_video(path: str, duration: float = 5.0):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc=duration={duration}:size=640x480:rate=30",
         "-pix_fmt", "yuv420p", path],
        check=True, capture_output=True,
    )
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestIntegration:
    def test_probe_to_cutlist(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            create_test_video(path, duration=5.0)
            info = probe_video(path)
            assert info.duration_s > 4.0

            subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-vn", "-acodec", "pcm_s16le",
                 "-ar", "44100", "-ac", "2", path.replace(".mp4", ".wav")],
                check=True, capture_output=True,
            )
            audio_path = path.replace(".mp4", ".wav")
            beat_grid = detect_beats_librosa(audio_path)
            assert beat_grid is not None

            shots = [ShotBoundary(start_s=0.0, end_s=5.0, start_frame=0, end_frame=150)]
            energy = [0.5]
            cutlist = generate_cutlist_programmatic(beat_grid, shots, energy, ["wide"])
            assert len(cutlist.slots) > 0
        finally:
            for p in [path, path.replace(".mp4", ".wav")]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_cutlist_to_render(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name
        try:
            create_test_video(video_path, duration=5.0)
            beat_grid = BeatGrid(
                bpm=120.0, time_signature="4/4",
                beats=[0, 1, 2, 3, 4, 5],
                beat_positions=[0, 1, 2, 3, 4, 5],
                segments=[BeatSegment(start=0, end=4, label="intro")],
                downbeats=[0],
            )
            shots = [ShotBoundary(start_s=0.0, end_s=5.0, start_frame=0, end_frame=150)]
            cutlist = generate_cutlist_programmatic(beat_grid, shots, [0.5], ["wide"])
            for slot in cutlist.slots:
                slot.selected_clip_id = "main"
            config = RenderConfig(output_path=output_path, width=640, height=480)
            result = compile_timeline(cutlist, {"main": video_path}, output_path, config)
            assert os.path.exists(result)
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)
