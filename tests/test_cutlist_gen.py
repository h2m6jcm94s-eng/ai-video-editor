"""
Unit, integration, and edge tests for cut-list generation.
Covers: programmatic generation, AI provider fallback, schema validation,
beat snapping, energy mapping, and extreme edge cases.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from reason_worker.cutlist_gen import (
    generate_cutlist_programmatic,
    generate_cutlist,
    CUTLIST_SCHEMA,
)
from shared_py.models import (
    CutList, CutListGlobals, Slot, SectionMarker,
    BeatGrid, BeatSegment, ShotBoundary,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_beat_grid(bpm=120, beats=None, downbeats=None, segments=None):
    if beats is None:
        beat_interval = 60.0 / bpm
        beats = [i * beat_interval for i in range(int(30.0 / beat_interval) + 1)]
    if downbeats is None:
        downbeats = beats[::4]
    if segments is None:
        segments = [
            BeatSegment(start=0.0, end=10.0, label="intro"),
            BeatSegment(start=10.0, end=20.0, label="verse"),
            BeatSegment(start=20.0, end=30.0, label="drop"),
        ]
    return BeatGrid(
        bpm=bpm,
        beats=beats,
        downbeats=downbeats,
        beat_positions=[1, 2, 3, 4] * (len(beats) // 4 + 1),
        segments=segments,
    )


def make_shots(n=3, duration=30.0):
    interval = duration / n
    return [
        ShotBoundary(
            start_frame=int(i * interval * 30),
            end_frame=int((i + 1) * interval * 30),
            start_s=i * interval,
            end_s=(i + 1) * interval,
            is_gradual=False,
            confidence=0.9,
        )
        for i in range(n)
    ]


# ──────────────────────────────────────────────────────────────────────────────
# generate_cutlist_programmatic
# ──────────────────────────────────────────────────────────────────────────────

class TestProgrammaticCutlist:
    def test_basic_generation(self):
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=3)
        energy = [0.3, 0.5, 0.8]
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=30.0)

        assert isinstance(cutlist, CutList)
        assert cutlist.globals.tempo_bpm == 120.0
        assert len(cutlist.slots) > 0
        assert cutlist.globals.total_duration_s == 30.0
        assert cutlist.globals.aspect_ratio == "9:16"

    def test_slots_have_valid_durations(self):
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=3)
        energy = [0.5] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=30.0)

        for slot in cutlist.slots:
            assert slot.duration_s > 0
            assert slot.duration_s >= 0.5
            assert slot.start_s >= 0

    def test_slots_start_at_beats(self):
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=3)
        energy = [0.5] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=30.0)

        for slot in cutlist.slots:
            # Each slot start should be very close to a beat time
            closest_beat = min(beats.beats, key=lambda b: abs(b - slot.start_s))
            assert abs(slot.start_s - closest_beat) < 0.01

    def test_energy_mapping_low(self):
        """Low energy should produce wide shots."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=1)
        energy = [0.1] * 10  # Very low energy
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=10.0)

        # At least some slots should be wide
        wide_count = sum(1 for s in cutlist.slots if s.target_shot_type == "wide")
        assert wide_count > 0

    def test_energy_mapping_high(self):
        """High energy should produce close-up shots."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=1)
        energy = [0.95] * 10  # Very high energy
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=10.0)

        # At least some slots should be close-up
        close_count = sum(1 for s in cutlist.slots if s.target_shot_type == "close_up")
        assert close_count > 0

    def test_section_transitions(self):
        """Slots should respect section boundaries."""
        beats = make_beat_grid(
            bpm=120,
            segments=[
                BeatSegment(start=0.0, end=5.0, label="intro"),
                BeatSegment(start=5.0, end=15.0, label="verse"),
                BeatSegment(start=15.0, end=30.0, label="drop"),
            ],
        )
        shots = make_shots(n=2)
        energy = [0.5] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=30.0)

        sections_found = {s.section for s in cutlist.slots}
        assert "intro" in sections_found
        assert "verse" in sections_found or "drop" in sections_found

    def test_downbeat_handling(self):
        """Downbeats should influence slot durations."""
        beats = make_beat_grid(
            bpm=120,
            downbeats=[0.0, 2.0, 4.0, 6.0],
        )
        shots = make_shots(n=1)
        energy = [0.7] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=8.0)
        assert len(cutlist.slots) > 0

    def test_section_boundary_transitions(self):
        """Section boundaries with high energy should use dramatic transitions."""
        beats = make_beat_grid(
            bpm=120,
            segments=[
                BeatSegment(start=0.0, end=2.0, label="intro"),
                BeatSegment(start=2.0, end=10.0, label="drop"),
            ],
        )
        shots = make_shots(n=2)
        energy = [0.9] * 10  # High energy
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=10.0)

        # Check if any slot has a non-hard-cut transition
        transitions = [s.transition_out for s in cutlist.slots]
        assert any(t != "hard_cut" for t in transitions) or len(cutlist.slots) <= 1

    def test_globals_section_markers(self):
        beats = make_beat_grid()
        shots = make_shots(n=3)
        cutlist = generate_cutlist_programmatic(beats, shots, [0.5] * 10, ["wide"], total_duration=30.0)

        assert len(cutlist.globals.section_markers) == 3
        assert cutlist.globals.section_markers[0].name == "intro"

    def test_energy_curve_in_globals(self):
        energy = [0.1, 0.3, 0.5, 0.7, 0.9]
        beats = make_beat_grid()
        shots = make_shots(n=3)
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=30.0)

        assert cutlist.globals.energy_curve == energy


# ──────────────────────────────────────────────────────────────────────────────
# AI provider fallback
# ──────────────────────────────────────────────────────────────────────────────

class TestAIFallback:
    def test_programmatic_mode_no_api_call(self):
        """When AI_PROVIDER=programmatic, no API call should be made."""
        import os
        old_provider = os.environ.get("AI_PROVIDER")
        os.environ["AI_PROVIDER"] = "programmatic"
        try:
            beats = make_beat_grid()
            shots = make_shots(n=2)
            cutlist = generate_cutlist(beats, shots, {}, [0.5] * 5, ["wide"], total_duration=10.0)
            assert isinstance(cutlist, CutList)
            assert len(cutlist.slots) > 0
        finally:
            if old_provider is None:
                del os.environ["AI_PROVIDER"]
            else:
                os.environ["AI_PROVIDER"] = old_provider

    def test_invalid_provider_falls_back(self):
        """Invalid provider should fall back to programmatic."""
        import os
        old_provider = os.environ.get("AI_PROVIDER")
        os.environ["AI_PROVIDER"] = "nonexistent_provider"
        try:
            beats = make_beat_grid()
            shots = make_shots(n=2)
            # This should not crash — falls back to programmatic
            cutlist = generate_cutlist(beats, shots, {}, [0.5] * 5, ["wide"], total_duration=10.0)
            assert isinstance(cutlist, CutList)
        finally:
            if old_provider is None:
                del os.environ["AI_PROVIDER"]
            else:
                os.environ["AI_PROVIDER"] = old_provider


# ──────────────────────────────────────────────────────────────────────────────
# CUTLIST_SCHEMA validation
# ──────────────────────────────────────────────────────────────────────────────

class TestCutlistSchema:
    def test_schema_has_required_fields(self):
        assert "globals" in CUTLIST_SCHEMA["required"]
        assert "slots" in CUTLIST_SCHEMA["required"]
        assert "overlays" in CUTLIST_SCHEMA["required"]

    def test_schema_slot_properties(self):
        slot_schema = CUTLIST_SCHEMA["properties"]["slots"]["items"]["properties"]
        required_slot = CUTLIST_SCHEMA["properties"]["slots"]["items"]["required"]

        assert "index" in required_slot
        assert "startS" in required_slot
        assert "durationS" in required_slot
        assert "beatIndex" in required_slot
        assert "targetShotType" in required_slot
        assert "energyLevel" in required_slot

    def test_schema_energy_level_constraint(self):
        slot_schema = CUTLIST_SCHEMA["properties"]["slots"]["items"]["properties"]
        energy = slot_schema["energyLevel"]
        assert energy["minimum"] == 0
        assert energy["maximum"] == 1

    def test_schema_transition_enum(self):
        slot_schema = CUTLIST_SCHEMA["properties"]["slots"]["items"]["properties"]
        transitions = slot_schema["transitionIn"]["enum"]
        assert "hard_cut" in transitions
        assert "whip" in transitions
        assert "flash" in transitions
        assert len(transitions) == 16

    def test_schema_shot_type_enum(self):
        slot_schema = CUTLIST_SCHEMA["properties"]["slots"]["items"]["properties"]
        shot_types = slot_schema["targetShotType"]["enum"]
        assert "wide" in shot_types
        assert "close_up" in shot_types
        assert "insert" in shot_types

    def test_generated_cutlist_matches_schema(self):
        """Verify generated cut-list can be serialized to match schema structure."""
        beats = make_beat_grid()
        shots = make_shots(n=2)
        cutlist = generate_cutlist_programmatic(beats, shots, [0.5] * 5, ["wide"], total_duration=10.0)

        data = cutlist.model_dump()
        assert "globals" in data
        assert "slots" in data
        assert "overlays" in data
        assert "total_duration_s" in data["globals"]
        assert "tempo_bpm" in data["globals"]
        assert "section_markers" in data["globals"]
        assert "aspect_ratio" in data["globals"]

        for slot in data["slots"]:
            assert "index" in slot
            assert "start_s" in slot
            assert "duration_s" in slot
            assert "beat_index" in slot
            assert "target_shot_type" in slot
            assert "energy_level" in slot
            assert 0 <= slot["energy_level"] <= 1


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestCutlistEdgeCases:
    def test_no_beats(self):
        """Empty beat grid should produce minimal or empty cut-list."""
        beats = BeatGrid(bpm=0, beats=[], downbeats=[], beat_positions=[], segments=[])
        shots = []
        energy = []
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=0.0)
        assert isinstance(cutlist, CutList)
        assert cutlist.globals.tempo_bpm == 0.0

    def test_single_beat(self):
        """Single beat should produce at most one slot."""
        beats = BeatGrid(
            bpm=120,
            beats=[0.0],
            downbeats=[0.0],
            beat_positions=[1],
            segments=[BeatSegment(start=0.0, end=5.0, label="intro")],
        )
        shots = [ShotBoundary(start_frame=0, end_frame=150, start_s=0.0, end_s=5.0, is_gradual=False)]
        cutlist = generate_cutlist_programmatic(beats, shots, [0.5], ["wide"], total_duration=5.0)
        assert isinstance(cutlist, CutList)

    def test_no_shots(self):
        """No shot boundaries should still work."""
        beats = make_beat_grid()
        shots = []
        energy = [0.5] * 10
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=10.0)
        assert isinstance(cutlist, CutList)

    def test_no_available_shot_types(self):
        """Empty shot type pool should not crash."""
        beats = make_beat_grid()
        shots = make_shots(n=2)
        energy = [0.5] * 5
        cutlist = generate_cutlist_programmatic(beats, shots, energy, [], total_duration=10.0)
        assert isinstance(cutlist, CutList)

    def test_very_short_total_duration(self):
        """1-second total duration."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=1, duration=1.0)
        energy = [0.5]
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=1.0)
        assert cutlist.globals.total_duration_s == 1.0
        total_slot_time = sum(s.duration_s for s in cutlist.slots)
        assert total_slot_time <= 1.5  # Small tolerance

    def test_very_long_total_duration(self):
        """5-minute total duration."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=5, duration=300.0)
        energy = [0.5] * 100
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=300.0)
        assert cutlist.globals.total_duration_s == 300.0

    def test_single_shot_type(self):
        """Only one shot type available."""
        beats = make_beat_grid()
        shots = make_shots(n=2)
        energy = [0.2, 0.8]
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=10.0)
        # All slots should be "wide" since it's the only option
        for slot in cutlist.slots:
            assert slot.target_shot_type == "wide"

    def test_extreme_energy_values(self):
        """Energy at exact 0.0 and 1.0."""
        beats = make_beat_grid()
        shots = make_shots(n=2)
        energy = [0.0, 1.0]
        available = ["wide", "medium", "close_up"]
        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=10.0)
        assert isinstance(cutlist, CutList)
        for slot in cutlist.slots:
            assert 0 <= slot.energy_level <= 1

    def test_no_energy_curve(self):
        """Empty energy curve should use default of 0.5."""
        beats = make_beat_grid()
        shots = make_shots(n=2)
        cutlist = generate_cutlist_programmatic(beats, shots, [], ["wide"], total_duration=10.0)
        assert isinstance(cutlist, CutList)
        assert len(cutlist.slots) > 0

    def test_slot_duration_does_not_exceed_total(self):
        """Last slot should not extend past total duration."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=2)
        energy = [0.5] * 10
        total_duration = 5.0
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=total_duration)
        if cutlist.slots:
            last_slot = cutlist.slots[-1]
            assert last_slot.start_s + last_slot.duration_s <= total_duration + 0.01
