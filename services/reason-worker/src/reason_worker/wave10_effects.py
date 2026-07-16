# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Wave 10 mood-driven effect additions.

Adds dedicated-effect-module effects to the cutlist when the ``use_wave_10_effects``
feature flag is enabled:

- ``zoom_punch_in`` aligned to kick drum events on high-energy slots.
- ``vignette`` on CRISIS / VICTORY narrative beats.
- ``hm_mvgd_hm`` on the strongest available slot.
- ``chromatic_aberration`` as a tension accent on aggressive arc beats.

All additions respect the per-slot two-effect cap with a deterministic priority.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from shared_py.feature_tracer import FeatureTracer
from shared_py.models import (
    AdaptiveFeatures,
    ChromaticAberrationParams,
    CutList,
    Effect,
    HmMvgdHmParams,
    MusicEventGrid,
    Slot,
    VignetteParams,
    ZoomPunchInParams,
)

# Lower number = higher priority, kept first when the two-effect cap is applied.
_EFFECT_PRIORITY: Dict[str, int] = {
    "vignette": 1,
    "hm_mvgd_hm": 2,
    "zoom_punch_in": 3,
    "chromatic_aberration": 4,
    "color_pop": 5,
    "shake": 6,
    "glitch": 7,
    "focus_pull": 8,
    "film_grain": 9,
}

# Arc-beat emotions that receive a chromatic-aberration accent.
_AGGRESSIVE_BEATS: Set[str] = {"anger", "triumph", "tension", "fear"}


def _apply_effect_cap(slot: Slot) -> None:
    """Keep only the two highest-priority effects on a slot."""
    effects = slot.effects or []
    effects.sort(key=lambda e: _EFFECT_PRIORITY.get(e.type, 99))
    slot.effects = effects[:2]


def apply_wave_10_effects(
    cutlist: CutList,
    music_event_grid: Optional[MusicEventGrid],
    features: Optional[AdaptiveFeatures],
) -> None:
    """Mutate ``cutlist`` to inject Wave 10 effects when the feature is on."""
    if not features or not features.use_wave_10_effects:
        return

    with FeatureTracer("wave10_effects") as ft:
        added_types: List[str] = []
        kicks = (
            getattr(music_event_grid, "kick_times", None) or []
            if music_event_grid
            else []
        )

        # 1. Zoom punch-ins locked to kick drums on high-energy slots.
        kick_slots: Set[int] = set()
        for slot in cutlist.slots:
            # Use a low threshold because narrative arc beats may have lowered
            # the slot's target energy while the underlying music (kick) is still
            # strong enough to deserve a punch-in.
            if slot.energy_level < 0.3:
                continue
            for kick in kicks:
                if slot.start_s <= kick < slot.start_s + slot.duration_s:
                    if slot.index in kick_slots:
                        continue
                    # Replace any existing downbeat zoom with a kick-aligned one.
                    slot.effects = [e for e in slot.effects if e.type != "zoom_punch_in"]
                    slot.effects.append(
                        Effect(
                            type="zoom_punch_in",
                            start_s=kick,
                            duration_s=min(0.25, slot.duration_s),
                            params=ZoomPunchInParams(
                                target_scale=1.2,
                                duration_ms=200,
                                easing="easeOut",
                            ).model_dump(by_alias=True),
                        )
                    )
                    kick_slots.add(slot.index)
                    added_types.append("zoom_punch_in")
                    break

        # 2. Vignette on CRISIS / VICTORY narrative beats.
        for slot in cutlist.slots:
            story_beat = getattr(slot, "story_beat", None)
            if story_beat in {"CRISIS", "VICTORY"}:
                slot.effects.append(
                    Effect(
                        type="vignette",
                        start_s=slot.start_s,
                        duration_s=slot.duration_s,
                        params=VignetteParams(
                            intensity=0.45,
                        ).model_dump(by_alias=True),
                    )
                )
                added_types.append("vignette")
                break

        # 3. HM-MVGD-HM colour grade on the strongest slot that has room.
        sorted_by_energy = sorted(
            cutlist.slots,
            key=lambda s: s.energy_level,
            reverse=True,
        )
        for slot in sorted_by_energy:
            slot.effects.append(
                Effect(
                    type="hm_mvgd_hm",
                    start_s=slot.start_s,
                    duration_s=slot.duration_s,
                    params=HmMvgdHmParams(
                        strength=0.6,
                        warmth=0.1,
                        tint=0.0,
                    ).model_dump(by_alias=True),
                )
            )
            added_types.append("hm_mvgd_hm")
            break

        # 4. Chromatic aberration accent on aggressive high-energy arc beats.
        for slot in cutlist.slots:
            if slot.energy_level < 0.75:
                continue
            emotion_target = getattr(slot, "arc_beat_emotion_target", None) or ""
            if emotion_target in _AGGRESSIVE_BEATS:
                slot.effects.append(
                    Effect(
                        type="chromatic_aberration",
                        start_s=slot.start_s,
                        duration_s=min(1.0, slot.duration_s),
                        params=ChromaticAberrationParams(
                            shift_x=4,
                            shift_y=0,
                            intensity=0.35,
                        ).model_dump(by_alias=True),
                    )
                )
                added_types.append("chromatic_aberration")
                break

        # Enforce the two-effect cap after all mood-driven additions.
        for slot in cutlist.slots:
            _apply_effect_cap(slot)

        ft.signature(f"added={','.join(sorted(set(added_types)))}")
        ft.real()
