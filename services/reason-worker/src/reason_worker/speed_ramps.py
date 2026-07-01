# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Deterministic speed-ramp assignment for cinematic pacing.

Speed ramps compress or stretch source time to match the musical energy of a
slot.  For Sprint A only average-speed remapping is rendered (via FFmpeg
``setpts``); variable curves are accepted at the cutlist level so the feature
tracer can report a real path as soon as two or more ramps are emitted.
"""

from __future__ import annotations

from typing import List, Optional

from shared_py.feature_tracer import FeatureTracer
from shared_py.logging_config import StructuredLogger
from shared_py.models import Effect, Slot, SpeedRampParams

logger = StructuredLogger("reason_worker.speed_ramps")

# Minimum slot length that can absorb a speed change without looking stuttery.
_MIN_SLOT_DURATION_S = 1.2

# Ramp presets keyed by narrative moment.
_RAMP_PRESETS = {
    "hit": {"start_speed": 1.0, "end_speed": 2.0, "curve": "ramp_up"},
    "drop": {"start_speed": 0.5, "end_speed": 1.0, "curve": "s_curve"},
    "build": {"start_speed": 1.0, "end_speed": 1.6, "curve": "ramp_up"},
    "breather": {"start_speed": 1.6, "end_speed": 1.0, "curve": "ramp_down"},
}


def _pick_ramp_for_slot(slot: Slot, used_indices: set) -> Optional[Effect]:
    """Return a speed-ramp effect if this slot is a good candidate."""
    if slot.index in used_indices:
        return None
    if slot.duration_s < _MIN_SLOT_DURATION_S:
        return None

    energy = slot.energy_level
    section = (slot.section or "").lower()

    if section in ("drop", "chorus") and energy >= 0.75:
        preset = _RAMP_PRESETS["hit"]
    elif section in ("build", "bridge") and energy >= 0.65:
        preset = _RAMP_PRESETS["build"]
    elif section in ("verse", "intro") and energy <= 0.45:
        preset = _RAMP_PRESETS["breather"]
    elif energy >= 0.85:
        preset = _RAMP_PRESETS["hit"]
    else:
        return None

    return Effect(
        type="speed_ramp",
        start_s=slot.start_s,
        duration_s=slot.duration_s,
        params=SpeedRampParams(**preset).model_dump(by_alias=True),
    )


def assign_speed_ramps_to_slots(
    slots: List[Slot],
    min_ramps: int = 2,
    max_ramps: int = 6,
) -> List[Slot]:
    """Assign speed-ramp effects to high-energy/transition slots.

    Mutates ``slot.effects`` in place.  Wraps the work in a ``speed_ramps``
    FeatureTracer so the render gate can verify the real path ran.
    """
    with FeatureTracer("speed_ramps", gated_in=True) as ft:
        used_indices: set = set()
        ramps: List[Effect] = []

        # Prefer high-energy slots first.
        candidates = sorted(
            [s for s in slots if s.duration_s >= _MIN_SLOT_DURATION_S],
            key=lambda s: s.energy_level,
            reverse=True,
        )

        for slot in candidates:
            if len(ramps) >= max_ramps:
                break
            ramp = _pick_ramp_for_slot(slot, used_indices)
            if ramp is None:
                continue
            slot.effects.append(ramp)
            used_indices.add(slot.index)
            ramps.append(ramp)
            # Re-apply the per-slot effect cap used by the renderer.
            if len(slot.effects) > 2:
                slot.effects = slot.effects[:2]

        if len(ramps) >= min_ramps:
            ft.signature(f"n_ramps={len(ramps)},curves={','.join(r.params.get('curve', 'linear') for r in ramps)}")
            ft.real()
            logger.info("speed_ramps_assigned", n_ramps=len(ramps))
        else:
            ft.fallback(f"not_enough_candidates:{len(ramps)}_ramps")
            logger.warning("speed_ramps_fallback", n_ramps=len(ramps), min_required=min_ramps)

    return slots
