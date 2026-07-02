# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Aggregate per-song analyses into a unified SongMeaning artifact."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from shared_py.logging_config import StructuredLogger
from shared_py.models import BeatGrid, SongMeaning, SongMoodProfile, VocalEmotionCurve

from ingest_worker.beat_detect import detect_beats
from ingest_worker.loudness import analyze_loudness
from ingest_worker.song_lyrics import transcribe_song_lyrics
from ingest_worker.song_mood import analyze_song
from ingest_worker.stem_events import detect_music_events
from ingest_worker.stem_separate import separate_song_stems
from ingest_worker.vocal_emotion import analyze_vocal_stem

logger = StructuredLogger("ingest_worker.song_meaning")


def _song_hash(audio_path: str) -> str:
    """Stable hash for an audio file based on path, mtime and size."""
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


def load_song_meaning(
    song_path: str,
    cache_dir: Optional[Path] = None,
) -> Optional[SongMeaning]:
    """Load a cached SongMeaning if it exists and matches the file."""
    cache_dir = cache_dir or _default_cache_dir()
    song_hash = _song_hash(song_path)
    cache_file = cache_dir / f"{song_hash}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return SongMeaning(**data)
        except Exception as e:
            logger.warning("song meaning cache corrupt; recomputing", error=str(e))
    return None


def aggregate_song_meaning(
    song_path: str,
    beat_grid: Optional[BeatGrid] = None,
    cache_dir: Optional[Path] = None,
) -> SongMeaning:
    """Run or load all song analyses and return a unified ``SongMeaning``.

    Each sub-analysis respects its own on-disk cache, so calling this function
    repeatedly is cheap after the first run.
    """
    cache_dir = cache_dir or _default_cache_dir()
    song_hash = _song_hash(song_path)

    cached = load_song_meaning(song_path, cache_dir=cache_dir)
    if cached is not None:
        logger.info("song meaning loaded from cache", song_hash=song_hash)
        return cached

    logger.info("aggregating song meaning", path=song_path, song_hash=song_hash)

    if beat_grid is None:
        beat_grid = detect_beats(song_path)

    mood_profile = analyze_song(song_path, beat_grid, cache_dir=cache_dir)
    stems = separate_song_stems(song_path)
    stems_dir = Path(stems.get("drums", "")).parent
    words = transcribe_song_lyrics(song_path)

    vocals_path = stems.get("vocals")
    vocal_emotion = (
        analyze_vocal_stem(str(vocals_path), song_hash=song_hash, cache_dir=cache_dir)
        if vocals_path
        else VocalEmotionCurve(song_hash=song_hash)
    )

    music_events = detect_music_events(stems_dir, words, cache_dir=cache_dir)
    loudness = analyze_loudness(song_path, cache_dir=cache_dir)

    meaning = SongMeaning(
        song_hash=song_hash,
        genre_tags=mood_profile.genre_tags,
        section_moods=mood_profile.section_moods,
        vocal_emotion_curve=vocal_emotion,
        music_event_grid=music_events,
        loudness=loudness,
    )

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cache_dir / f"{song_hash}.tmp"
        tmp.write_text(meaning.model_dump_json(), encoding="utf-8")
        tmp.replace(cache_dir / f"{song_hash}.json")
        logger.info(
            "song meaning cached",
            song_hash=song_hash,
            genres=len(meaning.genre_tags),
            sections=len(meaning.section_moods),
            vocal_samples=len(vocal_emotion.samples),
            kicks=len(music_events.kick_times),
            snares=len(music_events.snare_times),
        )
    except Exception as e:
        logger.warning("failed to write song meaning cache", error=str(e))

    return meaning
