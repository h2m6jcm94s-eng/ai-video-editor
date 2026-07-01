# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Narrative arc templates for emotion-led editing.

Each arc is a sequence of beats with target emotion, energy, preferred shots,
and kinetic-text archetype.  The templates are intentionally small and
interpretable: they act as a style palette that the arc-to-song mapper turns
into concrete time ranges.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal

from shared_py.models import EmotionLabel


@dataclass
class ArcBeat:
    """A single beat inside a narrative arc."""

    name: str
    emotion_target: EmotionLabel
    preferred_shots: List[str]
    energy_target: float  # 0 = calm, 1 = intense
    motion_target: Literal["still", "slow", "medium", "fast"] = "medium"
    text_archetype: str = "moment"
    position_start_pct: float = 0.0  # inclusive start on the 0-1 song timeline
    position_end_pct: float = 1.0  # inclusive end on the 0-1 song timeline

    def __post_init__(self):
        self.energy_target = float(max(0.0, min(1.0, self.energy_target)))
        self.position_start_pct = float(max(0.0, min(1.0, self.position_start_pct)))
        self.position_end_pct = float(
            max(self.position_start_pct, min(1.0, self.position_end_pct))
        )


@dataclass
class ArcTemplate:
    """A complete narrative arc made of ordered beats."""

    name: str
    type: Literal["trailer", "tragic", "classical"]
    beats: List[ArcBeat] = field(default_factory=list)

    def beat_by_name(self, name: str) -> Optional[ArcBeat]:
        for beat in self.beats:
            if beat.name == name:
                return beat
        return None


# Trailer arc: fast, loud, heroic/suspenseful.  Designed for AMVs and hype cuts.
TRAILER_ARC = ArcTemplate(
    name="Trailer",
    type="trailer",
    beats=[
        ArcBeat(
            name="HOOK",
            emotion_target="awe",
            preferred_shots=["close_up", "wide"],
            energy_target=0.7,
            motion_target="medium",
            text_archetype="the hook",
            position_start_pct=0.0,
            position_end_pct=0.10,
        ),
        ArcBeat(
            name="WORLD",
            emotion_target="intrigue",
            preferred_shots=["wide", "medium"],
            energy_target=0.4,
            motion_target="slow",
            text_archetype="the world",
            position_start_pct=0.10,
            position_end_pct=0.30,
        ),
        ArcBeat(
            name="CONFLICT",
            emotion_target="tension",
            preferred_shots=["medium", "close_up"],
            energy_target=0.6,
            motion_target="fast",
            text_archetype="the clash",
            position_start_pct=0.30,
            position_end_pct=0.50,
        ),
        ArcBeat(
            name="CRISIS",
            emotion_target="fear",
            preferred_shots=["close_up"],
            energy_target=0.3,
            motion_target="slow",
            text_archetype="the fall",
            position_start_pct=0.50,
            position_end_pct=0.70,
        ),
        ArcBeat(
            name="VICTORY",
            emotion_target="triumph",
            preferred_shots=["wide", "close_up"],
            energy_target=0.9,
            motion_target="fast",
            text_archetype="the rise",
            position_start_pct=0.70,
            position_end_pct=1.0,
        ),
    ],
)


# Tragic arc: hope followed by loss.  Designed for melancholic songs and dramas.
TRAGIC_ARC = ArcTemplate(
    name="Tragic",
    type="tragic",
    beats=[
        ArcBeat(
            name="HOPE",
            emotion_target="joy",
            preferred_shots=["wide", "medium"],
            energy_target=0.5,
            motion_target="slow",
            text_archetype="the dream",
            position_start_pct=0.0,
            position_end_pct=0.20,
        ),
        ArcBeat(
            name="DREAM",
            emotion_target="awe",
            preferred_shots=["wide", "medium"],
            energy_target=0.4,
            motion_target="slow",
            text_archetype="the promise",
            position_start_pct=0.20,
            position_end_pct=0.40,
        ),
        ArcBeat(
            name="RISE",
            emotion_target="triumph",
            preferred_shots=["medium", "wide"],
            energy_target=0.7,
            motion_target="medium",
            text_archetype="the rise",
            position_start_pct=0.40,
            position_end_pct=0.55,
        ),
        ArcBeat(
            name="FALL",
            emotion_target="tension",
            preferred_shots=["close_up", "medium"],
            energy_target=0.5,
            motion_target="medium",
            text_archetype="the turn",
            position_start_pct=0.55,
            position_end_pct=0.75,
        ),
        ArcBeat(
            name="GRIEF",
            emotion_target="grief",
            preferred_shots=["close_up"],
            energy_target=0.2,
            motion_target="still",
            text_archetype="the loss",
            position_start_pct=0.75,
            position_end_pct=1.0,
        ),
    ],
)


