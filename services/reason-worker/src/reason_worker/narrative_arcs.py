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

from shared_py.models import EmotionLabel, SongMeaning, SectionMoodTags


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
    type: Literal["trailer", "tragic", "romantic", "classical"]
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


# Romantic arc: longing, connection, beauty, ache.  Designed for love songs,
# bittersweet ballads, and emotional character pieces.
ROMANTIC_ARC = ArcTemplate(
    name="Romantic",
    type="romantic",
    beats=[
        ArcBeat(
            name="PEACE",
            emotion_target="calm",
            preferred_shots=["wide", "medium"],
            energy_target=0.3,
            motion_target="slow",
            text_archetype="the quiet before",
            position_start_pct=0.0,
            position_end_pct=0.20,
        ),
        ArcBeat(
            name="LONGING",
            emotion_target="joy",
            preferred_shots=["medium", "close_up"],
            energy_target=0.4,
            motion_target="slow",
            text_archetype="the wish",
            position_start_pct=0.20,
            position_end_pct=0.40,
        ),
        ArcBeat(
            name="CRACK",
            emotion_target="tension",
            preferred_shots=["close_up", "medium"],
            energy_target=0.5,
            motion_target="medium",
            text_archetype="the distance",
            position_start_pct=0.40,
            position_end_pct=0.55,
        ),
        ArcBeat(
            name="LOSS",
            emotion_target="grief",
            preferred_shots=["close_up", "extreme_close_up"],
            energy_target=0.3,
            motion_target="still",
            text_archetype="the ache",
            position_start_pct=0.55,
            position_end_pct=0.75,
        ),
        ArcBeat(
            name="ACCEPTANCE",
            emotion_target="awe",
            preferred_shots=["wide", "medium"],
            energy_target=0.5,
            motion_target="slow",
            text_archetype="the letting go",
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


_TRAGIC_KEYWORDS = [
    "loss", "grief", "sorrow", "broken", "alone", "fall", "nostalgic",
    "despair", "empty", "hollow", "hurt", "devastated", "shattered",
    "mourning", "bereaved", "anguish", "torment",
]

# Milder melancholy keywords that should push toward ROMANTIC rather than TRAGIC.
_ROMANTIC_KEYWORDS = [
    "regret", "apologetic", "sorry", "miss", "ache", "yearn", "wish",
    "surrender", "peaceful", "bittersweet", "longing", "love", "devotion",
    "intimate", "tender",
]

_ROMANTIC_MOODS = {"romantic", "peaceful", "nostalgic", "melancholic"}
_TRIUMPHANT_MOODS = {"triumphant", "uplifting", "hopeful"}
_TRAILER_MOODS = {"aggressive", "chaotic", "furious", "triumphant", "dark", "tense"}
_TRAILER_GENRES = {"hip-hop", "trap", "electronic", "dubstep", "rock", "metal"}


def _section_top_mood_names(
    section_moods: List[SectionMoodTags], start_s: float, end_s: float
) -> List[str]:
    """Return the top mood tag names for the section overlapping the window."""
    for s in section_moods:
        if s.start_s <= start_s < s.end_s:
            return [m for m, _ in s.top_moods]
    return []


def _arc_from_song_meaning(
    song_meaning: SongMeaning, energy_curve: List[float]
) -> Optional[ArcTemplate]:
    """Select an arc primarily from SongMeaning semantics.

    Song meaning is the authoritative signal for emotional arc. Reference style
    and energy curve are used only when the song's own narrative is ambiguous.
    """
    if not song_meaning.narrative:
        return None
    sections = song_meaning.narrative.sections
    if not sections:
        return None

    section_moods = song_meaning.section_moods or []

    # Pair each narrative section with its overlapping CLAP mood tag block.
    moods_for_section: List[List[Tuple[str, float]]] = []
    for s in sections:
        matched: List[Tuple[str, float]] = []
        for sm in section_moods:
            if sm.start_s <= s.start_s < sm.end_s:
                matched = sm.top_moods
                break
        moods_for_section.append(matched)

    # 1. Tragic: strong language of loss/grief/longing in lyric sentiment.
    tragic_scores: List[int] = []
    for s in sections:
        text = s.lyric_sentiment.lower()
        score = sum(2 for kw in _TRAGIC_KEYWORDS if kw in text)
        score += sum(1 for kw in _ROMANTIC_KEYWORDS if kw in text)
        tragic_scores.append(score)
    strong_tragic_sections = sum(1 for sc in tragic_scores if sc >= 2)
    if strong_tragic_sections >= 1 and max(tragic_scores, default=0) >= 4:
        return TRAGIC_ARC

    # 2. Trailer: high-energy + dramatic drop + dark/aggressive/triumphant moods.
    #    Checked before Romantic so that aggressive/dark energy wins over surface
    #    romantic tags (e.g., a hip-hop track with romantic moods but furious
    #    drops still edits as a trailer).
    has_drop = _has_dramatic_drop(energy_curve)
    max_intensity = max((s.emotional_intensity for s in sections), default=0.0)

    dark_aggressive_hits = 0
    for top_moods, s in zip(moods_for_section, sections):
        if not top_moods:
            continue
        # Top-1 mood is a strong trailer signal.
        top1, top1_score = top_moods[0]
        if top1 in _TRAILER_MOODS and top1_score >= 0.25:
            dark_aggressive_hits += 1
            continue
        # Top-2 mood can count if it is loud enough and the section is intense.
        if len(top_moods) >= 2:
            top2, top2_score = top_moods[1]
            if top2 in _TRAILER_MOODS and top2_score >= 0.25 and s.emotional_intensity >= 0.6:
                dark_aggressive_hits += 1
                continue

    dark_aggressive_ratio = dark_aggressive_hits / max(1, len(sections))

    genre_top = (song_meaning.genre_tags or [("", 0.0)])[0][0].lower()
    genre_is_trailer = genre_top in _TRAILER_GENRES

    if (
        has_drop
        and max_intensity >= 0.7
        and (dark_aggressive_ratio >= 0.15 or (genre_is_trailer and dark_aggressive_hits >= 1))
    ):
        return TRAILER_ARC

    # 3. Romantic: peaceful/nostalgic/melancholic/romantic moods OR a sustained
    #    longing/devotion sentiment, but not enough tragedy/darkness to claim
    #    TRAGIC/TRAILER.
    romantic_hits = 0
    for top_moods in moods_for_section:
        names = {m for m, _ in top_moods}
        if names & _ROMANTIC_MOODS:
            romantic_hits += 1
    romantic_ratio = romantic_hits / max(1, len(sections))

    romantic_sentiment_hits = sum(
        1
        for s in sections
        if any(kw in s.lyric_sentiment.lower() for kw in ("longing", "love", "devotion", "intimate", "tender"))
        or any(kw in s.lyric_sentiment.lower() for kw in _ROMANTIC_KEYWORDS)
    )
    if romantic_ratio >= 0.4 or romantic_sentiment_hits >= 2:
        return ROMANTIC_ARC

    return None


def select_arc(
    energy_curve: List[float],
    style_analysis: Optional[Dict[str, Any]] = None,
    key: Optional[str] = None,
    song_meaning: Optional[SongMeaning] = None,
) -> ArcTemplate:
    """Pick the best arc template for a song + reference.

    Uses SongMeaning.narrative + section_moods when available. Falls back to
    energy curve / reference style when SongMeaning is missing.

    - Tragic when lyric sentiment speaks of loss/grief/brokenness.
    - Romantic when CLAP moods are peaceful/nostalgic/melancholic/romantic or
      the lyric sentiment is dominated by longing/devotion.
    - Trailer when energy drops dramatically AND the song carries dark,
      aggressive, or intensely triumphant moods.
    - Classical as the safe default.
    """
    if song_meaning is not None:
        arc = _arc_from_song_meaning(song_meaning, energy_curve)
        if arc is not None:
            return arc

    # Fallback heuristics when SongMeaning is missing or ambiguous.
    has_drop = _has_dramatic_drop(energy_curve)
    if has_drop and _reference_motion_ratio(style_analysis) > 0.6:
        return TRAILER_ARC
    if _is_minor_key(key) and _reference_long_hold_ratio(style_analysis) > 0.4:
        return TRAGIC_ARC

    return CLASSICAL_ARC
