"""Tests for cut-list generation."""

import pytest
from reason_worker.cutlist_gen import generate_cutlist_programmatic
from shared_py.models import BeatGrid, BeatSegment, ShotBoundary


def test_generate_cutlist_programmatic():
    """Test programmatic cut-list generation."""
    beats = BeatGrid(
        bpm=120,
        beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
        downbeats=[0.0, 2.0, 4.0],
        beat_positions=[1, 2, 3, 4, 1, 2, 3, 4, 1],
        segments=[
            BeatSegment(start=0, end=2, label="intro"),
            BeatSegment(start=2, end=4, label="verse"),
        ],
    )

    shots = [
        ShotBoundary(start_frame=0, end_frame=60, start_s=0, end_s=2.0, is_gradual=False),
        ShotBoundary(start_frame=60, end_frame=120, start_s=2.0, end_s=4.0, is_gradual=False),
    ]

    energy = [0.3, 0.5, 0.7, 0.9]
    available = ["wide", "medium", "close_up"]

    cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=4.0)

    assert cutlist.globals.tempo_bpm == 120
    assert len(cutlist.slots) > 0
    assert all(s.start_s >= 0 for s in cutlist.slots)
    assert all(s.duration_s > 0 for s in cutlist.slots)
