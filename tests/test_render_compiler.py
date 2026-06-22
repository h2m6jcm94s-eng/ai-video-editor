"""
Unit, integration, and edge tests for FFmpeg render compiler.
Covers: timeline compilation, transition mapping, LUT/text overlay integration,
preview rendering, and edge cases (empty cutlist, missing clips, no slots).
"""

import pytest
import os
import sys
import tempfile
import subprocess
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "render-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

import warnings

from PIL import Image
from render_worker.compiler import compile_timeline, render_preview, resolve_render_dimensions, XFADE_MAP, _get_fontconfig_file
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, RenderConfig, Effect, Subtitle


def create_test_video(path: str, duration: float = 5.0, fps: int = 30,
                      resolution: tuple = (640, 480)):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    width, height = resolution
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
            "-pix_fmt", "yuv420p",
            path,
        ],
        check=True, capture_output=True,
    )
    return path


class TestFontconfig:
    def test_generates_config_when_system_font_dirs_exist(self, monkeypatch):
        monkeypatch.delenv("FONTCONFIG_FILE", raising=False)
        config_path = _get_fontconfig_file()
        # On most systems at least one standard font directory exists.
        if config_path:
            assert os.path.exists(config_path)
            with open(config_path, "r", encoding="utf-8") as f:
                contents = f.read()
            assert "<fontconfig>" in contents
            assert "<cachedir>" in contents

    def test_respects_existing_fontconfig_file_env(self, monkeypatch):
        existing = "/path/to/existing/fonts.conf"
        monkeypatch.setenv("FONTCONFIG_FILE", existing)
        assert _get_fontconfig_file() == existing


