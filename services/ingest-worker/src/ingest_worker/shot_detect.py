# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Shot boundary detection using PySceneDetect + optional TransNet V2."""

import os
from typing import List
import numpy as np

try:
    from scenedetect import detect, ContentDetector, ThresholdDetector
except ImportError:
    detect = None
    ContentDetector = None
    ThresholdDetector = None

try:
    import torch
    from transnetv2 import TransNetV2
except ImportError:
    torch = None
    TransNetV2 = None

from shared_py.logging_config import StructuredLogger
from shared_py.models import ShotBoundary

logger = StructuredLogger("ingest_worker.shot_detect")

try:
    import av
except ImportError:
    av = None  # type: ignore[assignment]

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


def detect_shot_boundaries_pyscenedetect(
    video_path: str, threshold: float = 27.0
) -> List[ShotBoundary]:
    """Fast shot detection using PySceneDetect content detector."""
    if detect is None:
        raise ImportError("scenedetect not installed")

    scene_list = detect(video_path, ContentDetector(threshold=threshold))
    boundaries = []

    for i, scene in enumerate(scene_list):
        boundaries.append(
            ShotBoundary(
                start_frame=scene[0].get_frames(),
                end_frame=scene[1].get_frames(),
                start_s=scene[0].get_seconds(),
                end_s=scene[1].get_seconds(),
                is_gradual=False,
                confidence=0.8,
            )
        )

    return boundaries


def detect_shot_boundaries_transnet(
    video_path: str, device: str = "cpu", fps: float = 30.0
) -> List[ShotBoundary]:
    """Higher-quality shot detection using TransNet V2."""
    if TransNetV2 is None or torch is None:
        raise ImportError("transnetv2 or torch not installed")

    model = TransNetV2()
    if device == "cuda" and torch.cuda.is_available():
        model = model.cuda()
    model.eval()

    # Read video frames at TransNet's native resolution (48x27)
    if av is None:
        raise ImportError("av not installed")
    container = av.open(video_path)
    stream = container.streams.video[0]

    frames = []
    for packet in container.demux(stream):
        for frame in packet.decode():
            # Resize to 48x27
            img = frame.to_ndarray(format="rgb24")
            if cv2 is None:
                raise ImportError("cv2 not installed")
            img = cv2.resize(img, (48, 27), interpolation=cv2.INTER_LINEAR)
            frames.append(img)

    container.close()

    if not frames:
        return []

    frames_arr = np.stack(frames).astype(np.float32) / 255.0
    frames_tensor = torch.from_numpy(frames_arr).unsqueeze(0)
    if device == "cuda" and torch.cuda.is_available():
        frames_tensor = frames_tensor.cuda()

    with torch.no_grad():
        single_frame_pred, all_frames_pred = model(frames_tensor)

    # Get shot boundaries from predictions
    probs = torch.sigmoid(single_frame_pred).cpu().numpy()[0]
    boundaries = []

    # Find peaks above threshold
    threshold = 0.5
    from scipy.signal import find_peaks
    peaks, _ = find_peaks(probs[:, 0], height=threshold, distance=8)

    # Also get gradual transitions from all_frames_pred
    gradual_probs = torch.sigmoid(all_frames_pred).cpu().numpy()[0] if all_frames_pred is not None else None

    prev_end = 0
    for peak in peaks:
        is_gradual = False
        if gradual_probs is not None and peak < len(gradual_probs):
            is_gradual = gradual_probs[peak, 0] > 0.3

        boundaries.append(
            ShotBoundary(
                start_frame=prev_end,
                end_frame=int(peak),
                start_s=prev_end / fps,  # approximate
                end_s=int(peak) / fps,
                is_gradual=is_gradual,
                confidence=float(probs[peak, 0]),
            )
        )
        prev_end = int(peak)

    # Add final shot
    if frames_arr.shape[0] > prev_end:
        boundaries.append(
            ShotBoundary(
                start_frame=prev_end,
                end_frame=frames_arr.shape[0],
                start_s=prev_end / fps,
                end_s=frames_arr.shape[0] / fps,
                is_gradual=False,
                confidence=1.0,
            )
        )

    return boundaries


def detect_shot_boundaries(
    video_path: str, use_transnet: bool = False, device: str = "cpu", fps: float = 30.0
) -> List[ShotBoundary]:
    """Detect shot boundaries. Uses PySceneDetect by default, TransNet V2 if available."""
    if use_transnet and TransNetV2 is not None:
        try:
            return detect_shot_boundaries_transnet(video_path, device, fps)
        except Exception as e:
            logger.warning("TransNet failed, falling back to PySceneDetect", error=str(e))
            return detect_shot_boundaries_pyscenedetect(video_path)
    return detect_shot_boundaries_pyscenedetect(video_path)
