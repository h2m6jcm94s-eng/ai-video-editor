# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Intent → technique mapper for the intent-first editing architecture.

Takes the viewer intent assigned to each slot and translates it into concrete
editing choices: transition style, target shot size, motion hint, and text
density. This is a downstream consumer of T5 (intent composer); it does not
decide what the viewer should feel, only how to make them feel it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared_py.logging_config import StructuredLogger
from shared_py.models import Slot

logger = StructuredLogger("reason_worker.intent_technique_mapper")


# ---------------------------------------------------------------------------
# Static intent → technique tables
# ---------------------------------------------------------------------------

_INTENT_TRANSITION_IN = {
    "BREATHE": "fade",
    "PUNCTUATE": "hard_cut",
    "RAMP_UP": "hard_cut",
    "RELEASE": "hard_cut",
    "REVEAL": "dissolve",
    "WITHHOLD": "fade",
    "CONNECT": "dissolve",
    "ISOLATE": "hard_cut",
    "SHOCK": "hard_cut",
    "CARRY": "hard_cut",
    "LINGER": "dissolve",
    "JAB": "hard_cut",
    "LAYER": "dissolve",
    "STRIP_DOWN": "fade",
    "AMPLIFY": "hard_cut",
}

_INTENT_SHOT_TYPE = {
    "BREATHE": "wide",
    "PUNCTUATE": "medium",
    "RAMP_UP": "medium",
    "RELEASE": "wide",
    "REVEAL": "medium",
    "WITHHOLD": "close_up",
    "CONNECT": "medium",
    "ISOLATE": "close_up",
    "SHOCK": "medium_close_up",
    "CARRY": "medium",
    "LINGER": "close_up",
    "JAB": "close_up",
    "LAYER": "medium",
    "STRIP_DOWN": "wide",
    "AMPLIFY": "medium",
}

_INTENT_MOTION_HINT = {
    "BREATHE": "static",
    "PUNCTUATE": "dynamic",
    "RAMP_UP": "accelerating",
    "RELEASE": "explosive",
    "REVEAL": "panning",
    "WITHHOLD": "static",
    "CONNECT": "tracking",
    "ISOLATE": "static",
    "SHOCK": "jarring",
    "CARRY": "continuous",
    "LINGER": "static",
    "JAB": "dynamic",
    "LAYER": "complex",
    "STRIP_DOWN": "static",
    "AMPLIFY": "accelerating",
}

_INTENT_TEXT_DENSITY = {
    "BREATHE": "low",
    "PUNCTUATE": "medium",
    "RAMP_UP": "low",
    "RELEASE": "high",
    "REVEAL": "low",
    "WITHHOLD": "low",
    "CONNECT": "medium",
    "ISOLATE": "low",
    "SHOCK": "high",
    "CARRY": "low",
    "LINGER": "low",
    "JAB": "medium",
    "LAYER": "high",
    "STRIP_DOWN": "low",
    "AMPLIFY": "high",
}

# Pairs that read better with a whip/dissolve than a hard cut.
_SMOOTH_PAIRS = {
    ("BREATHE", "LINGER"),
    ("LINGER", "BREATHE"),
    ("REVEAL", "LINGER"),
    ("LINGER", "REVEAL"),
    ("CONNECT", "LINGER"),
    ("LINGER", "CONNECT"),
    ("STRIP_DOWN", "BREATHE"),
    ("BREATHE", "STRIP_DOWN"),
}

_HARD_PAIRS = {
    ("SHOCK", "RELEASE"),
    ("RELEASE", "SHOCK"),
    ("JAB", "RELEASE"),
    ("RELEASE", "JAB"),
    ("PUNCTUATE", "SHOCK"),
    ("SHOCK", "PUNCTUATE"),
}


def _transition_between(prev_intent: Optional[str], next_intent: str) -> str:
    """Pick a transition that respects the relationship between two intents."""
    if not prev_intent:
        return _INTENT_TRANSITION_IN.get(next_intent, "hard_cut")
    pair = (prev_intent, next_intent)
    if pair in _HARD_PAIRS:
        return "hard_cut"
    if pair in _SMOOTH_PAIRS:
        return "dissolve"
    return _INTENT_TRANSITION_IN.get(next_intent, "hard_cut")


def _clamp_motion_hint(hint: str) -> str:
    """Ensure motion hints stay in the vocabulary the ranker expects."""
    valid = {"static", "dynamic", "accelerating", "explosive", "panning",
             "tracking", "jarring", "continuous", "complex"}
    return hint if hint in valid else "dynamic"


