# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Intent composer for the intent-first editing architecture.

Assigns one of the 15 viewer intents to each cutlist slot by combining:
  - the selected narrative arc / anchors
  - the reference video's intent trajectory
  - song section, energy, and mood
  - simple variety constraints so the edit doesn't get monotone
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared_py.logging_config import StructuredLogger
from shared_py.models import EDIT_INTENT_LABELS, Slot, SongMeaning

logger = StructuredLogger("reason_worker.intent_composer")


# Fallback mapping from narrative-arc beat names to default intents.
# These are overwritten when a reference intent profile is available.
_ARC_BEAT_INTENTS = {
    "opening": "BREATHE",
    "hook": "REVEAL",
    "build": "RAMP_UP",
    "climax": "RELEASE",
    "release": "CARRY",
    "outro": "LINGER",
}

# Energy + song-section heuristic.
_ENERGY_SECTION_INTENTS = {
    ("high", "drop"): "RELEASE",
    ("high", "chorus"): "AMPLIFY",
    ("high", "generic"): "PUNCTUATE",
    ("mid", "chorus"): "CARRY",
    ("mid", "verse"): "CARRY",
    ("mid", "bridge"): "LAYER",
    ("mid", "generic"): "CARRY",
    ("low", "verse"): "BREATHE",
    ("low", "bridge"): "WITHHOLD",
    ("low", "intro"): "BREATHE",
    ("low", "outro"): "LINGER",
    ("low", "generic"): "BREATHE",
}

# CLAP-style mood tags -> intent bias.
_MOOD_INTENT_BIAS = {
    "aggressive": "SHOCK",
    "angry": "SHOCK",
    "dramatic": "PUNCTUATE",
    "epic": "AMPLIFY",
    "happy": "CARRY",
    "joyful": "CARRY",
    "melancholic": "LINGER",
    "peaceful": "BREATHE",
    "romantic": "CONNECT",
    "sad": "WITHHOLD",
    "tense": "WITHHOLD",
    "triumphant": "RELEASE",
}


def _energy_bucket(energy: float) -> str:
    if energy > 0.7:
        return "high"
    if energy < 0.35:
        return "low"
    return "mid"


def _energy_section_intent(energy: float, section: str) -> str:
    bucket = _energy_bucket(energy)
    section_key = section.lower() if section else "generic"
    return _ENERGY_SECTION_INTENTS.get(
        (bucket, section_key),
        _ENERGY_SECTION_INTENTS.get((bucket, "generic"), "CARRY"),
    )


def _reference_intent_at(reference_intent_profile: Optional[Dict[str, Any]], t_s: float) -> Optional[str]:
    """Return the reference intent active at time ``t_s`` if any."""
    if not reference_intent_profile:
        return None
    trajectory = reference_intent_profile.get("intentTrajectory") or reference_intent_profile.get("intent_trajectory") or []
    for entry in trajectory:
        if isinstance(entry, dict):
            start_s = entry.get("start_s", 0.0)
            end_s = entry.get("end_s", 0.0)
            intent = entry.get("intent", "")
        elif isinstance(entry, (list, tuple)) and len(entry) >= 3:
            intent, start_s, end_s = entry[0], entry[1], entry[2]
        else:
            continue
        if intent and start_s <= t_s < end_s and intent in EDIT_INTENT_LABELS:
            return intent
    return None


def _arc_intent_at(arc_template: Optional[Any], arc_anchors: Optional[List[Any]], t_s: float) -> Optional[str]:
    """Return the narrative-arc intent for the anchor containing ``t_s``."""
    if not arc_anchors:
        return None
    for anchor in arc_anchors:
        if anchor.start_s <= t_s < anchor.end_s:
            return _ARC_BEAT_INTENTS.get(anchor.name)
    return None


def _song_mood_at(t_s: float, song_meaning: Optional[SongMeaning]) -> Optional[str]:
    if not song_meaning or not song_meaning.section_moods:
        return None
    for section in song_meaning.section_moods:
        if section.start_s <= t_s < section.end_s:
            return section.top_moods[0][0] if section.top_moods else None
    return None


def _mood_intent(mood: Optional[str]) -> Optional[str]:
    if not mood:
        return None
    return _MOOD_INTENT_BIAS.get(mood.lower())


def _slot_energy(slot: Slot, energy_curve: Optional[List[float]], total_duration: float) -> float:
    """Energy at the slot midpoint."""
    if not energy_curve or total_duration <= 0:
        return slot.energy_level
    t = slot.start_s + slot.duration_s / 2.0
    progress = min(1.0, max(0.0, t / total_duration))
    idx = min(int(progress * len(energy_curve)), len(energy_curve) - 1)
    return energy_curve[idx]


def _break_runs(intents: List[str]) -> List[str]:
    """Replace every third identical intent in a row with a common alternative."""
    if len(intents) < 3:
        return intents
    result = list(intents)
    alternatives = ["CARRY", "PUNCTUATE", "BREATHE", "AMPLIFY"]
    for i in range(2, len(result)):
        if result[i] == result[i - 1] == result[i - 2]:
            for alt in alternatives:
                if alt != result[i]:
                    result[i] = alt
                    break
    return result


def assign_intents_to_slots(
    slots: List[Slot],
    arc_template: Optional[Any] = None,
    arc_anchors: Optional[List[Any]] = None,
    reference_intent_profile: Optional[Dict[str, Any]] = None,
    song_meaning: Optional[SongMeaning] = None,
    energy_curve: Optional[List[float]] = None,
) -> None:
    """Assign an edit intent to every slot.

    The function mutates ``slot.intent`` in place. It is designed to be safe to
    call on both programmatic and AI-generated cutlists.
    """
    if not slots:
        return

    total_duration = max(s.start_s + s.duration_s for s in slots)
    assigned: List[str] = []

    for slot in slots:
        t = slot.start_s + slot.duration_s / 2.0
        energy = _slot_energy(slot, energy_curve, total_duration)

        votes: Dict[str, float] = {}

        # Reference trajectory has the strongest voice (the editor's actual style).
        ref_intent = _reference_intent_at(reference_intent_profile, t)
        if ref_intent:
            votes[ref_intent] = votes.get(ref_intent, 0.0) + 2.0

        # Narrative arc supplies dramatic structure.
        arc_intent = _arc_intent_at(arc_template, arc_anchors, t)
        if arc_intent:
            votes[arc_intent] = votes.get(arc_intent, 0.0) + 1.5

        # Energy + section is the song-driven demand.
        energy_intent = _energy_section_intent(energy, slot.section)
        votes[energy_intent] = votes.get(energy_intent, 0.0) + 1.0

        # Mood adds emotional color.
        mood = _song_mood_at(t, song_meaning)
        mood_intent = _mood_intent(mood)
        if mood_intent:
            votes[mood_intent] = votes.get(mood_intent, 0.0) + 0.7

        best = max(votes, key=votes.get) if votes else "CARRY"
        assigned.append(best)

    assigned = _break_runs(assigned)

    for slot, intent in zip(slots, assigned):
        slot.intent = intent

    logger.info(
        "intents_assigned",
        slot_count=len(slots),
        histogram={intent: assigned.count(intent) for intent in set(assigned)},
    )
