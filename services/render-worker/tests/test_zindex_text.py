# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import RenderConfig, Slot
from render_worker.compiler import _extract_segment, _find_font


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _make_test_video(path: str, width: int = 720, height: int = 1280, duration: float = 1.0) -> str:
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        path,
    ])
    return path


def _make_white_mask(path: str, width: int = 720, height: int = 1280, duration: float = 1.0) -> str:
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=white:s={width}x{height}:d={duration}:r=30",
        "-pix_fmt", "gray",
        "-c:v", "libx264",
        path,
    ])
    return path


def _copy_font(temp_dir: str) -> str:
    fontfile = _find_font()
    if fontfile and os.path.exists(fontfile):
        local_font = os.path.join(temp_dir, "font.ttf")
        shutil.copy2(fontfile, local_font)
        return "font.ttf"
    return ""


def _make_slot(**overrides) -> Slot:
    defaults = {
        "index": 0,
        "start_s": 0.0,
        "duration_s": 1.0,
        "beat_index": 0,
        "section": "chorus",
        "target_shot_type": "wide",
        "subject_hint": "person",
        "motion_hint": "static",
        "energy_level": 0.5,
    }
    defaults.update(overrides)
    return Slot(**defaults)


def _make_config(slot_mask_paths=None) -> RenderConfig:
    return RenderConfig(
        output_path=os.path.join(tempfile.gettempdir(), "out.mp4"),
        width=360,
        height=640,
        fps=30.0,
        video_preset="ultrafast",
        video_crf=28,
        slot_mask_paths=slot_mask_paths or {},
    )


def test_layered_text_filter_includes_drawtext_and_overlay(monkeypatch):
    """Verify the behind-subject path builds a drawtext + overlay filter graph.

    FFmpeg's drawtext filter crashes in some Windows builds, so we mock the
    FFmpeg runner and assert the produced command is structurally correct while
    still exercising the full path up to the subprocess call.
    """
    temp_dir = tempfile.mkdtemp(prefix="ave_zindex_test_")
    clip_path = _make_test_video(os.path.join(temp_dir, "clip.mp4"), width=360, height=640)
    mask_path = _make_white_mask(os.path.join(temp_dir, "mask.mp4"), width=360, height=640)
    relative_font = _copy_font(temp_dir)

    slot = _make_slot(
        index=0,
        selected_clip_id="clip",
        enable_kinetic_text=True,
        text_z_layer="behind_subject",
        identity_ids_present=[1],
        protagonist_matte_enabled=True,
        kinetic_text="BEHIND",
    )
    config = _make_config(slot_mask_paths={0: mask_path})
    kinetic_overlays = []

    captured: list[tuple[list[str], str]] = []

    def fake_run_ffmpeg(cmd: list[str], context: str, cwd=None) -> None:
        captured.append((cmd, context))
        if "layered kinetic text" in context:
            # Simulate successful output creation so the caller can continue.
            output_path = cmd[-1]
            with open(output_path, "wb") as f:
                f.write(b"fake layered output")
            return
        # For non-layered calls, run the real FFmpeg (segment + mask extraction).
        subprocess.run(cmd, check=True, capture_output=True, cwd=cwd)

    monkeypatch.setattr("render_worker.compiler._run_ffmpeg", fake_run_ffmpeg)

    result = _extract_segment((slot, clip_path, 1.0, config, temp_dir, relative_font, "full_remix", kinetic_overlays))

    assert result is not None
    assert os.path.exists(result["path"])
    assert len(kinetic_overlays) == 0

    layered_cmd = next((cmd for cmd, ctx in captured if "layered kinetic text" in ctx), None)
    assert layered_cmd is not None
    fc_index = layered_cmd.index("-filter_complex")
    filter_complex = layered_cmd[fc_index + 1]
    assert "drawtext" in filter_complex
    assert "BEHIND" in filter_complex
    assert "overlay=0:0" in filter_complex
    assert "alphamerge" in filter_complex
    if relative_font:
        assert "font.ttf" in filter_complex


def test_fallback_to_on_top_when_no_mask():
    temp_dir = tempfile.mkdtemp(prefix="ave_zindex_test_")
    clip_path = _make_test_video(os.path.join(temp_dir, "clip.mp4"), width=360, height=640)
    relative_font = _copy_font(temp_dir)

    slot = _make_slot(
        index=1,
        selected_clip_id="clip",
        enable_kinetic_text=True,
        text_z_layer="behind_subject",
        identity_ids_present=[1],
        protagonist_matte_enabled=True,
        kinetic_text="ON TOP",
    )
    config = _make_config()
    kinetic_overlays = []

    result = _extract_segment((slot, clip_path, 1.0, config, temp_dir, relative_font, "full_remix", kinetic_overlays))

    assert result is not None
    assert os.path.exists(result["path"])
    assert len(kinetic_overlays) == 1
    assert kinetic_overlays[0].text == "ON TOP"
    assert kinetic_overlays[0].start_s == slot.start_s


def test_on_top_layer_ignores_matte():
    temp_dir = tempfile.mkdtemp(prefix="ave_zindex_test_")
    clip_path = _make_test_video(os.path.join(temp_dir, "clip.mp4"), width=360, height=640)
    mask_path = _make_white_mask(os.path.join(temp_dir, "mask.mp4"), width=360, height=640)
    relative_font = _copy_font(temp_dir)

    slot = _make_slot(
        index=2,
        selected_clip_id="clip",
        enable_kinetic_text=True,
        text_z_layer="on_top",
        identity_ids_present=[1],
        protagonist_matte_enabled=True,
        kinetic_text="FRONT",
    )
    config = _make_config(slot_mask_paths={2: mask_path})
    kinetic_overlays = []

    result = _extract_segment((slot, clip_path, 1.0, config, temp_dir, relative_font, "full_remix", kinetic_overlays))

    assert result is not None
    assert len(kinetic_overlays) == 1
    assert kinetic_overlays[0].text == "FRONT"
