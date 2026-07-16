# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.

import pytest

from shared_py.models import Keyframe
from render_worker.keyframes import lerp, sample, ffmpeg_expression, normalize_track


class TestLerp:
    def test_basic(self):
        assert lerp(0.5, 0, 1, 0, 10) == pytest.approx(5.0)

    def test_clamps_outside_range(self):
        assert lerp(-1, 0, 1, 0, 10) == pytest.approx(0.0)
        assert lerp(2, 0, 1, 0, 10) == pytest.approx(10.0)

    def test_zero_duration_returns_start(self):
        assert lerp(0.5, 1, 1, 3, 7) == 3


class TestSample:
    def test_empty(self):
        assert sample([], 0.5) == 0.0

    def test_single(self):
        assert sample([Keyframe(t_s=0.2, value=4.0)], 0.5) == 4.0

    def test_before_first(self):
        kfs = [Keyframe(t_s=1.0, value=10.0), Keyframe(t_s=2.0, value=20.0)]
        assert sample(kfs, 0.0) == 10.0

    def test_after_last(self):
        kfs = [Keyframe(t_s=1.0, value=10.0), Keyframe(t_s=2.0, value=20.0)]
        assert sample(kfs, 5.0) == 20.0

    def test_interpolates(self):
        kfs = [Keyframe(t_s=0.0, value=0.0), Keyframe(t_s=2.0, value=10.0)]
        assert sample(kfs, 1.0) == pytest.approx(5.0)


class TestFFmpegExpression:
    def test_empty(self):
        assert ffmpeg_expression([]) == "0"

    def test_single(self):
        assert ffmpeg_expression([Keyframe(t_s=0.0, value=5.0)]) == "5.0"

    def test_two_keyframes(self):
        expr = ffmpeg_expression(
            [Keyframe(t_s=0.0, value=0.0), Keyframe(t_s=2.0, value=10.0)]
        )
        assert "if(t<2.0,0.0+(10.0-0.0)*(t-0.0)/(2.0-0.0),10.0)" == expr

    def test_three_keyframes(self):
        expr = ffmpeg_expression(
            [
                Keyframe(t_s=0.0, value=0.0),
                Keyframe(t_s=1.0, value=5.0),
                Keyframe(t_s=3.0, value=9.0),
            ]
        )
        assert expr.count("if") == 2
        assert expr.endswith(")")


class TestNormalizeTrack:
    def test_adds_endpoints(self):
        kfs = [Keyframe(t_s=1.0, value=5.0)]
        out = normalize_track(kfs, 4.0)
        assert out[0].t_s == 0.0
        assert out[-1].t_s == 4.0
        assert len(out) == 3

    def test_clamps_excess_time(self):
        kfs = [Keyframe(t_s=0.0, value=1.0), Keyframe(t_s=10.0, value=2.0)]
        out = normalize_track(kfs, 3.0)
        assert out[0].t_s == 0.0
        assert out[-1].t_s == 3.0
