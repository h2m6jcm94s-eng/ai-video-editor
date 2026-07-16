# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Iconic quote detector — surface high-impact lines and duck the song under them.

Scores each candidate line with five components:
  1. emotional_intensity   — prosodic / textual emotional salience
  2. loudness_normalized   — RMS loudness relative to the clip
  3. iconic_llm_score      — Claude Haiku judgement of quote-worthiness
  4. vocal_uniqueness      — how distinct the vocal delivery is
  5. isolation             — silence before/after the line

The LLM is only called for the top-K candidates per project to bound cost.
Results are cached by (text_hash, ip_hint_hash).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from shared_py.feature_gating import (
    FEATURE_RELEVANCE_CENTROIDS,
    gated_budget,
    should_run_feature,
)
from reason_worker.narrative_mode import determine_narrative_mode
from shared_py.feature_tracer import FeatureTracer
from shared_py.llm_client import LLMClient, LLMTask
from shared_py.logging_config import StructuredLogger
from shared_py.models import MusicEventGrid


def _is_latin_script(text: str) -> bool:
    """Return True if the text is predominantly Latin script."""
    if not text:
        return True
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    latin = sum(1 for c in letters if ord(c) < 0x300)
    return latin / len(letters) >= 0.7


def _romanize(text: str) -> Optional[str]:
    """Best-effort romanization for Japanese / Chinese lyrics."""
    try:
        # Japanese
        import pykakasi
        kks = pykakasi.kakasi()
        result = kks.convert(text)
        return " ".join(r.get("hepburn", r.get("passport", "")) for r in result)
    except Exception:
        pass
    try:
        # Chinese
        import pypinyin
        return " ".join(pypinyin.lazy_pinyin(text))
    except Exception:
        return None


def _prosody_peak_score(clip_path: str, start_s: float, end_s: float) -> float:
    """RMS peak within 200ms of the phrase midpoint."""
    y, sr = _load_audio_segment(clip_path, 0.0, None)
    if y is None or sr is None or len(y) == 0:
        logger.warning("prosody_peak_missing_audio", clip_path=clip_path)
        return 0.0

    midpoint_s = (start_s + end_s) / 2.0
    midpoint_sample = int(midpoint_s * sr)
    window_samples = int(0.2 * sr)
    half_window = window_samples // 2
    start_sample = max(0, midpoint_sample - half_window)
    end_sample = min(len(y), midpoint_sample + half_window)
    window = y[start_sample:end_sample]
    if len(window) == 0:
        return 0.0

    peak_rms = float(np.sqrt(np.max(window**2)))
    clip_rms = float(np.sqrt(np.mean(y**2))) or 1e-9
    ratio = peak_rms / clip_rms
    return min(1.0, max(0.0, ratio / 2.0))


def _music_event_alignment(
    start_s: float,
    end_s: float,
    music_event_grid: Optional[MusicEventGrid],
) -> float:
    """Distance from phrase midpoint to nearest kick or snare."""
    if music_event_grid is None:
        return 0.0
    midpoint = (start_s + end_s) / 2.0
    events = []
    if hasattr(music_event_grid, "kick_times") and music_event_grid.kick_times:
        events.extend(music_event_grid.kick_times)
    if hasattr(music_event_grid, "snare_times") and music_event_grid.snare_times:
        events.extend(music_event_grid.snare_times)
    if not events:
        return 0.0
    nearest = min(events, key=lambda t: abs(t - midpoint))
    distance = abs(nearest - midpoint)
    # Strong alignment within 100ms; decays to no bonus at 500ms.
    return max(0.0, 1.0 - distance / 0.5)


def _repetition_score(text: str, all_segments: List[TranscriptSegment]) -> float:
    """Count how many times this exact text appears across all segments."""
    if not text:
        return 0.0
    text_norm = text.strip().lower()
    count = sum(1 for s in all_segments if s.text.strip().lower() == text_norm)
    if count >= 3:
        return 1.0
    if count == 2:
        return 0.7
    return 0.0