def apply_techniques_from_intents(
    slots: List[Slot],
    reference_transitions: Optional[List[str]] = None,
    style_analysis: Optional[Dict[str, Any]] = None,
    available_shot_types: Optional[List[str]] = None,
) -> None:
    """Map each slot's intent to concrete technique choices.

    Mutates ``slots`` in place: sets ``transition_in``, ``transition_out``,
    ``target_shot_type``, ``motion_hint``, and ``text_density``.

    Args:
        slots: cutlist slots, each with ``intent`` already populated.
        reference_transitions: optional list of transition types detected in
            the reference video; used as a soft bias when the intent table
            yields a generic result.
        style_analysis: optional reference style genome; ``cameraMotions`` are
            applied as motion hints when present.
        available_shot_types: optional pool of shot types; used to keep energy-
            based shot selection honest after intent mapping.
    """
    if not slots:
        return

    style_analysis = style_analysis or {}
    camera_motions = (
        style_analysis.get("cameraMotions")
        or style_analysis.get("camera_motions")
        or []
    )

    ref_hard_ratio = 0.0
    if reference_transitions:
        hard_like = {"hard_cut", "cut", "whip"}
        ref_hard_ratio = sum(1 for t in reference_transitions if t in hard_like) / len(reference_transitions)

    # Remember dramatic transitions produced by upstream style/energy rules
    # (e.g. a flash at a high-energy section boundary) so they survive mapping.
    original_transition_out = [slot.transition_out for slot in slots]

    def _with_reference(base: str) -> str:
        """Replace a generic hard_cut with a reference transition when available."""
        if not reference_transitions or base != "hard_cut":
            return base
        non_hard = [t for t in reference_transitions if t not in {"hard_cut", "cut"}]
        return non_hard[0] if non_hard else base

    shot_pool = available_shot_types or []
    strong_shot_intents = {
        "BREATHE", "RELEASE", "STRIP_DOWN",
        "WITHHOLD", "ISOLATE", "SHOCK", "JAB", "LINGER",
    }

    for i, slot in enumerate(slots):
        intent = slot.intent or "CARRY"

        # Shot size from intent, then reconcile with the slot's energy so high-
        # energy moments don't get downgraded to a medium shot by a generic intent.
        slot.target_shot_type = _INTENT_SHOT_TYPE.get(intent, slot.target_shot_type or "medium")
        if shot_pool:
            if len(shot_pool) == 1:
                slot.target_shot_type = shot_pool[0]
            elif intent not in strong_shot_intents:
                if slot.energy_level >= 0.8:
                    for candidate in ("close_up", "medium_close_up"):
                        if candidate in shot_pool:
                            slot.target_shot_type = candidate
                            break
                elif slot.energy_level <= 0.3 and "wide" in shot_pool:
                    slot.target_shot_type = "wide"

        # Motion: intent table is the default, but explicit reference camera
        # motions override it when the user supplied a style genome.
        if camera_motions:
            slot.motion_hint = camera_motions[i % len(camera_motions)]
        else:
            slot.motion_hint = _clamp_motion_hint(_INTENT_MOTION_HINT.get(intent, slot.motion_hint or "dynamic"))

        # Text density.
        slot.text_density = _INTENT_TEXT_DENSITY.get(intent, slot.text_density)

        # Transition in: consider the previous slot's intent.
        prev_intent = slots[i - 1].intent if i > 0 else None
        transition_in = _with_reference(_transition_between(prev_intent, intent))

        # Soft reference bias: if the reference is very hard-cut-heavy, prefer
        # hard cuts unless the intent table explicitly asks for fade/dissolve.
        if ref_hard_ratio > 0.7 and transition_in not in ("fade", "dissolve"):
            transition_in = "hard_cut"

        slot.transition_in = transition_in

        # Transition out defaults to the intent table, possibly biased by refs.
        slot.transition_out = _with_reference(_INTENT_TRANSITION_IN.get(intent, "hard_cut"))

    # Second pass: align transition_out with the next slot's transition_in
    # so adjacent slots don't contradict each other.
    for i in range(len(slots) - 1):
        slots[i].transition_out = slots[i + 1].transition_in

    # Restore upstream flash transitions at high-energy section boundaries.
    for i, slot in enumerate(slots):
        if original_transition_out[i] == "flash" and slot.energy_level > 0.7:
            slot.transition_out = "flash"


    logger.info(
        "techniques_mapped",
        slot_count=len(slots),
        intent_histogram={intent: sum(1 for s in slots if s.intent == intent) for intent in set(s.intent for s in slots if s.intent)},
    )
