# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Per-clip emotion profiling for narrative arc-driven editing.

The module is designed to be importable even when heavyweight dependencies
(DeepFace, transformers) are missing.  Inference only runs when dependencies are
present; otherwise it returns a neutral profile with low confidence.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from shared_py.feature_tracer import FeatureTracer
from shared_py.models import ClipEmotionProfile, EmotionSample, EmotionLabel

try:
    import cv2

    _CV2 = True
except Exception:  # pragma: no cover - optional dep
    _CV2 = False

try:
    import numpy as np

    _NUMPY = True
except Exception:  # pragma: no cover - optional dep
    np = None  # type: ignore[assignment]
    _NUMPY = False

try:
    from PIL import Image

    _PIL = True
except Exception:  # pragma: no cover - optional dep
    _PIL = False

try:
    from deepface import DeepFace

    _DEEPFACE = True
except Exception:  # pragma: no cover - optional dep
    _DEEPFACE = False

try:
    import librosa

    _LIBROSA = True
except Exception:  # pragma: no cover - optional dep
    librosa = None  # type: ignore[assignment]
    _LIBROSA = False

try:
    from transformers import pipeline

    _TRANSFORMERS = True
except Exception:  # pragma: no cover - optional dep
    _TRANSFORMERS = False


logger = logging.getLogger(__name__)

EMOTION_ORDER = ["joy", "calm", "intrigue", "tension", "grief", "triumph", "fear", "anger", "awe"]
DEFAULT_SAMPLE_FPS = 0.5
MAX_BATCH_FRAMES = 32

# DeepFace backend priority.  CPU-safe defaults when CUDA is missing.
DEEPFACE_BACKENDS = ["opencv", "ssd", "dlib", "mtcnn", "retinaface"]


def cache_path_for_clip(clip_path: str) -> str:
    """Return the JSON cache path for a given clip file."""
    return f"{clip_path}.emotion.json"


def _open_clip(clip_path: str):
    """Open a video capture and return metadata, or None on failure."""
    if not _CV2:
        logger.warning("cv2 not available; cannot open clip")
        return None
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        logger.warning("Could not open video for emotion extraction: %s", clip_path)
        return None
    video_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return cap, video_fps, total_frames, width, height


def _sample_frames_uniform(
    clip_path: str,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
) -> List[Tuple[int, object, float]]:
    """Sample frames uniformly from a clip.

    Returns a list of (frame_idx, frame, t_s) tuples.
    """
    opened = _open_clip(clip_path)
    if opened is None:
        return []
    cap, video_fps, total_frames, _, _ = opened
    sample_interval = max(1, int(round(video_fps / sample_fps)))

    frames: List[Tuple[int, object, float]] = []
    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % sample_interval == 0:
                t_s = frame_idx / video_fps
                frames.append((frame_idx, frame, t_s))
            frame_idx += 1
            if frame_idx > total_frames + 10:
                break
    finally:
        cap.release()
    return frames


def _deepface_analyze_safe(frame_bgr: object) -> Optional[dict]:
    """Run DeepFace analyze on a single BGR frame, returning the dominant emotion.

    Returns a dict with emotion distribution and dominant emotion, or None on
    failure.  The function tries multiple backends because DeepFace is brittle on
    Windows and with CPU-only installs.
    """
    if not _DEEPFACE or not _CV2:
        return None
    for backend in DEEPFACE_BACKENDS:
        try:
            result = DeepFace.analyze(
                img_path=frame_bgr,
                actions=["emotion"],
                enforce_detection=False,
                detector_backend=backend,
                silent=True,
            )
            if isinstance(result, list):
                result = result[0]
            return result
        except Exception as exc:
            logger.debug("DeepFace backend %s failed: %s", backend, exc)
            continue
    return None


def _extract_face_emotion(frames: List[Tuple[int, object, float]]) -> Tuple[Dict[str, float], float]:
    """Extract a fused face-emotion distribution from sampled frames.

    Uses DeepFace on frames most likely to contain a face (mid, 25%, 75%).
    Returns a normalized distribution and a confidence in [0, 1].
    """
    if not frames:
        return {}, 0.0

    indices_to_test = sorted({
        len(frames) // 4,
        len(frames) // 2,
        3 * len(frames) // 4,
    })

    aggregated: Dict[str, float] = {k: 0.0 for k in EMOTION_ORDER}
    successful = 0

    for idx in indices_to_test:
        _, frame, _ = frames[idx]
        result = _deepface_analyze_safe(frame)
        if result is None:
            continue
        emotion = result.get("emotion", {})
        if not emotion:
            continue
        for k in EMOTION_ORDER:
            aggregated[k] += emotion.get(k, 0.0)
        successful += 1

    if successful == 0:
        return {}, 0.0

    total = sum(aggregated.values())
    if total > 0:
        aggregated = {k: v / total for k, v in aggregated.items()}
    confidence = min(1.0, successful / len(indices_to_test))
    return aggregated, confidence


