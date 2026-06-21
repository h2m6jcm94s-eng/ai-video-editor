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

from unittest.mock import patch

import ingest_worker.beat_detect as beat_detect_module
from ingest_worker.beat_detect import decode_to_wav, detect_beats, detect_beats_librosa, compute_energy_curve
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


class TestDecodeToWav:
    def test_cleans_up_temp_file_on_ffmpeg_failure(self, tmp_path):
        fake_path = str(tmp_path / "failed.wav")
        proc_err = subprocess.CalledProcessError(1, ["ffmpeg"])
        proc_err.stderr = b"ffmpeg error"
        with patch.object(beat_detect_module.subprocess, "run", side_effect=proc_err), \
             patch.object(beat_detect_module.tempfile, "mkstemp", return_value=(0, fake_path)):
            with pytest.raises(RuntimeError, match="FFmpeg decode_to_wav failed"):
                beat_detect_module.decode_to_wav("input.mp3")
        assert not os.path.exists(fake_path)

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
    def test_success_returns_existing_wav(self, tmp_path):
        input_path = str(tmp_path / "input.wav")
        create_sine_wave(input_path, duration=1.0)
        wav_path = beat_detect_module.decode_to_wav(input_path)
        try:
            assert os.path.exists(wav_path)
            assert wav_path.endswith(".wav")
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)


class TestDetectBeats:
    def test_librosa_fallback_runs_on_decoded_wav(self, monkeypatch, tmp_path):
        wav_path = str(tmp_path / "decoded.wav")
        open(wav_path, "w").close()

        calls = []
        monkeypatch.setattr(
            beat_detect_module, "decode_to_wav", lambda p: calls.append(("decode", p)) or wav_path
        )
        monkeypatch.setattr(
            beat_detect_module, "detect_beats_allin1", lambda p: calls.append(("allin1", p)) or None
        )

        def fake_librosa(p):
            calls.append(("librosa", p))
            return BeatGrid(
                bpm=100.0,
                beats=[0.0, 0.5],
                downbeats=[0.0],
                beat_positions=[1],
                segments=[],
            )

        monkeypatch.setattr(beat_detect_module, "detect_beats_librosa", fake_librosa)
        result = beat_detect_module.detect_beats("song.mp3")
        assert result.bpm == 100.0
        assert ("librosa", wav_path) in calls
        assert not os.path.exists(wav_path)


class TestComputeEnergyCurveNoLibrosa:
    def test_returns_default_curve_when_librosa_missing(self, monkeypatch):
        monkeypatch.setattr(beat_detect_module, "_HAS_LIBROSA", False)
        curve = beat_detect_module.compute_energy_curve("any.wav", n_points=7)
        assert curve == [0.0] * 7
