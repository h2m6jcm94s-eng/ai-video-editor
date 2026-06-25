#!/usr/bin/env python3
"""Heuristic scorer for AI-video-editor cutlists.

Scores are in [0, 1]. The scorer is intentionally cheap (no LLM calls) so it can
be used inside an iterative edit-improvement loop. It measures editing qualities
that are easy to compute from the cutlist JSON:

- pacing: shot-duration variety and avoidance of extreme durations
- sync: slot start times aligning to the song tempo
- diversity: reuse of clips and shot types
- energy_arc: whether energy builds and releases over time
- transition_variety: use of more than just hard cuts
"""

from __future__ import annotations

import math
from typing import Any


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def _cv(values: list[float]) -> float:
    m = _mean(values)
    if m == 0:
        return 0.0
    return _std(values) / m


def pacing_score(slots: list[dict[str, Any]]) -> float:
    """Reward moderate duration variety; penalize boring uniformity and jarring chaos."""
    durations = [s.get("durationS", 0.0) for s in slots]
    if not durations:
        return 0.0

    cv = _cv(durations)
    # Ideal coefficient of variation for engaging short-form edits.
    ideal_cv = 0.5
    cv_penalty = abs(cv - ideal_cv)

    # Penalize shots that are too short or too long.
    extreme_penalty = 0.0
    for d in durations:
        if d < 0.4:
            extreme_penalty += 0.25
        elif d > 8.0:
            extreme_penalty += 0.15
    extreme_penalty = min(extreme_penalty, 1.0)

    return _clamp(1.0 - cv_penalty - extreme_penalty)


def sync_score(slots: list[dict[str, Any]], tempo_bpm: float) -> float:
    """Reward slot start times landing close to beat grid intervals."""
    if tempo_bpm <= 0 or len(slots) < 2:
        return 0.5

    beat_interval = 60.0 / tempo_bpm
    if beat_interval <= 0:
        return 0.5

    errors = []
    for s in slots:
        start = s.get("startS", 0.0)
        phase = (start % beat_interval) / beat_interval
        # Distance to nearest beat, normalized to [0, 0.5].
        err = min(phase, 1.0 - phase)
        errors.append(err)

    mean_err = _mean(errors)
    # A mean error of 0 -> score 1; 0.25 (halfway between beats) -> score 0.
    return _clamp(1.0 - 4.0 * mean_err)


def diversity_score(slots: list[dict[str, Any]]) -> float:
    """Reward using many different clips and shot types; penalize repetition."""
    n = len(slots)
    if n == 0:
        return 0.0

    selected = [s.get("selectedClipId") for s in slots]
    unique_clips = len(set(x for x in selected if x))
    clip_diversity = unique_clips / n

    shot_types = [s.get("targetShotType") for s in slots]
    unique_shots = len(set(x for x in shot_types if x))
    shot_diversity = unique_shots / n

    # Penalize immediately repeated clips.
    repeats = sum(
        1
        for i in range(1, n)
        if selected[i] and selected[i - 1] and selected[i] == selected[i - 1]
    )
    repeat_penalty = min(repeats / max(n - 1, 1), 1.0)

    return _clamp(0.6 * clip_diversity + 0.3 * shot_diversity + 0.1 * (1.0 - repeat_penalty))


def energy_arc_score(slots: list[dict[str, Any]], energy_curve: list[float] | None = None) -> float:
    """Reward an energy curve that rises toward the middle/end and has variation."""
    n = len(slots)
    if n == 0:
        return 0.0

    levels = [s.get("energyLevel", 0.5) for s in slots]
    if energy_curve and len(energy_curve) == n:
        # Compare slot energy to the song's energy curve (Pearson-ish correlation).
        m_levels = _mean(levels)
        m_curve = _mean(energy_curve)
        num = sum((l - m_levels) * (c - m_curve) for l, c in zip(levels, energy_curve))
        den = math.sqrt(
            sum((l - m_levels) ** 2 for l in levels) * sum((c - m_curve) ** 2 for c in energy_curve)
        )
        correlation = num / den if den else 0.0
        return _clamp(0.5 + 0.5 * correlation)

    # No energy curve: reward a simple "ramp up" arc.
    expected = [0.3 + 0.6 * (i / max(n - 1, 1)) for i in range(n)]
    mse = sum((l - e) ** 2 for l, e in zip(levels, expected)) / n
    # MSE of 0 -> 1, 0.25 -> 0.
    return _clamp(1.0 - 4.0 * mse)


def transition_variety_score(slots: list[dict[str, Any]]) -> float:
    """Reward use of varied transitions; penalize all-hard-cut edits."""
    n = len(slots)
    if n == 0:
        return 0.0

    transitions = []
    for s in slots:
        t_in = s.get("transitionIn", "hard_cut")
        t_out = s.get("transitionOut", "hard_cut")
        transitions.extend([t_in, t_out])

    unique = len(set(transitions))
    total = len(transitions)
    variety = unique / total if total else 0.0

    hard_cut_ratio = transitions.count("hard_cut") / total if total else 0.0
    # Some hard cuts are fine; all hard cuts is boring.
    hard_penalty = max(0.0, hard_cut_ratio - 0.5)

    return _clamp(variety + (1.0 - hard_penalty) - 0.5)


def score_cutlist(cutlist: dict[str, Any]) -> dict[str, Any]:
    """Return a dict of component scores and a weighted total score."""
    slots = cutlist.get("slots", []) if isinstance(cutlist, dict) else []
    globals_ = cutlist.get("globals", {}) if isinstance(cutlist, dict) else {}
    tempo_bpm = float(globals_.get("tempoBpm", 0.0) or 0.0)
    energy_curve = globals_.get("energyCurve") or []

    scores = {
        "pacing": pacing_score(slots),
        "sync": sync_score(slots, tempo_bpm),
        "diversity": diversity_score(slots),
        "energy_arc": energy_arc_score(slots, energy_curve),
        "transition_variety": transition_variety_score(slots),
    }

    weights = {
        "pacing": 0.25,
        "sync": 0.20,
        "diversity": 0.20,
        "energy_arc": 0.20,
        "transition_variety": 0.15,
    }

    total = sum(weights[k] * scores[k] for k in scores)
    scores["total"] = _clamp(total)
    return scores


def format_score(score: dict[str, float]) -> str:
    parts = [f"{k}={v:.2f}" for k, v in score.items() if k != "total"]
    return f"total={score.get('total', 0.0):.2f} ({', '.join(parts)})"


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python scripts/cutlist_scorer.py <cutlist.json>")
        sys.exit(1)

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(format_score(score_cutlist(data)))