def _extract_audio_prosody(clip_path: str) -> Tuple[EmotionLabel, float, float]:
    """Extract audio prosody emotion and arousal from a clip.

    Uses a fast librosa heuristic by default.  Optionally tries a local
    Wav2Vec2 emotion classifier when ``AVE_USE_WAV2VEC2=1`` is set and the
    model is already cached, to avoid repeated slow downloads / disk-full
    failures during batch runs.
    """
    use_wav2vec2 = os.environ.get("AVE_USE_WAV2VEC2", "0").lower() in ("1", "true", "on")

    if use_wav2vec2 and _TRANSFORMERS and _model_is_cached():
        try:
            label, arousal, confidence = _wav2vec2_emotion(clip_path)
            if confidence > 0.3:
                return label, arousal, confidence
        except Exception as exc:
            logger.debug("Wav2Vec2 emotion inference failed: %s", exc)

    if _LIBROSA:
        try:
            return _librosa_prosody(clip_path)
        except Exception as exc:
            logger.debug("librosa prosody inference failed: %s", exc)

    return "calm", 0.3, 0.0


def _model_is_cached() -> bool:
    """Return True if the Wav2Vec2 emotion model is already on disk."""
    try:
        from transformers.utils import TRANSFORMERS_CACHE

        cache_root = Path(TRANSFORMERS_CACHE)
        marker = cache_root / "models--superb--wav2vec2-base-superb-er"
        return marker.exists()
    except Exception:
        return False


_wav2vec_pipe: Optional[object] = None


def _wav2vec2_emotion(clip_path: str) -> Tuple[EmotionLabel, float, float]:
    """Run a lightweight Wav2Vec2 emotion classifier on the clip audio.

    Uses the supervised emotion-recognition model from SUPERB.  The model is
    cached after first use.  If the model cannot be loaded, the function raises
    so the caller can fall back to the librosa heuristic.
    """
    global _wav2vec_pipe
    if _wav2vec_pipe is None:
        _wav2vec_pipe = pipeline(
            "audio-classification",
            model="superb/wav2vec2-base-superb-er",
            device=-1,
        )

    y, sr = librosa.load(clip_path, sr=16000, mono=True)  # type: ignore[misc]
    result = _wav2vec_pipe({"array": y, "sampling_rate": sr})
    if not result:
        raise RuntimeError("empty Wav2Vec2 result")

    label_map = {
        "ang": "anger",
        "hap": "joy",
        "sad": "grief",
        "neu": "calm",
        "exc": "joy",
        "fru": "anger",
    }
    top = result[0]
    raw_label = str(top.get("label", "neu")).lower()
    emotion = label_map.get(raw_label, "calm")
    confidence = float(top.get("score", 0.0))
    arousal = 0.7 if emotion in ("anger", "joy") else 0.4
    return emotion, arousal, confidence  # type: ignore[return-value]


def _librosa_prosody(clip_path: str) -> Tuple[EmotionLabel, float, float]:
    """Heuristic prosody using librosa.

    High RMS variance + high centroid => tension/anger.
    Low RMS variance + low centroid => calm/grief.
    Mid values => intrigue.
    """
    y, sr = librosa.load(clip_path, sr=22050, mono=True)  # type: ignore[misc]
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=512)[0]

    rms_mean = float(np.mean(rms))  # type: ignore[misc]
    rms_std = float(np.std(rms))
    centroid_mean = float(np.mean(centroid))  # type: ignore[misc]

    # Normalize to roughly [0, 1] using empirical ranges.
    energy = min(1.0, rms_mean / 0.15)
    instability = min(1.0, rms_std / 0.08)
    brightness = min(1.0, centroid_mean / 4000.0)

    arousal = 0.3 + 0.5 * energy + 0.2 * instability
    if arousal > 0.65 and brightness > 0.5:
        emotion = "anger"
    elif arousal > 0.65:
        emotion = "tension"
    elif arousal < 0.35 and brightness < 0.35:
        emotion = "grief"
    elif arousal < 0.35:
        emotion = "calm"
    else:
        emotion = "intrigue"

    confidence = 0.4 + 0.3 * instability
    return emotion, arousal, min(1.0, confidence)  # type: ignore[return-value]