# Classical arc: stable three-act structure.  Safe default for most songs.
CLASSICAL_ARC = ArcTemplate(
    name="Classical",
    type="classical",
    beats=[
        ArcBeat(
            name="WORLD",
            emotion_target="calm",
            preferred_shots=["wide", "medium"],
            energy_target=0.3,
            motion_target="slow",
            text_archetype="the world",
            position_start_pct=0.0,
            position_end_pct=0.20,
        ),
        ArcBeat(
            name="INCITING_INCIDENT",
            emotion_target="intrigue",
            preferred_shots=["medium", "close_up"],
            energy_target=0.5,
            motion_target="medium",
            text_archetype="the spark",
            position_start_pct=0.20,
            position_end_pct=0.35,
        ),
        ArcBeat(
            name="RISING_ACTION",
            emotion_target="tension",
            preferred_shots=["medium", "close_up"],
            energy_target=0.6,
            motion_target="medium",
            text_archetype="the chase",
            position_start_pct=0.35,
            position_end_pct=0.60,
        ),
        ArcBeat(
            name="CLIMAX",
            emotion_target="triumph",
            preferred_shots=["close_up", "wide"],
            energy_target=0.9,
            motion_target="fast",
            text_archetype="the peak",
            position_start_pct=0.60,
            position_end_pct=0.80,
        ),
        ArcBeat(
            name="RESOLUTION",
            emotion_target="awe",
            preferred_shots=["wide", "medium"],
            energy_target=0.4,
            motion_target="slow",
            text_archetype="the aftermath",
            position_start_pct=0.80,
            position_end_pct=1.0,
        ),
    ],
)


def _has_dramatic_drop(energy_curve: List[float]) -> bool:
    """True if energy drops by at least 50% of the peak at some point."""
    if not energy_curve or len(energy_curve) < 3:
        return False
    peak = max(energy_curve)
    if peak <= 0.01:
        return False
    trough = min(energy_curve)
    return (peak - trough) / peak >= 0.5


def _reference_motion_ratio(style_analysis: Optional[Dict[str, Any]]) -> float:
    """Return a normalized motion ratio from a style analysis dict."""
    if not style_analysis:
        return 0.5
    motions = style_analysis.get("camera_motions", [])
    if not motions:
        return 0.5
    fast_motions = {"fast_pan", "whip", "zoom_in", "zoom_out", "handheld"}
    return sum(1 for m in motions if m in fast_motions) / len(motions)


def _reference_long_hold_ratio(style_analysis: Optional[Dict[str, Any]]) -> float:
    """Estimate long-hold ratio from detected transitions.

    A long hold is inferred when the style analysis lists few transitions or
    explicitly notes "long_take" / "static" camera motions.
    """
    if not style_analysis:
        return 0.0
    transitions = style_analysis.get("detected_transitions", [])
    motions = style_analysis.get("camera_motions", [])
    if not transitions and not motions:
        return 0.0
    static_signals = {"long_take", "static", "still"}
    static_count = sum(1 for m in motions if m in static_signals)
    total = max(1, len(transitions) + len(motions))
    return static_count / total


def _is_minor_key(key: Optional[str]) -> bool:
    """Heuristic: treat unknown key as minor if the song is labeled with 'm'."""
    if not key:
        return False
    return "m" in key.lower() or "minor" in key.lower()


def select_arc(
    energy_curve: List[float],
    style_analysis: Optional[Dict[str, Any]] = None,
    key: Optional[str] = None,
) -> ArcTemplate:
    """Pick the best arc template for a song + reference.

    - Trailer when the energy curve has a dramatic drop and the reference is
      fast/motion-heavy.
    - Tragic when the key is minor and the reference favors long holds / stills.
    - Classical as the safe default.
    """
    if _has_dramatic_drop(energy_curve) and _reference_motion_ratio(style_analysis) > 0.6:
        return TRAILER_ARC
    if _is_minor_key(key) and _reference_long_hold_ratio(style_analysis) > 0.4:
        return TRAGIC_ARC
    return CLASSICAL_ARC
