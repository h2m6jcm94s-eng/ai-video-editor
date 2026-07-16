# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Map narrative arc templates to concrete song time ranges.

Wave 6X.1 replaces the legacy RMS-energy anchoring with SongMeaning.narrative
labels produced by the Gemma section labeler.  When no SongMeaning is available
(e.g. cache from before Wave 5X, or analysis disabled), the module falls back to
the old energy-based mapper and logs the fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from shared_py.models import BeatGrid, EmotionLabel, SongMeaning
from reason_worker.narrative_arcs import ArcTemplate, ArcBeat


@dataclass
class ArcBeatAnchor:
    """A concrete time window for one narrative beat."""

    name: str
    start_s: float
    end_s: float
    energy_target: float
    emotion_target: EmotionLabel
    preferred_shots: List[str]
    text_archetype: str
    reason: str = ""

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)


_CRISIS_KEYWORDS = [
    "loss", "grief", "despair", "alone", "fall", "broken", "hurt", "regret",
    "empty", "hollow",
]

_VICTORY_KEYWORDS = [
    "triumph", "hope", "rebirth", "rise", "freedom", "light", "victory",
    "found", "home",
]


def _energy_at_time(time_s: float, energy_curve: List[float], duration_s: float) -> float:
    if not energy_curve or duration_s <= 0:
        return 0.5
    progress = max(0.0, min(1.0, time_s / duration_s))
    idx = min(int(progress * len(energy_curve)), len(energy_curve) - 1)
    return energy_curve[idx]


def find_lowest_valley_in_range(
    energy_curve: List[float],
    duration_s: float,
    start_pct: float,
    end_pct: float,
) -> float:
    """Return the time (in seconds) of the lowest energy valley in a percentage range."""
    if not energy_curve:
        return duration_s * (start_pct + end_pct) / 2

    start_s = duration_s * start_pct
    end_s = duration_s * end_pct
    best_t = (start_s + end_s) / 2
    best_energy = float("inf")
    for idx, energy in enumerate(energy_curve):
        t_s = duration_s * idx / max(1, len(energy_curve) - 1)
        if t_s < start_s - 1e-6 or t_s > end_s + 1e-6:
            continue
        if energy < best_energy:
            best_energy = energy
            best_t = t_s
    return best_t


def find_climax_peak(
    energy_curve: List[float],
    duration_s: float,
    start_pct: float,
    end_pct: float,
) -> float:
    """Return the time (in seconds) of the highest energy peak in a percentage range."""
    if not energy_curve:
        return duration_s * (start_pct + end_pct) / 2

    start_s = duration_s * start_pct
    end_s = duration_s * end_pct
    best_t = (start_s + end_s) / 2
    best_energy = float("-inf")
    for idx, energy in enumerate(energy_curve):
        t_s = duration_s * idx / max(1, len(energy_curve) - 1)
        if t_s < start_s - 1e-6 or t_s > end_s + 1e-6:
            continue
        if energy > best_energy:
            best_energy = energy
            best_t = t_s
    return best_t


def nearest_downbeat(time_s: float, downbeats: List[float]) -> float:
    """Snap a time to the nearest downbeat, returning the original time if none."""
    if not downbeats:
        return time_s
    return min(downbeats, key=lambda d: abs(d - time_s))


def _sentiment_score(lyric_sentiment: str, keywords: List[str]) -> int:
    """Count keyword substring matches in a sentiment phrase."""
    text = lyric_sentiment.lower()
    return sum(1 for kw in keywords if kw in text)


def _section_top_moods(
    section_moods: List["SectionMoodTags"], start_s: float, end_s: float
) -> List[Tuple[str, float]]:
    """Return the top moods of the section overlapping the given window."""
    for s in section_moods:
        if s.start_s <= start_s < s.end_s:
            return s.top_moods
    return []


def _find_first(
    sections: List["SongSectionSemantics"],
    predicate,
    default: Optional["SongSectionSemantics"] = None,
):
    for s in sections:
        if predicate(s):
            return s
    return default


def _energy_trough_section(
    song_meaning: SongMeaning,
    energy_curve: List[float],
    duration_s: float,
) -> "SongSectionSemantics":
    """Return the narrative section containing the lowest energy trough in the middle 60%."""
    sections = song_meaning.narrative.sections if song_meaning.narrative else []
    trough_t = find_lowest_valley_in_range(energy_curve, duration_s, 0.2, 0.8)
    for s in sections:
        if s.start_s <= trough_t < s.end_s:
            return s
    return sections[0] if sections else None


