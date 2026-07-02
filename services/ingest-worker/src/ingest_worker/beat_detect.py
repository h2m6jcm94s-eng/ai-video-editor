# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Beat, downbeat, and section detection using allin1 + librosa fallback."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np

try:
    import librosa
    _HAS_LIBROSA = True
except ImportError:
    librosa = None  # type: ignore[assignment]
    _HAS_LIBROSA = False

try:
    from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor
    _HAS_MADMOM = True
except ImportError:
    DBNBeatTrackingProcessor = None  # type: ignore[misc,assignment]
    RNNBeatProcessor = None  # type: ignore[misc,assignment]
    _HAS_MADMOM = False

from shared_py.logging_config import StructuredLogger
from shared_py.models import BeatGrid, BeatSegment

logger = StructuredLogger("ingest_worker.beat_detect")


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
    return Path(root) / "beat"


def _safe_audio_path(input_path: str) -> Tuple[str, Optional[Path]]:
    """Return (path_to_decode, temp_copy_to_clean_up).

    FFmpeg on Windows can fail or corrupt metadata when the input path contains
    characters outside the active code page (e.g. Polish ``Ł``). Copy to an
    ASCII-only temporary file when necessary.
    """
    try:
        input_path.encode("ascii")
        return input_path, None
    except UnicodeEncodeError:
        suffix = Path(input_path).suffix or ".flac"
        tmp_copy = Path(tempfile.mkstemp(suffix=suffix, prefix="beat_safe_")[1])
        shutil.copy2(input_path, tmp_copy)
        return str(tmp_copy), tmp_copy


def decode_to_wav(input_path: str) -> str:
    """Decode any audio to 44.1kHz WAV PCM.

    Creates a temporary WAV file that the caller is responsible for cleaning up.
    The temp file is removed automatically if FFmpeg fails.
    """
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="ingest_beat_")
    os.close(fd)

    safe_input, safe_copy = _safe_audio_path(input_path)
    try:
        cmd = [
            "ffmpeg", "-y", "-i", safe_input,
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            "-map", "0:a:0",  # ignore attached cover art / video streams
            wav_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="replace")[:1000] if e.stderr else ""
            # Best-effort cleanup so failed decodes do not leak temp files.
            try:
                os.remove(wav_path)
            except FileNotFoundError:
                pass
            raise RuntimeError(
                f"FFmpeg decode_to_wav failed (exit {e.returncode}): {stderr}"
            ) from e
    finally:
        if safe_copy is not None:
            try:
                safe_copy.unlink(missing_ok=True)
            except Exception:
                pass
    return wav_path


