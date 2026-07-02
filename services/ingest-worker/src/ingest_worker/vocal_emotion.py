# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Wav2Vec2 vocal-emotion analysis on the Demucs vocals stem."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from shared_py.logging_config import StructuredLogger
from shared_py.models import VocalEmotionCurve, VocalEmotionSample

logger = StructuredLogger("ingest_worker.vocal_emotion")

EMOTION_CLASSES = ["neutral", "happy", "sad", "angry", "fear"]

# The superb/wav2vec2-large-superb-er model emits abbreviated labels.
_LABEL_MAP = {
    "neu": "neutral",
    "hap": "happy",
    "sad": "sad",
    "ang": "angry",
    "angry": "angry",
    "fea": "fear",
    "fear": "fear",
    "neutral": "neutral",
    "happy": "happy",
}
_WAV2VEC_SR = 16_000
_WINDOW_S = 3.0
_HOP_S = 1.0
_RMS_FLOOR = 0.005

_vocal_classifier: Optional[object] = None


def _vocals_hash(vocals_wav_path: str) -> str:
    path = Path(vocals_wav_path).resolve()
    try:
        stat = path.stat()
        raw = f"{path}|{stat.st_mtime}|{stat.st_size}"
    except FileNotFoundError:
        raw = str(path)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "song_meaning"


def _load_classifier() -> object:
    """Lazy-load the Wav2Vec2 emotion classifier. Fails loudly on error."""
    global _vocal_classifier
    if _vocal_classifier is not None:
        return _vocal_classifier

    from transformers import pipeline

    logger.info("loading Wav2Vec2 emotion classifier", model="superb/wav2vec2-large-superb-er")
    _vocal_classifier = pipeline(
        "audio-classification",
        model="superb/wav2vec2-large-superb-er",
        device=0 if _has_cuda() else -1,
    )
    logger.info("Wav2Vec2 emotion classifier loaded")
    return _vocal_classifier


def _has_cuda() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def _load_vocals(vocals_wav_path: str) -> np.ndarray:
    """Load vocals stem as 16kHz mono float array."""
    try:
        import librosa

        y, _ = librosa.load(vocals_wav_path, sr=_WAV2VEC_SR, mono=True)
        return y
    except Exception as e:
        logger.warning("librosa load failed for vocals", path=vocals_wav_path, error=str(e))
        raise


def _window_rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(y.astype(np.float64) ** 2)))


def _softmax(scores: Dict[str, float]) -> Dict[str, float]:
    vals = np.array(list(scores.values()), dtype=np.float64)
    exps = np.exp(vals - np.max(vals))
    probs = exps / exps.sum()
    return {label: float(p) for label, p in zip(scores.keys(), probs)}


def _classify_window(y: np.ndarray) -> Dict[str, float]:
    classifier = _load_classifier()
    raw = classifier(y)
    scores: Dict[str, float] = {}
    for item in raw:
        canonical = _LABEL_MAP.get(item["label"], item["label"])
        scores[canonical] = float(item["score"])
    # Apply softmax in case the model returns logits.
    return _softmax(scores)


def analyze_vocal_stem(
    vocals_wav_path: str,
    song_hash: Optional[str] = None,
    window_s: float = _WINDOW_S,
    hop_s: float = _HOP_S,
    rms_floor: float = _RMS_FLOOR,
    cache_dir: Optional[Path] = None,
) -> VocalEmotionCurve:
    """Slide a window over the vocals stem and build an emotion trajectory.

    Windows with RMS < ``rms_floor`` are skipped as instrumental.
    Caches the result under ``<cache_dir>/<hash>/vocal_emotion.json``.
    """
    vocals_path = Path(vocals_wav_path)
    if not vocals_path.exists():
        raise FileNotFoundError(
            f"vocals stem missing for song hash {song_hash or 'unknown'}: {vocals_wav_path}"
        )

    cache_dir = cache_dir or _default_cache_dir()
    file_hash = _vocals_hash(vocals_wav_path)
    cache_file = cache_dir / file_hash / "vocal_emotion.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            curve = VocalEmotionCurve(**data)
            logger.info("vocal emotion curve loaded from cache", song_hash=file_hash)
            return curve
        except Exception as e:
            logger.warning("vocal emotion cache corrupt; recomputing", error=str(e))

    y = _load_vocals(vocals_wav_path)
    sr = _WAV2VEC_SR
    window_samples = int(window_s * sr)
    hop_samples = int(hop_s * sr)

    samples: List[VocalEmotionSample] = []
    silent = 0
    total = 0

    for start in range(0, max(len(y) - window_samples + 1, 1), hop_samples):
        end = min(start + window_samples, len(y))
        window = y[start:end]
        total += 1
        rms = _window_rms(window)
        if rms < rms_floor:
            silent += 1
            continue

        try:
            distribution = _classify_window(window)
        except Exception as e:
            logger.warning("emotion classification failed for window", start_s=start / sr, error=str(e))
            continue

        dominant = max(distribution, key=distribution.get)
        samples.append(
            VocalEmotionSample(
                t_center_s=(start + window_samples / 2) / sr,
                dominant_emotion=dominant,
                distribution=distribution,
                rms=rms,
            )
        )

    silent_ratio = silent / total if total > 0 else 0.0
    curve = VocalEmotionCurve(
        song_hash=song_hash or file_hash,
        samples=samples,
        silent_ratio=silent_ratio,
    )

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(curve.model_dump_json(), encoding="utf-8")
        tmp.replace(cache_file)
        logger.info(
            "vocal emotion curve cached",
            song_hash=song_hash or file_hash,
            samples=len(samples),
            silent_ratio=silent_ratio,
        )
    except Exception as e:
        logger.warning("failed to write vocal emotion cache", error=str(e))

    return curve


def get_vocal_emotion_cache_path(
    vocals_wav_path: str, cache_dir: Optional[Path] = None
) -> Path:
    cache_dir = cache_dir or _default_cache_dir()
    return cache_dir / _vocals_hash(vocals_wav_path) / "vocal_emotion.json"
