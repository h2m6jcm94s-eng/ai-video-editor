# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Attribute cut-list edits to BehaviorVector deltas.

This module is intentionally independent of the API/DB layer so it can be
unit-tested and reused in workers or notebooks.
"""

from typing import Any, Dict, List, Optional

from shared_py.models import BehaviorVector, CutList


def _transition_is_hard_cut(transition: Optional[str]) -> bool:
    return transition in {"hard_cut", "hardcut", None, ""}


def behavior_vector_from_cutlist(cutlist: CutList) -> Dict[str, float]:
    """Derive an absolute BehaviorVector-like dict from a cut-list."""
    slots = cutlist.slots or []
    total_duration = max(cutlist.globals.total_duration_s or 0.0, 0.001)

    n_slots = len(slots)
    cut_density_per_sec = n_slots / total_duration

    durations = [slot.duration_s for slot in slots]
    slot_duration_mean_s = sum(durations) / n_slots if n_slots else 0.0
    variance = (
        sum((d - slot_duration_mean_s) ** 2 for d in durations) / n_slots if n_slots else 0.0
    )
    slot_duration_std_s = variance**0.5

    transition_count = 0
    hard_cut_count = 0
    for slot in slots:
        for key in ("transition_in", "transition_out"):
            transition = getattr(slot, key, None)
            if transition:
                transition_count += 1
                if _transition_is_hard_cut(transition):
                    hard_cut_count += 1
    hard_cut_ratio = hard_cut_count / transition_count if transition_count else 0.7

    total_effects = sum(len(slot.effects or []) for slot in slots)
    effect_intensity = min(1.0, (total_effects / n_slots) / 3.0) if n_slots else 0.5

    text_density_per_sec = len(cutlist.overlays or []) / total_duration

    return {
        "cut_density_per_sec": cut_density_per_sec,
        "slot_duration_mean_s": slot_duration_mean_s,
        "slot_duration_std_s": slot_duration_std_s,
        "hard_cut_ratio": hard_cut_ratio,
        "effect_intensity": effect_intensity,
        "text_density_per_sec": text_density_per_sec,
    }


def diff_cutlists(old: Any, new: Any) -> Dict[str, float]:
    """Return BehaviorVector deltas implied by editing `old` into `new`.

    Accepts `CutList` objects or raw dicts (e.g. from JSON).
    """
    old_obj = old if isinstance(old, CutList) else CutList(**old)
    new_obj = new if isinstance(new, CutList) else CutList(**new)

    old_vector = behavior_vector_from_cutlist(old_obj)
    new_vector = behavior_vector_from_cutlist(new_obj)

    deltas = {key: new_vector[key] - old_vector[key] for key in old_vector}
    return deltas


def apply_deltas(base: BehaviorVector, deltas: Dict[str, float]) -> BehaviorVector:
    """Return a new BehaviorVector with attributed deltas applied."""
    data = base.model_dump()
    for key, delta in deltas.items():
        if key in data:
            data[key] += delta
    return BehaviorVector(**data)
