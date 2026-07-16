import os
import subprocess
import tempfile

import pytest

try:
    from PIL import Image

    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False

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
        opacity_line = next(line for line in lines if "geq=lum=" in line)
        assert "exp" in opacity_line and "sin" in opacity_line

    @pytest.mark.parametrize("mode", ["screen", "multiply", "overlay", "addition", "lighten", "darken"])
    def test_blend_mode_generates_blend_filter(self, mode):
        layers = [
            Layer(id="base", type="color", source="#000000", z_index=0, out_s=2.0),
            Layer(id="blend", type="color", source="#FF0000", z_index=1, out_s=2.0, blend_mode=mode),
        ]
        inputs, lines, label = _build_layer_filter_complex(layers, 2.0, 1080, 1920, 30.0)
        graph = ";".join(lines)
        assert f"blend=all_mode={mode}" in graph

    def test_matte_source_adds_alphamerge(self):
        if not _PIL:
            pytest.skip("PIL not available")
        with tempfile.TemporaryDirectory() as tmp:
            img_path = os.path.join(tmp, "img.png")
            matte_path = os.path.join(tmp, "matte.png")
            Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(img_path)
            Image.new("L", (100, 100), 128).save(matte_path)
            layers = [
                Layer(
                    id="m1",
                    type="image",
                    source=img_path,
                    matte_source=matte_path,
                    z_index=1,
                    out_s=1.0,
                )
            ]
            inputs, lines, label = _build_layer_filter_complex(layers, 1.0, 100, 100, 30.0)
            graph = ";".join(lines)
            assert "alphamerge" in graph
            assert matte_path in inputs


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

    @pytest.mark.skipif(not _PIL, reason="PIL not available")
    def test_three_layer_demo_frame_renders(self):
        """Render a real frame with base + 3 color layers (including a blend mode)."""
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "base.mp4")
            # Create a small 2-second base video (opaque green).
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i",
                    "color=c=0x00FF00:s=160x120:d=2.0:r=30",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", base_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            layers = [
                Layer(id="l1", type="color", source="#FF0000", blend_mode="normal", z_index=1, out_s=2.0, opacity=0.5),
                Layer(id="l2", type="color", source="#0000FF", blend_mode="screen", z_index=2, out_s=2.0, opacity=0.5),
                Layer(id="l3", type="color", source="#FFFFFF", blend_mode="multiply", z_index=3, out_s=2.0, opacity=0.3),
            ]

            def run_ffmpeg(cmd, _desc):
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            output_path = composite_layers(
                base_path,
                layers,
                2.0,
                160,
                120,
                30.0,
                ["-c:v", "libx264", "-pix_fmt", "yuv420p"],
                run_ffmpeg,
                tmp,
            )
            assert os.path.exists(output_path)
            # Extract a single frame to prove the graph produced pixels.
            frame_path = os.path.join(tmp, "frame.png")
            subprocess.run(
                ["ffmpeg", "-y", "-i", output_path, "-ss", "0.5", "-vframes", "1", frame_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            assert os.path.exists(frame_path)
            with Image.open(frame_path) as img:
                assert img.size == (160, 120)