class TestXfadeMap:
    def test_all_transitions_mapped(self):
        transitions = [
            "fade", "dissolve", "wipe_left", "wipe_right",
            "wipe_up", "wipe_down", "circle_open", "slide_up",
            "slide_down", "slide_left", "slide_right", "pixelize",
            "hlslice", "flash", "whip",
        ]
        for t in transitions:
            assert t in XFADE_MAP
            assert XFADE_MAP[t] is not None

    def test_flash_maps_to_fade(self):
        assert XFADE_MAP["flash"] == "fade"

    def test_dissolve_maps_to_fade(self):
        assert XFADE_MAP["dissolve"] == "fade"

    def test_hard_cut_not_in_map(self):
        assert "hard_cut" not in XFADE_MAP


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestCompileTimeline:
    def test_compile_single_slot(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name
        try:
            create_test_video(video_path, duration=5.0)
            cutlist = CutList(
                globals=CutListGlobals(total_duration_s=2.0, tempo_bpm=120,
                                       time_signature="4/4", energy_curve=[0.5],
                                       section_markers=[], aspect_ratio="16:9"),
                slots=[Slot(index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                            section="intro", target_shot_type="wide",
                            subject_hint="test", motion_hint="static",
                            energy_level=0.5, required_tags=[], avoid_tags=[],
                            selected_clip_id="clip_0")],
            )
            config = RenderConfig(output_path=output_path, width=640, height=480,
                                  video_preset="ultrafast", video_crf=28)
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_compile_with_subject_mask(self):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
            video_path = vf.name
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as mf:
            mask_path = mf.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as of:
            output_path = of.name
        try:
            create_test_video(video_path, duration=5.0)
            # White mask means the whole subject is kept; black background is added.
            Image.new("L", (640, 480), 255).save(mask_path)
            cutlist = CutList(
                globals=CutListGlobals(total_duration_s=2.0, tempo_bpm=120,
                                       time_signature="4/4", energy_curve=[0.5],
                                       section_markers=[], aspect_ratio="16:9"),
                slots=[Slot(index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                            section="intro", target_shot_type="wide",
                            subject_hint="test", motion_hint="static",
                            energy_level=0.5, required_tags=[], avoid_tags=[],
                            selected_clip_id="clip_0")],
            )
            config = RenderConfig(
                output_path=output_path,
                width=640,
                height=480,
                video_preset="ultrafast",
                video_crf=28,
                mask_paths={"clip_0": mask_path},
            )
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, mask_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_compile_multiple_slots(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name
        try:
            create_test_video(video_path, duration=10.0)
            cutlist = CutList(
                globals=CutListGlobals(total_duration_s=4.0, tempo_bpm=120,
                                       time_signature="4/4", energy_curve=[0.3, 0.7],
                                       section_markers=[], aspect_ratio="16:9"),
                slots=[
                    Slot(index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                         section="intro", target_shot_type="wide",
                         subject_hint="test", motion_hint="static",
                         energy_level=0.3, required_tags=[], avoid_tags=[],
                         selected_clip_id="clip_0"),
                    Slot(index=1, start_s=2.0, duration_s=2.0, beat_index=2,
                         section="verse", target_shot_type="close_up",
                         subject_hint="test", motion_hint="handheld",
                         energy_level=0.7, required_tags=[], avoid_tags=[],
                         selected_clip_id="clip_0"),
                ],
            )
            config = RenderConfig(output_path=output_path, width=640, height=480,
                                  video_preset="ultrafast", video_crf=28)
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)


class TestEffectRendering:
    """Verify that slot effects accepted by the schema actually render through FFmpeg."""

    def _cutlist_with_effects(self, effects):
        return CutList(
            globals=CutListGlobals(total_duration_s=3.0, tempo_bpm=120,
                                   time_signature="4/4", energy_curve=[0.5],
                                   section_markers=[], aspect_ratio="16:9"),
            slots=[Slot(index=0, start_s=0.0, duration_s=3.0, beat_index=0,
                        section="intro", target_shot_type="wide",
                        subject_hint="test", motion_hint="static",
                        energy_level=0.5, required_tags=[], avoid_tags=[],
                        selected_clip_id="clip_0", effects=effects)],
        )

    def test_zoom_punch_in_renders(self):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as v:
            video_path = v.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as o:
            output_path = o.name
        try:
            create_test_video(video_path, duration=5.0)
            cutlist = self._cutlist_with_effects([
                Effect(type="zoom_punch_in", start_s=0.0, duration_s=0.3,
                       params={"target_scale": 1.25, "duration_ms": 250}),
            ])
            config = RenderConfig(output_path=output_path, width=640, height=480,
                                  video_preset="ultrafast", video_crf=28)
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_focus_pull_renders(self):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as v:
            video_path = v.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as o:
            output_path = o.name
        try:
            create_test_video(video_path, duration=5.0)
            cutlist = self._cutlist_with_effects([
                Effect(type="focus_pull", start_s=0.5, duration_s=0.8,
                       params={"target_blur": 4.0, "duration_ms": 600}),
            ])
            config = RenderConfig(output_path=output_path, width=640, height=480,
                                  video_preset="ultrafast", video_crf=28)
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_vignette_and_film_grain_renders(self):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as v:
            video_path = v.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as o:
            output_path = o.name
        try:
            create_test_video(video_path, duration=5.0)
            cutlist = self._cutlist_with_effects([
                Effect(type="vignette", start_s=0.0, duration_s=3.0,
                       params={"intensity": 0.4}),
                Effect(type="film_grain", start_s=0.0, duration_s=3.0,
                       params={"intensity": 0.15}),
            ])
            config = RenderConfig(output_path=output_path, width=640, height=480,
                                  video_preset="ultrafast", video_crf=28)
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_glitch_and_color_pop_renders(self):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as v:
            video_path = v.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as o:
            output_path = o.name
        try:
            create_test_video(video_path, duration=5.0)
            cutlist = self._cutlist_with_effects([
                Effect(type="glitch", start_s=0.5, duration_s=0.5,
                       params={"intensity": 0.3}),
                Effect(type="color_pop", start_s=1.0, duration_s=0.5,
                       params={"saturation": 1.8, "hue_shift": 15.0}),
            ])
            config = RenderConfig(output_path=output_path, width=640, height=480,
                                  video_preset="ultrafast", video_crf=28)
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_text_effect_renders(self):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as v:
            video_path = v.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as o:
            output_path = o.name
        try:
            create_test_video(video_path, duration=5.0)
            cutlist = self._cutlist_with_effects([
                Effect(type="lower_third", start_s=0.5, duration_s=1.0,
                       params={"text": "HELLO", "font_size_px": 32}),
            ])
            config = RenderConfig(output_path=output_path, width=640, height=480,
                                  video_preset="ultrafast", video_crf=28)
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_unimplemented_effects_warn(self):
        if not shutil.which("ffmpeg"):
            pytest.skip("FFmpeg not available")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as v:
            video_path = v.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as o:
            output_path = o.name
        try:
            create_test_video(video_path, duration=5.0)
            cutlist = self._cutlist_with_effects([
                Effect(type="speed_ramp", start_s=0.0, duration_s=1.0,
                       params={"start_speed": 1.0, "end_speed": 2.0}),
                Effect(type="freeze_frame", start_s=1.0, duration_s=0.5,
                       params={"hold_ms": 200}),
                Effect(type="whoosh_sfx", start_s=2.0, duration_s=0.5, params={}),
            ])
            config = RenderConfig(output_path=output_path, width=640, height=480,
                                  video_preset="ultrafast", video_crf=28)
            with pytest.warns(UserWarning):
                result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)


