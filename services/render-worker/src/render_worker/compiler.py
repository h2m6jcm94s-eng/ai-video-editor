# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""FFmpeg-based timeline compiler for beat-synced video rendering."""

import os
import tempfile
import subprocess
import warnings
from typing import List, Optional, Dict
import numpy as np
from PIL import ImageFont

from shared_py.models import CutList, Slot, Overlay, RenderConfig, Effect, AudioTrack


# Ordered from least to most capability. Used for tier-gating warnings only in M1.
STYLE_TIERS = ("cuts_only", "color_grade", "with_text", "with_effects", "full_remix")


def _tier_index(tier: str) -> int:
    try:
        return STYLE_TIERS.index(tier)
    except ValueError:
        return len(STYLE_TIERS) - 1


def _warn_if_below(style_tier: str, required_tier: str, feature: str) -> None:
    if _tier_index(style_tier) < _tier_index(required_tier):
        warnings.warn(
            f"Style tier '{style_tier}' does not include {feature}; "
            f"upgrade to '{required_tier}' or higher to render it.",
            stacklevel=3,
        )


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


def _get_param(params, key: str, default):
    """Read an effect parameter whether params is a dict or a pydantic model."""
    if isinstance(params, dict):
        return params.get(key, default)
    return getattr(params, key, default)


def _apply_video_effects(slot: Slot, base_vf: str) -> str:
    """Apply video effects to a slot's filter chain."""
    filters = [base_vf] if base_vf else []
    for effect in slot.effects or []:
        etype = effect.type
        params = effect.params
        if etype == "zoom_punch_in":
            scale = _get_param(params, "target_scale", 1.3)
            dur = _get_param(params, "duration_ms", 300) / 1000.0
            filters.append(
                f"zoompan=z='1+({scale}-1)*min(t/{dur},1)':d=1:s=1280x720"
            )
        elif etype == "vignette":
            intensity = _get_param(params, "intensity", 0.4)
            filters.append(f"vignette=PI/{max(0.01, 1 - intensity)}")
        elif etype == "film_grain":
            intensity = _get_param(params, "intensity", 0.2)
            filters.append(f"noise=c0s={intensity*10}:allf=t+u")
        elif etype == "shake":
            intensity = _get_param(params, "intensity", 5)
            dur = _get_param(params, "duration_ms", 300) / 1000.0
            filters.append(
                f"crop=iw:ih:(random(1)*{intensity}):(random(1)*{intensity}):enable='lte(t,{dur})'"
            )
    return ",".join(filters)


def _build_audio_filter(audio_tracks: List[AudioTrack], base_input_count: int, song_path: Optional[str]) -> tuple[str, int]:
    """Build amix filter for multi-audio tracks. Returns filter string and output audio label."""
    if not audio_tracks and not song_path:
        return "", -1

    parts = []
    inputs = []
    idx = base_input_count

    for track in audio_tracks:
        parts.append(f"[{idx}:a]afade=t=in:ss=0:d={track.fade_in_s},afade=t=out:st={max(0, track.end_s - track.start_s - track.fade_out_s)}:d={track.fade_out_s},volume={track.gain_db}dB[a{idx}]")
        inputs.append(f"[a{idx}]")
        idx += 1

    if song_path:
        parts.append(f"[{idx}:a]anull[asong]")
        inputs.append("[asong]")
        idx += 1

    if len(inputs) > 1:
        parts.append(f"{''.join(inputs)}amix=inputs={len(inputs)}:duration=longest:dropout_transition=0[amixed]")
        return ";".join(parts), idx
    elif inputs:
        parts.append(f"{inputs[0]}anull[amixed]")
        return ";".join(parts), idx
    return "", idx


