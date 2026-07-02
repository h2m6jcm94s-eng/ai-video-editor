# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Per-stem music-event detection for cut-on-hit snapping."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

import librosa
import numpy as np

from shared_py.logging_config import StructuredLogger
from shared_py.models import MusicEventGrid

if TYPE_CHECKING:
    from ingest_worker.song_lyrics import LyricWord

logger = StructuredLogger("ingest_worker.stem_events")

_DETECT_SR = 22_050
_DRUM_WINDOW_MS = 30
_DEDUP_MS = 30


def _song_hash_from_stems(stems_dir: Path) -> str:
    """Stable hash from the four expected stem files."""
    parts = []
    for stem in ["drums.wav", "bass.wav", "vocals.wav", "other.wav"]:
        path = stems_dir / stem
        try:
            stat = path.stat()
            parts.append(f"{stem}|{stat.st_mtime}|{stat.st_size}")
        except FileNotFoundError:
            parts.append(f"{stem}|missing")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "song_meaning"


def _load_audio(audio_path: str, sr: int = _DETECT_SR) -> np.ndarray:
    import librosa

    y, _ = librosa.load(audio_path, sr=sr, mono=True)
    return y


def _rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(y.astype(np.float64) ** 2)))


def classify_drum_onset(
    y: np.ndarray,
    sr: int,
    onset_time_s: float,
    window_ms: int = _DRUM_WINDOW_MS,
) -> str:
    """Classify a single drum onset as kick/snare/hihat from its spectral peak."""
    half = int(window_ms / 2000 * sr)
    center = int(onset_time_s * sr)
    start = max(0, center - half)
    end = min(len(y), center + half)
    segment = y[start:end]
    if len(segment) < 32:
        return "unknown"

    n_fft = 512
    hop = 128
    D = np.abs(librosa.stft(segment, n_fft=n_fft, hop_length=hop))
    mag = D.mean(axis=1)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    peak_freq = freqs[mag.argmax()]

    if 40 <= peak_freq <= 80:
        return "kick"
    if peak_freq >= 6000:
        return "hihat"
    if 150 <= peak_freq <= 350:
        return "snare"

    centroid = float(librosa.feature.spectral_centroid(y=segment, sr=sr)[0].mean())
    return "snare" if centroid < 2500 else "hihat"


def _deduplicate_onsets(
    onsets: List[Tuple[float, str, float]], min_gap_s: float
) -> Tuple[List[float], List[float], List[float]]:
    """Deduplicate overlapping onsets, keeping the highest-intensity event.

    Returns (kick_times, snare_times, hihat_times).
    """
    if not onsets:
        return [], [], []
    # Sort by time.
    onsets = sorted(onsets, key=lambda x: x[0])
    kept: List[Tuple[float, str, float]] = []
    for t, label, intensity in onsets:
        merged = False
        for i, (kt, klabel, kintensity) in enumerate(kept):
            if abs(t - kt) <= min_gap_s:
                if intensity > kintensity:
                    kept[i] = (t, label, intensity)
                merged = True
                break
        if not merged:
            kept.append((t, label, intensity))

    kicks = [t for t, label, _ in kept if label == "kick"]
    snares = [t for t, label, _ in kept if label == "snare"]
    hihats = [t for t, label, _ in kept if label == "hihat"]
    return kicks, snares, hihats


def _detect_drum_events(drums_wav: Path) -> Tuple[List[float], List[float], List[float]]:
    """Return (kick_times, snare_times, hihat_times)."""
    logger.info("detecting drum events", path=str(drums_wav))
    y = _load_audio(str(drums_wav), sr=_DETECT_SR)
    sr = _DETECT_SR
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, wait=5, pre_avg=8, post_avg=8
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    onsets: List[Tuple[float, str, float]] = []
    for t in onset_times:
        label = classify_drum_onset(y, sr, float(t))
        if label == "unknown":
            continue
        center = int(t * sr)
        half = int(_DRUM_WINDOW_MS / 2000 * sr)
        window = y[max(0, center - half) : min(len(y), center + half)]
        intensity = _rms(window)
        onsets.append((float(t), label, intensity))

    return _deduplicate_onsets(onsets, min_gap_s=_DEDUP_MS / 1000.0)


def _detect_bass_drops(bass_wav: Path, min_interval_s: float = 0.5) -> List[float]:
    """Detect RMS/onset peaks in the bass stem."""
    logger.info("detecting bass drops", path=str(bass_wav))
    y = _load_audio(str(bass_wav), sr=_DETECT_SR)
    sr = _DETECT_SR
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    peaks = librosa.util.peak_pick(
        onset_env,
        pre_max=20,
        post_max=20,
        pre_avg=20,
        post_avg=20,
        delta=0.3,
        wait=int(min_interval_s * sr / 512),  # onset strength hop ~512
    )
    times = [float(t) for t in librosa.frames_to_time(peaks, sr=sr)]
    # Enforce min_interval by scanning sorted times.
    filtered: List[float] = []
    for t in sorted(times):
        if not filtered or t - filtered[-1] >= min_interval_s:
            filtered.append(t)
    return filtered


