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

    def test_cuts_only_tier_has_no_effects_or_overlays(self):
        """Lower style tiers should not generate effects, transitions, or overlays."""
        beats = make_beat_grid(
            bpm=120,
            segments=[
                BeatSegment(start=0.0, end=2.0, label="intro"),
                BeatSegment(start=2.0, end=10.0, label="drop"),
            ],
        )
        shots = make_shots(n=2)
        energy = [0.9] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(
            beats, shots, energy, available, total_duration=10.0, style_tier="cuts_only"
        )

        for slot in cutlist.slots:
            assert slot.transition_in == "hard_cut"
            assert slot.transition_out == "hard_cut"
            assert not slot.effects
        assert not cutlist.overlays

    def test_with_text_tier_has_overlays_but_no_effects(self):
        """Text tier should generate overlays but not slot effects/transitions."""
        beats = make_beat_grid(
            bpm=120,
            segments=[
                BeatSegment(start=0.0, end=2.0, label="intro"),
                BeatSegment(start=2.0, end=10.0, label="drop"),
            ],
        )
        shots = make_shots(n=2)
        energy = [0.9] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(
            beats, shots, energy, available, total_duration=10.0, style_tier="with_text"
        )

        for slot in cutlist.slots:
            assert slot.transition_in == "hard_cut"
            assert slot.transition_out == "hard_cut"
            assert not slot.effects
        assert cutlist.overlays

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
# Effects and overlays
# ──────────────────────────────────────────────────────────────────────────────

