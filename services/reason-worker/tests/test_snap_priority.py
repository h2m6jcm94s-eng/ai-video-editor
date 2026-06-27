# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import pytest

from reason_worker.cutlist_gen import _snap_slots_to_shots_and_beats
from shared_py.models import BeatGrid, ShotBoundary, Slot


def _make_beat_grid(beats, downbeats=None):
    return BeatGrid(
        bpm=120.0,
        beats=beats,
        downbeats=downbeats or [],
        beat_positions=[1] * len(beats),
        segments=[{"start": 0.0, "end": 30.0, "label": "verse"}],
    )


def _make_slot(start_s: float) -> Slot:
    return Slot(
        index=0,
        start_s=start_s,
        duration_s=1.0,
        beat_index=0,
        section="verse",
        transition_in="hard_cut",
        transition_out="hard_cut",
        target_shot_type="wide",
        subject_hint="person",
        motion_hint="static",
        energy_level=0.5,
    )


def test_downbeat_locks_despite_nearby_shot():
    """A downbeat within the lock radius wins over a shot boundary."""
    slot = _make_slot(start_s=5.0)
    beat_grid = _make_beat_grid(beats=[4.5, 5.0, 5.5], downbeats=[5.0])
    shots = [ShotBoundary(start_frame=0, end_frame=30, start_s=5.23, end_s=6.0)]

    _snap_slots_to_shots_and_beats(
        [slot],
        shots,
        beat_grid,
        content_end=10.0,
        downbeat_lock_radius=0.10,
        beat_prefer_radius=0.05,
    )

    assert slot.start_s == 5.0


def test_weak_beat_yields_to_very_close_shot():
    """A non-downbeat beat yields to a shot boundary within the small prefer radius."""
    slot = _make_slot(start_s=5.0)
    beat_grid = _make_beat_grid(beats=[4.5, 5.0, 5.5], downbeats=[4.0])
    shots = [ShotBoundary(start_frame=0, end_frame=30, start_s=5.04, end_s=6.0)]

    _snap_slots_to_shots_and_beats(
        [slot],
        shots,
        beat_grid,
        content_end=10.0,
        downbeat_lock_radius=0.10,
        beat_prefer_radius=0.05,
    )

    assert slot.start_s == 5.04


def test_no_beat_nearby_falls_back_to_shot_boundary():
    """When no beat is nearby, the slot snaps to the reference shot boundary."""
    slot = _make_slot(start_s=5.15)
    beat_grid = _make_beat_grid(beats=[4.0, 6.0], downbeats=[4.0])
    shots = [ShotBoundary(start_frame=0, end_frame=30, start_s=5.23, end_s=6.0)]

    _snap_slots_to_shots_and_beats(
        [slot],
        shots,
        beat_grid,
        content_end=10.0,
        downbeat_lock_radius=0.10,
        beat_prefer_radius=0.05,
    )

    assert slot.start_s == 5.23


def test_beat_index_updated_after_snap():
    """After snapping to a beat, the slot's beat_index reflects the new position."""
    slot = _make_slot(start_s=5.0)
    slot.beat_index = 0
    beat_grid = _make_beat_grid(beats=[4.5, 5.0, 5.5], downbeats=[5.0])
    shots = [ShotBoundary(start_frame=0, end_frame=30, start_s=5.23, end_s=6.0)]

    _snap_slots_to_shots_and_beats(
        [slot],
        shots,
        beat_grid,
        content_end=10.0,
        downbeat_lock_radius=0.10,
        beat_prefer_radius=0.05,
    )

    assert slot.start_s == 5.0
    assert slot.beat_index == 1