def _detect_vocal_onsets(
    vocals_wav: Path,
    whisper_words: List["LyricWord"],
) -> Tuple[List[float], List[float]]:
    """Return (vocal_onset_times, phrase_boundary_times)."""
    logger.info("detecting vocal onsets", path=str(vocals_wav))
    y = _load_audio(str(vocals_wav), sr=_DETECT_SR)
    sr = _DETECT_SR
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, wait=3, pre_avg=4, post_avg=4
    )
    librosa_onsets = list(librosa.frames_to_time(onset_frames, sr=sr))

    # Merge Whisper word starts as additional onsets.
    word_onsets = [w.start_s for w in whisper_words]
    all_onsets = sorted(set(librosa_onsets + word_onsets))

    # Deduplicate within 100ms.
    deduped: List[float] = []
    for t in all_onsets:
        if not deduped or t - deduped[-1] >= 0.10:
            deduped.append(t)
        elif t > deduped[-1]:
            # Keep the earlier onset (word timestamps are usually more accurate).
            pass

    # Phrase boundaries = word starts after a gap > 500ms.
    phrase_boundaries: List[float] = []
    prev_end: Optional[float] = None
    for word in sorted(whisper_words, key=lambda w: w.start_s):
        if prev_end is not None and word.start_s - prev_end > 0.5:
            phrase_boundaries.append(word.start_s)
        prev_end = word.end_s

    return deduped, phrase_boundaries


def _detect_sweeps(other_wav: Path) -> List[float]:
    """Detect filter-sweep peaks from spectral centroid slope."""
    logger.info("detecting sweep peaks", path=str(other_wav))
    y = _load_audio(str(other_wav), sr=_DETECT_SR)
    sr = _DETECT_SR
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    times = librosa.frames_to_time(np.arange(len(centroid)), sr=sr)

    if len(centroid) < 3:
        return []

    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import find_peaks

    smooth = gaussian_filter1d(centroid.astype(np.float64), sigma=2.0)
    slope = np.gradient(smooth)
    abs_slope = np.abs(slope)

    std = float(np.std(slope))
    max_abs = float(np.max(np.abs(slope))) if len(slope) else 0.0
    threshold = max(std * 1.5, max_abs * 0.05)
    if threshold <= 0 or not np.isfinite(threshold):
        return []

    peak_indices, _ = find_peaks(slope, height=threshold, distance=10)
    return [float(times[int(p)]) for p in peak_indices]


def detect_music_events(
    stems_dir: Path,
    whisper_words: List["LyricWord"],
    cache_dir: Optional[Path] = None,
) -> MusicEventGrid:
    """Detect kick/snare/hihat/bass_drop/vocal_onset/sweep events from stems."""
    cache_dir = cache_dir or _default_cache_dir()
    song_hash = _song_hash_from_stems(stems_dir)
    cache_file = cache_dir / song_hash / "music_events.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            grid = MusicEventGrid(**data)
            logger.info("music events loaded from cache", song_hash=song_hash)
            return grid
        except Exception as e:
            logger.warning("music events cache corrupt; recomputing", error=str(e))

    stems_dir = Path(stems_dir)
    drums_wav = stems_dir / "drums.wav"
    bass_wav = stems_dir / "bass.wav"
    vocals_wav = stems_dir / "vocals.wav"
    other_wav = stems_dir / "other.wav"

    kick_times, snare_times, hihat_times = _detect_drum_events(drums_wav)
    bass_drop_times = _detect_bass_drops(bass_wav)
    vocal_onset_times, phrase_boundary_times = _detect_vocal_onsets(vocals_wav, whisper_words)
    sweep_peak_times = _detect_sweeps(other_wav)

    grid = MusicEventGrid(
        song_hash=song_hash,
        kick_times=kick_times,
        snare_times=snare_times,
        hihat_times=hihat_times,
        bass_drop_times=bass_drop_times,
        vocal_onset_times=vocal_onset_times,
        phrase_boundary_times=phrase_boundary_times,
        sweep_peak_times=sweep_peak_times,
    )

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(grid.model_dump_json(), encoding="utf-8")
        tmp.replace(cache_file)
        logger.info(
            "music events cached",
            song_hash=song_hash,
            kicks=len(kick_times),
            snares=len(snare_times),
            hihats=len(hihat_times),
            bass_drops=len(bass_drop_times),
            vocal_onsets=len(vocal_onset_times),
            sweeps=len(sweep_peak_times),
        )
    except Exception as e:
        logger.warning("failed to write music events cache", error=str(e))

    return grid


def get_music_events_cache_path(stems_dir: Path, cache_dir: Optional[Path] = None) -> Path:
    cache_dir = cache_dir or _default_cache_dir()
    return cache_dir / _song_hash_from_stems(stems_dir) / "music_events.json"
