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
from render_worker.compiler import compile_timeline, render_preview, resolve_render_dimensions, XFADE_MAP, _get_fontconfig_file, _build_audio_filter, _build_audio_filter_v2
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, RenderConfig, Effect, Subtitle, AudioTrack


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

    def test_slot_mask_disabled_is_skipped(self):
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
            Image.new("L", (640, 480), 255).save(mask_path)
            cutlist = CutList(
                globals=CutListGlobals(total_duration_s=2.0, tempo_bpm=120,
                                       time_signature="4/4", energy_curve=[0.5],
                                       section_markers=[], aspect_ratio="16:9"),
                slots=[Slot(index=0, start_s=0.0, duration_s=2.0, beat_index=0,
                            section="intro", target_shot_type="wide",
                            subject_hint="test", motion_hint="static",
                            energy_level=0.5, required_tags=[], avoid_tags=[],
                            selected_clip_id="clip_0", mask_enabled=False)],
            )
            config = RenderConfig(
                output_path=output_path,
                width=640,
                height=480,
                video_preset="ultrafast",
                video_crf=28,
                slot_mask_paths={0: mask_path},
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
            "youtube_16_9": (1920, 1080),
            "youtube_4k_16_9": (3840, 2160),
            "reels_9_16": (1080, 1920),
            "tiktok_9_16": (1080, 1920),
            "square_1_1": (1080, 1080),
            "preview_360p_16_9": (640, 360),
        }
        for preset, dims in expected.items():
            assert resolve_render_dimensions(preset, None) == dims

    def test_preset_wins_over_aspect_ratio(self):
        assert resolve_render_dimensions("youtube_16_9", "9:16") == (1920, 1080)

    def test_aspect_ratio_fallbacks(self):
        assert resolve_render_dimensions(None, "16:9") == (1920, 1080)
        assert resolve_render_dimensions(None, "9:16") == (1080, 1920)
        assert resolve_render_dimensions(None, "4:5") == (1080, 1350)
        assert resolve_render_dimensions(None, "1:1") == (1080, 1080)

    def test_unknown_values_fallback_to_vertical(self):
        assert resolve_render_dimensions("unknown_preset", "unknown_ratio") == (1080, 1920)


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


class TestAudioDucking:
    def test_no_dialogue_uses_plain_amix(self):
        tracks = [
            AudioTrack(asset_id="m1", role="music", start_s=0.0, end_s=30.0, gain_db=-6.0),
            AudioTrack(asset_id="s1", role="sfx", start_s=0.0, end_s=30.0, gain_db=-12.0),
        ]
        filt, _, _ = _build_audio_filter(tracks, ["", ""], 2, None)
        assert "amix" in filt
        assert "sidechaincompress" not in filt

    def test_dialogue_triggers_sidechaincompress_on_music(self):
        tracks = [
            AudioTrack(asset_id="m1", role="music", start_s=0.0, end_s=30.0, gain_db=-6.0),
            AudioTrack(asset_id="d1", role="dialogue", start_s=0.0, end_s=30.0, gain_db=0.0),
        ]
        filt, _, _ = _build_audio_filter(tracks, ["", ""], 2, None)
        assert "sidechaincompress" in filt
        # The raw dialogue input is used directly as the sidechain key, while a
        # gain-adjusted copy goes to the final mix.
        assert "[trk2_raw][3:a]sidechaincompress" in filt
        assert "[dlg3_mix]" in filt
        assert "[trk2]" in filt

    def test_multiple_dialogues_fall_back_to_plain_amix(self):
        tracks = [
            AudioTrack(asset_id="m1", role="music", start_s=0.0, end_s=30.0),
            AudioTrack(asset_id="d1", role="dialogue", start_s=0.0, end_s=30.0),
            AudioTrack(asset_id="d2", role="voiceover", start_s=0.0, end_s=30.0),
        ]
        filt, _, extra = _build_audio_filter(tracks, ["", "", ""], 2, None)
        assert "sidechaincompress" not in filt
        assert "amix" in filt
        assert "[dlg_mix]" in filt
        assert extra == []

    def test_ducking_parameters_in_filter(self):
        tracks = [
            AudioTrack(
                asset_id="m1",
                role="music",
                start_s=0.0,
                end_s=30.0,
                duck_gain_db=-18.0,
                duck_attack_ms=10,
                duck_release_ms=500,
                duck_threshold=0.1,
            ),
            AudioTrack(asset_id="d1", role="dialogue", start_s=0.0, end_s=30.0),
        ]
        filt, _, _ = _build_audio_filter(tracks, ["", ""], 2, None)
        assert "threshold=0.1" in filt
        assert "attack=10" in filt
        assert "release=500" in filt
        # -18 dB reduction -> ratio = 10^(18/20) ≈ 7.94, rounded to 7.94 or 7.95.
        assert "ratio=7.9" in filt

    def test_empty_tracks_returns_no_audio(self):
        filt, next_idx, extra = _build_audio_filter([], [], 2, None)
        assert filt == ""
        assert next_idx == -1
        assert extra == []


