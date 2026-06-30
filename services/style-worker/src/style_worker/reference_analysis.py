# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Shared, cached reference analysis — single source of truth for LUT, style,
shot boundaries, genome, and quality warnings derived from a reference video.

``analyze_reference`` is the one entry point style-worker activities should use.
It caches results in ``assets.metadata.referenceAnalysis`` keyed by
``extractorVersion`` so downstream consumers (LUT extraction, genome extraction,
auto-LUT matching, reason-worker) never re-analyze the same reference.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

try:
    import cv2
except Exception:  # pragma: no cover - optional dep
    cv2 = None  # type: ignore[assignment]

from shared_py.logging_config import StructuredLogger
from shared_py.models import BeatGrid, ShotBoundary, StyleAnalysis, StyleGenome
from style_worker.genome.extract import extract_genome
from style_worker.lut_extract import extract_lut_from_reference, sample_frames

logger = StructuredLogger("style_worker.reference_analysis")

EXTRACTOR_VERSION = "1.0.0"

# Minimums for a reference to be considered high-enough quality to imitate.
_MIN_DURATION_S = 3.0
_MIN_WIDTH = 360
_MIN_HEIGHT = 360
_MIN_FPS = 24.0
_MIN_FILE_SIZE_MB = 0.5


@dataclass(frozen=True)
class TechnicalQuality:
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration_s: float = 0.0
    file_size_bytes: int = 0
    sample_frame_count: int = 0


