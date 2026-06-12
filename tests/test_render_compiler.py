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

from render_worker.compiler import compile_timeline, render_preview, XFADE_MAP
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, RenderConfig, Effect


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
