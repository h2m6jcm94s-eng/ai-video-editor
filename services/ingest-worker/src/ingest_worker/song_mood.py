# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""CLAP zero-shot mood/genre tagging for songs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from shared_py.logging_config import StructuredLogger
from shared_py.models import BeatGrid, BeatSegment, SectionMoodTags, SongMoodProfile

logger = StructuredLogger("ingest_worker.song_mood")

MOOD_TAGS = [
    "aggressive",
    "melancholic",
    "uplifting",
    "tense",
    "romantic",
    "chaotic",
    "peaceful",
    "dark",
    "triumphant",
    "hopeful",
    "hollow",
    "furious",
    "reverent",
    "playful",
    "nostalgic",
]

GENRE_TAGS = [
    "hip-hop",
    "rock",
    "electronic",
    "orchestral",
    "acoustic",
    "metal",
    "synth-wave",
    "trap",
    "ambient",
    "jazz",
]

_CLAP_SR = 48_000
_CLAP_MAX_SEGMENT_S = 10.0

_clap_pipeline: Optional[object] = None


def _song_hash(audio_path: str) -> str:
    path = Path(audio_path).resolve()
    try:
        stat = path.stat()
        raw = f"{path}|{stat.st_mtime}|{stat.st_size}"
    except FileNotFoundError:
        raw = str(path)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "song_meaning"


def _clap_device() -> int:
    try:
        import torch

        return 0 if torch.cuda.is_available() else -1
    except Exception:
        return -1


def _load_clap_pipeline() -> object:
    """Lazy-load the CLAP zero-shot audio classification pipeline.

    Fails loudly if the model cannot be downloaded or loaded.
    """
    global _clap_pipeline
    if _clap_pipeline is not None:
        return _clap_pipeline

    from transformers import pipeline

    device = _clap_device()
    logger.info("loading CLAP model", model="laion/clap-htsat-fused", device=device)
    _clap_pipeline = pipeline(
        "zero-shot-audio-classification",
        model="laion/clap-htsat-fused",
        device=device,
    )
    logger.info("CLAP model loaded")
    return _clap_pipeline