class TestAudioFilterV2:
    """Unit tests for the two-pass adaptive ducking filter graph."""

    def _make_slot(self, idx: int, start_s: float, duration_s: float, song_db: float = 0.0, has_dialogue: bool = True):
        from render_worker.compiler import SlotAudioMix
        slot = Slot(
            index=idx,
            start_s=start_s,
            duration_s=duration_s,
            beat_index=idx,
            section="verse",
            target_shot_type="medium_shot",
            subject_hint="protagonist",
            motion_hint="still",
            energy_level=0.5,
        )
        mix = SlotAudioMix(song_level_db=song_db, clip_audio_enabled=has_dialogue)
        return slot, mix

    def test_no_dialogue_returns_music_only(self, tmp_path):
        slot, mix = self._make_slot(0, 0.0, 5.0, has_dialogue=False)
        filt = _build_audio_filter_v2([slot], 1, [], [mix], str(tmp_path))
        assert "[music]anull[a_out]" in filt
        assert "sidechaincompress" not in filt

    def test_single_dialogue_has_sidechain(self, tmp_path):
        slot, mix = self._make_slot(0, 0.0, 5.0, has_dialogue=True)
        dialogue_specs = [(0, 2, 0, 5.0)]
        filt = _build_audio_filter_v2([slot], 1, dialogue_specs, [mix], str(tmp_path))
        assert "sidechaincompress" in filt
        assert "[music][dlg_sc_padded]sidechaincompress" in filt
        assert "[dlg_sc]apad=" in filt
        assert "[a_out]" in filt

    def test_multiple_dialogues_have_sidechain(self, tmp_path):
        slots, mixes = [], []
        dialogue_specs = []
        for i in range(3):
            slot, mix = self._make_slot(i, i * 5.0, 5.0, has_dialogue=True)
            slots.append(slot)
            mixes.append(mix)
            dialogue_specs.append((i, 2 + i, int(i * 5000), 5.0))
        filt = _build_audio_filter_v2(slots, 1, dialogue_specs, mixes, str(tmp_path))
        assert "sidechaincompress" in filt
        assert filt.count("agate=") == 3
        assert "amix=inputs=3" in filt

    def test_each_dialogue_is_gated_before_mix(self, tmp_path):
        slot, mix = self._make_slot(0, 0.0, 5.0, has_dialogue=True)
        dialogue_specs = [(0, 2, 0, 5.0)]
        filt = _build_audio_filter_v2([slot], 1, dialogue_specs, [mix], str(tmp_path))
        assert "agate=threshold=-45dB" in filt
        assert "asplit=2[dlg_sc_0][dlg_mix_0]" in filt

    def test_final_mix_has_limiter(self, tmp_path):
        slot, mix = self._make_slot(0, 0.0, 5.0, has_dialogue=True)
        dialogue_specs = [(0, 2, 0, 5.0)]
        filt = _build_audio_filter_v2([slot], 1, dialogue_specs, [mix], str(tmp_path))
        assert "alimiter" in filt

    def test_music_gain_changes_use_asendcmd(self, tmp_path):
        slots, mixes = [], []
        for i in range(3):
            slot, mix = self._make_slot(i, i * 5.0, 5.0, song_db=float(i * -2), has_dialogue=False)
            slots.append(slot)
            mixes.append(mix)
        filt = _build_audio_filter_v2(slots, 1, [], mixes, str(tmp_path))
        assert "asendcmd=f=volume_sendcmd.txt" in filt
        assert (tmp_path / "volume_sendcmd.txt").exists()
