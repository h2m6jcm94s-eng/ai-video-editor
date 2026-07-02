# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
r"""Song lyric transcription with word-level timestamps.

Uses faster-whisper (large-v3) so the rest of the pipeline can build
karaoke-style captions and narrative labels from the vocal line.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

from shared_py.logging_config import StructuredLogger
from shared_py.storage import LocalStorage

logger = StructuredLogger("ingest_worker.song_lyrics")


@dataclass
class LyricWord:
    text: str
    start_s: float
    end_s: float
    probability: float = 0.0


# Lazy singleton so model import/loading only happens when lyrics are actually
# requested, not on every ingest worker import.
_whisper_model: Optional[object] = None


def _song_hash(audio_path: str) -> str:
    """Stable hash for an audio file based on content identity."""
    path = Path(audio_path).resolve()
    stat = path.stat()
    raw = f"{path}|{stat.st_mtime}|{stat.st_size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "lyrics"


def _whisper_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _load_whisper_model(model_size: str = "large-v3") -> Optional[object]:
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        logger.warning("faster-whisper not available", error=str(e))
        return None
    try:
        device = _whisper_device()
        compute_type = "float16" if device == "cuda" else "int8"
        _whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("whisper model loaded", model=model_size, device=device, compute_type=compute_type)
    except Exception as e:
        logger.warning("failed to load whisper model", model=model_size, error=str(e))
        return None
    return _whisper_model


def _word_probability(word: object) -> float:
    """Best-effort probability for a faster-whisper word object."""
    prob = getattr(word, "probability", None)
    if prob is not None:
        return float(prob)
    avg = getattr(word, "avg_logprob", None)
    if avg is not None:
        return min(1.0, max(0.0, 1.0 + float(avg)))
    return 0.0


def transcribe_song_lyrics(
    audio_path: str,
    model_size: str = "large-v3",
    cache_dir: Optional[Path] = None,
    min_word_probability: float = 0.4,
    language: Optional[str] = None,
) -> List[LyricWord]:
    """Transcribe a song and return word-level lyric timestamps.

    Results are cached under ``<cache_dir>/<song_hash>/lyrics.json`` so
    repeated renders do not re-run the model.
    """
    cache_dir = cache_dir or _default_cache_dir()
    song_hash = _song_hash(audio_path)
    cache_file = cache_dir / song_hash / "lyrics.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            words = [LyricWord(**w) for w in data.get("words", [])]
            logger.info("lyrics loaded from cache", song_hash=song_hash, words=len(words))
            return words
        except Exception as e:
            logger.warning("lyrics cache corrupt; recomputing", error=str(e))

    model = _load_whisper_model(model_size)
    if model is None:
        logger.warning("lyrics transcription unavailable: no whisper model")
        return []

    logger.info("transcribing lyrics", path=audio_path, model=model_size)
    try:
        segments, info = model.transcribe(
            audio_path,
            word_timestamps=True,
            condition_on_previous_text=False,
            language=language,
        )
    except Exception as e:
        logger.warning("lyrics transcription failed", path=audio_path, error=str(e))
        return []

    words: List[LyricWord] = []
    for segment in segments:
        for word in segment.words or []:
            text = getattr(word, "word", "").strip()
            if not text:
                continue
            prob = _word_probability(word)
            if prob < min_word_probability:
                continue
            words.append(
                LyricWord(
                    text=text,
                    start_s=float(getattr(word, "start", segment.start)),
                    end_s=float(getattr(word, "end", segment.end)),
                    probability=prob,
                )
            )

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "song_hash": song_hash,
                    "model": model_size,
                    "language": info.language if info else None,
                    "words": [asdict(w) for w in words],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(cache_file)
        logger.info("lyrics cached", song_hash=song_hash, words=len(words))
    except Exception as e:
        logger.warning("failed to write lyrics cache", error=str(e))

    return words


def get_lyrics_cache_path(audio_path: str, cache_dir: Optional[Path] = None) -> Path:
    cache_dir = cache_dir or _default_cache_dir()
    return cache_dir / _song_hash(audio_path) / "lyrics.json"
