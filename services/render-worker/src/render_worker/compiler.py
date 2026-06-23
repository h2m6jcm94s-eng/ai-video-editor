# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""FFmpeg-based timeline compiler for beat-synced video rendering."""

import os
import shutil
import tempfile
import subprocess
import warnings
from typing import List, Optional, Dict
from shared_py.models import CutList, Slot, RenderConfig, AudioTrack


# Ordered from least to most capability. Used for tier-gating warnings only in M1.
STYLE_TIERS = ("cuts_only", "color_grade", "with_text", "with_effects", "full_remix")

PRESET_DIMENSIONS = {
    "youtube_16_9": (1280, 720),
    "reels_9_16": (720, 1280),
    "tiktok_9_16": (720, 1280),
    "square_1_1": (720, 720),
}

ASPECT_RATIO_DIMENSIONS = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "4:5": (720, 900),
    "1:1": (720, 720),
}


def resolve_render_dimensions(export_preset: Optional[str], aspect_ratio: Optional[str]) -> tuple[int, int]:
    """Resolve output width/height from export preset or cut-list aspect ratio."""
    if export_preset:
        return PRESET_DIMENSIONS.get(export_preset, (720, 1280))
    return ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (720, 1280))


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
        "C:\\Windows\\Fonts\\segoeuib.ttf",  # Windows
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\calibri.ttf",
        "C:\\Windows\\Fonts\\verdana.ttf",
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    return ""