def _extract_color_warmth(frames: List[Tuple[int, object, float]]) -> float:
    """Estimate color warmth in [-1, 1].

    Positive values indicate warm (red/orange) tones, negative values indicate
    cool (blue/cyan) tones.  Uses a rough RGB -> warmth heuristic so we do not
    need scikit-image or heavy color science dependencies.
    """
    if not frames or not _NUMPY:
        return 0.0

    mid_frame = frames[len(frames) // 2][1]
    rgb = cv2.cvtColor(mid_frame, cv2.COLOR_BGR2RGB).astype(np.float32)  # type: ignore[misc]
    r = np.mean(rgb[:, :, 0])
    g = np.mean(rgb[:, :, 1])
    b = np.mean(rgb[:, :, 2])
    total = r + g + b + 1e-6
    warmth = (r - b) / total
    return float(np.clip(warmth * 2.0, -1.0, 1.0))  # type: ignore[misc]


def _extract_motion_vibe(frames: List[Tuple[int, object, float]]) -> float:
    """Estimate motion intensity in [0, 1] from sparse optical flow.

    Uses Farneback optical flow between consecutive sampled frames.
    """
    if len(frames) < 2 or not _NUMPY:
        return 0.0

    prev_gray = cv2.cvtColor(frames[0][1], cv2.COLOR_BGR2GRAY)
    magnitudes: List[float] = []
    for _, frame, _ in frames[1:]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        magnitudes.append(float(np.mean(mag)))  # type: ignore[misc]
        prev_gray = gray

    if not magnitudes:
        return 0.0
    mean_mag = float(np.mean(magnitudes))  # type: ignore[misc]
    # Normalize: 0-5 pixels/frame is typical for handheld video.
    return float(np.clip(mean_mag / 5.0, 0.0, 1.0))  # type: ignore[misc]


def _distribution_to_primary(distribution: Dict[str, float]) -> EmotionLabel:
    if not distribution:
        return "calm"
    return max(distribution, key=distribution.get)  # type: ignore[return-value]


def _vad_from_distribution(distribution: Dict[str, float]) -> Tuple[float, float, float]:
    """Map a 9-class emotion distribution to VAD space.

    These mappings are approximate and derived from Russell's circumplex model
    and Plutchik's wheel, compressed to the 9 narrative classes.
    """
    valence_map = {
        "joy": 0.8,
        "calm": 0.4,
        "intrigue": 0.2,
        "tension": -0.3,
        "grief": -0.8,
        "triumph": 0.7,
        "fear": -0.7,
        "anger": -0.6,
        "awe": 0.3,
    }
    arousal_map = {
        "joy": 0.7,
        "calm": 0.2,
        "intrigue": 0.5,
        "tension": 0.7,
        "grief": 0.2,
        "triumph": 0.8,
        "fear": 0.8,
        "anger": 0.9,
        "awe": 0.6,
    }
    dominance_map = {
        "joy": 0.5,
        "calm": 0.4,
        "intrigue": 0.3,
        "tension": 0.2,
        "grief": 0.1,
        "triumph": 0.8,
        "fear": 0.1,
        "anger": 0.6,
        "awe": 0.3,
    }

    total = sum(distribution.values())
    if total == 0:
        return 0.0, 0.3, 0.3

    valence = sum(distribution.get(k, 0.0) * valence_map[k] for k in EMOTION_ORDER) / total
    arousal = sum(distribution.get(k, 0.0) * arousal_map[k] for k in EMOTION_ORDER) / total
    dominance = sum(distribution.get(k, 0.0) * dominance_map[k] for k in EMOTION_ORDER) / total
    return valence, arousal, dominance


def _build_timeline(
    frames: List[Tuple[int, object, float]],
    audio_label: EmotionLabel,
    audio_arousal: float,
) -> List[EmotionSample]:
    """Build a sparse timeline from sampled frames.

    Face emotion per frame is too expensive, so we reuse the audio prosody
    signal and interpolate a simple arousal curve from motion cues.
    """
    timeline: List[EmotionSample] = []
    if not frames:
        return timeline

    prev_gray = None
    for _, frame, t_s in frames:
        arousal = audio_arousal
        if _CV2 and _NUMPY:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                motion_arousal = float(np.clip(np.mean(mag) / 5.0, 0.0, 1.0))  # type: ignore[misc]
                arousal = 0.7 * arousal + 0.3 * motion_arousal
            prev_gray = gray
        timeline.append(
            EmotionSample(
                t_s=t_s,
                primary_emotion=audio_label,
                valence=0.0,
                arousal=arousal,
                dominance=0.5,
                confidence=0.3,
            )
        )
    return timeline


def compute_clip_emotion_profile(
    clip_path: str,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
) -> ClipEmotionProfile:
    """Compute (or load cached) emotion profile for a single clip."""
    cache_path = cache_path_for_clip(clip_path)
    cached = _load_emotion_cache(cache_path)
    if cached is not None:
        return cached

    with FeatureTracer("clip_emotion", gated_in=True) as ft:
        if not _CV2 or not _NUMPY:
            ft.fallback("cv2_or_numpy_unavailable")
            profile = _neutral_profile("cv2_or_numpy_unavailable")
            _write_emotion_cache(cache_path, profile)
            return profile

        frames = _sample_frames_uniform(clip_path, sample_fps=sample_fps)
        if not frames:
            ft.fallback("no_frames_sampled")
            profile = _neutral_profile("no_frames_sampled")
            _write_emotion_cache(cache_path, profile)
            return profile

        face_distribution, face_confidence = _extract_face_emotion(frames)
        audio_label, audio_arousal, audio_confidence = _extract_audio_prosody(clip_path)
        color_warmth = _extract_color_warmth(frames)
        motion_vibe = _extract_motion_vibe(frames)

        if face_distribution:
            primary = _distribution_to_primary(face_distribution)
            valence, arousal, dominance = _vad_from_distribution(face_distribution)
            confidence = face_confidence
        else:
            primary = audio_label
            valence = 0.0
            arousal = audio_arousal
            dominance = 0.5
            confidence = audio_confidence * 0.5

        timeline = _build_timeline(frames, audio_label, audio_arousal)

        profile = ClipEmotionProfile(
            primary_emotion=primary,
            valence=valence,
            arousal=arousal,
            dominance=dominance,
            face_emotion_distribution=face_distribution,
            audio_prosody_emotion=audio_label,
            audio_prosody_arousal=audio_arousal,
            color_warmth=color_warmth,
            motion_vibe=motion_vibe,
            confidence=confidence,
            timeline=timeline,
        )
        ft.signature(
            f"primary={primary},face_conf={face_confidence:.2f},audio_conf={audio_confidence:.2f},"
            f"motion={motion_vibe:.2f},warmth={color_warmth:.2f}"
        )
        _write_emotion_cache(cache_path, profile)
        return profile


def _neutral_profile(reason: str) -> ClipEmotionProfile:
    logger.warning("Returning neutral emotion profile (%s): %s", reason, reason)
    return ClipEmotionProfile(
        primary_emotion="calm",
        valence=0.0,
        arousal=0.3,
        dominance=0.3,
        confidence=0.0,
    )


def compute_clip_emotion_profiles(
    clip_paths: Dict[str, str],
    sample_fps: float = DEFAULT_SAMPLE_FPS,
) -> Dict[str, ClipEmotionProfile]:
    """Compute emotion profiles for multiple clips with disk caching.

    ``clip_paths`` maps clip_id -> filesystem path.  Results are written to
    ``{path}.emotion.json`` and returned as a dict keyed by clip_id.
    """
    results: Dict[str, ClipEmotionProfile] = {}
    for idx, (clip_id, clip_path) in enumerate(clip_paths.items()):
        logger.info(
            "Computing emotion profile %d/%d: %s",
            idx + 1,
            len(clip_paths),
            Path(clip_path).name,
        )
        try:
            results[clip_id] = compute_clip_emotion_profile(
                clip_path, sample_fps=sample_fps
            )
        except Exception as exc:
            logger.warning(
                "Emotion profile extraction failed for %s: %s; using neutral fallback",
                clip_path,
                exc,
            )
            results[clip_id] = _neutral_profile(str(exc))
    return results


def _profile_to_dict(profile: ClipEmotionProfile) -> dict:
    return profile.model_dump(by_alias=False, mode="json")


def _profile_from_dict(data: dict) -> Optional[ClipEmotionProfile]:
    try:
        return ClipEmotionProfile.model_validate(data)
    except Exception as exc:
        logger.warning("Failed to parse emotion cache: %s", exc)
        return None


def _load_emotion_cache(cache_path: str) -> Optional[ClipEmotionProfile]:
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _profile_from_dict(data)
    except Exception as exc:
        logger.warning("Failed to load emotion cache %s: %s", cache_path, exc)
    return None


def _write_emotion_cache(cache_path: str, profile: ClipEmotionProfile) -> None:
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(_profile_to_dict(profile), f, indent=2)
    except Exception as exc:
        logger.warning("Failed to write emotion cache %s: %s", cache_path, exc)
