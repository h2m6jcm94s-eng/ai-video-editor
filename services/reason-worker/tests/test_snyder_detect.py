# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for Save-the-Cat beat detection."""

import numpy as np
import pytest

from reason_worker.snyder_detect import (
    SNYDER_PERCENTAGE_ANCHORS,
    DetectedBeat,
    assign_slot_beat,
    detect_snyder_beats,
)


ALL_BEAT_NAMES = list(SNYDER_PERCENTAGE_ANCHORS.keys())


def test_detect_snyder_beats_returns_all_fifteen_beats():
    beats = detect_snyder_beats(total_duration_s=100.0)
    assert len(beats) == 15
    assert [b.name for b in beats] == ALL_BEAT_NAMES


def test_detect_snyder_beats_uses_percentage_anchors_by_default():
    duration = 200.0
    beats = detect_snyder_beats(total_duration_s=duration)
    for beat in beats:
        expected = SNYDER_PERCENTAGE_ANCHORS[beat.name] * duration
        assert beat.t == pytest.approx(expected, abs=1e-6)


def test_detect_snyder_beats_zero_duration_returns_zero_anchors():
    beats = detect_snyder_beats(total_duration_s=0.0)
    assert len(beats) == 15
    assert all(b.t == 0.0 and b.confidence == 0.0 for b in beats)


def test_detect_snyder_beats_dialogue_drives_theme_and_debate():
    duration = 100.0
    dialogue = [
        {"start": 6.0, "end": 8.0, "text": "theme line"},
        {"start": 16.0, "end": 18.0, "text": "debate line"},
    ]
    beats = detect_snyder_beats(total_duration_s=duration, dialogue_segments=dialogue)

    theme = next(b for b in beats if b.name == "theme_stated")
    debate = next(b for b in beats if b.name == "debate")

    assert theme.t == pytest.approx(6.0, abs=0.5)
    assert theme.confidence > 0.9
    assert debate.t == pytest.approx(16.0, abs=0.5)
    assert debate.confidence > 0.9


def test_detect_snyder_beats_motion_curve_drives_peaks():
    duration = 100.0
    # High motion at 35s (fun and games), 65s (bad guys close in), and 90s (finale).
    motion = np.zeros(1000)
    for center, scale in [(350, 2.0), (650, 1.5), (900, 2.5)]:
        motion[max(0, center - 20) : min(len(motion), center + 20)] = scale

    beats = detect_snyder_beats(total_duration_s=duration, motion_curve=motion)

    fun = next(b for b in beats if b.name == "fun_and_games")
    bgci = next(b for b in beats if b.name == "bad_guys_close_in")
    finale = next(b for b in beats if b.name == "finale")

    assert 30.0 <= fun.t <= 49.0
    assert 51.0 <= bgci.t <= 74.0
    assert 81.0 <= finale.t <= 99.0
    assert fun.confidence > 0.9
    assert bgci.confidence > 0.9
    assert finale.confidence > 0.9


def test_detect_snyder_beats_chord_seq_fallback_for_break_into_three():
    duration = 100.0
    # No chord sequence supplied: break_into_three should fall back to 80%.
    beats = detect_snyder_beats(total_duration_s=duration, chord_seq=None)
    break3 = next(b for b in beats if b.name == "break_into_three")
    assert break3.t == pytest.approx(80.0, abs=1e-6)
    assert break3.confidence < 0.7


def test_detect_snyder_beats_chord_seq_drives_break_into_three():
    duration = 100.0
    chord_seq = [
        {"start": 0.0, "end": 20.0, "label": "C"},
        {"start": 20.0, "end": 50.0, "label": "G"},
        {"start": 50.0, "end": 78.0, "label": "Am"},
        {"start": 78.0, "end": 100.0, "label": "F"},
    ]
    beats = detect_snyder_beats(total_duration_s=duration, chord_seq=chord_seq)
    break3 = next(b for b in beats if b.name == "break_into_three")
    assert break3.t == pytest.approx(78.0, abs=1e-6)
    assert break3.confidence > 0.9


def test_detect_snyder_beats_audio_drives_opening_and_final_image():
    sr = 1000
    duration = 20.0
    samples = int(sr * duration)
    audio = np.zeros(samples)
    # Audio present between 0.5s and 19.0s.
    audio[int(0.5 * sr) : int(19.0 * sr)] = 0.5

    beats = detect_snyder_beats(song_audio=audio, sr=sr, total_duration_s=duration)

    opening = next(b for b in beats if b.name == "opening_image")
    final_image = next(b for b in beats if b.name == "final_image")

    assert opening.t == pytest.approx(0.5, abs=0.2)
    # Final image should land near the actual audio end or the canonical 99.5% anchor.
    assert final_image.t >= 18.0
    assert opening.confidence > 0.9


def test_assign_slot_beat_nearest_anchor():
    duration = 100.0
    beats = detect_snyder_beats(total_duration_s=duration)
    # A slot at 8s should be closest to Set-Up (4.5s) or Catalyst (10s).
    beat_name, section = assign_slot_beat(8.0, duration, beats)
    assert beat_name in {"setup", "catalyst"}
    assert section in {"intro", "verse"}


def test_assign_slot_beat_empty_beats():
    beat_name, section = assign_slot_beat(5.0, 100.0, [])
    assert beat_name == "Finale"
    assert section == "outro"


def test_detected_beat_equality():
    a = DetectedBeat(name="midpoint", t=50.0, confidence=1.0)
    b = DetectedBeat(name="midpoint", t=50.0, confidence=1.0)
    assert a == b
