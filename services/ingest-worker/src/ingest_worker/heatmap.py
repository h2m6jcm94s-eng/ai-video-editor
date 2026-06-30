# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Compute a per-clip "interestingness" heatmap used by the clip ranker."""

import hashlib
import json
import os
import platform
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from shared_py.feature_tracer import FeatureTracer
from shared_py.logging_config import StructuredLogger

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]

logger = StructuredLogger("ingest_worker.heatmap")


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


try:
    import librosa
    _HAS_LIBROSA = True
except ImportError:
    librosa = None  # type: ignore[assignment]
    _HAS_LIBROSA = False


@dataclass
class ClipWindow:
    start_s: float
    end_s: float
    score: float
    components: dict
    dominant_motion: str = "still"


# Tunable weights for the fused score.
# Face detection is omitted in this version because MediaPipe is not a project
# dependency yet; the weights are redistributed across motion, aesthetic,
# sharpness, audio, and stability.
WEIGHTS = {
    "motion": 0.30,
    "aesthetic": 0.25,
    "sharpness": 0.20,
    "audio": 0.15,
    "stability": 0.10,
}


# Target resolution for optical-flow analysis. 1080p flow is wasteful for a
# coarse motion score; 240p is plenty for direction + magnitude.
_FLOW_TARGET_HEIGHT = 240


def _default_max_workers() -> int:
    """Conservative default that avoids Windows memory-allocation crashes.

    Windows spawn-like overhead for PyTorch/CUDA + OpenCV FFmpeg backends can
    exhaust the paging file when too many threads allocate GPU/decoder memory
    concurrently. Limit to half the cores (max 4); Linux/Mac can use all cores.
    """
    cpu_count = os.cpu_count() or 1
    if platform.system() == "Windows":
        return min(4, cpu_count // 2)
    return cpu_count


def _sample_frames(
    video_path: str, stride_s: float, target_height: int = _FLOW_TARGET_HEIGHT
) -> List[tuple[float, np.ndarray]]:
    """Yield (timestamp, frame) pairs sampled evenly from the clip.

    Frames are resized to ``target_height`` before being returned so that
    downstream optical flow runs on smaller images.
    """
    if cv2 is None:
        logger.warning("cv2 not available, cannot sample frames")
        return []

    # Use the FFmpeg backend explicitly and release it in a finally block to
    # avoid leaking handles/decoder memory across threaded workers on Windows.
    cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        logger.warning("Failed to open video with FFmpeg backend", video_path=video_path)
        cap.release()
        return []

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0.0

        samples: List[tuple[float, np.ndarray]] = []
        step = max(1, int(stride_s * fps))
        for frame_idx in range(0, total_frames, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue
            timestamp = frame_idx / fps
            # Skip dark/letterboxed frames.
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_brightness = gray.mean()
            if 15 < mean_brightness < 240:
                # Downscale for flow; keep original for sharpness/aesthetic if needed.
                h, w = frame.shape[:2]
                if h > target_height:
                    scale = target_height / h
                    frame = cv2.resize(frame, (int(w * scale), target_height))
                samples.append((timestamp, frame))
    finally:
        cap.release()

    return samples


def _motion_energy(flows: List[np.ndarray]) -> float:
    if not flows:
        return 0.0
    magnitudes = [np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean() for flow in flows]
    return float(np.clip(np.mean(magnitudes) / 10.0, 0.0, 1.0))


def _dominant_motion(flows: List[np.ndarray]) -> str:
    """Return dominant motion direction (left/right/up/down/still) from optical flow."""
    if not flows:
        return "still"
    mean_flow = np.mean(np.stack(flows), axis=(0, 1, 2))
    dx, dy = float(mean_flow[0]), float(mean_flow[1])
    magnitude = np.sqrt(dx * dx + dy * dy)
    if magnitude < 0.5:
        return "still"
    if abs(dx) > abs(dy):
        return "left" if dx < 0 else "right"
    return "up" if dy < 0 else "down"


def _stability_score(flows: List[np.ndarray]) -> float:
    """High-frequency motion = shake (bad); low-frequency = intentional camera move (good)."""
    if not flows or len(flows) < 4:
        return 0.5
    magnitudes = np.array([np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean() for flow in flows])
    if magnitudes.std() < 1e-6:
        return 0.5
    fft = np.fft.rfft(magnitudes - magnitudes.mean())
    power = np.abs(fft) ** 2
    total = power.sum()
    if total == 0:
        return 0.5
    freqs = np.fft.rfftfreq(len(magnitudes))
    # Low frequencies (< 0.25 of Nyquist) are good; high frequencies are shake.
    low_freq_power = power[freqs <= 0.25].sum()
    return float(np.clip(low_freq_power / total, 0.0, 1.0))


def _sharpness_score(frame: np.ndarray) -> float:
    if cv2 is None:
        return 0.5
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.clip(cv2.Laplacian(gray, cv2.CV_64F).var() / 500.0, 0.0, 1.0))


def _audio_onset_score(audio_path: str, start_s: float, end_s: float) -> float:
    if not _HAS_LIBROSA or librosa is None:
        return 0.5
    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True, offset=start_s, duration=end_s - start_s)
        if y.size == 0:
            return 0.0
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        return float(np.clip(onset_env.mean() / onset_env.max() if onset_env.max() > 0 else 0.0, 0.0, 1.0))
    except Exception as e:
        logger.warning("Audio onset scoring failed", error=str(e))
        return 0.5


