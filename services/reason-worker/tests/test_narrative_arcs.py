# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reason_worker.narrative_arcs import (
    TRAILER_ARC,
    TRAGIC_ARC,
    CLASSICAL_ARC,
    ArcBeat,
    ArcTemplate,
    select_arc,
    _has_dramatic_drop,
)


def test_trailer_arc_has_five_beats():
    assert len(TRAILER_ARC.beats) == 5
    assert [b.name for b in TRAILER_ARC.beats] == ["HOOK", "WORLD", "CONFLICT", "CRISIS", "VICTORY"]


def test_tragic_arc_has_five_beats():
    assert len(TRAGIC_ARC.beats) == 5
    assert [b.name for b in TRAGIC_ARC.beats] == ["HOPE", "DREAM", "RISE", "FALL", "GRIEF"]


def test_classical_arc_has_five_beats():
    assert len(CLASSICAL_ARC.beats) == 5
    assert [b.name for b in CLASSICAL_ARC.beats] == [
        "WORLD",
        "INCITING_INCIDENT",
        "RISING_ACTION",
        "CLIMAX",
        "RESOLUTION",
    ]


def test_arc_beat_post_init_clamps_values():
    beat = ArcBeat(
        name="TEST",
        emotion_target="joy",
        preferred_shots=["close_up"],
        energy_target=1.5,
        position_start_pct=-0.2,
        position_end_pct=2.0,
    )
    assert beat.energy_target == pytest.approx(1.0)
    assert beat.position_start_pct == pytest.approx(0.0)
    assert beat.position_end_pct == pytest.approx(1.0)


def test_arc_template_beat_by_name():
    assert TRAILER_ARC.beat_by_name("CRISIS") is not None
    assert TRAILER_ARC.beat_by_name("NOT_REAL") is None


def test_has_dramatic_drop_true():
    curve = [0.2, 0.9, 0.8, 0.1, 0.5]
    assert _has_dramatic_drop(curve) is True


def test_has_dramatic_drop_false():
    curve = [0.5, 0.55, 0.5, 0.52]
    assert _has_dramatic_drop(curve) is False


def test_select_arc_prefers_trailer_for_drop_and_motion():
    style = {"camera_motions": ["fast_pan", "whip", "zoom_in", "handheld"]}
    curve = [0.2, 0.9, 0.1, 0.8]
    arc = select_arc(curve, style_analysis=style)
    assert arc.type == "trailer"


def test_select_arc_prefers_tragic_for_minor_and_long_holds():
    style = {"camera_motions": ["long_take", "static", "still", "slow_pan"]}
    arc = select_arc([0.5, 0.5, 0.5], style_analysis=style, key="C minor")
    assert arc.type == "tragic"


def test_select_arc_defaults_classical():
    arc = select_arc([0.5, 0.5, 0.5], style_analysis=None, key="C major")
    assert arc.type == "classical"
