"""
Unit, integration, and edge tests for beat detection.
Covers: librosa fallback, energy curve, and edge cases.
"""

import pytest
import os
import sys
import tempfile
import subprocess
import shutil
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ingest-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from ingest_worker.beat_detect import detect_beats_librosa, compute_energy_curve
from shared_py.models import BeatGrid


def create_sine_wave(path: str, duration: float = 5.0):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-ar", "44100", path],
        check=True, capture_output=True,
    )
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestDetectBeatsLibrosa:
    def test_detects_beats(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_sine_wave(path, duration=5.0)
            beat_grid = detect_beats_librosa(path)
            assert beat_grid is not None
            assert isinstance(beat_grid, BeatGrid)
            assert beat_grid.bpm > 0
        finally:
            os.unlink(path)

    def test_returns_segments(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_sine_wave(path, duration=5.0)
            beat_grid = detect_beats_librosa(path)
            assert len(beat_grid.segments) > 0
        finally:
            os.unlink(path)

    def test_downbeats_present(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_sine_wave(path, duration=8.0)
            beat_grid = detect_beats_librosa(path)
            assert len(beat_grid.downbeats) > 0
        finally:
            os.unlink(path)

    def test_beat_positions_length(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_sine_wave(path, duration=4.0)
            beat_grid = detect_beats_librosa(path)
            assert len(beat_grid.beat_positions) >= len(beat_grid.beats)
        finally:
            os.unlink(path)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestComputeEnergyCurve:
    def test_basic_energy_curve(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_sine_wave(path, duration=5.0)
            energy = compute_energy_curve(path, n_points=10)
            assert len(energy) == 10
            assert all(0 <= e <= 1 for e in energy)
        finally:
            os.unlink(path)

    def test_single_point(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_sine_wave(path, duration=3.0)
            energy = compute_energy_curve(path, n_points=1)
            assert len(energy) == 1
            assert 0 <= energy[0] <= 1
        finally:
            os.unlink(path)

    def test_many_points(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_sine_wave(path, duration=5.0)
            energy = compute_energy_curve(path, n_points=50)
            assert len(energy) == 50
        finally:
            os.unlink(path)

    def test_empty_audio(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=duration=0.1",
                 "-ar", "44100", path],
                check=True, capture_output=True,
            )
            energy = compute_energy_curve(path, n_points=5)
            assert len(energy) == 5
        finally:
            os.unlink(path)


class TestBeatDetectEdgeCases:
    def test_nonexistent_file(self):
        with pytest.raises(Exception):
            detect_beats_librosa("/nonexistent/audio.wav")

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"")
            path = f.name
        try:
            with pytest.raises(Exception):
                detect_beats_librosa(path)
        finally:
            os.unlink(path)
