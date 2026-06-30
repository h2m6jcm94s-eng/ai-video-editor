# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for shared reference analysis cache."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

try:
    import cv2
except Exception:  # pragma: no cover - optional dep
    cv2 = None

from style_worker.reference_analysis import (
    EXTRACTOR_VERSION,
    ReferenceAnalysis,
    _compute_quality_score,
    _load_cached_analysis,
    analyze_reference,
)


@pytest.fixture
def reference_video(tmp_path: Path) -> str:
    """Create a tiny synthetic reference video with one hard cut."""
    if cv2 is None:
        pytest.skip("OpenCV not available")

    path = str(tmp_path / "reference.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 30.0, (640, 480))
    if not writer.isOpened():
        pytest.skip("Could not open video writer")

    for frame_idx in range(90):
        # First half blue-ish, second half red-ish to create a cut + color variance.
        if frame_idx < 45:
            color = (200, 100, 50)
        else:
            color = (50, 80, 200)
        frame = np.full((480, 640, 3), color, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


def test_quality_score_high_for_good_video():
    info = {
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "duration_s": 30.0,
        "file_size_bytes": 50 * 1024 * 1024,
    }
    score = _compute_quality_score(info, [object() for _ in range(10)])
    assert 0.5 <= score <= 1.0


def test_quality_score_low_for_tiny_video():
    info = {
        "width": 320,
        "height": 240,
        "fps": 15.0,
        "duration_s": 1.0,
        "file_size_bytes": 10 * 1024,
    }
    score = _compute_quality_score(info, [object() for _ in range(2)])
    assert 0.0 <= score <= 0.4


def test_analyze_reference_returns_full_analysis(reference_video: str):
    analysis = analyze_reference(reference_video)

    assert isinstance(analysis, ReferenceAnalysis)
    assert analysis.extractor_version == EXTRACTOR_VERSION
    assert analysis.quality_score > 0.0
    assert analysis.lut_path is not None
    assert len(analysis.shot_boundaries) >= 1
    assert analysis.style_analysis is not None
    assert analysis.style_genome is not None
    assert analysis.technical_quality.width == 640
    assert analysis.technical_quality.height == 480


def test_analyze_reference_detects_low_quality(reference_video: str, tmp_path: Path):
    # Make a tiny, low-res copy.
    tiny_path = str(tmp_path / "tiny.mp4")
    if cv2 is None:
        pytest.skip("OpenCV not available")
    cap = cv2.VideoCapture(reference_video)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(tiny_path, fourcc, 20.0, (240, 180))
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        writer.write(cv2.resize(frame, (240, 180)))
    cap.release()
    writer.release()

    analysis = analyze_reference(tiny_path)
    assert analysis.quality_score < 0.5
    assert any("low" in w.lower() or "resolution" in w.lower() for w in analysis.warnings)


def test_cache_hit_returns_same_object(reference_video: str):
    first = analyze_reference(reference_video, asset_id="asset-1")
    cached_dict = first.model_dump()

    second = _load_cached_analysis({"referenceAnalysis": cached_dict})
    assert second is not None
    assert second.extractor_version == EXTRACTOR_VERSION
    assert second.quality_score == pytest.approx(first.quality_score)
    assert len(second.shot_boundaries) == len(first.shot_boundaries)


def test_cache_miss_on_version_mismatch(reference_video: str):
    first = analyze_reference(reference_video, asset_id="asset-1")
    cached_dict = first.model_dump()
    cached_dict["extractorVersion"] = "0.0.0"

    assert _load_cached_analysis({"referenceAnalysis": cached_dict}) is None


def test_model_dump_round_trip(reference_video: str):
    analysis = analyze_reference(reference_video, asset_id="asset-1")
    dumped = analysis.model_dump()
    rehydrated = ReferenceAnalysis.from_cache_dict(dumped)

    assert rehydrated.asset_id == analysis.asset_id
    assert rehydrated.quality_score == pytest.approx(analysis.quality_score)
    assert rehydrated.is_consistent_style == analysis.is_consistent_style
    assert rehydrated.lut_path == analysis.lut_path
    assert len(rehydrated.warnings) == len(analysis.warnings)