def _audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds, using librosa when possible."""
    if _HAS_LIBROSA:
        try:
            return float(librosa.get_duration(path=audio_path))
        except Exception:
            pass
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return max(0.0, float(out.strip()))
    except Exception:
        logger.warning("Could not determine audio duration; using default", path=audio_path)
        return 120.0


def _synthetic_beat_grid(audio_path: str, bpm: float = 120.0) -> BeatGrid:
    """Last-resort beat grid: a steady 120 BPM (or provided BPM) grid."""
    duration = _audio_duration(audio_path)
    beat_period = 60.0 / bpm
    beats = np.arange(0.0, duration, beat_period).tolist()
    downbeats = beats[::4] if beats else []
    beat_positions = ([1, 2, 3, 4] * (len(beats) // 4 + 1))[: len(beats)]

    # Simple four-section fallback so downstream cutlist generation still works.
    segment_len = max(duration / 4, 1.0)
    segments = [
        BeatSegment(start=i * segment_len, end=min((i + 1) * segment_len, duration), label=label)
        for i, label in enumerate(["intro", "verse", "chorus", "outro"])
    ]

    return BeatGrid(
        bpm=bpm,
        beats=beats,
        downbeats=downbeats,
        beat_positions=beat_positions,
        segments=segments,
    )


def detect_beats_madmom(audio_path: str) -> Optional[BeatGrid]:
    """Try madmom for beats + downbeats, fall back to librosa structure for sections."""
    if not _HAS_MADMOM or DBNBeatTrackingProcessor is None or RNNBeatProcessor is None:
        return None

    try:
        act = RNNBeatProcessor()(audio_path)
        beat_proc = DBNBeatTrackingProcessor(fps=100)
        beat_times = np.array(beat_proc(act))

        if len(beat_times) < 2:
            return None

        intervals = np.diff(beat_times)
        estimated_bpm = float(60.0 / np.median(intervals)) if len(intervals) else 120.0
        estimated_bpm = max(30.0, min(300.0, estimated_bpm))

        downbeats = beat_times[::4].tolist()
        beat_positions = ([1, 2, 3, 4] * (len(beat_times) // 4 + 1))[: len(beat_times)]

        segments = _detect_structure_librosa(audio_path, beat_times)

        return BeatGrid(
            bpm=estimated_bpm,
            beats=beat_times.tolist(),
            downbeats=downbeats,
            beat_positions=beat_positions,
            segments=segments,
        )
    except Exception as e:
        logger.warning("madmom beat detection failed", error=str(e))
        return None


def _label_structure_segments(boundary_times: List[float], energies: List[float]) -> List[str]:
    """Assign conventional song-section labels to detected boundaries.

    Labels are inferred from the relative energy and temporal order of each
    segment. This is a heuristic fallback; when allin1 is available it provides
    real section labels from a trained model.
    """
    n = len(energies)
    labels = [""] * n
    labels[0] = "intro"
    labels[-1] = "outro"

    # Energy-ranked candidates among interior segments.
    ranked = sorted(((energies[i], i) for i in range(1, n - 1)), reverse=True)
    if ranked:
        labels[ranked[0][1]] = "drop"
    if len(ranked) > 1:
        labels[ranked[1][1]] = "chorus"

    drop_idx = next((i for i, l in enumerate(labels) if l == "drop"), None)
    chorus_idx = next((i for i, l in enumerate(labels) if l == "chorus"), None)
    ref = drop_idx if drop_idx is not None else chorus_idx

    for i in range(1, n - 1):
        if labels[i]:
            continue
        labels[i] = "verse" if ref is None or i < ref else "bridge"

    return labels


def _detect_structure_librosa(audio_path: str, beat_times: np.ndarray) -> List[BeatSegment]:
    """Detect real song structure using chroma + energy clustering.

    Returns a list of BeatSegment objects with labels like intro, verse,
    chorus, drop, bridge, outro. Falls back to equal-duration chunks if any
    step fails so the pipeline never crashes.
    """
    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)
        hop = 512

        # Map reference beat times to frame indices at the analysis sr.
        beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=hop)
        beat_frames = np.unique(np.clip(beat_frames, 0, len(y) - 1))
        if len(beat_frames) < 4:
            raise ValueError("Too few beats for structure analysis")

        def _sync(feature: np.ndarray, frames: np.ndarray) -> np.ndarray:
            return librosa.util.sync(feature, frames, aggregate=np.mean)

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
        mel = librosa.feature.melspectrogram(y=y, sr=sr, hop_length=hop)
        logmel = librosa.power_to_db(mel, ref=np.max)
        rms = librosa.feature.rms(y=y, hop_length=hop)[0]

        chroma_sync = _sync(chroma, beat_frames)
        logmel_sync = _sync(logmel, beat_frames)
        rms_sync = _sync(rms.reshape(1, -1), beat_frames)

        # Weight RMS so energy influences the clustering while still respecting
        # harmonic similarity via chroma/log-mel.
        features = np.vstack([chroma_sync, logmel_sync, rms_sync * 5])

        # Determine a sensible number of segments based on duration.
        k = max(3, min(6, int(duration // 20)))
        k = min(k, len(beat_frames) // 2)

        # Affinity recurrence matrix + agglomerative segmentation.
        R = librosa.segment.recurrence_matrix(features, mode="affinity", width=3, sym=True)
        R = librosa.segment.path_enhance(R, 5)
        boundary_indices = librosa.segment.agglomerative(features, k)
        boundary_indices = sorted(set([0] + boundary_indices.tolist() + [len(beat_frames)]))

        boundary_times = [float(beat_times[min(i, len(beat_times) - 1)]) for i in boundary_indices]
        seg_energy = [
            float(np.mean(rms_sync[0, s:e]))
            for s, e in zip(boundary_indices[:-1], boundary_indices[1:])
        ]
        labels = _label_structure_segments(boundary_times, seg_energy)

        return [
            BeatSegment(start=start, end=end, label=label)
            for start, end, label in zip(boundary_times[:-1], boundary_times[1:], labels)
        ]
    except Exception as e:
        logger.warning("librosa structure analysis failed, falling back to equal chunks", error=str(e))
        try:
            y, sr = librosa.load(audio_path, sr=22050, mono=True)
            duration = librosa.get_duration(y=y, sr=sr)
        except Exception:
            duration = float(beat_times[-1]) if len(beat_times) else 30.0
        segment_len = max(duration / 4, 1.0)
        return [
            BeatSegment(start=i * segment_len, end=min((i + 1) * segment_len, duration), label=label)
            for i, label in enumerate(["intro", "verse", "chorus", "outro"])
        ]


def detect_beats_librosa(audio_path: str) -> BeatGrid:
    """Fallback beat detection using librosa."""
    if not _HAS_LIBROSA:
        raise ImportError("librosa is required for the librosa beat-detection fallback")

    y, sr = librosa.load(audio_path, sr=44100, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # Tempo and beat frames
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # Fallback: librosa often returns zero or near-zero beats for synthetic/
    # ambient audio (e.g. pure sine tones). Synthesize a regular grid from a
    # reliable tempo estimate so downstream cutlist generation always has
    # usable beat anchors.
    def _bpm_from_result(value):
        if isinstance(value, np.ndarray):
            value = value.item() if value.size == 1 else value[0]
        return float(value)

    estimated_bpm = _bpm_from_result(tempo)
    if estimated_bpm <= 0:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
        estimated_bpm = _bpm_from_result(onset_tempo)
    if estimated_bpm <= 0 or not np.isfinite(estimated_bpm):
        estimated_bpm = 120.0

    if len(beat_times) < 2:
        beat_period = 60.0 / estimated_bpm
        beat_times = np.arange(0.0, duration, beat_period)
        tempo = estimated_bpm

    # Downbeats: assume first beat is downbeat, then every 4th
    downbeats = beat_times[::4].tolist() if len(beat_times) > 0 else []

    # Real song-structure detection via chroma/energy clustering. If the
    # analysis fails for any reason we still fall back to equal chunks.
    segments = _detect_structure_librosa(audio_path, beat_times)

    bpm_value = _bpm_from_result(tempo)
    if bpm_value <= 0 or not np.isfinite(bpm_value):
        bpm_value = estimated_bpm

    beat_positions = ([1, 2, 3, 4] * (len(beat_times) // 4 + 1))[:len(beat_times)]

    return BeatGrid(
        bpm=bpm_value,
        beats=beat_times.tolist(),
        downbeats=downbeats,
        beat_positions=beat_positions,
        segments=segments,
    )


def detect_beats(
    audio_path: str,
    cache_dir: Optional[Path] = None,
    use_cache: bool = True,
) -> BeatGrid:
    """Detect beat grid. Cascade: madmom -> librosa -> synthetic 120 BPM grid.

    The synthetic grid guarantees that cutlist generation never crashes, even
    when every analyzer is unavailable or the audio is unanalyzable.
    Results are cached under ``<cache_dir>/<song_hash>/beatgrid.json``.
    """
    cache_dir = cache_dir or _default_cache_dir()
    song_hash = _song_hash(audio_path)
    cache_file = cache_dir / song_hash / "beatgrid.json"
    path_exists = Path(audio_path).exists()

    if use_cache and path_exists and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            grid = BeatGrid(**data)
            logger.info("beat grid loaded from cache", song_hash=song_hash)
            return grid
        except Exception as e:
            logger.warning("beat grid cache corrupt; recomputing", error=str(e))

    wav_path = decode_to_wav(audio_path)
    try:
        result = detect_beats_madmom(wav_path)
        if result is None:
            if _HAS_LIBROSA:
                try:
                    result = detect_beats_librosa(wav_path)
                except Exception as e:
                    logger.warning("librosa beat detection failed, using synthetic grid", error=str(e))
            if result is None:
                result = _synthetic_beat_grid(wav_path)

        if path_exists:
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                tmp = cache_file.with_suffix(".tmp")
                tmp.write_text(result.model_dump_json(), encoding="utf-8")
                tmp.replace(cache_file)
                logger.info("beat grid cached", song_hash=song_hash)
            except Exception as e:
                logger.warning("failed to write beat grid cache", error=str(e))
        return result
    finally:
        if os.path.exists(wav_path) and wav_path != audio_path:
            os.remove(wav_path)


def compute_energy_curve(audio_path: str, num_points: int = 64) -> list:
    """Compute normalized energy curve for the audio.

    If librosa is not installed, returns a flat default curve so callers do not
    crash with a ``NameError``.
    """
    if not _HAS_LIBROSA:
        logger.warning("librosa unavailable; returning flat energy curve", num_points=num_points)
        return [0.0] * num_points

    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    rms = librosa.feature.rms(y=y, hop_length=512)[0]

    # Smooth with Gaussian
    from scipy.ndimage import gaussian_filter1d
    rms_smooth = gaussian_filter1d(rms, sigma=sr / 512 * 0.2)

    # Sample num_points evenly
    indices = np.linspace(0, len(rms_smooth) - 1, num_points, dtype=int)
    samples = rms_smooth[indices]

    # Normalize to 0-1
    if samples.max() > 0:
        samples = samples / samples.max()
    return samples.tolist()
