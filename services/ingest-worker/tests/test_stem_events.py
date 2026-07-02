# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Unit tests for per-stem music event detection."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ingest_worker import stem_events
from ingest_worker.song_lyrics import LyricWord

SR = 22_050
DURATION = 2.0


def _silence(duration_s: float = DURATION) -> np.ndarray:
    return np.zeros(int(SR * duration_s), dtype=np.float32)


def _tone(freq: float, onset_s: float, length_s: float = 0.05, amp: float = 0.5) -> np.ndarray:
    y = _silence()
    start = int(onset_s * SR)
    n = int(length_s * SR)
    t = np.arange(n) / SR
    sig = amp * np.sin(2 * np.pi * freq * t)
    # exponential decay
    sig *= np.exp(-t * 20)
    y[start : start + n] = sig.astype(np.float32)
    return y


def _noise_band(
    low: float, high: float, onset_s: float, length_s: float = 0.05, amp: float = 0.5
) -> np.ndarray:
    y = _silence()
    start = int(onset_s * SR)
    n = int(length_s * SR)
    # white noise filtered with FFT brick-wall
    raw = np.random.RandomState(42).randn(n).astype(np.float32)
    fft = np.fft.rfft(raw)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    mask = (freqs >= low) & (freqs <= high)
    fft[~mask] = 0
    sig = amp * np.fft.irfft(fft, n=n)
    y[start : start + n] = sig
    return y


def _sweep(onset_s: float, length_s: float = 0.3, amp: float = 0.5) -> np.ndarray:
    y = _silence()
    start = int(onset_s * SR)
    n = int(length_s * SR)
    t = np.arange(n) / SR
    # linear sweep from 400Hz to 8kHz
    f0, f1 = 400.0, 8000.0
    phase = 2 * np.pi * (f0 * t + 0.5 * (f1 - f0) / length_s * t**2)
    sig = amp * np.sin(phase) * np.hanning(n)
    y[start : start + n] = sig.astype(np.float32)
    return y


def _write_stem(tmp_path: Path, name: str, y: np.ndarray) -> Path:
    path = tmp_path / name
    sf.write(path, y, SR, subtype="PCM_16")
    return path


def _make_stem_dir(tmp_path: Path) -> Path:
    stems_dir = tmp_path / "stems"
    stems_dir.mkdir()
    return stems_dir


def test_classify_drum_onset():
    # Kick: 60Hz
    kick = _tone(60.0, 0.5)
    assert stem_events.classify_drum_onset(kick, SR, 0.5) == "kick"

    # Snare: 250Hz sine within expected band.
    snare = _tone(250.0, 0.5)
    assert stem_events.classify_drum_onset(snare, SR, 0.5) == "snare"

    # Hihat: 8kHz
    hihat = _tone(8000.0, 0.5)
    assert stem_events.classify_drum_onset(hihat, SR, 0.5) == "hihat"


def test_detect_drum_events(tmp_path: Path):
    stems_dir = _make_stem_dir(tmp_path)
    y = (
        _tone(60.0, 0.5)
        + _tone(250.0, 1.0)
        + _tone(8000.0, 1.5)
    )
    _write_stem(stems_dir, "drums.wav", y)

    kicks, snares, hihats = stem_events._detect_drum_events(stems_dir / "drums.wav")
    assert len(kicks) == 1
    assert len(snares) == 1
    assert len(hihats) == 1
    assert abs(kicks[0] - 0.5) < 0.05
    assert abs(snares[0] - 1.0) < 0.05
    assert abs(hihats[0] - 1.5) < 0.05


def test_detect_bass_drops(tmp_path: Path):
    stems_dir = _make_stem_dir(tmp_path)
    y = _tone(80.0, 0.7, length_s=0.2, amp=0.8)
    _write_stem(stems_dir, "bass.wav", y)

    drops = stem_events._detect_bass_drops(stems_dir / "bass.wav")
    assert len(drops) == 1
    assert abs(drops[0] - 0.7) < 0.05


def test_detect_vocal_onsets(tmp_path: Path):
    stems_dir = _make_stem_dir(tmp_path)
    # Vocal tones at 0.3s and 0.9s, with a 500ms+ gap for phrase boundary.
    y = _tone(1000.0, 0.3, length_s=0.15, amp=0.3) + _tone(
        1000.0, 1.0, length_s=0.15, amp=0.3
    )
    _write_stem(stems_dir, "vocals.wav", y)

    words = [
        LyricWord(text="one", start_s=0.30, end_s=0.45, probability=0.9),
        LyricWord(text="two", start_s=1.00, end_s=1.15, probability=0.9),
    ]
    onsets, phrases = stem_events._detect_vocal_onsets(stems_dir / "vocals.wav", words)
    assert any(abs(t - 0.3) < 0.05 for t in onsets)
    assert any(abs(t - 1.0) < 0.05 for t in onsets)
    assert len(phrases) >= 1
    assert any(abs(t - 1.0) < 0.05 for t in phrases)


def test_detect_sweeps(tmp_path: Path):
    stems_dir = _make_stem_dir(tmp_path)
    y = _sweep(0.6)
    _write_stem(stems_dir, "other.wav", y)

    sweeps = stem_events._detect_sweeps(stems_dir / "other.wav")
    assert len(sweeps) >= 1
    assert abs(sweeps[0] - 0.6) < 0.15


def test_detect_music_events_caches(tmp_path: Path):
    stems_dir = _make_stem_dir(tmp_path)
    y = _tone(60.0, 0.5)
    _write_stem(stems_dir, "drums.wav", y)
    _write_stem(stems_dir, "bass.wav", _silence())
    _write_stem(stems_dir, "vocals.wav", _silence())
    _write_stem(stems_dir, "other.wav", _silence())

    cache_dir = tmp_path / "cache"
    words: list[LyricWord] = []

    grid1 = stem_events.detect_music_events(stems_dir, words, cache_dir=cache_dir)
    grid2 = stem_events.detect_music_events(stems_dir, words, cache_dir=cache_dir)

    assert grid1 == grid2
    assert (cache_dir / grid1.song_hash / "music_events.json").exists()


def test_events_in_window_priority():
    grid = stem_events.MusicEventGrid(
        song_hash="fake",
        snare_times=[1.0],
        kick_times=[1.02],
        bass_drop_times=[1.01],
        vocal_onset_times=[0.95],
    )
    events = grid.events_in_window(1.0, window_s=0.1)
    assert events[0].stem == "snare"