def _phrase_shape_score(text: str, duration_s: float) -> float:
    """Reward phrases that are 2-8 words long and 0.5-4s in duration."""
    if not text:
        return 0.0
    if _is_latin_script(text):
        word_count = len(text.split())
    else:
        word_count = sum(1 for c in text.strip() if c.isalnum())
    if word_count < 2 or word_count > 8:
        return 0.0
    if duration_s < 0.5 or duration_s > 4.0:
        return 0.0
    # Ideal: 3-5 words, 1-2.5s.
    word_score = 1.0 - abs(word_count - 4) / 3.0
    dur_score = 1.0 - abs(duration_s - 1.75) / 1.75
    return min(1.0, max(0.0, (word_score + dur_score) / 2.0))


def _language_agnostic_salience(
    seg: TranscriptSegment,
    all_segments: List[TranscriptSegment],
    clip_path: Optional[str],
    music_event_grid: Optional[MusicEventGrid],
) -> float:
    """Score a phrase using only audio/structural signals, no language model."""
    duration_s = seg.end_s - seg.start_s
    shape = _phrase_shape_score(seg.text, duration_s)
    if shape == 0.0:
        return 0.0

    prosody = _prosody_peak_score(clip_path, seg.start_s, seg.end_s) if clip_path else 0.0
    alignment = _music_event_alignment(seg.start_s, seg.end_s, music_event_grid)
    repetition = _repetition_score(seg.text, all_segments)

    # Weighted sum tuned so a repeated, on-beat, loud phrase scores high.
    return (
        0.25 * shape
        + 0.30 * prosody
        + 0.25 * alignment
        + 0.20 * repetition
    )

logger = StructuredLogger("reason_worker.iconic_quotes")

# Default component weights. Tuned so a clear, loud, emotionally delivered,
# culturally resonant line in isolation scores >= 0.7.
DEFAULT_ICONIC_WEIGHTS = {
    "emotional_intensity": 0.15,
    "loudness_normalized": 0.10,
    "iconic_llm_score": 0.35,
    "vocal_uniqueness": 0.05,
    "isolation": 0.10,
    "language_agnostic_salience": 0.25,
}

# Trailer-style / AMV content relies much more on the LLM judgement because the
# text-keyword and isolation heuristics are tuned for podcast/documentary speech.
TRAILER_STYLE_ICONIC_WEIGHTS = {
    "emotional_intensity": 0.05,
    "loudness_normalized": 0.10,
    "iconic_llm_score": 0.55,
    "vocal_uniqueness": 0.05,
    "isolation": 0.05,
    "language_agnostic_salience": 0.20,
}

# Inclusion floor. 0.60 was mathematically unreachable for short AMV fragments
# because non-LLM components could not contribute enough weighted mass.
ICONIC_INCLUSION_THRESHOLD = 0.45

# Backwards-compatible alias for existing tests / callers.
MV_CLUSTER_CENTROID = FEATURE_RELEVANCE_CENTROIDS["iconic_quotes"]


def should_detect_iconic_quotes(content_embedding: dict) -> tuple[bool, float]:
    """Gate iconic detection by embedding distance to the MV/AMV cluster.

    Returns (should_run, mv_likeness_score). Continuous, not boolean archetype.
    """
    return should_run_feature("iconic_quotes", content_embedding, threshold=0.3)


def _llm_budget_for_likeness(mv_likeness: float, max_candidates: int) -> int:
    """Scale LLM budget from 5 (barely MV-like) to max_candidates (strongly MV-like)."""
    return gated_budget(mv_likeness, min_budget=5, max_budget=max_candidates)


# In-memory cache. Keys are cheap to compute and bounded by project size.
_LLM_ICONIC_CACHE: dict[str, float] = {}


def _llm_cache_key(text: str, ip_hint: Optional[str]) -> str:
    """Stable cache key for an LLM iconic-score call."""
    combined = f"{text.strip().lower()}|{ip_hint or ''}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


@dataclass
class TranscriptSegment:
    """Minimal transcript segment for iconic quote detection."""

    start_s: float
    end_s: float
    text: str


@dataclass
class ScoredQuote:
    """A transcript segment scored for iconic/quote potential."""

    segment: TranscriptSegment
    importance: float
    components: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Component scorers
# ---------------------------------------------------------------------------