def _map_arc_to_song_rms(
    arc_template: ArcTemplate,
    energy_curve: List[float],
    beat_grid: BeatGrid,
    duration_s: float,
) -> List[ArcBeatAnchor]:
    """Legacy RMS-based arc anchoring (fallback when SongMeaning is unavailable)."""
    downbeats = sorted(b for b in beat_grid.downbeats if b <= duration_s)
    anchors: List[ArcBeatAnchor] = []

    valley_beats = {"CRISIS", "FALL", "RESOLUTION"}
    peak_beats = {"VICTORY", "CLIMAX", "GRIEF", "HOOK"}

    raw_times: dict = {}
    for beat in arc_template.beats:
        if beat.name in valley_beats:
            raw_times[beat.name] = find_lowest_valley_in_range(
                energy_curve, duration_s, beat.position_start_pct, beat.position_end_pct
            )
        elif beat.name in peak_beats:
            raw_times[beat.name] = find_climax_peak(
                energy_curve, duration_s, beat.position_start_pct, beat.position_end_pct
            )
        else:
            center = duration_s * (beat.position_start_pct + beat.position_end_pct) / 2
            raw_times[beat.name] = nearest_downbeat(center, downbeats)

    prev_end: Optional[float] = 0.0
    for i, beat in enumerate(arc_template.beats):
        next_time = raw_times.get(arc_template.beats[i + 1].name) if i + 1 < len(arc_template.beats) else None
        anchor = _anchor_beat_rms(
            beat,
            raw_times[beat.name],
            next_anchor_time_s=next_time,
            prev_anchor_time_s=prev_end,
            duration_s=duration_s,
            downbeats=downbeats,
        )
        anchors.append(anchor)
        prev_end = anchor.end_s

    return anchors


def _anchor_beat_rms(
    beat: ArcBeat,
    anchor_time_s: float,
    next_anchor_time_s: Optional[float],
    prev_anchor_time_s: Optional[float],
    duration_s: float,
    downbeats: List[float],
) -> ArcBeatAnchor:
    """Build an anchored window around a target time for one arc beat (RMS fallback)."""
    start_pct = beat.position_start_pct
    end_pct = beat.position_end_pct

    soft_start = duration_s * start_pct
    soft_end = duration_s * end_pct

    center = nearest_downbeat(anchor_time_s, downbeats)
    half_width = (soft_end - soft_start) / 2

    if prev_anchor_time_s is not None:
        soft_start = max(soft_start, prev_anchor_time_s)
    if next_anchor_time_s is not None:
        soft_end = min(soft_end, next_anchor_time_s)

    start_s = max(soft_start, min(center - half_width, soft_end - 0.5))
    end_s = max(start_s + 0.5, min(center + half_width, soft_end))

    start_s = max(0.0, min(duration_s, start_s))
    end_s = max(start_s + 0.5, min(duration_s, end_s))
    if downbeats:
        snapped_start = nearest_downbeat(start_s, downbeats)
        if snapped_start >= start_s - 0.5:
            start_s = snapped_start
        start_s = max(soft_start, start_s)

    return ArcBeatAnchor(
        name=beat.name,
        start_s=round(start_s, 3),
        end_s=round(end_s, 3),
        energy_target=beat.energy_target,
        emotion_target=beat.emotion_target,
        preferred_shots=beat.preferred_shots,
        text_archetype=beat.text_archetype,
        reason="rms_energy_fallback",
    )


_BEAT_KEYWORDS: dict[str, List[str]] = {
    "PEACE": ["calm", "quiet", "still", "soft", "gentle"],
    "HOPE": ["hope", "dream", "wish", "light", "begin"],
    "LONGING": ["longing", "yearn", "want", "miss", "wish"],
    "DREAM": ["dream", "hope", "promise", "future"],
    "WORLD": ["world", "place", "space", "around"],
    "RISE": ["rise", "climb", "grow", "build"],
    "CRACK": ["break", "crack", "split", "distance", "apart"],
    "CONFLICT": ["fight", "conflict", "tension", "clash", "struggle"],
    "FALL": ["fall", "drop", "lose", "fail", "break"],
    "LOSS": ["loss", "gone", "empty", "hollow", "missing"],
    "GRIEF": ["grief", "sorrow", "cry", "tears", "pain"],
    "ACCEPTANCE": ["accept", "let go", "peace", "release", "free"],
    "RESOLUTION": ["resolve", "peace", "calm", "after", "end"],
    "CLIMAX": ["peak", "climax", "high", "top"],
    "VICTORY": ["triumph", "win", "rise", "victory", "found"],
    "HOOK": ["start", "begin", "open", "hook"],
    "INCITING_INCIDENT": ["spark", "start", "turn", "incite"],
    "RISING_ACTION": ["chase", "run", "build", "rise", "tension"],
}


