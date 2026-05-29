# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Analyze camera motion from video frames."""

from typing import List
import numpy as np
import cv2



def analyze_camera_motion(video_path: str, shot_boundaries: list) -> List[str]:
    """Analyze camera motion per shot."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    motions = []

    for shot in shot_boundaries:
        start_frame = shot.start_frame
        end_frame = shot.end_frame
        if end_frame <= start_frame + 1:
            motions.append("static")
            continue

        frames = []
        for f in range(start_frame, min(end_frame, total_frames)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frames.append(gray)

        if len(frames) < 2:
            motions.append("static")
            continue

        # Compute optical flow between consecutive frames
        flows = []
        for i in range(len(frames) - 1):
            flow = cv2.calcOpticalFlowFarneback(
                frames[i], frames[i + 1], None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
            )
            flows.append(flow)

        if not flows:
            motions.append("static")
            continue

        # Fit affine transformation
        # Use good features to track
        p0 = cv2.goodFeaturesToTrack(frames[0], maxCorners=100, qualityLevel=0.3, minDistance=7)
        if p0 is None:
            motions.append("static")
            continue

        transforms = []
        for i in range(len(flows)):
            p1, st, err = cv2.calcOpticalFlowPyrLK(frames[i], frames[i + 1], p0, None)
            if p1 is not None:
                good_prev = p0[st == 1]
                good_next = p1[st == 1]
                if len(good_prev) >= 3:
                    M, inliers = cv2.estimateAffinePartial2D(
                        good_prev, good_next, method=cv2.RANSAC, ransacReprojThreshold=3.0
                    )
                    if M is not None:
                        transforms.append(M)
                # Update tracking points for next iteration
                if len(good_next) > 0:
                    p0 = good_next.reshape(-1, 1, 2).astype(np.float32)

        if not transforms:
            motions.append("static")
            continue

        # Analyze transform parameters
        tx_values = [t[0, 2] for t in transforms]
        ty_values = [t[1, 2] for t in transforms]
        # Extract scale and rotation from 2x2 part
        scales = []
        rotations = []
        for t in transforms:
            a, b = t[0, 0], t[0, 1]
            scale = np.sqrt(a * a + b * b)
            rot = np.arctan2(b, a) * 180 / np.pi
            scales.append(scale)
            rotations.append(rot)

        # Classify motion
        tx_std = np.std(tx_values)
        ty_std = np.std(ty_values)
        tx_trend = np.polyfit(range(len(tx_values)), tx_values, 1)[0]
        ty_trend = np.polyfit(range(len(ty_values)), ty_values, 1)[0]
        scale_mean = np.mean(scales)
        scale_std = np.std(scales)

        # Heuristics
        if abs(tx_trend) < 0.5 and abs(ty_trend) < 0.5 and scale_std < 0.01:
            if tx_std > 2 or ty_std > 2:
                motions.append("handheld")
            else:
                motions.append("static")
        elif abs(tx_trend) > abs(ty_trend) * 2:
            motions.append("pan_right" if tx_trend > 0 else "pan_left")
        elif abs(ty_trend) > abs(tx_trend) * 2:
            motions.append("tilt_down" if ty_trend > 0 else "tilt_up")
        elif scale_std > 0.02:
            if scale_mean > 1.0:
                motions.append("zoom_in")
            else:
                motions.append("zoom_out")
        else:
            motions.append("gimbal")

    cap.release()
    return motions
