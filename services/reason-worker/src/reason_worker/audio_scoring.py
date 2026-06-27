# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Score dialogue/voiceover lines inside user clips for adaptive audio mixing.

The default implementation uses OpenAI Whisper when available.  On machines
where Whisper is not installed (or CUDA is unavailable) it falls back to a
light-weight spectral heuristic that flags speech-like audio segments.  The
heuristic is intentionally conservative: only segments that look and sound like
clear human speech score above the dialogue threshold.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("reason_worker.audio_scoring")

# Lazy singleton cache so the model is loaded once per worker process.
_whisper_model: Optional[object] = None
_transcript_cache: Dict[str, List[DialogueSegment]] = {}


def _cache_key(path: str) -> str:
    from pathlib import Path
    p = Path(path)
    try:
        stat = p.stat()
        return f"{p.resolve()}|{stat.st_mtime}|{stat.st_size}"
    except Exception:
        return path


@dataclass
class DialogueSegment:
    """A detected speech segment inside a clip."""

    start_s: float
    end_s: float
    text: str = ""
    speech_score: float = 0.0  # 0-1, how likely this is usable dialogue
    phrase_match_score: float = 0.0  # 0-1, overlap with iconic/key phrases
    source_clip_id: Optional[str] = None

    @property
    def total_score(self) -> float:
        """Combined priority score used for mix decisions."""
        # Phrase matches dominate; otherwise rely on speech quality.
        if self.phrase_match_score > 0.8:
            return 0.5 * self.speech_score + 0.5 * self.phrase_match_score
        return self.speech_score


@dataclass
class ScoringConfig:
    """Tuning knobs for dialogue scoring."""

    model_size: str = "base"
    language: Optional[str] = "en"
    # Minimum combined score for a segment to become a dialogue audio track.
    min_dialogue_score: float = 0.65
    # Phrases that should be preserved / emphasized in the mix.
    iconic_phrases: List[str] = field(default_factory=list)
    # Whisper-specific: segments with high no-speech probability are dropped.
    max_no_speech_prob: float = 0.75

    def __post_init__(self):
        # Normalize phrases for fuzzy matching (lowercase, strip punctuation).
        self.iconic_phrases = [
            re.sub(r"[^\w\s]", "", p.lower()).strip()
            for p in self.iconic_phrases
            if p.strip()
        ]


def _whisper_device() -> str:
    """Pick CUDA when available, otherwise CPU."""
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _load_whisper_model(model_size: str = "base") -> Optional[object]:
    """Load the Whisper model once and cache it."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        import whisper
    except ImportError:
        logger.warning("openai-whisper not installed; using spectral dialogue fallback")
        return None
    try:
        device = _whisper_device()
        _whisper_model = whisper.load_model(model_size, device=device)
        logger.info("whisper model loaded", model=model_size, device=device)
        return _whisper_model
    except Exception as e:
        logger.warning("failed to load whisper model", error=str(e))
        return None


def _phrase_match_score(text: str, phrases: List[str]) -> float:
    """Return a fuzzy match score [0,1] against a list of iconic phrases."""
    if not phrases:
        return 0.0
    normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(normalized.split())
    best = 0.0
    for phrase in phrases:
        phrase_words = phrase.split()
        if not phrase_words:
            continue
        # Exact substring match = 1.0
        if phrase in normalized:
            return 1.0
        # Jaccard-ish overlap
        pset = set(phrase_words)
        overlap = len(words & pset) / len(pset)
        if overlap > best:
            best = overlap
    return best


def _whisper_segments(
    clip_path: str,
    cfg: ScoringConfig,
) -> List[DialogueSegment]:
    """Transcribe a clip with Whisper and score each segment."""
    key = _cache_key(clip_path)
    if key in _transcript_cache:
        return _transcript_cache[key]

    model = _load_whisper_model(cfg.model_size)
    if model is None:
        return []

    try:
        device = _whisper_device()
        fp16 = device == "cuda"
        result = model.transcribe(
            clip_path,
            language=cfg.language,
            fp16=fp16,
            verbose=False,
            word_timestamps=False,
        )
    except Exception as e:
        logger.warning("whisper transcription failed", path=clip_path, error=str(e))
        return []

    segments: List[DialogueSegment] = []
    for seg in result.get("segments", []):
        no_speech = seg.get("no_speech_prob", 0.0) or 0.0
        if no_speech > cfg.max_no_speech_prob:
            continue
        avg_logprob = seg.get("avg_logprob", -1.0) or -1.0
        # Convert avg_logprob (usually -1..0) to a 0..1 speech-confidence score.
        speech_score = min(1.0, max(0.0, 1.0 + avg_logprob))
        text = seg.get("text", "")
        phrase_score = _phrase_match_score(text, cfg.iconic_phrases)
        segments.append(
            DialogueSegment(
                start_s=float(seg.get("start", 0.0)),
                end_s=float(seg.get("end", 0.0)),
                text=text,
                speech_score=speech_score,
                phrase_match_score=phrase_score,
            )
        )
    _transcript_cache[key] = segments
    return segments


def _spectral_dialogue_segments(
    clip_path: str,
    cfg: ScoringConfig,
) -> List[DialogueSegment]:
    """Fallback speech detection using librosa spectral features.

    Tuned to avoid flagging music or loud SFX as dialogue.  This is a fallback;
    Whisper is strongly preferred for actual lyric/line detection.
    """
    try:
        import librosa
    except ImportError:
        logger.warning("librosa unavailable; cannot run spectral dialogue fallback")
        return []

    try:
        y, sr = librosa.load(clip_path, sr=16000, mono=True)
    except Exception as e:
        logger.warning("librosa load failed", path=clip_path, error=str(e))
        return []

    hop = int(sr * 0.2)  # 200 ms windows
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    zcr = librosa.feature.zero_crossing_rate(y=y, hop_length=hop)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    # Speech-ish regions: moderate RMS, moderate ZCR, centroid in voice band.
    speech_mask = (
        (rms > np.percentile(rms, 40))
        & (zcr > 0.03)
        & (zcr < 0.25)
        & (centroid > 400)
        & (centroid < 3500)
    )

    segments = []
    in_speech = False
    seg_start = 0.0
    for t, is_speech in zip(times, speech_mask):
        if is_speech and not in_speech:
            seg_start = float(t)
            in_speech = True
        elif not is_speech and in_speech:
            if t - seg_start >= 0.5:
                segments.append(
                    DialogueSegment(
                        start_s=seg_start,
                        end_s=float(t),
                        speech_score=0.6,
                        phrase_match_score=0.0,
                    )
                )
            in_speech = False
    if in_speech and times[-1] - seg_start >= 0.5:
        segments.append(
            DialogueSegment(
                start_s=seg_start,
                end_s=float(times[-1]),
                speech_score=0.6,
                phrase_match_score=0.0,
            )
        )
    return segments


def score_clip_dialogue(
    clip_path: str,
    cfg: Optional[ScoringConfig] = None,
) -> List[DialogueSegment]:
    """Return scored dialogue segments for a single clip.

    Uses Whisper when possible; falls back to spectral heuristics otherwise.
    """
    cfg = cfg or ScoringConfig()

    # Try Whisper first.
    if _load_whisper_model(cfg.model_size) is not None:
        segments = _whisper_segments(clip_path, cfg)
        if segments:
            return segments

    return _spectral_dialogue_segments(clip_path, cfg)