def _get_fontconfig_file() -> Optional[str]:
    """Return a usable fontconfig configuration file path.

    FFmpeg's drawtext filter uses fontconfig to resolve font names.  On
    Windows the default config is often missing, which produces a non-fatal
    warning.  We generate a minimal config pointing at the system font
    directories so the warning is suppressed and font lookup works.
    """
    if os.environ.get("FONTCONFIG_FILE"):
        return os.environ.get("FONTCONFIG_FILE")

    cache_dir = os.path.join(tempfile.gettempdir(), "ave_fontconfig_cache")
    os.makedirs(cache_dir, exist_ok=True)

    font_dirs = []
    if os.name == "nt":
        font_dirs.append("C:\\Windows\\Fonts")
        # Some FFmpeg builds ship their own fonts directory.
        ffmpeg_dir = os.path.dirname(shutil.which("ffmpeg") or "")
        if ffmpeg_dir:
            font_dirs.append(os.path.join(ffmpeg_dir, "fonts"))
    else:
        font_dirs.extend([
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
        ])

    # Only keep dirs that actually exist so fontconfig doesn't complain.
    font_dirs = [d for d in font_dirs if os.path.isdir(d)]
    if not font_dirs:
        return None

    dir_xml = "".join(f"    <dir>{d}</dir>\n" for d in font_dirs)
    config = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
{dir_xml}    <cachedir>{cache_dir}</cachedir>
</fontconfig>
"""
    config_path = os.path.join(tempfile.gettempdir(), "ave_fonts.conf")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config)
    return config_path


def _run_ffmpeg(cmd: List[str], context: str, cwd: Optional[str] = None) -> None:
    """Run FFmpeg with rich error context on failure."""
    env = os.environ.copy()
    fontconfig = _get_fontconfig_file()
    if fontconfig and not env.get("FONTCONFIG_FILE"):
        env["FONTCONFIG_FILE"] = fontconfig

    try:
        subprocess.run(cmd, check=True, capture_output=True, cwd=cwd, env=env)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        log_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".log", prefix="ave_ffmpeg_", delete=False
            ) as f:
                log_path = f.name
                f.write(f"\n--- {context} ---\n")
                f.write(f"Command: {' '.join(cmd)}\n")
                f.write(f"Return code: {e.returncode}\n")
                f.write(f"Stderr:\n{stderr}\n")
        except Exception:
            pass
        raise RuntimeError(
            f"FFmpeg failed during {context}: {e.returncode}\n"
            f"Command: {' '.join(cmd[:20])}...\n"
            f"Log: {log_path}\n"
            f"Stderr: {stderr[:2000]}"
        ) from e


# Paths supplied by callers must stay inside temp directories / cwd so FFmpeg
# cannot be tricked into reading or writing arbitrary filesystem locations.
_ALLOWED_ROOTS = {
    os.path.abspath(tempfile.gettempdir()),
    os.path.abspath(os.getcwd()),
}


def _safe_path(p: str, must_exist: bool = False) -> str:
    """Resolve p, reject path-traversal, and optionally require existence.

    Input clips must live inside an allowed root so FFmpeg cannot be asked to
    read arbitrary files. Output paths only need to be absolute and free of
    parent-directory traversal; the worker controls the actual destination.
    """
    abs_path = os.path.abspath(p)
    norm_path = os.path.normpath(abs_path)
    if ".." in norm_path.split(os.sep):
        raise ValueError(f"Refusing unsafe path: {p}")

    if not must_exist:
        normalized_input = os.path.normpath(p)
        is_abs = (
            normalized_input.startswith(("/", "\\"))
            or (len(normalized_input) > 1 and normalized_input[1] == ":")
        )
        if is_abs and ".." not in normalized_input.split(os.sep):
            return abs_path
        raise ValueError(f"Output path must be absolute: {p}")

    for root in _ALLOWED_ROOTS:
        if norm_path == root or norm_path.startswith(root + os.sep):
            if not os.path.exists(abs_path):
                raise ValueError(f"Required path does not exist: {p}")
            return abs_path
    raise ValueError(f"Path outside allowed roots: {p}")


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
    # Inside a single-quoted FFmpeg filter value, a literal single quote is
    # represented by two single quotes (''). Backslash escapes are not honored
    # inside single quotes, so we only need to escape '%' (strftime sequences).
    return t.replace("'", "''").replace("%", "\\%")


def _get_param(params, key: str, default):
    """Read an effect parameter whether params is a dict or a pydantic model."""
    if isinstance(params, dict):
        return params.get(key, default)
    return getattr(params, key, default)


def _enable_expr(start_s: float, end_s: float) -> str:
    """Build an FFmpeg enable expression for a time window.

    Commas are escaped because the filter chain is comma-separated.
    """
    # Commas inside the single-quoted enable expression are literal and must
    # not be escaped; FFmpeg's filter parser treats \\, inside quotes as an
    # invalid terminator and fails with EINVAL on Windows.
    return f"between(t,{start_s:.3f},{end_s:.3f})"


def _drawtext_filter(
    text: str,
    start_s: float,
    end_s: float,
    position: str,
    font_size_px: int,
    color: str,
    stroke: str,
    fontfile: str,
) -> str:
    """Build a drawtext filter string for an in-slot text effect."""
    x_expr = "(w-text_w)/2"
    y_expr = "(h-text_h)/2"
    if position == "top":
        y_expr = "h*0.1"
    elif position == "bottom":
        y_expr = "h*0.9"
    elif position == "top_left":
        x_expr = "w*0.05"
        y_expr = "h*0.1"
    elif position == "top_right":
        x_expr = "w*0.95-text_w"
        y_expr = "h*0.1"
    elif position == "bottom_left":
        x_expr = "w*0.05"
        y_expr = "h*0.9-text_h"
    elif position == "bottom_right":
        x_expr = "w*0.95-text_w"
        y_expr = "h*0.9-text_h"

    font_clause = f"fontfile={fontfile}:" if fontfile else ""
    enable = _enable_expr(start_s, end_s)
    return (
        f"drawtext=text='{_esc_text(text)}':"
        f"x={x_expr}:y={y_expr}:"
        f"fontsize={font_size_px}:"
        f"fontcolor={color}:"
        f"{font_clause}"
        f"borderw=2:bordercolor={stroke}:"
        f"enable='{enable}'"
    )


def _apply_video_effects(
    slot: Slot,
    base_vf: str,
    temp_dir: str,
    relative_font: str,
    config: RenderConfig,
    style_tier: str = "full_remix",
) -> str:
    """Apply video effects to a slot's filter chain.

    Effects are applied during segment extraction, so ``t`` is relative to the
    start of the slot.  ``effect.start_s`` is absolute timeline time; we compute
    a relative window for timeline-enabled filters.
    """
    filters = [base_vf] if base_vf else []

    if _tier_index(style_tier) < _tier_index("with_effects"):
        if slot.effects:
            _warn_if_below(style_tier, "with_effects", f"slot effects ({slot.index})")
        return ",".join(filters)

    for effect in slot.effects or []:
        etype = effect.type
        params = effect.params
        rel_start = max(0.0, effect.start_s - slot.start_s)
        rel_end = rel_start + min(effect.duration_s, slot.duration_s - rel_start)
        if rel_end <= rel_start:
            continue

        if etype == "zoom_punch_in":
            scale = _get_param(params, "target_scale", 1.3)
            dur = min(_get_param(params, "duration_ms", 300) / 1000.0, rel_end - rel_start)
            # Use a time-varying crop window to simulate a zoom/punch-in.
            # ``n`` is the frame index relative to the start of the segment.
            fps = config.fps or 30
            start_frame = int(rel_start * fps)
            end_frame = start_frame + max(1, int(dur * fps))
            ramp_expr = f"max(0\\,min(1\\,(n-{start_frame})/({end_frame}-{start_frame})))"
            filters.append(
                f"crop='iw/(1+({scale}-1)*{ramp_expr})':"
                f"'ih/(1+({scale}-1)*{ramp_expr})':"
                f"(iw-ow)/2:(ih-oh)/2"
            )

        elif etype == "vignette":
            intensity = _get_param(params, "intensity", 0.4)
            filters.append(
                f"vignette=PI/{max(0.01, 1 - intensity)}:enable='{_enable_expr(rel_start, rel_end)}'"
            )

        elif etype == "film_grain":
            intensity = _get_param(params, "intensity", 0.2)
            filters.append(
                f"noise=c0s={intensity * 10}:allf=t+u:enable='{_enable_expr(rel_start, rel_end)}'"
            )

        elif etype == "shake":
            intensity = _get_param(params, "intensity", 5)
            dur = min(_get_param(params, "duration_ms", 300) / 1000.0, rel_end - rel_start)
            fps = config.fps or 30
            start_frame = int(rel_start * fps)
            end_frame = start_frame + max(1, int(dur * fps))
            window = f"between(n\\,{start_frame}\\,{end_frame})"
            filters.append(
                f"crop=iw:ih:"
                f"'(random(1)*{intensity})*{window}':"
                f"'(random(1)*{intensity})*{window}'"
            )

        elif etype == "focus_pull":
            target_blur = _get_param(params, "target_blur", 4.0)
            dur = min(_get_param(params, "duration_ms", 600) / 1000.0, rel_end - rel_start)
            # Apply a Gaussian blur ramped up over the effect window.  gblur's
            # sigma is constant, so we simulate a ramp with a short fade-in by
            # chaining two blur passes of increasing strength.
            mid = rel_start + dur * 0.5
            filters.append(
                f"gblur=sigma={target_blur * 0.4:.2f}:steps=1:"
                f"enable='{_enable_expr(rel_start, mid)}'"
            )
            filters.append(
                f"gblur=sigma={target_blur:.2f}:steps=2:"
                f"enable='{_enable_expr(mid, rel_start + dur)}'"
            )

        elif etype == "glitch":
            intensity = _get_param(params, "intensity", 0.3)
            shift = max(1, int(intensity * 20))
            filters.append(
                f"rgbashift=rh={shift}:gh=-{shift}:bv={shift}:"
                f"enable='{_enable_expr(rel_start, rel_end)}'"
            )
            filters.append(
                f"noise=c0s={intensity * 8}:allf=t+u:"
                f"enable='{_enable_expr(rel_start, rel_end)}'"
            )

        elif etype == "color_pop":
            saturation = _get_param(params, "saturation", 1.5)
            hue_shift = _get_param(params, "hue_shift", 0.0)
            filters.append(
                f"eq=saturation={saturation}:"
                f"enable='{_enable_expr(rel_start, rel_end)}'"
            )
            if abs(hue_shift) > 0.1:
                filters.append(
                    f"hue=h={hue_shift}:enable='{_enable_expr(rel_start, rel_end)}'"
                )

        elif etype in ("text_kinetic", "lower_third", "callout_arrow"):
            text = _get_param(params, "text", "")
            if not text or not relative_font:
                continue
            position = "bottom" if etype == "lower_third" else _get_param(params, "position", "center")
            font_size_px = _get_param(params, "font_size_px", 42)
            color = _get_param(params, "color", "#FFFFFF")
            stroke = _get_param(params, "stroke", "#000000")
            # Render text via drawtext directly into the segment filter chain.
            # This keeps text locked to the slot; full-cutlist overlays are still
            # rendered in Stage 2 for global text elements.
            filters.append(
                _drawtext_filter(
                    text=text,
                    start_s=rel_start,
                    end_s=rel_end,
                    position=position,
                    font_size_px=font_size_px,
                    color=color,
                    stroke=stroke,
                    fontfile=relative_font,
                )
            )

        elif etype == "freeze_frame":
            warnings.warn(
                f"freeze_frame effect on slot {slot.index} is not yet rendered; "
                "it changes clip timing and requires time-remapping support.",
                stacklevel=3,
            )

        elif etype == "speed_ramp":
            warnings.warn(
                f"speed_ramp effect on slot {slot.index} is not yet rendered; "
                "it requires non-linear time-remapping to preserve timeline duration.",
                stacklevel=3,
            )

        elif etype in ("whoosh_sfx", "ding_sfx", "record_scratch_sfx"):
            warnings.warn(
                f"{etype} effect on slot {slot.index} is an audio SFX and is not "
                "yet rendered by the video compiler.",
                stacklevel=3,
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
        track_filters = []
        if track.fade_in_s and track.fade_in_s > 0:
            track_filters.append(f"afade=t=in:ss=0:d={track.fade_in_s}")

        fade_out = track.fade_out_s or 0.0
        if fade_out > 0:
            clip_dur = max(0.0, track.end_s - track.start_s)
            out_start = max(0.0, clip_dur - fade_out)
            if out_start > 0:
                track_filters.append(f"afade=t=out:st={out_start}:d={fade_out}")

        track_filters.append(f"volume={track.gain_db}dB")
        parts.append(f"[{idx}:a]{','.join(track_filters)}[a{idx}]")
        inputs.append(f"[a{idx}]")
        idx += 1

    if len(inputs) > 1:
        parts.append(f"{''.join(inputs)}amix=inputs={len(inputs)}:duration=longest:dropout_transition=0[amixed]")
        return ";".join(parts), idx
    elif inputs:
        parts.append(f"{inputs[0]}anull[amixed]")
        return ";".join(parts), idx
    return "", idx


def _apply_subject_mask(
    segment_path: str,
    mask_path: str,
    output_path: str,
    config: RenderConfig,
    temp_dir: str,
) -> None:
    """Composite a subject mask over a black background using FFmpeg.

    The mask is treated as an alpha matte: white areas keep the subject,
    black areas become transparent and reveal the black background.
    """
    width = config.width
    height = config.height
    fps = config.fps or 30.0

    filter_complex = (
        f"[1:v]format=gray,"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"setsar=1[mask];"
        f"[0:v][mask]alphamerge[fg];"
        f"color=c=black:s={width}x{height}:r={fps}[bg];"
        f"[bg][fg]overlay=0:0:shortest=1:format=auto"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", segment_path,
        "-i", mask_path,
        "-filter_complex", filter_complex,
        "-c:v", config.video_codec,
        "-preset", config.video_preset,
        "-crf", str(config.video_crf),
        "-pix_fmt", config.pix_fmt,
        "-an",
        output_path,
    ]
    _run_ffmpeg(cmd, "subject mask composite", cwd=temp_dir)


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

    # M1: enforce style tier gating. Hard cuts are allowed at every tier;
    # everything else is gated and silently dropped when below the required tier.
    enable_color_grade = _tier_index(style_tier) >= _tier_index("color_grade")
    enable_text = _tier_index(style_tier) >= _tier_index("with_text")
    enable_effects = _tier_index(style_tier) >= _tier_index("with_effects")
    enable_audio = _tier_index(style_tier) >= _tier_index("full_remix")

    if config.lut_path and not enable_color_grade:
        _warn_if_below(style_tier, "color_grade", "LUT / color grade")
    if cutlist.overlays and not enable_text:
        _warn_if_below(style_tier, "with_text", "text overlays")
    if cutlist.subtitles and not enable_text:
        _warn_if_below(style_tier, "with_text", "subtitles")
    if (cutlist.audio_tracks or config.song_path) and not enable_audio:
        _warn_if_below(style_tier, "full_remix", "audio tracks / song")
    for slot in cutlist.slots:
        if slot.effects and not enable_effects:
            _warn_if_below(style_tier, "with_effects", f"slot effects ({slot.index})")
        if (slot.transition_out != "hard_cut" or slot.transition_in != "hard_cut") and not enable_effects:
            _warn_if_below(style_tier, "with_effects", f"transitions ({slot.index})")

    # Sanitize input/output paths before handing them to FFmpeg.
    output_path = _safe_path(output_path)
    sanitized_clip_paths = {cid: _safe_path(p, must_exist=True) for cid, p in clip_paths.items()}

    # Stage 1: Extract each slot's segment from its assigned clip
    slot_segments = []
    temp_dir = tempfile.mkdtemp(prefix="ave_render_")

    try:
        # Copy the system font and LUT into the render temp dir up-front so both
        # per-slot text effects (Stage 1) and global overlays/LUT (Stage 2) can
        # reference them with relative, colon-free paths on Windows.
        fontfile = _find_font()
        relative_font = ""
        if fontfile and os.path.exists(fontfile):
            local_font = os.path.join(temp_dir, "font.ttf")
            shutil.copy2(fontfile, local_font)
            relative_font = "font.ttf"

        relative_lut = ""
        if config.lut_path:
            lut_path = _safe_path(config.lut_path, must_exist=True)
            if lut_path and os.path.exists(lut_path):
                local_lut = os.path.join(temp_dir, "lut" + os.path.splitext(lut_path)[1])
                shutil.copy2(lut_path, local_lut)
                relative_lut = os.path.basename(local_lut)

        for slot in cutlist.slots:
            clip_id = slot.selected_clip_id
            if not clip_id or clip_id not in sanitized_clip_paths:
                continue

            if slot.start_s < 0:
                raise ValueError(f"Slot {slot.index} has negative start_s: {slot.start_s}")

            clip_path = sanitized_clip_paths[clip_id]
            segment_path = os.path.join(temp_dir, f"slot_{slot.index:03d}.mp4")

            duration = slot.duration_s
            start = float(slot.start_s)

            base_vf = (
                f"fps={config.fps},"
                f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
                f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2"
            )

            vf = _apply_video_effects(slot, base_vf, temp_dir, relative_font, config, style_tier=style_tier)

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
            _run_ffmpeg(cmd, f"segment extraction for slot {slot.index}", cwd=temp_dir)

            # If this slot (or its clip) has a segmentation mask and masks are
            # enabled for the slot, composite the subject over black. Per-slot
            # masks take precedence over per-clip masks.
            raw_mask_path = None
            if getattr(slot, "mask_enabled", True):
                if config.slot_mask_paths and slot.index in config.slot_mask_paths:
                    raw_mask_path = config.slot_mask_paths[slot.index]
                elif config.mask_paths and clip_id in config.mask_paths:
                    raw_mask_path = config.mask_paths[clip_id]
            mask_path = raw_mask_path and _safe_path(raw_mask_path, must_exist=True)
            if mask_path and os.path.exists(mask_path):
                masked_segment_path = os.path.join(temp_dir, f"slot_{slot.index:03d}_masked.mp4")
                _apply_subject_mask(segment_path, mask_path, masked_segment_path, config, temp_dir)
                segment_path = masked_segment_path

            slot_segments.append({
                "path": segment_path,
                "slot": slot,
            })

        if not slot_segments:
            raise ValueError("No valid segments could be extracted")

        # Stage 2: Build filter_complex for concatenation + transitions
        filter_parts = []

        for i, _ in enumerate(slot_segments):
            filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")

        current_label = "v0"
        current_duration = slot_segments[0]["slot"].duration_s
        for i in range(len(slot_segments) - 1):
            slot = slot_segments[i]["slot"]
            next_slot = slot_segments[i + 1]["slot"]
            transition = XFADE_MAP.get(slot.transition_out if enable_effects else "hard_cut", "fade")
            xfade_duration = min(0.3, slot.duration_s * 0.5, next_slot.duration_s * 0.5)
            offset = max(0.0, current_duration - xfade_duration)

            out_label = f"vx{i}"
            filter_parts.append(
                f"[{current_label}][v{i+1}]xfade=transition={transition}:duration={xfade_duration}:offset={offset}[{out_label}]"
            )
            current_label = out_label
            current_duration = current_duration + next_slot.duration_s - xfade_duration

        # LUT application if available and tier allows it.
        if relative_lut and enable_color_grade:
            lut_label = f"{current_label}_lut"
            filter_parts.append(
                f"[{current_label}]format=rgb24,lut3d=file={relative_lut}:interp=tetrahedral[{lut_label}]"
            )
            current_label = lut_label

        # Text overlays (only when tier allows).
        for overlay in (cutlist.overlays if enable_text else []):
            start_s = round(max(0.0, overlay.start_s), 3)
            end_s = round(min(overlay.end_s, current_duration - 0.05), 3)
            if start_s >= current_duration or end_s <= start_s:
                continue

            text_label = f"text_{start_s}"
            x_expr = "(w-text_w)/2"
            y_expr = "(h-text_h)/2"
            if overlay.position == "top":
                y_expr = "h*0.1"
            elif overlay.position == "bottom":
                y_expr = "h*0.9"

            enable_expr = _enable_expr(start_s, end_s)

            filter_parts.append(
                f"[{current_label}]drawtext=text='{_esc_text(overlay.text)}':"
                f"x={x_expr}:y={y_expr}:"
                f"fontsize={overlay.font_size_px}:"
                f"fontcolor={overlay.color}:"
                f"{'fontfile=' + relative_font + ':' if relative_font else ''}"
                f"borderw=2:bordercolor={overlay.stroke or 'black'}:"
                f"enable='{enable_expr}'[{text_label}]"
            )
            current_label = text_label

        # Subtitles (only when tier allows).
        for subtitle in (cutlist.subtitles if enable_text else []):
            start_s = round(max(0.0, subtitle.start_s), 3)
            end_s = round(min(subtitle.end_s, current_duration - 0.05), 3)
            if start_s >= current_duration or end_s <= start_s or not subtitle.text.strip():
                continue

            sub_label = f"sub_{subtitle.id}_{start_s:.0f}"
            enable_expr = _enable_expr(start_s, end_s)

            filter_parts.append(
                f"[{current_label}]drawtext=text='{_esc_text(subtitle.text)}':"
                f"x=(w-text_w)/2:y=h*0.85:"
                f"fontsize=48:"
                f"fontcolor=#FFFFFF:"
                f"{'fontfile=' + relative_font + ':' if relative_font else ''}"
                f"borderw=2:bordercolor=#000000:"
                f"enable='{enable_expr}'[{sub_label}]"
            )
            current_label = sub_label

        # Final output mapping
        filter_parts.append(f"[{current_label}]format=yuv420p[outv]")
        final_label = "outv"

        # Build full command
        input_args = []
        for seg in slot_segments:
            input_args.extend(["-i", seg["path"]])

        # Audio inputs (only when tier allows remixing audio).
        audio_tracks: List[AudioTrack] = []
        if enable_audio:
            audio_tracks = list(cutlist.audio_tracks) if hasattr(cutlist, "audio_tracks") else []
            if not audio_tracks and config.song_path and os.path.exists(config.song_path or ""):
                audio_tracks = [AudioTrack(asset_id="song", start_s=0.0, end_s=1e9, gain_db=0.0)]

        for track in audio_tracks:
            path = sanitized_clip_paths.get(track.asset_id) or (config.song_path and _safe_path(config.song_path, must_exist=True))
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

        _run_ffmpeg(cmd, "final render", cwd=temp_dir)
        return output_path
    finally:
        # Remove the entire render scratch directory including fonts and any
        # segments that were created. ``ignore_errors`` keeps cleanup from
        # masking the real exception.
        shutil.rmtree(temp_dir, ignore_errors=True)

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
