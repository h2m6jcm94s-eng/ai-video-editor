# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Density-driven slot generation.

Separates cut DENSITY (how often cuts happen) from cut PLACEMENT (where they
land). The behavior vector predicts density; beat grid and energy curve provide
placement candidates. This replaces the previous "one slot per beat" loop that
forced excessive slot counts and clip repeats.
"""

from typing import List, Optional

import sys
import os

# Add shared-py to path when running this file directly.
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
shared_py_path = os.path.join(repo_root, "shared-py", "src")
if shared_py_path not in sys.path:
    sys.path.insert(0, shared_py_path)

from shared_py.models import BeatGrid, BehaviorVector, Slot


# No source window should be asked to cover more than this many seconds without a
# cut. Longer slots force the compiler to pad/loop or display static footage,
# which triggers the no_frozen_frames gate.
MAX_SLOT_GAP_S = 8.0


def _energy_at_time(time_s: float, energy_curve: List[float], content_end: float) -> float:
    """Sample the energy curve at a given time."""
    if not energy_curve or content_end <= 0:
        return 0.5
    progress = max(0.0, min(1.0, time_s / content_end))
    idx = min(int(progress * len(energy_curve)), len(energy_curve) - 1)
    return energy_curve[idx]


def weighted_sample_with_min_gap(
    candidates: List[float],
    weights: List[float],
    n: int,
    min_gap: float,
) -> List[float]:
    """Greedy weighted sampling with a minimum spacing constraint.

    Picks the highest-weight candidate, then removes all candidates within
    ``min_gap`` seconds. Repeats until ``n`` candidates are selected or no
    candidates remain. Returns the selected times sorted ascending.
    """
    if not candidates or n <= 0:
        return []

    if len(candidates) != len(weights):
        raise ValueError("candidates and weights must have the same length")

    # Sort by candidate time so gap checks are simple.
    indexed = sorted(enumerate(candidates), key=lambda x: x[1])
    sorted_candidates = [c for _, c in indexed]
    sorted_weights = [weights[i] for i, _ in indexed]

    available = [True] * len(sorted_candidates)
    selected: List[float] = []

    while len(selected) < n and any(available):
        best_idx: Optional[int] = None
        best_weight = -1.0
        for i, (candidate, weight, avail) in enumerate(
            zip(sorted_candidates, sorted_weights, available)
        ):
            if avail and weight > best_weight:
                best_weight = weight
                best_idx = i

        if best_idx is None:
            break

        selected.append(sorted_candidates[best_idx])
        # Exclude neighbors that would violate the minimum gap.
        chosen_time = sorted_candidates[best_idx]
        for i in range(len(sorted_candidates)):
            if available[i] and abs(sorted_candidates[i] - chosen_time) < min_gap:
                available[i] = False

    return sorted(selected)


def generate_slots_adaptive(
    beat_grid: BeatGrid,
    song_duration: float,
    behavior: BehaviorVector,
    energy_curve: List[float],
    content_end: float,
) -> List[Slot]:
    """Generate slot skeletons from a target cut density and beat candidates.

    The returned ``Slot`` objects contain only structural fields (start, duration,
    index). Callers are expected to fill in section, transitions, effects, and
    shot-type metadata afterward.
    """
    effective_duration = max(0.0, min(song_duration, content_end))
    if effective_duration <= 0 or not beat_grid.beats:
        return []

    # 1. Target slot count from behavior.
    target_cuts = max(1, round(behavior.cut_density_per_sec * effective_duration))

    # 2. Build beat candidates within the content window.
    # Always include t=0 so the cutlist starts at the beginning.
    beat_candidates = [b for b in beat_grid.beats if 0 <= b < content_end]
    candidates = [0.0] + [b for b in beat_candidates if b > 0]

    if len(candidates) <= 1:
        # Degenerate case: only one candidate. Return a single full-duration slot.
        return [
            Slot(
                index=0,
                start_s=0.0,
                duration_s=effective_duration,
                beat_index=0,
                section="intro",
                transition_in="hard_cut",
                transition_out="hard_cut",
                target_shot_type="medium",
                subject_hint="",
                motion_hint="static",
                energy_level=0.5,
            )
        ]

    # 3. Weight candidates by energy curve.
    weights = [_energy_at_time(t, energy_curve, content_end) for t in candidates]
    # Ensure a minimum weight so silence/intro sections still get cuts.
    weights = [max(0.1, w) for w in weights]

    # 4. Boost downbeat candidates.
    downbeat_set = set(round(d, 3) for d in (beat_grid.downbeats or []))
    for i, t in enumerate(candidates):
        if any(abs(t - d) < 0.02 for d in downbeat_set):
            weights[i] *= 2.5

    # 5. Force the cutlist to start at t=0 so the video begins immediately.
    # Find the 0.0 candidate (always inserted above) and give it the highest weight.
    for i, t in enumerate(candidates):
        if abs(t) < 1e-6:
            weights[i] = max(weights) * 10.0

    # 5. Minimum gap: at least half the mean slot duration, bounded.
    min_gap = max(0.5, min(4.0, behavior.slot_duration_mean_s * 0.5))

    # 6. Sample cut positions.
    target_cuts = min(target_cuts, len(candidates))
    cut_positions = weighted_sample_with_min_gap(candidates, weights, target_cuts, min_gap)

    if not cut_positions:
        cut_positions = [0.0]

    # 6b. Enforce a maximum gap between cuts so no slot is forced to cover
    # footage longer than a typical clip can provide without padding. Insert
    # additional cuts at the beat candidate nearest to ``gap_start + max_gap``
    # (i.e., the latest cut that still keeps the first sub-gap within the cap).
    max_gap = max(min_gap * 2, min(MAX_SLOT_GAP_S, behavior.slot_duration_mean_s * 2))
    extra_cuts: List[float] = []
    all_positions = sorted(set([0.0] + list(cut_positions) + [content_end]))
    for i in range(len(all_positions) - 1):
        gap_start = all_positions[i]
        gap_end = all_positions[i + 1]
        while gap_end - gap_start > max_gap + 1e-6:
            target_t = gap_start + max_gap
            # Find the candidate closest to the target, avoiding the edges.
            best_t = None
            best_dist = float("inf")
            for t in candidates:
                if gap_start + 0.1 < t < gap_end - 0.1 and abs(t - gap_start) > 0.3:
                    dist = abs(t - target_t)
                    if dist < best_dist:
                        best_dist = dist
                        best_t = t
            if best_t is None:
                # No beat candidate usable; fall back to the exact target time.
                best_t = target_t
            insert_t = round(best_t, 3)
            extra_cuts.append(insert_t)
            gap_start = insert_t
    if extra_cuts:
        cut_positions = sorted(set(cut_positions) | set(extra_cuts))

    # 7. Build slot skeletons; durations are gaps between consecutive cuts.
    slots: List[Slot] = []
    for i, start_s in enumerate(cut_positions):
        end_s = cut_positions[i + 1] if i + 1 < len(cut_positions) else content_end
        duration_s = max(0.5, end_s - start_s)
        slots.append(
            Slot(
                index=i,
                start_s=start_s,
                duration_s=duration_s,
                beat_index=0,  # Updated by the beat snap pass.
                section="intro",
                transition_in="hard_cut",
                transition_out="hard_cut",
                target_shot_type="medium",
                subject_hint="",
                motion_hint="static",
                energy_level=_energy_at_time(start_s, energy_curve, content_end),
            )
        )

    return slots