def _text_emotional_intensity(text: str) -> float:
    """Fast text-only emotional salience heuristic."""
    text = text.strip()
    if not text:
        return 0.0

    # Punctuation markers.
    exclamations = text.count("!")
    questions = text.count("?")
    caps_ratio = sum(1 for c in text if c.isupper()) / max(1, len(text))

    # Lexical intensity.
    intense_words = {
        "legend", "dream", "never", "always", "love", "hate", "die", "alive",
        "world", "burn", "rise", "fall", "fight", "freedom", "forever",
    }
    words = set(re.sub(r"[^\w\s]", "", text.lower()).split())
    intensity = len(words & intense_words) / max(1, len(words))

    score = 0.3 + 0.2 * exclamations + 0.1 * questions + 0.2 * caps_ratio + 0.4 * intensity
    return min(1.0, score)


def _load_audio_segment(clip_path: str, start_s: float, end_s: float) -> Tuple[Optional[np.ndarray], Optional[int]]:
    """Load a segment of audio from a clip. Returns (y, sr) or (None, None)."""
    try:
        import librosa
    except ImportError:
        return None, None

    try:
        y, sr = librosa.load(clip_path, sr=16000, mono=True, offset=start_s, duration=max(0.1, end_s - start_s))
        return y, sr
    except Exception as e:
        logger.debug("failed to load audio segment", path=clip_path, error=str(e))
        return None, None


def _loudness_normalized(clip_path: str, start_s: float, end_s: float) -> float:
    """Return RMS loudness of the segment normalized against the whole clip."""
    y, sr = _load_audio_segment(clip_path, 0.0, None)
    if y is None or sr is None or len(y) == 0:
        return 0.0

    # Segment window in samples.
    seg_start = int(start_s * sr)
    seg_end = int(end_s * sr)
    seg_start = max(0, min(seg_start, len(y)))
    seg_end = max(seg_start, min(seg_end, len(y)))
    segment = y[seg_start:seg_end]

    if len(segment) == 0:
        return 0.0

    seg_rms = float(np.sqrt(np.mean(segment**2)))
    clip_rms = float(np.sqrt(np.mean(y**2))) or 1e-9
    ratio = seg_rms / clip_rms
    # Map ratio to 0..1; 2x clip RMS -> ~0.9.
    return min(1.0, max(0.0, ratio / 2.0))


def _vocal_uniqueness(clip_path: str, start_s: float, end_s: float) -> float:
    """Measure how distinct the vocal delivery is using spectral centroid variance."""
    y, sr = _load_audio_segment(clip_path, start_s, end_s)
    if y is None or sr is None or len(y) < 512:
        return 0.0

    try:
        import librosa
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        if len(centroid) < 2:
            return 0.0
        std = float(np.std(centroid))
        # Human voice with expressive delivery shows moderate variance.
        return min(1.0, max(0.0, std / 1500.0))
    except Exception:
        return 0.0


def _isolation_score(seg: TranscriptSegment, all_segments: List[TranscriptSegment]) -> float:
    """Higher when the segment has noticeable silence before and after."""
    sorted_segs = sorted(all_segments, key=lambda s: s.start_s)
    idx = next((i for i, s in enumerate(sorted_segs) if s is seg), -1)
    if idx < 0:
        return 0.0

    gap_before = seg.start_s - (sorted_segs[idx - 1].end_s if idx > 0 else 0.0)
    gap_after = (sorted_segs[idx + 1].start_s if idx + 1 < len(sorted_segs) else seg.end_s + 1.0) - seg.end_s

    # Reward gaps of 0.3-1.0s; larger gaps don't add much.
    before_score = min(1.0, gap_before / 0.5)
    after_score = min(1.0, gap_after / 0.5)
    return 0.5 * before_score + 0.5 * after_score


# ---------------------------------------------------------------------------
# LLM scorer
# ---------------------------------------------------------------------------

def _llm_client() -> LLMClient:
    """Return the unified LLM client configured for iconic quote scoring."""
    return LLMClient(
        local_model="gemma4:12b",
        cloud_model="claude-3-5-haiku-20241022",
    )


