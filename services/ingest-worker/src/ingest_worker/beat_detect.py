# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Beat, downbeat, and section detection using allin1 + librosa fallback."""

import os
import tempfile
from typing import Optional
import numpy as np
import librosa
import soundfile as sf

from shared_py.models import BeatGrid, BeatSegment


def decode_to_wav(input_path: str) -> str:
    """Decode any audio to 44.1kHz WAV PCM."""
    import subprocess
    wav_path = os.path.join(tempfile.gettempdir(), f"{os.path.basename(input_path)}.wav")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
        wav_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace")[:1000] if e.stderr else ""
        raise RuntimeError(
            f"FFmpeg decode_to_wav failed (exit {e.returncode}): {stderr}"
        ) from e
    return wav_path


def detect_beats_allin1(audio_path: str) -> Optional[BeatGrid]:
    """Try allin1 for beats + downbeats + sections."""
    try:
        from allin1 import analyze
        result = analyze(audio_path)

        return BeatGrid(
            bpm=result.bpm,
            beats=result.beats.tolist() if hasattr(result.beats, "tolist") else list(result.beats),
            downbeats=result.downbeats.tolist() if hasattr(result.downbeats, "tolist") else list(result.downbeats),
            beat_positions=result.beat_positions.tolist() if hasattr(result.beat_positions, "tolist") else list(result.beat_positions),
            segments=[
                BeatSegment(start=s.start, end=s.end, label=s.label)
                for s in result.segments
            ],
        )
    except ImportError:
        return None
    except Exception as e:
        print(f"allin1 failed: {e}")
        return None


def detect_beats_librosa(audio_path: str) -> BeatGrid:
    """Fallback beat detection using librosa."""
    y, sr = librosa.load(audio_path, sr=44100, mono=True)

    # Tempo and beat frames
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # Downbeats: assume first beat is downbeat, then every 4th
    downbeats = beat_times[::4].tolist() if len(beat_times) > 0 else []

    # Simple section detection using onset strength clustering
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    # Divide into 4 roughly equal segments as a naive approach
    duration = librosa.get_duration(y=y, sr=sr)
    segment_len = duration / 4
    segments = [
        BeatSegment(start=i * segment_len, end=min((i + 1) * segment_len, duration), label=label)
        for i, label in enumerate(["intro", "verse", "chorus", "outro"])
    ]

    return BeatGrid(
        bpm=float(tempo) if isinstance(tempo, (int, float, np.number)) else float(tempo[0]),
        beats=beat_times.tolist(),
        downbeats=downbeats,
        beat_positions=[1, 2, 3, 4] * (len(beat_times) // 4 + 1),
        segments=segments,
    )


def detect_beats(audio_path: str) -> BeatGrid:
    """Detect beat grid. Try allin1 first, fall back to librosa."""
    wav_path = decode_to_wav(audio_path)

    try:
        result = detect_beats_allin1(wav_path)
        if result is not None:
            return result
    finally:
        if os.path.exists(wav_path) and wav_path != audio_path:
            os.remove(wav_path)

    return detect_beats_librosa(audio_path)


def compute_energy_curve(audio_path: str, n_points: int = 10) -> list:
    """Compute normalized energy curve for the audio."""
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    rms = librosa.feature.rms(y=y, hop_length=512)[0]

    # Smooth with Gaussian
    from scipy.ndimage import gaussian_filter1d
    rms_smooth = gaussian_filter1d(rms, sigma=sr / 512 * 0.2)

    # Sample n_points evenly
    indices = np.linspace(0, len(rms_smooth) - 1, n_points, dtype=int)
    samples = rms_smooth[indices]

    # Normalize to 0-1
    if samples.max() > 0:
        samples = samples / samples.max()
    return samples.tolist()