def compile_timeline(
    cutlist: CutList,
    clip_paths: Dict[str, str],
    output_path: str,
    config: RenderConfig,
    style_tier: str = "full_remix",
) -> str:
    """Compile a cut-list into a final video using FFmpeg."""
    if not cutlist.slots:
        raise ValueError("Cut list has no slots")

    # M1: warn when the cutlist requests features above the purchased style tier.
    #     Hard cuts are allowed at every tier; everything else is gated.
    if config.lut_path:
        _warn_if_below(style_tier, "color_grade", "LUT / color grade")
    if cutlist.overlays:
        _warn_if_below(style_tier, "with_text", "text overlays")
    if cutlist.audio_tracks or config.song_path:
        _warn_if_below(style_tier, "full_remix", "audio tracks / song")
    for slot in cutlist.slots:
        if slot.effects:
            _warn_if_below(style_tier, "with_effects", f"slot effects ({slot.index})")
        if slot.transition_out != "hard_cut" or slot.transition_in != "hard_cut":
            _warn_if_below(style_tier, "with_effects", f"transitions ({slot.index})")

    # Stage 1: Extract each slot's segment from its assigned clip
    slot_segments = []
    temp_files = []
    temp_dir = tempfile.mkdtemp(prefix="ave_render_")

    for slot in cutlist.slots:
        clip_id = slot.selected_clip_id
        if not clip_id or clip_id not in clip_paths:
            continue

        clip_path = clip_paths[clip_id]
        segment_path = os.path.join(temp_dir, f"slot_{slot.index:03d}.mp4")

        duration = slot.duration_s
        start = 0.0

        base_vf = (
            f"fps={config.fps},"
            f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
            f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2"
        )

        vf = _apply_video_effects(slot, base_vf)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", clip_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "23", "-pix_fmt", "yuv420p",
            "-an",
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
    filter_parts = []

    for i, _ in enumerate(slot_segments):
        filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")

    current_label = "v0"
    for i in range(len(slot_segments) - 1):
        slot = slot_segments[i]["slot"]
        transition = XFADE_MAP.get(slot.transition_out, "fade")
        xfade_duration = min(0.3, slot.duration_s * 0.5)
        offset = max(0.0, slot.duration_s - xfade_duration)

        out_label = f"vx{i}"
        filter_parts.append(
            f"[{current_label}][v{i+1}]xfade=transition={transition}:duration={xfade_duration}:offset={offset}[{out_label}]"
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
        x_expr = "(w-text_w)/2"
        y_expr = "(h-text_h)/2"
        if overlay.position == "top":
            y_expr = "h*0.1"
        elif overlay.position == "bottom":
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
    filter_parts.append(f"[{current_label}]format=yuv420p[outv]")
    final_label = "outv"

    # Build full command
    input_args = []
    for seg in slot_segments:
        input_args.extend(["-i", seg["path"]])

    # Audio inputs
    audio_tracks = list(cutlist.audio_tracks) if hasattr(cutlist, "audio_tracks") else []
    if not audio_tracks and config.song_path and os.path.exists(config.song_path or ""):
        audio_tracks = [AudioTrack(asset_id="song", start_s=0.0, end_s=1e9, gain_db=0.0)]

    for track in audio_tracks:
        path = clip_paths.get(track.asset_id) or config.song_path
        if path and os.path.exists(path):
            input_args.extend(["-i", path])

    audio_filter, _ = _build_audio_filter(audio_tracks, len(slot_segments), config.song_path)
    if audio_filter:
        filter_parts.append(audio_filter)

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

    if audio_filter:
        cmd.extend(["-map", "[amixed]", "-c:a", config.audio_codec, "-b:a", config.audio_bitrate, "-shortest"])
    else:
        cmd.extend(["-an"])

    cmd.extend(["-movflags", "+faststart", output_path])

    _run_ffmpeg(cmd, "final render")

    # Cleanup temp files
    for f in temp_files:
        try:
            os.remove(f)
        except OSError:
            pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass

    return output_path


def render_preview(
    cutlist: CutList,
    clip_paths: Dict[str, str],
    output_path: str,
    width: int = 360,
    height: int = 640,
    duration_cap: float = 15.0,
    style_tier: str = "full_remix",
) -> str:
    """Render a fast 360p preview."""
    config = RenderConfig(
        output_path=output_path,
        width=width,
        height=height,
        video_preset="ultrafast",
        video_crf=28,
    )

    preview_cutlist = cutlist.model_copy(deep=True)
    total = 0.0
    preview_slots = []
    for slot in preview_cutlist.slots:
        if total + slot.duration_s > duration_cap:
            break
        preview_slots.append(slot)
        total += slot.duration_s
    preview_cutlist.slots = preview_slots

    return compile_timeline(preview_cutlist, clip_paths, output_path, config, style_tier=style_tier)