def _load_audio_segment(
    audio_path: str,
    start_s: float,
    end_s: Optional[float],
    sr: int = _CLAP_SR,
) -> np.ndarray:
    """Load a mono audio segment at the target sample rate."""
    full_file = end_s is None or not np.isfinite(end_s)
    duration = None if full_file else max(0.0, end_s - start_s)
    try:
        import librosa

        y, _ = librosa.load(
            audio_path,
            sr=sr,
            mono=True,
            offset=start_s,
            duration=duration,
        )
        return y
    except Exception as e:
        logger.warning("librosa load failed, falling back to ffmpeg", error=str(e))

    # Fallback: decode the segment via ffmpeg to a temp WAV, then load with soundfile.
    suffix = Path(audio_path).suffix or ".flac"
    tmp_in = Path(tempfile.mkstemp(suffix=suffix, prefix="mood_safe_")[1])
    tmp_wav = Path(tempfile.mkstemp(suffix=".wav", prefix="mood_seg_")[1])
    try:
        import shutil

        shutil.copy2(audio_path, tmp_in)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(tmp_in),
            "-ar",
            str(sr),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-ss",
            str(start_s),
        ]
        if duration is not None:
            cmd.extend(["-t", str(duration)])
        cmd.append(str(tmp_wav))
        import subprocess

        subprocess.run(cmd, check=True, capture_output=True)
        import soundfile as sf

        y, _ = sf.read(str(tmp_wav), dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        return y
    finally:
        for p in (tmp_in, tmp_wav):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass


def _center_segment_clip(y: np.ndarray, sr: int, max_duration_s: float) -> np.ndarray:
    """Return a central clip of at most ``max_duration_s`` seconds."""
    max_samples = int(max_duration_s * sr)
    if len(y) <= max_samples:
        return y
    start = (len(y) - max_samples) // 2
    return y[start : start + max_samples]


def tag_song_section(
    audio_segment_path: str,
    candidate_tags: List[str],
    top_k: int = 3,
) -> List[Tuple[str, float]]:
    """Zero-shot classify a WAV/audio segment against candidate tags via CLAP.

    Returns top-k ``(tag, confidence)`` sorted descending.
    """
    if not candidate_tags:
        return []

    y = _load_audio_segment(audio_segment_path, 0.0, float("inf"), sr=_CLAP_SR)
    y = _center_segment_clip(y, _CLAP_SR, _CLAP_MAX_SEGMENT_S)
    if len(y) < 16:
        return [(tag, 0.0) for tag in candidate_tags[:top_k]]

    classifier = _load_clap_pipeline()
    results = classifier(y, candidate_labels=candidate_tags)
    # Results are already sorted by score descending.
    ranked = [(r["label"], float(r["score"])) for r in results]
    return ranked[:top_k]


def analyze_song(
    song_path: str,
    beat_grid: BeatGrid,
    cache_dir: Optional[Path] = None,
) -> SongMoodProfile:
    """Full song analysis: per-section moods + global genres.

    Writes to ``<cache_dir>/<hash>/mood_tags.json``.
    """
    cache_dir = cache_dir or _default_cache_dir()
    song_hash = _song_hash(song_path)
    cache_file = cache_dir / song_hash / "mood_tags.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            profile = SongMoodProfile(**data)
            logger.info("mood profile loaded from cache", song_hash=song_hash)
            return profile
        except Exception as e:
            logger.warning("mood profile cache corrupt; recomputing", error=str(e))

    segments = beat_grid.segments
    if not segments:
        duration = _audio_duration(song_path)
        segments = [BeatSegment(start=0.0, end=duration, label="full")]

    section_moods: List[SectionMoodTags] = []
    for seg in segments:
        start_s = float(seg.start)
        end_s = float(seg.end)
        y = _load_audio_segment(song_path, start_s, end_s, sr=_CLAP_SR)
        y = _center_segment_clip(y, _CLAP_SR, _CLAP_MAX_SEGMENT_S)
        top_moods = []
        if len(y) >= 16:
            classifier = _load_clap_pipeline()
            results = classifier(y, candidate_labels=MOOD_TAGS)
            top_moods = [(r["label"], float(r["score"])) for r in results[:3]]
        section_moods.append(
            SectionMoodTags(
                start_s=start_s,
                end_s=end_s,
                section_label=seg.label,
                top_moods=top_moods,
            )
        )

    # Global genre tags from a representative center clip of the song.
    full_y = _load_audio_segment(song_path, 0.0, None, sr=_CLAP_SR)
    genre_clip = _center_segment_clip(full_y, _CLAP_SR, _CLAP_MAX_SEGMENT_S)
    genre_tags: List[Tuple[str, float]] = []
    if len(genre_clip) >= 16:
        classifier = _load_clap_pipeline()
        results = classifier(genre_clip, candidate_labels=GENRE_TAGS)
        genre_tags = [(r["label"], float(r["score"])) for r in results[:3]]

    profile = SongMoodProfile(
        song_hash=song_hash,
        genre_tags=genre_tags,
        section_moods=section_moods,
    )

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(profile.model_dump_json(), encoding="utf-8")
        tmp.replace(cache_file)
        logger.info("mood profile cached", song_hash=song_hash, sections=len(section_moods))
    except Exception as e:
        logger.warning("failed to write mood profile cache", error=str(e))

    return profile


def _audio_duration(audio_path: str) -> float:
    try:
        import librosa

        return float(librosa.get_duration(path=audio_path))
    except Exception:
        try:
            import subprocess

            out = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return max(0.0, float(out.strip()))
        except Exception:
            return 0.0


def get_mood_cache_path(song_path: str, cache_dir: Optional[Path] = None) -> Path:
    cache_dir = cache_dir or _default_cache_dir()
    return cache_dir / _song_hash(song_path) / "mood_tags.json"