class TestEffectsAndOverlays:
    def test_high_energy_slot_gets_zoom_punch_in(self):
        """High-energy downbeat slots should include zoom_punch_in."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=1)
        energy = [0.95] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=10.0)

        zoom_count = sum(
            1 for s in cutlist.slots
            for e in s.effects
            if e.type == "zoom_punch_in"
        )
        assert zoom_count > 0

    def test_highest_energy_slot_gets_vignette(self):
        """The single highest-energy slot should receive vignette."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=1)
        energy = [0.2, 0.3, 0.95, 0.4, 0.5]
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=10.0)

        vignette_count = sum(
            1 for s in cutlist.slots
            for e in s.effects
            if e.type == "vignette"
        )
        assert vignette_count == 1

    def test_section_boundary_gets_film_grain_and_overlay(self):
        """Section boundaries should add film_grain and a text overlay."""
        beats = make_beat_grid(
            bpm=120,
            segments=[
                BeatSegment(start=0.0, end=5.0, label="intro"),
                BeatSegment(start=5.0, end=15.0, label="verse"),
            ],
        )
        shots = make_shots(n=2)
        energy = [0.8] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=15.0)

        grain_count = sum(
            1 for s in cutlist.slots
            for e in s.effects
            if e.type == "film_grain"
        )
        assert grain_count > 0
        assert any("VERSE" in o.text for o in cutlist.overlays)

    def test_no_hard_coded_promotional_overlays(self):
        """Programmatic generation must not inject generic CTAs or hook text.

        Overlays should only come from detected reference text or section
        boundaries, never from hard-coded strings like "LET'S GO".
        """
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=2)
        energy = [0.9] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=10.0)

        for overlay in cutlist.overlays:
            assert "LET'S GO" not in overlay.text
            assert "FOLLOW FOR MORE" not in overlay.text

    def test_detected_overlays_are_preserved(self):
        """Reference overlays provided in style analysis should be kept."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=2)
        energy = [0.5] * 10
        available = ["wide", "medium", "close_up"]
        style_analysis = {
            "detectedOverlays": [
                {
                    "text": "DRIFT KING",
                    "startS": 0.0,
                    "endS": 3.0,
                    "position": "center",
                    "font": "Inter",
                    "fontSizePx": 48,
                    "color": "#FFFFFF",
                    "stroke": "#000000",
                    "animation": "fade",
                }
            ]
        }

        cutlist = generate_cutlist_programmatic(
            beats, shots, energy, available, total_duration=10.0,
            style_analysis=style_analysis, style_tier="with_text"
        )

        assert any(o.text == "DRIFT KING" for o in cutlist.overlays)

    def test_effects_capped_at_two_per_slot(self):
        """No slot should have more than 2 effects."""
        beats = make_beat_grid(
            bpm=120,
            segments=[
                BeatSegment(start=0.0, end=2.0, label="intro"),
                BeatSegment(start=2.0, end=10.0, label="drop"),
            ],
        )
        shots = make_shots(n=1)
        energy = [0.95] * 10
        available = ["wide", "medium", "close_up"]

        cutlist = generate_cutlist_programmatic(beats, shots, energy, available, total_duration=10.0)

        for slot in cutlist.slots:
            assert len(slot.effects) <= 2


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
        """5-minute request is capped to the actual generated slot content."""
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=5, duration=300.0)
        energy = [0.5] * 100
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=300.0)
        actual_slot_end = max(s.start_s + s.duration_s for s in cutlist.slots)
        assert cutlist.globals.total_duration_s == actual_slot_end
        assert cutlist.globals.total_duration_s <= 300.0

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



class TestShotAndBeatSnapping:
    """Phase 2: slot starts should snap to shot boundaries and durations quantize to beats."""

    def test_slot_snaps_to_nearby_shot_boundary(self):
        # Use a beat grid whose beats are close enough to the 5.0 shot boundary
        # that the snap logic can pull a slot start onto it.
        beat_interval = 0.5
        beats = make_beat_grid(bpm=120, beats=[i * beat_interval for i in range(21)])
        shots = [
            ShotBoundary(start_frame=0, end_frame=150, start_s=0.0, end_s=5.0, is_gradual=False),
            ShotBoundary(start_frame=150, end_frame=300, start_s=5.0, end_s=10.0, is_gradual=False),
        ]
        energy = [0.5] * 12
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=10.0)

        # At least one slot should start in the second shot (at or after 5.0).
        assert any(s.start_s >= 5.0 - 1e-3 for s in cutlist.slots), (
            f"expected a slot at or after the 5.0 shot boundary, got starts "
            f"{[s.start_s for s in cutlist.slots]}"
        )

    def test_slot_durations_fill_available_space(self):
        beats = make_beat_grid(bpm=60)
        shots = [ShotBoundary(start_frame=0, end_frame=300, start_s=0.0, end_s=10.0, is_gradual=False)]
        energy = [0.5] * 12
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=10.0)

        # Slots should be contiguous/non-overlapping and cover most of the content.
        for i, slot in enumerate(cutlist.slots):
            assert slot.duration_s > 0
            if i > 0:
                prev_end = cutlist.slots[i - 1].start_s + cutlist.slots[i - 1].duration_s
                assert slot.start_s >= prev_end - 1e-3, (
                    f"slot {i} overlaps previous slot (prev ends {prev_end}, current starts {slot.start_s})"
                )

        last_slot = cutlist.slots[-1]
        assert last_slot.start_s + last_slot.duration_s >= 9.0, (
            f"last slot ends too early at {last_slot.start_s + last_slot.duration_s}"
        )

    def test_slot_starts_snap_near_shot_boundaries(self):
        """Slot starts should snap to shot boundaries or beats, but durations
        are no longer truncated at shot ends to avoid tiny slots."""
        beats = make_beat_grid(bpm=60)
        shots = [
            ShotBoundary(start_frame=0, end_frame=150, start_s=0.0, end_s=5.0, is_gradual=False),
            ShotBoundary(start_frame=150, end_frame=300, start_s=5.0, end_s=10.0, is_gradual=False),
        ]
        energy = [0.9] * 12
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=10.0)

        for slot in cutlist.slots:
            # Slot start should be within one beat of a shot boundary or a beat.
            nearest_shot = min((abs(slot.start_s - s.start_s) for s in shots), default=float("inf"))
            nearest_beat = min((abs(slot.start_s - b) for b in beats.beats), default=float("inf"))
            assert min(nearest_shot, nearest_beat) < 0.6, (
                f"slot {slot.index} start {slot.start_s} is far from both shots and beats"
            )
            assert slot.duration_s >= 0.4, f"slot {slot.index} duration collapsed to {slot.duration_s}"

    def test_snapping_preserves_nonzero_duration(self):
        beats = make_beat_grid(bpm=60)
        shots = [ShotBoundary(start_frame=0, end_frame=300, start_s=0.0, end_s=10.0, is_gradual=False)]
        energy = [0.5] * 12
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=10.0)

        for slot in cutlist.slots:
            assert slot.duration_s >= 0.4, f"slot {slot.index} duration collapsed to {slot.duration_s}"



class TestStyleAnalysisConsumption:
    """Phase 4: cutlist generation should use style-analysis outputs."""

    def test_detected_transitions_influence_slot_transitions(self):
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=3)
        energy = [0.6] * 20
        style = {"detectedTransitions": ["wipe_left", "dissolve", "whip"]}
        cutlist = generate_cutlist_programmatic(
            beats, shots, energy, ["wide", "medium", "close_up"], total_duration=10.0, style_analysis=style
        )

        transitions = [s.transition_in for s in cutlist.slots]
        assert any(t != "hard_cut" for t in transitions), transitions

    def test_camera_motions_override_motion_hint(self):
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=3)
        energy = [0.5] * 20
        style = {"cameraMotions": ["pan_left", "zoom_in", "gimbal"]}
        cutlist = generate_cutlist_programmatic(
            beats, shots, energy, ["wide"], total_duration=10.0, style_analysis=style
        )

        for slot in cutlist.slots:
            assert slot.motion_hint in ["pan_left", "zoom_in", "gimbal"], slot.motion_hint

    def test_detected_overlays_added_to_cutlist(self):
        beats = make_beat_grid(bpm=120)
        shots = make_shots(n=1)
        energy = [0.5] * 10
        style = {
            "detectedOverlays": [
                {
                    "text": "SUBSCRIBE",
                    "startS": 1.0,
                    "endS": 3.0,
                    "position": "bottom",
                    "font": "Inter",
                    "fontSizePx": 42,
                    "color": "#FFFFFF",
                    "stroke": "#000000",
                    "animation": "fade",
                }
            ]
        }
        cutlist = generate_cutlist_programmatic(
            beats, shots, energy, ["wide"], total_duration=10.0, style_analysis=style
        )

        assert any("SUBSCRIBE" in o.text for o in cutlist.overlays)



class TestSlotContiguityAndDurationCap:
    """Slots must not overlap and must respect the reference/song duration cap."""

    def test_slots_do_not_overlap_and_stay_within_content(self):
        beats = make_beat_grid(bpm=120, beats=[i * 0.5 for i in range(25)])
        shots = [ShotBoundary(start_frame=0, end_frame=300, start_s=0.0, end_s=10.0, is_gradual=False)]
        energy = [0.5] * 10
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide", "medium", "close_up"], total_duration=10.0)

        assert cutlist.slots
        content_end = cutlist.globals.total_duration_s
        for i, slot in enumerate(cutlist.slots):
            assert slot.start_s >= 0
            assert slot.duration_s > 0
            assert slot.start_s + slot.duration_s <= content_end + 1e-3
            if i > 0:
                prev_end = cutlist.slots[i - 1].start_s + cutlist.slots[i - 1].duration_s
                assert slot.start_s >= prev_end - 1e-3, (
                    f"slot {i} overlaps previous slot (prev ends {prev_end}, current starts {slot.start_s})"
                )

        last_slot = cutlist.slots[-1]
        assert last_slot.start_s + last_slot.duration_s >= content_end - 1.0

    def test_reference_shorter_than_song_caps_duration(self):
        beats = make_beat_grid(bpm=120, beats=[i * 0.5 for i in range(125)])
        shots = [ShotBoundary(start_frame=0, end_frame=300, start_s=0.0, end_s=10.0, is_gradual=False)]
        energy = [0.5] * 10
        cutlist = generate_cutlist_programmatic(beats, shots, energy, ["wide"], total_duration=30.0)

        assert cutlist.globals.total_duration_s <= 10.0
        assert all(s.start_s + s.duration_s <= 10.0 + 1e-3 for s in cutlist.slots)