class TestRenderEdgeCases:
    def test_empty_cutlist(self):
        cutlist = CutList(
            globals=CutListGlobals(total_duration_s=0.0, tempo_bpm=120,
                                   time_signature="4/4", energy_curve=[],
                                   section_markers=[], aspect_ratio="16:9"),
            slots=[],
        )
        config = RenderConfig(output_path="/tmp/out.mp4")
        with pytest.raises(ValueError, match="no slots"):
            compile_timeline(cutlist, {}, "/tmp/out.mp4", config)

    def test_all_overlay_positions(self):
        positions = [
            "center", "top", "bottom", "left", "right",
            "top_left", "top_right", "bottom_left", "bottom_right",
        ]
        for pos in positions:
            overlay = Overlay(text="Test", start_s=0.0, end_s=1.0,
                              position=pos, font="Inter",
                              font_size_px=48, color="#FFFFFF", animation="none")
            assert overlay.position == pos


class TestStyleTierWarnings:
    """M1: compiler emits warnings when cutlist features exceed the purchased tier."""

    def _base_cutlist(self, **slot_overrides):
        return CutList(
            globals=CutListGlobals(total_duration_s=2.0, tempo_bpm=120,
                                   time_signature="4/4", energy_curve=[0.5],
                                   section_markers=[], aspect_ratio="16:9"),
            slots=[Slot(index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                        section="intro", target_shot_type="wide",
                        subject_hint="test", motion_hint="static",
                        energy_level=0.5, required_tags=[], avoid_tags=[],
                        selected_clip_id=None, **slot_overrides)],
        )

    def test_cuts_only_warns_on_transition(self):
        cutlist = self._base_cutlist(transition_out="fade")
        config = RenderConfig(output_path="/tmp/out.mp4")
        with pytest.warns(UserWarning, match="does not include transitions"):
            with pytest.raises(ValueError, match="No valid segments"):
                compile_timeline(cutlist, {}, "/tmp/out.mp4", config, style_tier="cuts_only")

    def test_color_grade_warns_on_overlay(self):
        cutlist = self._base_cutlist()
        cutlist.overlays = [Overlay(text="Hi", start_s=0.0, end_s=1.0, position="center",
                                    font="Inter", font_size_px=48, color="#FFFFFF", animation="none")]
        config = RenderConfig(output_path="/tmp/out.mp4")
        with pytest.warns(UserWarning, match="does not include text overlays"):
            with pytest.raises(ValueError, match="No valid segments"):
                compile_timeline(cutlist, {}, "/tmp/out.mp4", config, style_tier="color_grade")

    def test_with_text_warns_on_effects(self):
        cutlist = self._base_cutlist(effects=[Effect(type="vignette", start_s=0.0,
                                                     duration_s=1.0, params={"intensity": 0.4})])
        config = RenderConfig(output_path="/tmp/out.mp4")
        with pytest.warns(UserWarning, match="does not include slot effects"):
            with pytest.raises(ValueError, match="No valid segments"):
                compile_timeline(cutlist, {}, "/tmp/out.mp4", config, style_tier="with_text")

    def test_full_remix_no_warnings(self):
        cutlist = self._base_cutlist(transition_out="fade",
                                     effects=[Effect(type="vignette", start_s=0.0,
                                                     duration_s=1.0, params={"intensity": 0.4})])
        cutlist.overlays = [Overlay(text="Hi", start_s=0.0, end_s=1.0, position="center",
                                    font="Inter", font_size_px=48, color="#FFFFFF", animation="none")]
        config = RenderConfig(output_path="/tmp/out.mp4", lut_path="/tmp/lut.cube")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                compile_timeline(cutlist, {}, "/tmp/out.mp4", config, style_tier="full_remix")
            except ValueError:
                pass  # clips are absent; warnings are what we care about
        assert not [w for w in caught if "Style tier" in str(w.message)]

    def _base_cutlist_with_clip(self):
        return CutList(
            globals=CutListGlobals(
                total_duration_s=2.0, tempo_bpm=120, time_signature="4/4",
                energy_curve=[0.5], section_markers=[], aspect_ratio="16:9",
            ),
            slots=[Slot(
                index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                section="intro", target_shot_type="wide",
                subject_hint="test", motion_hint="static",
                energy_level=0.5, required_tags=[], avoid_tags=[],
                selected_clip_id="clip_0",
            )],
        )

    def test_color_grade_warns_on_lut(self):
        with tempfile.NamedTemporaryFile(suffix=".cube", delete=False) as lf:
            lut_path = lf.name
        try:
            _write_identity_cube(lut_path)
            cutlist = self._base_cutlist_with_clip()
            config = RenderConfig(output_path="/tmp/out.mp4", lut_path=lut_path)
            with pytest.warns(UserWarning, match="does not include LUT"):
                with pytest.raises(ValueError, match="No valid segments"):
                    compile_timeline(cutlist, {}, "/tmp/out.mp4", config, style_tier="cuts_only")
        finally:
            if os.path.exists(lut_path):
                os.unlink(lut_path)

    def test_with_text_warns_on_subtitle(self):
        cutlist = self._base_cutlist_with_clip()
        cutlist.subtitles = [Subtitle(id="sub-1", text="Hi", start_s=0.0, end_s=1.0)]
        config = RenderConfig(output_path="/tmp/out.mp4")
        with pytest.warns(UserWarning, match="does not include subtitles"):
            with pytest.raises(ValueError, match="No valid segments"):
                compile_timeline(cutlist, {}, "/tmp/out.mp4", config, style_tier="color_grade")



