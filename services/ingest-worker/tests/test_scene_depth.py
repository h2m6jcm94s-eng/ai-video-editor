# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.

import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from shared_py.models import DepthSample, Scene, SceneDepthAnalysis, ShotBoundary
from ingest_worker.scene_depth import (
    _aggregate_depth,
    _depth_stats,
    _estimate_depths,
    _fallback_depth_for_frame,
    _group_shots_into_scenes,
    analyze_scenes_and_depth,
)


def _make_video(path: str, frames: int = 30, fps: float = 30.0, size: tuple = (64, 64)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, size)
    for i in range(frames):
        intensity = int(255 * (i / max(frames - 1, 1)))
        frame = np.full((*size[::-1], 3), intensity, dtype=np.uint8)
        writer.write(frame)
    writer.release()


class TestDepthStats:
    def test_uniform_depth(self):
        depth = np.full((10, 10), 0.5, dtype=np.float32)
        stats = _depth_stats(depth)
        assert stats["mean_depth"] == pytest.approx(0.5)
        assert stats["depth_variance"] == pytest.approx(0.0)
        assert stats["near_ratio"] == 0.0
        assert stats["far_ratio"] == 0.0

    def test_gradient_depth(self):
        depth = np.linspace(0, 1, 100).reshape(10, 10).astype(np.float32)
        stats = _depth_stats(depth)
        assert stats["mean_depth"] == pytest.approx(0.5, abs=0.05)
        assert stats["depth_variance"] > 0.05


class TestFallbackDepth:
    def test_returns_normalized_array(self):
        frame = np.full((64, 64, 3), 128, dtype=np.uint8)
        arr = _fallback_depth_for_frame(frame)
        assert arr.min() >= 0.0
        assert arr.max() <= 1.0


class TestEstimateDepths:
    def test_returns_samples_for_video(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            _make_video(tmp.name, frames=30, fps=30.0)
            path = tmp.name
        try:
            samples, model_name = _estimate_depths(path, sample_fps=2.0)
            assert len(samples) >= 1
            assert isinstance(samples[0], DepthSample)
            assert samples[0].t_s >= 0.0
        finally:
            os.unlink(path)


class TestGroupShotsIntoScenes:
    def test_with_shot_boundaries(self):
        shots = [
            ShotBoundary(start_frame=0, end_frame=30, start_s=0.0, end_s=1.0),
            ShotBoundary(start_frame=30, end_frame=60, start_s=1.0, end_s=2.0),
        ]
        samples = [
            DepthSample(t_s=0.5, mean_depth=0.2, depth_variance=0.01),
            DepthSample(t_s=1.5, mean_depth=0.8, depth_variance=0.02),
        ]
        scenes = _group_shots_into_scenes(shots, samples, fps=30.0)
        assert len(scenes) == 2
        assert scenes[0].start_s == 0.0
        assert scenes[1].end_s == 2.0

    def test_without_boundaries_uses_windows(self):
        samples = [DepthSample(t_s=i * 0.5, mean_depth=0.5, depth_variance=0.01) for i in range(10)]
        scenes = _group_shots_into_scenes(None, samples, fps=30.0)
        assert len(scenes) >= 1
        assert all(isinstance(s, Scene) for s in scenes)


class TestAggregateDepth:
    def test_empty_returns_default(self):
        analysis = _aggregate_depth([])
        assert analysis.global_mean_depth == 0.0

    def test_aggregates_samples(self):
        samples = [
            DepthSample(t_s=0.0, mean_depth=0.2, depth_variance=0.01),
            DepthSample(t_s=1.0, mean_depth=0.8, depth_variance=0.02),
        ]
        analysis = _aggregate_depth(samples)
        assert analysis.global_mean_depth == pytest.approx(0.5)
        assert len(analysis.samples) == 2


class TestAnalyzeScenesAndDepth:
    def test_cache_round_trip(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            _make_video(tmp.name, frames=30, fps=30.0)
            path = tmp.name
        cache = Path(tempfile.mkdtemp())
        try:
            analysis1 = analyze_scenes_and_depth(
                path, "asset_cache_1", fps=30.0, cache_dir=cache
            )
            assert isinstance(analysis1, SceneDepthAnalysis)
            analysis2 = analyze_scenes_and_depth(
                path, "asset_cache_1", fps=30.0, cache_dir=cache
            )
            assert analysis2.asset_id == analysis1.asset_id
            assert len(analysis2.scenes) == len(analysis1.scenes)
        finally:
            os.unlink(path)
            for f in cache.glob("*"):
                f.unlink()
            cache.rmdir()

    def test_respects_shot_boundaries(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            _make_video(tmp.name, frames=60, fps=30.0)
            path = tmp.name
        cache = Path(tempfile.mkdtemp())
        try:
            shots = [
                ShotBoundary(start_frame=0, end_frame=30, start_s=0.0, end_s=1.0),
                ShotBoundary(start_frame=30, end_frame=60, start_s=1.0, end_s=2.0),
            ]
            analysis = analyze_scenes_and_depth(
                path, "asset_shots", fps=30.0, shot_boundaries=shots, cache_dir=cache
            )
            assert len(analysis.scenes) == 2
        finally:
            os.unlink(path)
            for f in cache.glob("*"):
                f.unlink()
            cache.rmdir()
