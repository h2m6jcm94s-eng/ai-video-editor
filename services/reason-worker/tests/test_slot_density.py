# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for density-driven slot generation."""

import pytest

from shared_py.models import AdaptiveFeatures, BeatGrid, BeatSegment, BehaviorVector, ShotBoundary
from reason_worker.cutlist_gen import generate_cutlist_programmatic, _behavior_from_style_analysis
from reason_worker.slot_generator import generate_slots_adaptive, weighted_sample_with_min_gap


def _make_beat_grid(duration_s: float = 226.0, bpm: float = 80.0) -> BeatGrid:
    """Build a beat grid with a beat every beat_interval seconds."""
    beat_interval = 60.0 / bpm
    beats = [round(i * beat_interval, 3) for i in range(int(duration_s / beat_interval) + 2)]
    # Every 4th beat is a downbeat.
    downbeats = [b for i, b in enumerate(beats) if i % 4 == 0]
    segments = [
        BeatSegment(start=0.0, end=duration_s * 0.25, label="intro"),
        BeatSegment(start=duration_s * 0.25, end=duration_s * 0.5, label="verse"),
        BeatSegment(start=duration_s * 0.5, end=duration_s * 0.75, label="chorus"),
        BeatSegment(start=duration_s * 0.75, end=duration_s, label="outro"),
    ]
    return BeatGrid(bpm=bpm, beats=beats, downbeats=downbeats, beat_positions=beats, segments=segments)


def _make_energy_curve(n: int = 100) -> list[float]:
    """Simple energy curve: low -> high -> low."""
    return [0.3 + 0.5 * (1 - abs(2 * i / n - 1)) for i in range(n)]


def test_weighted_sample_with_min_gap_respects_spacing():
    candidates = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    weights = [1.0] * len(candidates)
    selected = weighted_sample_with_min_gap(candidates, weights, n=10, min_gap=1.1)
    # Should pick every other candidate because min_gap > 0.5
    assert len(selected) >= 3
    for i in range(len(selected) - 1):
        assert selected[i + 1] - selected[i] >= 1.1 - 1e-6


def test_weighted_sample_with_min_gap_prefers_high_weight():
    candidates = [0.0, 1.0, 2.0]
    weights = [0.1, 1.0, 0.1]
    selected = weighted_sample_with_min_gap(candidates, weights, n=2, min_gap=0.5)
    assert 1.0 in selected


def test_generate_slots_adaptive_count_matches_density():
    duration = 226.0
    density = 0.16
    behavior = BehaviorVector(cut_density_per_sec=density, slot_duration_mean_s=2.5)
    beat_grid = _make_beat_grid(duration_s=duration)
    energy_curve = _make_energy_curve()

    slots = generate_slots_adaptive(beat_grid, duration, behavior, energy_curve, duration)
    # Density gives a lower-bound target; the max-gap enforcer adds cuts in
    # oversized gaps so no slot exceeds the compiler's comfortable span.
    expected_min = round(density * duration)
    assert len(slots) >= expected_min, f"Expected at least {expected_min} slots, got {len(slots)}"


def test_generate_slots_adaptive_respects_max_gap():
    duration = 226.0
    density = 0.16
    behavior = BehaviorVector(cut_density_per_sec=density, slot_duration_mean_s=2.5)
    beat_grid = _make_beat_grid(duration_s=duration)
    energy_curve = _make_energy_curve()

    slots = generate_slots_adaptive(beat_grid, duration, behavior, energy_curve, duration)
    max_gap = 8.0
    for i in range(len(slots) - 1):
        gap = slots[i + 1].start_s - slots[i].start_s
        assert gap <= max_gap + 0.1, f"Gap {gap:.2f}s between slots {slots[i].index} and {slots[i+1].index} exceeds {max_gap}s"


def test_generate_slots_adaptive_starts_on_beats():
    duration = 226.0
    behavior = BehaviorVector(cut_density_per_sec=0.16, slot_duration_mean_s=2.5)
    beat_grid = _make_beat_grid(duration_s=duration)
    energy_curve = _make_energy_curve()

    slots = generate_slots_adaptive(beat_grid, duration, behavior, energy_curve, duration)
    beat_set = set(round(b, 3) for b in beat_grid.beats)
    beat_set.add(0.0)
    for slot in slots:
        # Allow small floating-point tolerance.
        assert any(abs(slot.start_s - b) < 0.02 for b in beat_set), (
            f"Slot start {slot.start_s} not on a beat"
        )


def test_generate_cutlist_programmatic_adaptive_reduces_slots():
    duration = 226.0
    beat_grid = _make_beat_grid(duration_s=duration)
    energy_curve = _make_energy_curve()
    shot_boundaries = [ShotBoundary(start_frame=0, end_frame=100, start_s=0.0, end_s=duration)]

    legacy = generate_cutlist_programmatic(
        beat_grid,
        shot_boundaries,
        energy_curve,
        ["wide", "medium", "close_up"],
        total_duration=duration,
        features=AdaptiveFeatures(use_adaptive_slot_density=False),
    )
    adaptive = generate_cutlist_programmatic(
        beat_grid,
        shot_boundaries,
        energy_curve,
        ["wide", "medium", "close_up"],
        total_duration=duration,
        features=AdaptiveFeatures(use_adaptive_slot_density=True),
    )

    assert len(adaptive.slots) < len(legacy.slots)
    assert len(adaptive.slots) <= 40


def test_behavior_from_style_analysis_uses_reference_density():
    style_analysis = {
        "families": {
            "cut_rhythm": {
                "cut_density_per_min": 30.0,
            }
        }
    }
    behavior = _behavior_from_style_analysis(style_analysis)
    assert behavior.cut_density_per_sec == pytest.approx(0.5, abs=0.01)


def test_behavior_from_style_analysis_fallback():
    behavior = _behavior_from_style_analysis({})
    assert behavior.cut_density_per_sec == 0.16


def test_behavior_from_style_analysis_requested_density_override():
    style_analysis = {
        "families": {
            "cut_rhythm": {
                "cut_density_per_min": 30.0,
                "requested_cut_density_per_min": 60.0,
            }
        }
    }
    behavior = _behavior_from_style_analysis(style_analysis)
    assert behavior.cut_density_per_sec == pytest.approx(1.0, abs=0.01)


def test_behavior_from_style_analysis_requested_slot_count_override():
    style_analysis = {
        "requested_slot_count": 20,
        "families": {
            "cut_rhythm": {
                "cut_density_per_min": 30.0,
            }
        }
    }
    behavior = _behavior_from_style_analysis(style_analysis, total_duration=40.0)
    assert behavior.cut_density_per_sec == pytest.approx(0.5, abs=0.01)


def test_behavior_from_style_analysis_override_clamps_extremes():
    style_analysis = {
        "requested_slot_count": 100000,
    }
    behavior = _behavior_from_style_analysis(style_analysis, total_duration=10.0)
    assert behavior.cut_density_per_sec == pytest.approx(2.0, abs=0.01)
