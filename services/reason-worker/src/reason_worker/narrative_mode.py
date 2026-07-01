# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Narrative-mode dispatch for the Save-the-Cat assembler.

Decides whether a project should be edited as a coherent speech-driven story,
a high-energy trailer/music-video style cutlist, or left in the default ``off``
state (no narrative assembler overrides).
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

NarrativeMode = Literal["speech_coherent", "trailer_style", "off"]


def _numeric(value: Any) -> float:
    """Coerce a runtime signal value to float."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _get_signal(signals: Optional[Mapping[str, Any]], key: str) -> float:
    """Read a signal by key, supporting both dict and object attributes."""
    if signals is None:
        return 0.0
    if key in signals:
        return _numeric(signals[key])
    # Support snake_case and camelCase.
    camel = "".join(part.capitalize() if i else part for i, part in enumerate(key.split("_")))
    if camel in signals:
        return _numeric(signals[camel])
    return getattr(signals, key, 0.0)


def determine_narrative_mode(
    signals: Optional[Mapping[str, Any]] = None,
    transcripts: Optional[Sequence[Any]] = None,
) -> NarrativeMode:
    """Select the narrative assembler mode from content signals.

    Parameters
    ----------
    signals:
        Content signal mapping. Expected keys include ``speech_ratio``,
        ``avg_speech_segment_duration_s``, ``motion_density``, ``song_present``,
        and ``song_energy_mean``. May also be a ``ContentSignals`` object.
    transcripts:
        Optional sequence of transcript segments/dicts. Used as a tie-breaker
        when signal values are ambiguous.

    Returns
    -------
    ``"speech_coherent"`` when the content is dialogue-forward and segments are
    long enough to preserve meaning; ``"trailer_style"`` when the content is
    high-motion and music-driven; ``"off"`` when neither pattern is strong.
    """
    speech_ratio = _get_signal(signals, "speech_ratio")
    avg_speech_segment = _get_signal(signals, "avg_speech_segment_duration_s")
    motion_density = _get_signal(signals, "motion_density")
    song_present = _get_signal(signals, "song_present")
    song_energy = _get_signal(signals, "song_energy_mean")

    # Speech-coherent: lots of speech with long enough segments to follow.
    is_speech_coherent = speech_ratio >= 0.5 and avg_speech_segment >= 1.5

    # Trailer style: high motion and an energetic music bed.
    is_trailer_style = motion_density >= 0.5 and song_present >= 0.5 and song_energy >= 0.4

    # Tie-breakers from raw transcript presence.
    transcript_present = transcripts is not None and len(transcripts) > 0
    long_transcript_present = False
    if transcript_present:
        long_segments = 0
        for seg in transcripts:
            if seg is None:
                continue
            if isinstance(seg, Mapping):
                dur = _numeric(seg.get("duration_s", seg.get("end", 0.0) - seg.get("start", 0.0)))
            elif isinstance(seg, (list, tuple)) and len(seg) >= 2:
                dur = _numeric(seg[1]) - _numeric(seg[0])
            else:
                dur = 0.0
            if dur >= 2.0:
                long_segments += 1
        long_transcript_present = long_segments >= 2

    if is_speech_coherent and (not is_trailer_style or long_transcript_present):
        return "speech_coherent"
    if is_trailer_style and (not is_speech_coherent or not long_transcript_present):
        return "trailer_style"

    # Ambiguous cases default to off so the standard cutlist generator runs.
    return "off"