def _beat_section_score(beat: ArcBeat, section: "SongSectionSemantics") -> float:
    """Score how well a narrative section serves a given arc beat."""
    score = 0.0
    sentiment = section.lyric_sentiment.lower()

    # Keyword overlap between beat and lyric sentiment.
    keywords = _BEAT_KEYWORDS.get(beat.name, [])
    score += sum(0.5 for kw in keywords if kw in sentiment)

    # Story role alignment.
    role = section.story_role
    if beat.name in {"PEACE", "HOPE", "HOOK", "WORLD"} and role == "setup":
        score += 1.0
    if beat.name in {"RISE", "CONFLICT", "RISING_ACTION", "CRACK"} and role == "reveal":
        score += 1.0
    if beat.name in {"CLIMAX", "VICTORY"} and role == "climax":
        score += 1.5
    if beat.name in {"LOSS", "GRIEF", "FALL"} and role == "climax":
        score += 1.0
    if beat.name in {"ACCEPTANCE", "RESOLUTION"} and role == "resolution":
        score += 1.5

    # Emotional intensity alignment.
    if section.emotional_intensity >= 0.7 and beat.energy_target >= 0.7:
        score += 0.5
    if section.emotional_intensity <= 0.4 and beat.energy_target <= 0.4:
        score += 0.5

    # Gemma arc_beat_hint direct match.
    if section.arc_beat_hint and section.arc_beat_hint.upper() == beat.name.upper():
        score += 2.0

    return score


def _map_arc_to_song_semantic(
    arc_template: ArcTemplate,
    song_meaning: SongMeaning,
    energy_curve: List[float],
    beat_grid: BeatGrid,
    duration_s: float,
) -> List[ArcBeatAnchor]:
    """Map any arc template to narrative sections using semantic alignment."""
    narrative = song_meaning.narrative
    downbeats = sorted(b for b in beat_grid.downbeats if b <= duration_s)
    sections = list(narrative.sections) if narrative else []

    def _snap(t: float) -> float:
        return nearest_downbeat(t, downbeats)

    # Fallback to RMS if we don't have enough sections.
    if len(sections) < len(arc_template.beats):
        logger.warning(
            "arc_anchor_falling_back_to_rms",
            reason="too_few_narrative_sections",
            section_count=len(sections),
            beat_count=len(arc_template.beats),
        )
        return _map_arc_to_song_rms(arc_template, energy_curve, beat_grid, duration_s)

    # Greedy assignment: for each beat, pick the best remaining section.
    available = list(sections)
    assignments: List[tuple[ArcBeat, "SongSectionSemantics", float]] = []
    for beat in arc_template.beats:
        if not available:
            break
        scored = [(s, _beat_section_score(beat, s)) for s in available]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_section, best_score = scored[0]
        available.remove(best_section)
        assignments.append((beat, best_section, best_score))

    # Sort assignments by section start time to maintain chronological order.
    assignments.sort(key=lambda x: x[1].start_s)

    anchors: List[ArcBeatAnchor] = []
    for i, (beat, section, score) in enumerate(assignments):
        # Determine end time: next section start, or song end.
        if i + 1 < len(assignments):
            end_s = assignments[i + 1][1].start_s
        else:
            end_s = duration_s

        start_s = max(0.0, min(section.start_s, end_s - 0.5))
        end_s = max(start_s + 0.5, min(duration_s, end_s))

        anchors.append(
            ArcBeatAnchor(
                name=beat.name,
                start_s=round(_snap(start_s), 3),
                end_s=round(_snap(end_s), 3),
                energy_target=beat.energy_target,
                emotion_target=beat.emotion_target,
                preferred_shots=beat.preferred_shots,
                text_archetype=beat.text_archetype,
                reason=f"section_role={section.story_role},sentiment='{section.lyric_sentiment}',score={score:.1f}",
            )
        )

    logger.info(
        "arc_anchors_from_semantic",
        arc=arc_template.name,
        anchors=[(a.name, a.start_s, a.end_s, a.reason) for a in anchors],
    )
    return anchors


def map_arc_to_song(
    arc_template: ArcTemplate,
    energy_curve: List[float],
    beat_grid: BeatGrid,
    duration_s: float,
    song_meaning: Optional[SongMeaning] = None,
) -> List[ArcBeatAnchor]:
    """Map an arc template to concrete time windows on a song.

    Uses SongMeaning.narrative when available; otherwise falls back to RMS energy.
    """
    if song_meaning is None or song_meaning.narrative is None:
        logger.warning("arc_anchor_falling_back_to_rms", reason="song_meaning_missing")
        return _map_arc_to_song_rms(arc_template, energy_curve, beat_grid, duration_s)

    return _map_arc_to_song_semantic(
        arc_template, song_meaning, energy_curve, beat_grid, duration_s
    )


def anchor_for_time(anchors: List[ArcBeatAnchor], time_s: float) -> Optional[ArcBeatAnchor]:
    """Return the anchor whose window contains ``time_s``."""
    for anchor in anchors:
        if anchor.start_s <= time_s < anchor.end_s:
            return anchor
    if not anchors:
        return None
    return min(
        anchors,
        key=lambda a: abs((a.start_s + a.end_s) / 2 - time_s),
    )


# Import logger here to avoid circular import at module top.
from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("reason_worker.arc_anchor")
