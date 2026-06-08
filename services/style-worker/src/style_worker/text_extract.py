# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Extract text overlays using PaddleOCR + frame deduplication."""

from typing import List
import numpy as np

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

try:
    from paddleocr import PaddleOCR
except ImportError:
    PaddleOCR = None

from shared_py.models import Overlay


def extract_text_overlays(
    video_path: str,
    fps_sample: float = 5.0,
    iou_threshold: float = 0.5,
) -> List[Overlay]:
    """Extract text overlays from video using PaddleOCR."""
    if PaddleOCR is None:
        return []

    ocr = PaddleOCR(
        use_angle_cls=True,
        lang="en",
        show_log=False,
        use_gpu=False,
    )

    cap = cv2.VideoCapture(video_path)
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_interval = int(video_fps / fps_sample)

    detections = []  # List of (text, bbox, frame_idx)

    frame_idx = 0
    while frame_idx < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        result = ocr.ocr(frame, cls=True)
        if result and result[0]:
            for line in result[0]:
                bbox = line[0]
                text = line[1][0]
                conf = line[1][1]
                if conf > 0.7 and len(text.strip()) > 1:
                    detections.append({
                        "text": text,
                        "bbox": bbox,
                        "frame_idx": frame_idx,
                    })

        frame_idx += sample_interval

    cap.release()

    # Group detections into tracks using IoU
    tracks = []
    for det in detections:
        matched = False
        for track in tracks:
            if track["text"] == det["text"]:
                # Check IoU with last bbox in track
                last_bbox = track["bboxes"][-1]
                iou = compute_iou(det["bbox"], last_bbox)
                if iou > iou_threshold:
                    track["bboxes"].append(det["bbox"])
                    track["frames"].append(det["frame_idx"])
                    matched = True
                    break

        if not matched:
            tracks.append({
                "text": det["text"],
                "bboxes": [det["bbox"]],
                "frames": [det["frame_idx"]],
            })

    # Convert tracks to overlays
    overlays = []
    for track in tracks:
        if len(track["frames"]) < 2:
            continue  # Require at least 2 frames

        start_frame = min(track["frames"])
        end_frame = max(track["frames"])
        start_s = start_frame / video_fps
        end_s = end_frame / video_fps

        # Estimate position from bbox
        # bbox is [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        avg_bbox = np.mean(track["bboxes"], axis=0)
        center_x = (avg_bbox[0][0] + avg_bbox[2][0]) / 2
        center_y = (avg_bbox[0][1] + avg_bbox[2][1]) / 2

        # Determine position zone
        h, w = 1080, 1920  # Assume 1080p, will be overridden by actual frame size
        position = "center"
        if center_y < h * 0.3:
            position = "top" if center_x > w * 0.3 and center_x < w * 0.7 else "top_left" if center_x < w * 0.5 else "top_right"
        elif center_y > h * 0.7:
            position = "bottom" if center_x > w * 0.3 and center_x < w * 0.7 else "bottom_left" if center_x < w * 0.5 else "bottom_right"

        overlays.append(Overlay(
            text=track["text"],
            start_s=start_s,
            end_s=end_s,
            position=position,
            font="DejaVuSans-Bold",
            font_size_px=48,
            color="#FFFFFF",
            stroke="#000000",
            animation="fade",
        ))

    return overlays


def compute_iou(bbox1, bbox2):
    """Compute IoU between two quadrilateral bboxes."""
    # Convert to axis-aligned bounding boxes for simplicity
    x1_min = min(p[0] for p in bbox1)
    y1_min = min(p[1] for p in bbox1)
    x1_max = max(p[0] for p in bbox1)
    y1_max = max(p[1] for p in bbox1)

    x2_min = min(p[0] for p in bbox2)
    y2_min = min(p[1] for p in bbox2)
    x2_max = max(p[0] for p in bbox2)
    y2_max = max(p[1] for p in bbox2)

    xi_min = max(x1_min, x2_min)
    yi_min = max(y1_min, y2_min)
    xi_max = min(x1_max, x2_max)
    yi_max = min(y1_max, y2_max)

    inter_area = max(0, xi_max - xi_min) * max(0, yi_max - yi_min)
    area1 = (x1_max - x1_min) * (y1_max - y1_min)
    area2 = (x2_max - x2_min) * (y2_max - y2_min)
    union_area = area1 + area2 - inter_area

    return inter_area / union_area if union_area > 0 else 0.0
