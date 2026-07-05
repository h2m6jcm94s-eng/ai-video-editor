# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Emphasis-word picker for lyric and dialogue captions.

Wave 9 backfill: identifies the handful of words per phrase that deserve a
visual pop (scale + colour) without requiring a full LLM pass. The picker is
designed to fail open — if no clear emphasis targets exist, it returns an
empty list so captions still render normally.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Set

from shared_py.models import WordTiming


# Words that are too generic to emphasize even when repeated.
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall",
    "can", "need", "dare", "ought", "used", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "and",
    "but", "or", "yet", "so", "if", "because", "although", "though",
    "while", "where", "when", "that", "which", "who", "whom", "whose",
    "what", "this", "these", "those", "i", "you", "he", "she", "it",
    "we", "they", "me", "him", "her", "us", "them", "my", "your",
    "his", "its", "our", "their", "am", "oh", "ah", "uh", "um",
}


def _normalise(text: str) -> str:
    """Lower-case and strip trailing punctuation for duplicate counting."""
    return re.sub(r"[^a-z0-9']+$", "", text.lower())


def score_words(
    words: List[WordTiming],
    energy: float = 0.5,
) -> Dict[str, float]:
    """Return a score map for every normalised word in the phrase."""
    scores: Dict[str, float] = {}
    if not words:
        return scores

    counts = Counter(_normalise(w.text) for w in words if _normalise(w.text))

    for w in words:
        norm = _normalise(w.text)
        if not norm or norm in _STOPWORDS:
            continue
        score = 0.0
        # Repeated words are likely hook/chorus material.
        if counts[norm] > 1:
            score += 1.0 + 0.3 * (counts[norm] - 1)
        # Medium-length content words feel more important than tiny ones.
        if 4 <= len(norm) <= 10:
            score += 0.5
        # High-energy moments emphasise punchy words.
        if energy >= 0.75 and len(norm) <= 6:
            score += 0.4
        scores[norm] = score

    return scores


def pick_emphasis_words(
    words: List[WordTiming],
    energy: float = 0.5,
    max_emphasis: int = 3,
) -> Set[str]:
    """Return the normalised texts of the words that should pop visually."""
    scores = score_words(words, energy=energy)
    if not scores:
        return set()
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    cutoff = max(0.8, ranked[0][1] * 0.5) if ranked else 0.8
    chosen = {word for word, score in ranked if score >= cutoff}
    # Always cap so the effect stays cinematic, not spammy.
    if len(chosen) > max_emphasis:
        chosen = {word for word, _ in ranked[:max_emphasis]}
    return chosen


def mark_emphasis_in_words(
    words: List[WordTiming],
    energy: float = 0.5,
    max_emphasis: int = 3,
) -> List[WordTiming]:
    """Return a copy of ``words`` with ``is_emphasis`` set on chosen words."""
    chosen = pick_emphasis_words(words, energy=energy, max_emphasis=max_emphasis)
    out: List[WordTiming] = []
    for w in words:
        out.append(
            WordTiming(
                text=w.text,
                start_s=w.start_s,
                end_s=w.end_s,
                is_emphasis=_normalise(w.text) in chosen,
            )
        )
    return out
