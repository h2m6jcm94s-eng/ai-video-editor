# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.

import os
import tempfile

import pytest

from shared_py.models import Layer, Keyframe
from render_worker.layers import composite_layers, _build_layer_filter_complex


class TestBuildLayerFilterComplex:
    def test_empty_layers_returns_base_label(self):
        inputs, lines, label = _build_layer_filter_complex([], 2.0, 1080, 1920, 30.0)
        assert not inputs
        assert not lines
        assert label == "[0:v]"

    def test_color_layer_generates_source_filter(self):
        layers = [Layer(id="c1", type="color", source="#FF0000", z_index=1, out_s=2.0)]
        inputs, lines, label = _build_layer_filter_complex(layers, 2.0, 1080, 1920, 30.0)
        assert not inputs
        assert len(lines) == 2
        assert "color=c=0xFF0000" in lines[0]
        assert "overlay=" in lines[1]
        assert label == "[outv]"

    def test_image_layer_adds_input(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"fake")
            path = tmp.name
        try:
            layers = [Layer(id="i1", type="image", source=path, z_index=2, out_s=2.0)]
            inputs, lines, label = _build_layer_filter_complex(layers, 2.0, 1080, 1920, 30.0)
            assert inputs == ["-loop", "1", "-t", "2.000", "-i", path]
            assert lines[0].startswith("[1:v]")
        finally:
            os.unlink(path)

    def test_keyframe_position_expression(self):
        layers = [
            Layer(
                id="c1",
                type="color",
                source="#0000FF",
                z_index=1,
                out_s=2.0,
                keyframes={
                    "x": [Keyframe(t_s=0.0, value=0.0), Keyframe(t_s=2.0, value=100.0)],
                },
            )
        ]
        inputs, lines, label = _build_layer_filter_complex(layers, 2.0, 1080, 1920, 30.0)
        overlay = lines[1]
        assert "overlay=" in overlay
        assert "if(t<2.0" in overlay
        assert r"\," in overlay

    def test_text_layer_defaults_to_spring_easing(self):
        layers = [
            Layer(
                id="t1",
                type="text",
                source="HELLO",
                z_index=1,
                out_s=2.0,
                keyframes={
                    "opacity": [Keyframe(t_s=0.0, value=0.0), Keyframe(t_s=2.0, value=1.0)],
                },
            )
        ]
        inputs, lines, label = _build_layer_filter_complex(layers, 2.0, 1080, 1920, 30.0)
        # The text layer should be rendered on a transparent canvas.
        assert any("color=c=0x00000000" in line for line in lines)
        assert any("drawtext=" in line for line in lines)
        # The opacity track should use the spring expression.
        opacity_line = next(line for line in lines if "geq(a=" in line)
        assert "exp" in opacity_line and "sin" in opacity_line


class TestCompositeLayers:
    def test_no_layers_returns_base_path(self):
        assert composite_layers("/tmp/base.mp4", [], 2.0, 1080, 1920, 30.0, [], None, "/tmp") == "/tmp/base.mp4"

    def test_runs_ffmpeg_with_expected_args(self):
        calls = []

        def fake_run(cmd, desc):
            calls.append((cmd, desc))

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            base = tmp.name
        try:
            layers = [Layer(id="c1", type="color", source="#00FF00", z_index=1, out_s=1.0)]
            out = composite_layers(
                base, layers, 1.0, 1080, 1920, 30.0, ["-c:v", "libx264"], fake_run, os.path.dirname(base)
            )
            assert len(calls) == 1
            cmd, desc = calls[0]
            assert cmd[0] == "ffmpeg"
            assert "-filter_complex" in cmd
            assert out != base
        finally:
            if os.path.exists(base):
                os.unlink(base)