@dataclass(frozen=True)
class ReferenceAnalysis:
    """All derivable knowledge about a reference video."""

    asset_id: Optional[str]
    extractor_version: str
    quality_score: float  # 0..1
    is_consistent_style: bool
    style_analysis: StyleAnalysis
    style_genome: StyleGenome
    shot_boundaries: List[ShotBoundary]
    lut_path: Optional[str]
    lut_storage_key: Optional[str]
    color_variance_across_shots: float
    technical_quality: TechnicalQuality
    warnings: List[str] = field(default_factory=list)

    def model_dump(self) -> dict:
        """Serialize to a dict suitable for JSONB metadata storage."""
        return {
            "assetId": self.asset_id,
            "extractorVersion": self.extractor_version,
            "qualityScore": self.quality_score,
            "isConsistentStyle": self.is_consistent_style,
            "styleAnalysis": self.style_analysis.model_dump(by_alias=True),
            "styleGenome": self.style_genome.model_dump(by_alias=True),
            "shotBoundaries": [s.model_dump(by_alias=True) for s in self.shot_boundaries],
            "lutPath": self.lut_path,
            "lutStorageKey": self.lut_storage_key,
            "colorVarianceAcrossShots": self.color_variance_across_shots,
            "technicalQuality": asdict(self.technical_quality),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_cache_dict(cls, data: dict) -> "ReferenceAnalysis":
        """Rehydrate from a dict stored in asset metadata."""
        return cls(
            asset_id=data.get("assetId"),
            extractor_version=data.get("extractorVersion", EXTRACTOR_VERSION),
            quality_score=float(data.get("qualityScore", 0.0)),
            is_consistent_style=bool(data.get("isConsistentStyle", False)),
            style_analysis=StyleAnalysis(**data.get("styleAnalysis", {})),
            style_genome=StyleGenome(**data.get("styleGenome", {})),
            shot_boundaries=[ShotBoundary(**s) for s in data.get("shotBoundaries", [])],
            lut_path=data.get("lutPath"),
            lut_storage_key=data.get("lutStorageKey"),
            color_variance_across_shots=float(data.get("colorVarianceAcrossShots", 0.0)),
            technical_quality=TechnicalQuality(**data.get("technicalQuality", {})),
            warnings=list(data.get("warnings", [])),
        )


def _video_info(video_path: str) -> dict:
    """Cheap video metadata using OpenCV / ffprobe fallback."""
    info = {
        "fps": 30.0,
        "total_frames": 0,
        "duration_s": 0.0,
        "width": 0,
        "height": 0,
        "file_size_bytes": 0,
    }
    if os.path.exists(video_path):
        info["file_size_bytes"] = os.path.getsize(video_path)

    if cv2 is not None:
        cap = cv2.VideoCapture(video_path)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        info.update(
            {
                "fps": fps,
                "total_frames": total_frames,
                "duration_s": total_frames / fps if fps > 0 else 0.0,
                "width": width,
                "height": height,
            }
        )
    return info


def _compute_quality_score(info: dict, sample_frames: List[Any]) -> float:
    """Score reference technical quality on a 0..1 scale."""
    scores = []

    # Resolution: 720p = 1.0, 360p = 0.0, clipped.
    min_dim = min(info.get("width", 0), info.get("height", 0))
    resolution_score = (min_dim - _MIN_WIDTH) / (720 - _MIN_WIDTH)
    scores.append(max(0.0, min(1.0, resolution_score)))

    # Frame rate: 24fps = 0.6, 60fps = 1.0.
    fps = info.get("fps", 0.0)
    fps_score = (fps - _MIN_FPS) / (60.0 - _MIN_FPS)
    scores.append(max(0.0, min(1.0, fps_score)))

    # Duration: 3s = 0.0, 30s = 1.0.
    duration_s = info.get("duration_s", 0.0)
    duration_score = (duration_s - _MIN_DURATION_S) / (30.0 - _MIN_DURATION_S)
    scores.append(max(0.0, min(1.0, duration_score)))

    # File size: 0.5MB = 0.0, 20MB = 1.0 (very rough bitrate proxy).
    mb = info.get("file_size_bytes", 0) / (1024 * 1024)
    size_score = (mb - _MIN_FILE_SIZE_MB) / (20.0 - _MIN_FILE_SIZE_MB)
    scores.append(max(0.0, min(1.0, size_score)))

    # Sampling success: did we get usable frames?
    sample_score = 1.0 if len(sample_frames) >= 5 else (len(sample_frames) / 5.0)
    scores.append(sample_score)

    return float(sum(scores) / len(scores))


def _compute_color_variance_across_shots(
    video_path: str,
    shot_boundaries: List[ShotBoundary],
    sample_count_per_shot: int = 3,
) -> float:
    """Return mean LAB standard deviation across shot samples.

    Higher variance means the reference contains visually distinct shots.
    """
    if cv2 is None or not shot_boundaries:
        return 0.0

    per_shot_means = []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0.0

    try:
        for shot in shot_boundaries:
            start = int(shot.start_s * cap.get(cv2.CAP_PROP_FPS))
            end = int(shot.end_s * cap.get(cv2.CAP_PROP_FPS))
            if end <= start:
                continue
            indices = [int(start + i * (end - start) / (sample_count_per_shot + 1))
                       for i in range(1, sample_count_per_shot + 1)]
            shot_samples = []
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
                    shot_samples.append(lab.mean(axis=(0, 1)))
            if shot_samples:
                per_shot_means.append(sum(shot_samples) / len(shot_samples))
    finally:
        cap.release()

    if len(per_shot_means) < 2:
        return 0.0

    stacked = __import__("numpy").stack(per_shot_means)
    return float(stacked.std(axis=0).mean())


def _compute_style_consistency(
    color_variance: float,
    shot_boundaries: List[ShotBoundary],
    info: dict,
) -> bool:
    """Reference is "consistent" if it has enough cuts to imitate but isn't a
    chaotic montage of wildly different looks.

    Phase 1 heuristic: consistent if there are 2+ shots and color variance is
    moderate (not zero, not extreme). This will be replaced by corpus data.
    """
    if len(shot_boundaries) < 2:
        return False
    # Normalize variance crudely by resolution so 8-bit LAB std stays comparable.
    normalized = color_variance / 255.0
    return 0.01 < normalized < 0.25


def _build_warnings(
    info: dict,
    quality_score: float,
    is_consistent: bool,
    sample_frame_count: int,
) -> List[str]:
    """Human-readable warnings surfaced to the user before render."""
    warnings: List[str] = []
    duration_s = info.get("duration_s", 0.0)
    width = info.get("width", 0)
    height = info.get("height", 0)
    fps = info.get("fps", 0.0)
    mb = info.get("file_size_bytes", 0) / (1024 * 1024)

    if duration_s < _MIN_DURATION_S:
        warnings.append(f"Reference is very short ({duration_s:.1f}s); style may be unreliable.")
    if min(width, height) < _MIN_WIDTH:
        warnings.append(f"Reference resolution ({width}x{height}) is low; output quality may suffer.")
    if fps < _MIN_FPS:
        warnings.append(f"Reference frame rate ({fps:.1f}fps) is low; motion cues may be unreliable.")
    if mb < _MIN_FILE_SIZE_MB:
        warnings.append("Reference file is tiny; it may be heavily compressed or corrupt.")
    if sample_frame_count < 5:
        warnings.append("Could not sample enough valid frames from the reference.")
    if quality_score < 0.4:
        warnings.append("Reference quality score is low; consider using a clearer reference.")
    if not is_consistent:
        warnings.append("Reference style appears inconsistent (or only one shot); auto-LUT may be muted.")
    return warnings


def _load_cached_analysis(asset_metadata: Optional[dict]) -> Optional[ReferenceAnalysis]:
    """Return a cached ReferenceAnalysis if version matches, else None."""
    if not asset_metadata:
        return None
    cached = asset_metadata.get("referenceAnalysis")
    if not isinstance(cached, dict):
        return None
    if cached.get("extractorVersion") != EXTRACTOR_VERSION:
        return None
    try:
        return ReferenceAnalysis.from_cache_dict(cached)
    except Exception as exc:
        logger.warning("failed to parse cached reference analysis", error=str(exc))
        return None


def analyze_reference(
    reference_path: str,
    *,
    asset_id: Optional[str] = None,
    asset_metadata: Optional[dict] = None,
    output_dir: Optional[str] = None,
    lut_strength: float = 0.5,
    beat_grid: Optional[BeatGrid] = None,
    project_clips: Optional[Dict[str, Any]] = None,
) -> ReferenceAnalysis:
    """Analyze a reference video once and return a cached/shared result.

    If ``asset_metadata`` contains a cached ``referenceAnalysis`` with the
    current ``EXTRACTOR_VERSION``, it is returned directly. Otherwise the
    reference is sampled, scored, and run through LUT extraction + genome
    extraction, then returned (the caller is responsible for persisting the
    ``model_dump()`` back to asset metadata).
    """
    cached = _load_cached_analysis(asset_metadata)
    if cached is not None:
        logger.info("reference_analysis_cache_hit", asset_id=asset_id)
        return cached

    if not os.path.exists(reference_path):
        raise FileNotFoundError(f"Reference video not found: {reference_path}")

    info = _video_info(reference_path)
    frames = sample_frames(reference_path, n_samples=50)

    quality_score = _compute_quality_score(info, frames)

    # Derive shot boundaries via the genome fallback if none supplied.
    from style_worker.genome.extract import _detect_shot_boundaries

    shot_boundaries = _detect_shot_boundaries(reference_path, info)

    color_variance = _compute_color_variance_across_shots(reference_path, shot_boundaries)
    is_consistent = _compute_style_consistency(color_variance, shot_boundaries, info)

    warnings = _build_warnings(info, quality_score, is_consistent, len(frames))

    # LUT + base style analysis.
    if output_dir is None:
        output_dir = os.path.join(tempfile.gettempdir(), f"ave_ref_{asset_id or 'anon'}")
    lut_path, style_analysis = extract_lut_from_reference(
        reference_path, output_dir, strength=lut_strength, asset_id=asset_id
    )

    # Genome (50-feature fingerprint).
    genome_dict = extract_genome(
        reference_path,
        beat_grid=beat_grid,
        shot_boundaries=shot_boundaries,
        style_analysis=style_analysis,
        project_clips=project_clips,
    )
    style_genome = StyleGenome(**genome_dict)

    technical_quality = TechnicalQuality(
        width=info.get("width", 0),
        height=info.get("height", 0),
        fps=info.get("fps", 0.0),
        duration_s=info.get("duration_s", 0.0),
        file_size_bytes=info.get("file_size_bytes", 0),
        sample_frame_count=len(frames),
    )

    return ReferenceAnalysis(
        asset_id=asset_id,
        extractor_version=EXTRACTOR_VERSION,
        quality_score=quality_score,
        is_consistent_style=is_consistent,
        style_analysis=style_analysis,
        style_genome=style_genome,
        shot_boundaries=shot_boundaries,
        lut_path=lut_path,
        lut_storage_key=None,
        color_variance_across_shots=color_variance,
        technical_quality=technical_quality,
        warnings=warnings,
    )


import tempfile  # noqa: E402 - imported late to keep module-level namespace clean
