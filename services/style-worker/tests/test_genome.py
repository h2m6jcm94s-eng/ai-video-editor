# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for the Style Genome extractor."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

try:
    import cv2
except Exception:  # pragma: no cover - optional dep
    cv2 = None

from style_worker.genome.extract import extract_genome
from style_worker.genome.storage import load_genome_json, save_genome_json


@pytest.fixture
def reference_video(tmp_path: Path) -> str:
    """Create a tiny synthetic reference video with one hard cut."""
    if cv2 is None:
        pytest.skip("OpenCV not available")

    path = str(tmp_path / "reference.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 30.0, (320, 240))
    if not writer.isOpened():
        pytest.skip("Could not open video writer")

    for frame_idx in range(60):
        color = (255, 255, 255) if frame_idx < 30 else (0, 0, 0)
        frame = np.full((240, 320, 3), color, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


def _all_numeric_leaves_are_finite(obj: Any, allow_strings: set[str]) -> None:
    """Recursively assert every numeric leaf is finite."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in allow_strings and isinstance(value, str):
                continue
            _all_numeric_leaves_are_finite(value, allow_strings)
    elif isinstance(obj, list):
        for value in obj:
            _all_numeric_leaves_are_finite(value, allow_strings)
    elif isinstance(obj, (int, float)):
        assert math.isfinite(obj), f"non-finite numeric value: {obj}"
    elif isinstance(obj, str):
        assert obj in allow_strings, f"unexpected string leaf: {obj}"
    elif obj is not None:
        pytest.fail(f"unexpected leaf type: {type(obj)}")


def test_extract_genome_returns_50_features(reference_video: str) -> None:
    genome = extract_genome(reference_video)

    assert genome["version"] == "0.1.0"
    assert genome["featureCount"] == 50
    assert "families" in genome
    assert "extractedAt" in genome

    _all_numeric_leaves_are_finite(
        genome,
        allow_strings={"dominantShotSize", "version", "extractedAt"},
    )


def test_cut_rhythm_family_has_15_features(reference_video: str) -> None:
    genome = extract_genome(reference_video)
    cut_rhythm = genome["families"]["cutRhythm"]
    assert len(cut_rhythm) == 15
    expected = {
        "totalCuts",
        "avgCutDurationS",
        "stdCutDurationS",
        "minCutDurationS",
        "maxCutDurationS",
        "cutDensityPerMin",
        "verseCutDensity",
        "chorusCutDensity",
        "dropCutDensity",
        "introCutDensity",
        "outroCutDensity",
        "buildUpCutDensity",
        "hardCutRatio",
        "gradualTransitionRatio",
        "cutsOnDownbeatRatio",
    }
    assert set(cut_rhythm.keys()) == expected


def test_motion_family_has_12_features(reference_video: str) -> None:
    genome = extract_genome(reference_video)
    motion = genome["families"]["motion"]
    assert len(motion) == 12
    expected = {
        "avgMotionEnergy",
        "maxMotionEnergy",
        "motionEnergyStd",
        "pctStillShots",
        "pctPanLeft",
        "pctPanRight",
        "pctTiltUp",
        "pctTiltDown",
        "pctZoomIn",
        "pctZoomOut",
        "pctHandheld",
        "pctGimbal",
    }
    assert set(motion.keys()) == expected


def test_dwell_family_has_8_features(reference_video: str) -> None:
    genome = extract_genome(reference_video)
    dwell = genome["families"]["dwell"]
    assert len(dwell) == 8
    expected = {
        "avgFaceSizeRatio",
        "maxFaceSizeRatio",
        "avgSubjectsPerShot",
        "pctShotsWithFace",
        "avgFaceScreenTimeS",
        "protagonistPresentRatio",
        "avgShotSubjectCount",
        "faceSizeVariance",
    }
    assert set(dwell.keys()) == expected


def test_audio_align_family_has_10_features(reference_video: str) -> None:
    genome = extract_genome(reference_video)
    audio_align = genome["families"]["audioAlign"]
    assert len(audio_align) == 10
    expected = {
        "cutToBeatAlignment",
        "cutToDownbeatAlignment",
        "verseCutToBeatRatio",
        "chorusCutToBeatRatio",
        "dropCutToBeatRatio",
        "avgCutToNearestBeatS",
        "musicDuckFrequency",
        "dialogueClipRatio",
        "iconicLineCount",
        "avgDialogueDurationS",
    }
    assert set(audio_align.keys()) == expected


def test_composition_family_has_5_features(reference_video: str) -> None:
    genome = extract_genome(reference_video)
    composition = genome["families"]["composition"]
    assert len(composition) == 5
    expected = {
        "dominantShotSize",
        "pctCloseUp",
        "pctMediumShot",
        "pctWideShot",
        "ruleOfThirdsRatio",
    }
    assert set(composition.keys()) == expected
    assert composition["dominantShotSize"] in {"close_up", "medium", "wide"}


def test_save_and_load_genome_json(reference_video: str, tmp_path: Path) -> None:
    genome = extract_genome(reference_video)
    output_path = str(tmp_path / "genome.json")
    save_genome_json(genome, output_path)
    loaded = load_genome_json(output_path)

    assert loaded["version"] == genome["version"]
    assert loaded["featureCount"] == genome["featureCount"]
    assert loaded["families"] == genome["families"]
    assert loaded["extractedAt"] == genome["extractedAt"]