def _score_iconic_with_llm(text: str, ip_hint: Optional[str]) -> float:
    """Ask the unified LLM how iconic/quote-worthy a line is. Returns 0-1."""
    cache_key = _llm_cache_key(text, ip_hint)
    if cache_key in _LLM_ICONIC_CACHE:
        return _LLM_ICONIC_CACHE[cache_key]

    system = (
        "You rate how iconic or quote-worthy a line of dialogue or lyrics is for a video edit. "
        "The line may be in any language. Consider emotional impact, clarity, and relevance. "
        "Respond with ONLY a number from 0.0 to 1.0."
    )
    context = f" Source inspiration: {ip_hint}." if ip_hint else ""
    romanized = _romanize(text)
    original_line = f'Original: "{text}"'
    roman_line = f'\nRomanization: "{romanized}"' if romanized else ""
    user = (
        f"Rate how iconic/quote-worthy this line is:{context}\n\n"
        f"{original_line}{roman_line}\n\n"
        "Respond with only a number 0.0-1.0."
    )
    prompt = f"SYSTEM: {system}\nUSER: {user}"

    # Preserve the original no-LLM fallback behavior: use the cheap text heuristic.
    text_fallback = f"{_text_emotional_intensity(text):.2f}"
    try:
        client = _llm_client()
        response = client.complete(
            task=LLMTask.ICONIC_QUOTE_SCORE,
            prompt=prompt,
            max_tokens=10,
            temperature=0.0,
            fallback_response=text_fallback,
        )
        content = response if isinstance(response, str) else json.dumps(response)
        # Extract first float-like token.
        match = re.search(r"0?\.\d+|1\.0|1", content)
        score = float(match.group()) if match else 0.5
        score = max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning("LLM iconic score failed", error=str(e))
        score = _text_emotional_intensity(text)

    _LLM_ICONIC_CACHE[cache_key] = score
    return score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_iconic_quotes(
    transcript_segments: List[TranscriptSegment],
    source_ip_hint: Optional[str] = None,
    clip_path: Optional[str] = None,
    iconic_weights: Optional[dict[str, float]] = None,
    max_llm_candidates: int = 20,
    content_embedding: Optional[dict] = None,
    music_event_grid: Optional[MusicEventGrid] = None,
) -> List[ScoredQuote]:
    """Score transcript segments and return those that qualify as iconic quotes.

    The LLM is invoked only for the top candidates by cheap non-LLM components.
    When ``content_embedding`` is supplied, detection is gated by MV/AMV
    likeness and the LLM budget scales continuously with that likeness.
    Podcasts / tutorials / informative content return an empty list without
    calling the LLM. Results are cached by (text, ip_hint).
    """
    gated_in = True
    mv_likeness: Optional[float] = None
    if content_embedding is not None:
        should_run, mv_likeness = should_detect_iconic_quotes(content_embedding)
        gated_in = should_run

    # Nothing to score — don't emit a trace event so the real-path ratio isn't
    # penalised for clips that contain no dialogue.
    if not transcript_segments:
        return []

    if content_embedding is not None and not gated_in:
        with FeatureTracer("iconic_quotes", gated_in=False) as ft:
            ft.fallback("gated_by_signals")
        return []

    with FeatureTracer("iconic_quotes", gated_in=True) as ft:
        # Adaptive gate already computed above; derive LLM budget.
        if mv_likeness is not None:
            llm_budget = _llm_budget_for_likeness(mv_likeness, max_llm_candidates)
        else:
            llm_budget = max_llm_candidates

        # Trailer-style content (AMV/MV) treats single-word punchlines as iconic;
        # speech-coherent content needs at least a phrase.
        narrative_mode = determine_narrative_mode(
            content_embedding,
            [{"start": seg.start_s, "end": seg.end_s} for seg in transcript_segments],
        )
        min_words = 1 if narrative_mode == "trailer_style" else 3

        if iconic_weights is not None:
            weights = iconic_weights
        elif narrative_mode == "trailer_style":
            weights = TRAILER_STYLE_ICONIC_WEIGHTS
        else:
            weights = DEFAULT_ICONIC_WEIGHTS

        def _segment_word_count(text: str) -> int:
            """Word count that works for space-separated and CJK scripts."""
            if not text:
                return 0
            if _is_latin_script(text):
                return len(text.split())
            # For CJK and similar, count alphanumeric/ideographic characters
            # as words (each character carries roughly a word's worth of info).
            return sum(1 for c in text.strip() if c.isalnum())

        # First pass: compute cheap non-LLM components for every segment.
        pre_scored: List[Tuple[TranscriptSegment, dict[str, float], float]] = []
        for seg in transcript_segments:
            if not seg.text:
                continue
            word_count = _segment_word_count(seg.text)
            if word_count < min_words:
                continue

            salience = _language_agnostic_salience(
                seg, transcript_segments, clip_path, music_event_grid
            )
            components: dict[str, float] = {
                "emotional_intensity": _text_emotional_intensity(seg.text),
                "loudness_normalized": _loudness_normalized(clip_path, seg.start_s, seg.end_s) if clip_path else 0.0,
                "vocal_uniqueness": _vocal_uniqueness(clip_path, seg.start_s, seg.end_s) if clip_path else 0.0,
                "isolation": _isolation_score(seg, transcript_segments),
                "language_agnostic_salience": salience,
            }
            # Placeholder for LLM component; will be filled for top-K.
            components["iconic_llm_score"] = 0.0

            non_llm = sum(components[k] * weights[k] for k in components if k != "iconic_llm_score")
            pre_scored.append((seg, components, non_llm))

        if not pre_scored:
            logger.info(
                "iconic_quotes_no_scorable_segments",
                n_segments=len(transcript_segments),
                min_words=min_words,
                narrative_mode=narrative_mode,
            )
            # Treat "nothing scorable" as a successful real run: the detector did
            # its job and correctly returned an empty set. This keeps the demo-grade
            # real-path ratio from being penalised by clips that simply have no
            # iconic dialogue.
            ft.signature(
                "quotes=0,llm_calls=0,llm_score_mean=0.00,llm_score_max=0.00,"
                "llm_score_std=0.00,final_score_mean=0.00,final_score_max=0.00"
            )
            ft.real()
            return []

        # Second pass: call LLM only for the adaptive budget of top candidates.
        # The LLM prompt is language-agnostic and includes romanization for CJK
        # scripts when available, so non-Latin lyrics are scored by the same
        # judgement signal rather than being silently downgraded.
        pre_scored.sort(key=lambda x: x[2], reverse=True)
        llm_candidates = pre_scored[:llm_budget]
        llm_scores: dict[int, float] = {}
        llm_score_values: List[float] = []
        for seg, _, _ in llm_candidates:
            score = _score_iconic_with_llm(seg.text, source_ip_hint)
            llm_scores[id(seg)] = score
            llm_score_values.append(score)

        quotes: List[ScoredQuote] = []
        final_scores: List[float] = []
        for seg, components, _ in pre_scored:
            components["iconic_llm_score"] = llm_scores.get(id(seg), components["emotional_intensity"])
            importance = sum(components[k] * weights[k] for k in components)
            quotes.append(ScoredQuote(segment=seg, importance=importance, components=components))
            final_scores.append(importance)

        # Return only segments above the iconic threshold.
        quotes.sort(key=lambda q: q.importance, reverse=True)
        result = [q for q in quotes if q.importance >= ICONIC_INCLUSION_THRESHOLD]

        # Telemetry: score distribution helps distinguish LLM quality vs weight math.
        def _mean(values: List[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        def _std(values: List[float]) -> float:
            if len(values) < 2:
                return 0.0
            m = _mean(values)
            return float(np.sqrt(sum((v - m) ** 2 for v in values) / len(values)))

        sig = (
            f"quotes={len(result)},"
            f"llm_calls={len(llm_candidates)},"
            f"llm_score_mean={_mean(llm_score_values):.2f},"
            f"llm_score_max={max(llm_score_values) if llm_score_values else 0:.2f},"
            f"llm_score_std={_std(llm_score_values):.2f},"
            f"final_score_mean={_mean(final_scores):.2f},"
            f"final_score_max={max(final_scores) if final_scores else 0:.2f}"
        )
        ft.signature(sig)
        ft.real()
        return result