def _video_dimensions(path: str) -> tuple[int, int]:
    """Return (width, height) for a video file using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            path,
        ],
        check=True, capture_output=True, text=True,
    )
    width, height = result.stdout.strip().split("x")
    return int(width), int(height)


def _write_identity_cube(path: str, size: int = 2) -> None:
    """Write a minimal valid 3D LUT in Adobe .cube format."""
    with open(path, "w", encoding="utf-8") as f:
        f.write('TITLE "identity"\n')
        f.write(f"LUT_3D_SIZE {size}\n")
        f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
        step = 1.0 / (size - 1) if size > 1 else 0.0
        for b in range(size):
            for g in range(size):
                for r in range(size):
                    f.write(f"{r * step:.6f} {g * step:.6f} {b * step:.6f}\n")


class TestResolveRenderDimensions:
    def test_all_export_presets(self):
        expected = {
            "youtube_16_9": (1280, 720),
            "reels_9_16": (720, 1280),
            "tiktok_9_16": (720, 1280),
            "square_1_1": (720, 720),
        }
        for preset, dims in expected.items():
            assert resolve_render_dimensions(preset, None) == dims

    def test_preset_wins_over_aspect_ratio(self):
        assert resolve_render_dimensions("youtube_16_9", "9:16") == (1280, 720)

    def test_aspect_ratio_fallbacks(self):
        assert resolve_render_dimensions(None, "16:9") == (1280, 720)
        assert resolve_render_dimensions(None, "9:16") == (720, 1280)
        assert resolve_render_dimensions(None, "4:5") == (720, 900)
        assert resolve_render_dimensions(None, "1:1") == (720, 720)

    def test_unknown_values_fallback_to_vertical(self):
        assert resolve_render_dimensions("unknown_preset", "unknown_ratio") == (720, 1280)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestExportPresetDimensions:
    def _compile_preset(self, preset: str):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
            video_path = vf.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as of:
            output_path = of.name
        try:
            create_test_video(video_path, duration=3.0)
            cutlist = CutList(
                globals=CutListGlobals(
                    total_duration_s=2.0, tempo_bpm=120, time_signature="4/4",
                    energy_curve=[0.5], section_markers=[], aspect_ratio="16:9",
                ),
                slots=[Slot(
                    index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                    section="intro", target_shot_type="wide",
                    subject_hint="test", motion_hint="static",
                    energy_level=0.5, required_tags=[], avoid_tags=[],
                    selected_clip_id="clip_0",
                )],
            )
            width, height = resolve_render_dimensions(preset, None)
            config = RenderConfig(
                output_path=output_path, width=width, height=height,
                video_preset="ultrafast", video_crf=28,
            )
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert _video_dimensions(result) == (width, height)
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_compile_youtube_16_9(self):
        self._compile_preset("youtube_16_9")

    def test_compile_reels_9_16(self):
        self._compile_preset("reels_9_16")

    def test_compile_tiktok_9_16(self):
        self._compile_preset("tiktok_9_16")

    def test_compile_square_1_1(self):
        self._compile_preset("square_1_1")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestSubtitleBurnIn:
    def test_subtitle_renders(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
            video_path = vf.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as of:
            output_path = of.name
        try:
            create_test_video(video_path, duration=3.0)
            cutlist = CutList(
                globals=CutListGlobals(
                    total_duration_s=2.0, tempo_bpm=120, time_signature="4/4",
                    energy_curve=[0.5], section_markers=[], aspect_ratio="16:9",
                ),
                slots=[Slot(
                    index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                    section="intro", target_shot_type="wide",
                    subject_hint="test", motion_hint="static",
                    energy_level=0.5, required_tags=[], avoid_tags=[],
                    selected_clip_id="clip_0",
                )],
                subtitles=[Subtitle(
                    id="sub-1", text="Hello World", start_s=0.2, end_s=1.0,
                )],
            )
            config = RenderConfig(
                output_path=output_path, width=640, height=480,
                video_preset="ultrafast", video_crf=28,
            )
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
class TestLUTApplication:
    def test_identity_lut_renders(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
            video_path = vf.name
        with tempfile.NamedTemporaryFile(suffix=".cube", delete=False) as lf:
            lut_path = lf.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as of:
            output_path = of.name
        try:
            create_test_video(video_path, duration=3.0)
            _write_identity_cube(lut_path)
            cutlist = CutList(
                globals=CutListGlobals(
                    total_duration_s=2.0, tempo_bpm=120, time_signature="4/4",
                    energy_curve=[0.5], section_markers=[], aspect_ratio="16:9",
                ),
                slots=[Slot(
                    index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                    section="intro", target_shot_type="wide",
                    subject_hint="test", motion_hint="static",
                    energy_level=0.5, required_tags=[], avoid_tags=[],
                    selected_clip_id="clip_0",
                )],
            )
            config = RenderConfig(
                output_path=output_path, width=640, height=480,
                video_preset="ultrafast", video_crf=28,
                lut_path=lut_path,
            )
            result = compile_timeline(cutlist, {"clip_0": video_path}, output_path, config)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in [video_path, lut_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)
