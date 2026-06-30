# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Clip audio inclusion filter — decide which audio from user clips survives into the final mix.

The filter implements the behavior-vector audio policy. It is intentionally
simple for Phase 1: all supplied segments are assumed to be speech/dialogue
(detected by Whisper or the spectral fallback). Non-speech/SFX detection is
reserved for Phase 2 when full clip segmentation is added.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from shared_py.models import BehaviorVector

if TYPE_CHECKING:
    from reason_worker.audio_scoring import WordTimestamp


@dataclass
class AudioSegment:
    """A candidate audio segment from a user clip."""

    start_s: float
    end_s: float
    text: Optional[str] = None
    is_speech: bool = True
    # 0-1 combined importance (speech quality, phrase match, loudness, etc.)
    importance: float = 0.0
    # 0-1 iconic/quote score (populated by the iconic quote detector in PR-3)
    iconic_score: float = 0.0
    # Optional source clip id for debugging/telemetry
    source_clip_id: Optional[str] = None
    # Raw scores for transparency
    scores: dict = field(default_factory=dict)
    # Whisper word-level timestamps preserved for caption burning.
    words: List["WordTimestamp"] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)


def filter_clip_audio_for_inclusion(
    segments: List[AudioSegment],
    behavior: BehaviorVector,
) -> List[AudioSegment]:
    """Return the subset of clip audio segments that should be heard in the mix.

    Rules (applied in order):
      1. Non-speech is dropped when sfx_mute_aggressiveness > 0.5.
      2. Segments below clip_audio_min_importance are dropped.
      3. Strategy-specific filters:
         - "iconic_only": keep only high-iconic-score segments.
         - "speech_only": keep only speech segments.
         - "never": drop everything.
         - "always": keep everything that passed the importance gate.
    """
    survivors: List[AudioSegment] = []

    for seg in segments:
        if not seg.is_speech and behavior.sfx_mute_aggressiveness > 0.5:
            continue

        if seg.importance < behavior.clip_audio_min_importance:
            continue

        strategy = behavior.clip_audio_inclusion_strategy
        if strategy == "iconic_only":
            # Aligned with iconic_quotes ICONIC_INCLUSION_THRESHOLD (0.45).
            if seg.iconic_score < 0.45:
                continue
        elif strategy == "speech_only":
            if not seg.is_speech:
                continue
        elif strategy == "never":
            continue
        # "always" passes through after importance gate.

        survivors.append(seg)

    return survivors