def _cache_key(video_path: str, window_s: float, stride_s: float, target_height: int) -> str:
    """Stable cache key based on file content + algorithm parameters."""
    path = Path(video_path)
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_mtime}|{stat.st_size}|{window_s}|{stride_s}|{target_height}|v1"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_path(video_path: str, cache_dir: Path, window_s: float, stride_s: float, target_height: int) -> Path:
    key = _cache_key(video_path, window_s, stride_s, target_height)
    return cache_dir / f"{key}.heatmap.json"


def compute_clip_heatmap(
    video_path: str,
    audio_path: Optional[str] = None,
    window_s: float = 0.5,
    stride_s: float = 0.25,
    target_height: int = _FLOW_TARGET_HEIGHT,
) -> List[ClipWindow]:
    """Score every ``window_s`` window of the clip on multiple axes.

    Returns a list of ClipWindow objects with a fused 0..1 score and the
    per-component breakdown.
    """
    with FeatureTracer("heatmap", gated_in=True) as ft:
        if cv2 is None:
            ft.fallback("cv2_unavailable")
            logger.warning("cv2 not available, cannot compute heatmap")
            return []

        samples = _sample_frames(video_path, stride_s, target_height=target_height)
        if not samples:
            ft.fallback("no_sampled_frames")
            return []

        # Compute optical flow between consecutive samples.
        flows: List[np.ndarray] = []
        for i in range(1, len(samples)):
            prev_gray = cv2.cvtColor(samples[i - 1][1], cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(samples[i][1], cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray,
                curr_gray,
                None,
                pyr_scale=0.5,
                levels=3,
                winsize=15,
                iterations=3,
                poly_n=5,
                poly_sigma=1.2,
                flags=0,
            )
            flows.append(flow)

        from shared_py.aesthetic import score_image

        duration = samples[-1][0] + stride_s if samples else 0.0
        windows: List[ClipWindow] = []

        # Score windows centered on each sample timestamp.
        for i, (timestamp, frame) in enumerate(samples):
            start_s = max(0.0, timestamp - window_s / 2)
            end_s = min(duration, timestamp + window_s / 2)

            window_flows = flows[max(0, i - 1) : i + 1]
            components = {
                "motion": _motion_energy(window_flows),
                "aesthetic": score_image(frame),
                "sharpness": _sharpness_score(frame),
                "audio": _audio_onset_score(audio_path, start_s, end_s) if audio_path else 0.5,
                "stability": _stability_score(flows[max(0, i - 2) : i + 2]),
            }

            score = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
            windows.append(
                ClipWindow(
                    start_s=round(start_s, 3),
                    end_s=round(end_s, 3),
                    score=round(score, 4),
                    components={k: round(v, 4) for k, v in components.items()},
                    dominant_motion=_dominant_motion(window_flows),
                )
            )

        ft.signature(f"windows={len(windows)},duration={round(duration, 3)}")
        ft.real()
        return windows


def compute_clip_heatmap_cached(
    video_path: str,
    audio_path: Optional[str] = None,
    window_s: float = 0.5,
    stride_s: float = 0.25,
    target_height: int = _FLOW_TARGET_HEIGHT,
    cache_dir: Optional[Path] = None,
) -> List[ClipWindow]:
    """Compute heatmap with disk caching.

    This function is executed inside a thread-pool worker. We keep it
    thread-safe by isolating per-worker state: each worker can set the CUDA
    memory fraction (harmless for threads, meaningful when the same code is
    ever run in a process pool) and, on Windows, switch the C allocator to
    ``malloc`` via ``PYTHONMALLOC`` to work around allocator fragmentation that
    can trigger memory-allocation errors during parallel FFmpeg decoding.
    """
    if platform.system() == "Windows" and os.environ.get("PYTHONMALLOC") is None:
        # Workaround for Windows parallel heatmap memory errors (GPU-1, O.4).
        # The default Python allocator can fragment when many threads decode
        # video concurrently; malloc is more stable for this workload.
        os.environ["PYTHONMALLOC"] = "malloc"

    if torch is not None and torch.cuda.is_available():
        # Only meaningful for processes, harmless for threads. Keeps the same
        # worker safe if it is ever reused inside a process pool.
        torch.cuda.set_per_process_memory_fraction(0.4)

    cache_dir = cache_dir or Path(os.environ.get("AVE_HEATMAP_CACHE_DIR", ".heatmap-cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(video_path, cache_dir, window_s, stride_s, target_height)

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return [ClipWindow(**w) for w in data]
        except Exception as e:
            logger.warning("Heatmap cache read failed, recomputing", error=str(e))

    windows = compute_clip_heatmap(video_path, audio_path, window_s, stride_s, target_height)
    if windows:
        try:
            cache_file.write_text(
                json.dumps(
                    [
                        {
                            "start_s": w.start_s,
                            "end_s": w.end_s,
                            "score": w.score,
                            "components": w.components,
                            "dominant_motion": w.dominant_motion,
                        }
                        for w in windows
                    ],
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Heatmap cache write failed", error=str(e))
    else:
        logger.warning(
            "Heatmap computation returned no windows; skipping cache write so the next run retries",
            video_path=video_path,
        )

    return windows


def compute_clip_heatmaps_batch(
    video_paths: List[str],
    audio_path: Optional[str] = None,
    window_s: float = 0.5,
    stride_s: float = 0.25,
    target_height: int = _FLOW_TARGET_HEIGHT,
    cache_dir: Optional[Path] = None,
    max_workers: Optional[int] = None,
) -> Dict[str, List[ClipWindow]]:
    """Compute heatmaps for many clips in parallel with disk caching.

    Uses a thread pool rather than a process pool so Windows spawn does not
    need to reload PyTorch/CUDA libraries in every worker, which can exhaust
    the paging file and crash the pool.
    """
    from concurrent.futures import ThreadPoolExecutor

    cache_dir = cache_dir or Path(os.environ.get("AVE_HEATMAP_CACHE_DIR", ".heatmap-cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Load cached results first.
    results: Dict[str, List[ClipWindow]] = {}
    to_compute: List[str] = []
    from_cache = 0
    for path in video_paths:
        cache_file = _cache_path(path, cache_dir, window_s, stride_s, target_height)
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                results[path] = [ClipWindow(**w) for w in data]
                from_cache += 1
                continue
            except Exception as e:
                logger.warning("Heatmap cache read failed, recomputing", error=str(e))
        to_compute.append(path)

    if to_compute:
        workers = max_workers if max_workers is not None else _default_max_workers()
        logger.info("Computing heatmaps in parallel", clips=len(to_compute), workers=workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            computed = list(
                pool.map(
                    compute_clip_heatmap_cached,
                    to_compute,
                    [audio_path] * len(to_compute),
                    [window_s] * len(to_compute),
                    [stride_s] * len(to_compute),
                    [target_height] * len(to_compute),
                    [cache_dir] * len(to_compute),
                )
            )
        computed_count = 0
        empty_count = 0
        for path, windows in zip(to_compute, computed):
            results[path] = windows
            computed_count += 1
            if not windows:
                empty_count += 1
        logger.info(
            "Heatmap batch complete",
            from_cache=from_cache,
            computed=computed_count,
            empty=empty_count,
            total=len(video_paths),
        )
    else:
        logger.info("Heatmap batch complete (all from cache)", from_cache=from_cache, total=len(video_paths))

    return results


def heatmap_to_metadata(windows: List[ClipWindow]) -> List[dict]:
    """Convert ClipWindow objects to JSON-serializable metadata."""
    return [
        {
            "start_s": w.start_s,
            "end_s": w.end_s,
            "score": w.score,
            "components": w.components,
            "dominant_motion": w.dominant_motion,
        }
        for w in windows
    ]
