# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reason_worker.arc_anchor import (
    find_lowest_valley_in_range,
    find_climax_peak,
    nearest_downbeat,
    map_arc_to_song,
    anchor_for_time,
)
from reason_worker.narrative_arcs import TRAILER_ARC
from shared_py.models import BeatGrid, BeatSegment


def test_find_lowest_valley():
    duration = 10.0
    curve = [0.5] * 32
    # Put a valley at the 50% mark (index 16)
    curve[16] = 0.1
    t = find_lowest_valley_in_range(curve, duration, 0.4, 0.7)
    assert t == pytest.approx(5.0, abs=0.5)


def test_find_climax_peak():
    duration = 10.0
    curve = [0.5] * 32
    # Put a peak at the 70% mark (index 22)
    curve[22] = 1.0
    t = find_climax_peak(curve, duration, 0.6, 0.9)
    assert t == pytest.approx(7.0, abs=0.5)


def test_nearest_downbeat():
    assert nearest_downbeat(3.2, [0.0, 1.0, 2.0, 4.0, 5.0]) == pytest.approx(4.0)
    assert nearest_downbeat(2.4, [0.0, 1.0, 2.0, 4.0, 5.0]) == pytest.approx(2.0)


def test_map_arc_to_song_returns_five_anchors():
    duration = 20.0
    curve = [0.5] * 64
    # Make CRISIS valley around 60% and VICTORY peak around 80%
    for i in range(35, 40):
        curve[i] = 0.1
    for i in range(50, 55):
        curve[i] = 1.0

    beat_grid = BeatGrid(
        bpm=120.0,
        beats=list(range(0, 41)),
        downbeats=list(range(0, 41, 4)),
        beat_positions=([1, 2, 3, 4] * 11)[:41],
        segments=[BeatSegment(start=0, end=duration, label="verse")],
    )
    anchors = map_arc_to_song(TRAILER_ARC, curve, beat_grid, duration)
    assert len(anchors) == 5
    names = [a.name for a in anchors]
    assert names == ["HOOK", "WORLD", "CONFLICT", "CRISIS", "VICTORY"]


def test_anchor_for_time_finds_containing_window():
    from reason_worker.arc_anchor import ArcBeatAnchor

    anchors = [
        ArcBeatAnchor(name="A", start_s=0.0, end_s=2.0, energy_target=0.3, emotion_target="calm", preferred_shots=["wide"], text_archetype="world"),
        ArcBeatAnchor(name="B", start_s=2.0, end_s=5.0, energy_target=0.7, emotion_target="tension", preferred_shots=["close_up"], text_archetype="clash"),
    ]
    assert anchor_for_time(anchors, 1.0).name == "A"
    assert anchor_for_time(anchors, 3.0).name == "B"


def test_anchor_windows_are_non_overlapping_and_sorted():
    duration = 20.0
    curve = [0.5] * 64
    beat_grid = BeatGrid(
        bpm=120.0,
        beats=list(range(0, 41)),
        downbeats=list(range(0, 41, 4)),
        beat_positions=([1, 2, 3, 4] * 11)[:41],
        segments=[BeatSegment(start=0, end=duration, label="verse")],
    )
    anchors = map_arc_to_song(TRAILER_ARC, curve, beat_grid, duration)
    for i in range(len(anchors) - 1):
        assert anchors[i].start_s < anchors[i + 1].start_s
        assert anchors[i].end_s <= anchors[i + 1].start_s + 1e-3
