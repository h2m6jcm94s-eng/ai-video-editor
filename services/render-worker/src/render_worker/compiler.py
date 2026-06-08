# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""FFmpeg-based timeline compiler for beat-synced video rendering."""

import os
import tempfile
import subprocess
from typing import List, Optional, Dict
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from shared_py.models import CutList, Slot, Overlay, RenderConfig


def _find_font() -> str:
    """Find a suitable system font for drawtext, cross-platform."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
        "C:\\Windows\\Fonts\\arial.ttf",  # Windows
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    return ""


def _run_ffmpeg(cmd: List[str], context: str) -> None:
    """Run FFmpeg with rich error context on failure."""
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace")[:2000] if e.stderr else ""
        raise RuntimeError(
            f"FFmpeg failed during {context}: {e.returncode}\n"
            f"Command: {' '.join(cmd[:20])}...\n"
            f"Stderr: {stderr}"
        ) from e


# Map transition types to xfade names
XFADE_MAP = {
    "fade": "fade",
    "dissolve": "fade",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "wipe_up": "wipeup",
    "wipe_down": "wipedown",
    "circle_open": "circleopen",
    "slide_up": "slideup",
    "slide_down": "slidedown",
    "slide_left": "slideleft",
    "slide_right": "slideright",
    "pixelize": "pixelize",
    "hlslice": "hlslice",
    "flash": "fade",
    "whip": "hlslice",
}


def _esc_path(p: str) -> str:
    return p.replace("\\", "/").replace("'", "\\'").replace(":", "\\:")


def _esc_text(t: str) -> str:
    return t.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")


def compile_timeline(
    cutlist: CutList,
    clip_paths: Dict[str, str],
    output_path: str,
    config: RenderConfig,
) -> str:
    """Compile a cut-list into a final video using FFmpeg.

    Uses the concat demuxer with filter_complex for transitions, LUTs, and text.
    """
    if not cutlist.slots:
        raise ValueError("Cut list has no slots")

    # Stage 1: Extract each slot's segment from its assigned clip
    slot_segments = []
    temp_files = []
    temp_dir = tempfile.mkdtemp(prefix="ave_render_")

    for slot in cutlist.slots:
        clip_id = slot.selected_clip_id
        if not clip_id or clip_id not in clip_paths:
            # Skip missing clips or use placeholder
            continue

        clip_path = clip_paths[clip_id]
        segment_path = os.path.join(temp_dir, f"slot_{slot.index:03d}.mp4")

        # Extract exact segment using trim filter
        # We use -ss/-t for speed, then filter for frame accuracy
        duration = slot.duration_s
        start = 0.0  # For MVP, use start of clip; production would use smart offset

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", clip_path,
            "-vf", f"fps={config.fps},scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "23", "-pix_fmt", "yuv420p",
            "-an",  # No audio in segments
            segment_path,
        ]
        _run_ffmpeg(cmd, f"segment extraction for slot {slot.index}")

        slot_segments.append({
            "path": segment_path,
            "slot": slot,
        })
        temp_files.append(segment_path)

    if not slot_segments:
        raise ValueError("No valid segments could be extracted")

    # Stage 2: Build filter_complex for concatenation + transitions
    # For simplicity with transitions, we build a chain of xfade filters
    filter_parts = []
    inputs = []

    for i, seg in enumerate(slot_segments):
        inputs.append(f"[{i}:v]")

    # Build xfade chain
    current_label = "0:v"
    for i in range(len(slot_segments) - 1):
        slot = slot_segments[i]["slot"]
        next_slot = slot_segments[i + 1]["slot"]
        transition = XFADE_MAP.get(slot.transition_out, "fade")
        xfade_duration = min(0.3, slot.duration_s * 0.5)  # never exceed half of slot duration
        offset = max(0.0, slot.duration_s - xfade_duration)

        out_label = f"v{i}"
        filter_parts.append(
            f"[{current_label}][{i+1}:v]xfade=transition={transition}:duration={xfade_duration}:offset={offset}[{out_label}]"
        )
        current_label = out_label

    # LUT application if available
    if config.lut_path and os.path.exists(config.lut_path):
        lut_label = f"{current_label}_lut"
        filter_parts.append(
            f"[{current_label}]zscale=transfer=709:range=tv:out_range=pc,"
            f"lut3d=file={_esc_path(config.lut_path)}:interp=tetrahedral,"
            f"zscale=range=pc:out_range=tv[{lut_label}]"
        )
        current_label = lut_label

    # Text overlays
    for overlay in cutlist.overlays:
        text_label = f"text_{overlay.start_s}"
        # Build drawtext expression
        x_expr = "(w-text_w)/2"  # center
        y_expr = "(h-text_h)/2"
        if overlay.position == "top":
            y_expr = "h*0.1"
        elif overlay.position == "bottom":
            y_expr = "h*0.9"
        elif overlay.position == "top_left":
            x_expr = "w*0.05"
            y_expr = "h*0.1"
        elif overlay.position == "top_right":
            x_expr = "w*0.95-text_w"
            y_expr = "h*0.1"
        elif overlay.position == "bottom_left":
            x_expr = "w*0.05"
            y_expr = "h*0.9"
        elif overlay.position == "bottom_right":
            x_expr = "w*0.95-text_w"
            y_expr = "h*0.9"

        fontfile = _find_font()

        enable_expr = f"between(t\\,{overlay.start_s}\\,{overlay.end_s})"

        filter_parts.append(
            f"[{current_label}]drawtext=text='{_esc_text(overlay.text)}':"
            f"x={x_expr}:y={y_expr}:"
            f"fontsize={overlay.font_size_px}:"
            f"fontcolor={overlay.color}:"
            f"{'fontfile=' + fontfile + ':' if fontfile else ''}"
            f"borderw=2:bordercolor={overlay.stroke or 'black'}:"
            f"enable='{enable_expr}'[{text_label}]"
        )
        current_label = text_label

    # Final output mapping
    expected_label = f"v{len(slot_segments)-2}" if len(slot_segments) > 1 else "0:v"
    if current_label != expected_label:
        filter_parts.append(f"[{current_label}]format=yuv420p[outv]")
        final_label = "outv"
    else:
        final_label = current_label

    # Build full command
    input_args = []
    for seg in slot_segments:
        input_args.extend(["-i", seg["path"]])

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", f"[{final_label}]",
        "-c:v", config.video_codec,
        "-preset", config.video_preset,
        "-crf", str(config.video_crf),
        "-pix_fmt", config.pix_fmt,
    ]

    # Add song audio if provided
    if config.song_path and os.path.exists(config.song_path):
        audio_input_idx = len(slot_segments)  # audio is always the last input
        cmd.extend([
            "-i", config.song_path,
            "-map", f"{audio_input_idx}:a:0",
            "-c:a", config.audio_codec,
            "-b:a", config.audio_bitrate,
            "-shortest",
        ])
    else:
        cmd.extend(["-an"])

    cmd.extend(["-movflags", "+faststart", output_path])

    _run_ffmpeg(cmd, "final render")

    # Cleanup temp files
    for f in temp_files:
        try:
            os.remove(f)
        except:
            pass
    try:
        os.rmdir(temp_dir)
    except:
        pass

    return output_path


def render_preview(
    cutlist: CutList,
    clip_paths: Dict[str, str],
    output_path: str,
    width: int = 360,
    height: int = 640,
    duration_cap: float = 15.0,
) -> str:
    """Render a fast 360p preview."""
    config = RenderConfig(
        output_path=output_path,
        width=width,
        height=height,
        video_preset="ultrafast",
        video_crf=28,
    )

    # Truncate slots for preview
    preview_cutlist = cutlist.model_copy(deep=True)
    total = 0.0
    preview_slots = []
    for slot in preview_cutlist.slots:
        if total + slot.duration_s > duration_cap:
            break
        preview_slots.append(slot)
        total += slot.duration_s
    preview_cutlist.slots = preview_slots

    return compile_timeline(preview_cutlist, clip_paths, output_path, config)
