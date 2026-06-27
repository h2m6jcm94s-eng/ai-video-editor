# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""FFmpeg-based timeline compiler for beat-synced video rendering."""

import os
import shutil
import tempfile
import subprocess
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, NamedTuple
from shared_py.models import CutList, Slot, RenderConfig, AudioTrack, Overlay
from shared_py.tuning import COMPILER


# Ordered from least to most capability. Used for tier-gating warnings only in M1.
STYLE_TIERS = ("cuts_only", "color_grade", "with_text", "with_effects", "full_remix")

# Re-export dimension/quality tables from the centralized tuning module so
# existing imports continue to work.
PRESET_DIMENSIONS = COMPILER.PRESET_DIMENSIONS
QUALITY_PROFILES = COMPILER.QUALITY_PROFILES
ASPECT_RATIO_DIMENSIONS = COMPILER.ASPECT_RATIO_DIMENSIONS


def resolve_render_dimensions(export_preset: Optional[str], aspect_ratio: Optional[str]) -> tuple[int, int]:
    """Resolve output width/height from export preset or cut-list aspect ratio."""
    if export_preset:
        return PRESET_DIMENSIONS.get(export_preset, (1080, 1920))
    return ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1080, 1920))


def _video_encode_args(config: RenderConfig) -> List[str]:
    """Return codec/preset/quality args tuned for the selected encoder."""
    if config.use_nvenc or config.video_codec in ("h264_nvenc", "hevc_nvenc"):
        codec = config.video_codec if config.video_codec in ("h264_nvenc", "hevc_nvenc") else "h264_nvenc"
        preset = config.nvenc_preset or "p5"
        cq = config.nvenc_cq if config.nvenc_cq and config.nvenc_cq > 0 else 19
        return [
            "-c:v", codec,
            "-preset", preset,
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", str(cq),
            "-pix_fmt", config.pix_fmt,
        ]

    args = ["-c:v", config.video_codec, "-preset", config.video_preset]
    args.extend(["-crf", str(config.video_crf), "-pix_fmt", config.pix_fmt])
    return args


# Valid presets for the intermediate segment encoder.  NVENC presets are p1
# (fastest) through p7 (slowest/best); libx264 presets are the standard set.
_NVENC_PRESETS = frozenset({f"p{i}" for i in range(1, 8)})
_LIBX264_PRESETS = frozenset(
    {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"}
)


def _segment_video_args(config: RenderConfig) -> List[str]:
    """Return encoder args for intermediate slot segments.

    Intermediate segments are re-encoded before final concat.  Using NVENC here
    (when available) removes the biggest CPU bottleneck in the render pipeline.
    """
    if config.use_nvenc:
        preset = config.nvenc_preset if config.nvenc_preset in _NVENC_PRESETS else "p5"
        cq = config.nvenc_cq if config.nvenc_cq and config.nvenc_cq > 0 else 19
        return [
            "-c:v", "h264_nvenc",
            "-preset", preset,
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", str(cq),
            "-pix_fmt", config.pix_fmt,
            "-an",
        ]

    preset = config.video_preset if config.video_preset in _LIBX264_PRESETS else "ultrafast"
    return [
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(config.video_crf),
        "-pix_fmt", config.pix_fmt,
        "-an",
    ]


def _tier_index(tier: str) -> int:
    try:
        return STYLE_TIERS.index(tier)
    except ValueError:
        return len(STYLE_TIERS) - 1


_ffprobe_duration_cache: Dict[str, float] = {}


def _probe_duration(video_path: str) -> float:
    """Return video duration in seconds using ffprobe, with caching."""
    if video_path in _ffprobe_duration_cache:
        return _ffprobe_duration_cache[video_path]

    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        duration = float(out) if out else 0.0
    except Exception:
        duration = 0.0

    _ffprobe_duration_cache[video_path] = duration
    return duration


def _db_to_linear(gain_db: float) -> float:
    """Convert a dB gain to a linear amplitude ratio."""
    return 10 ** (gain_db / 20.0)


def _extract_dialogue_audio(
    clip_path: str,
    source_start_s: float,
    source_end_s: float,
    temp_dir: str,
) -> Optional[str]:
    """Extract a single dialogue segment as a 48kHz stereo WAV with fades.

    Fades remove click/pop artefacts at cut points and resampling guarantees a
    common sample rate for the final mix.
    """
    duration = max(0.0, source_end_s - source_start_s)
    if duration < 0.05 or not os.path.exists(clip_path):
        return None

    fade_dur = min(COMPILER.DIALOGUE_FADE_MIN_S, duration / 2.0)
    out_start = max(0.0, duration - fade_dur)
    wav_path = os.path.join(temp_dir, f"dlg_{abs(hash(clip_path))}_{int(source_start_s*1000)}.wav")

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(source_start_s),
        "-t", str(duration),
        "-i", clip_path,
        "-vn",
        "-af", f"aresample={COMPILER.SILENCE_SAMPLE_RATE},afade=t=in:st=0:d={fade_dur},afade=t=out:st={out_start}:d={fade_dur}",
        "-ar", str(COMPILER.SILENCE_SAMPLE_RATE), "-ac", "2",
        wav_path,
    ]
    _run_ffmpeg(cmd, "dialogue audio extraction", cwd=temp_dir)
    return wav_path


def _dummy_silence_audio(duration: float, temp_dir: str) -> str:
    """Return a silent WAV of the requested duration."""
    duration = max(0.0, duration)
    wav_path = os.path.join(temp_dir, f"silence_{int(duration*1000)}.wav")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r={COMPILER.SILENCE_SAMPLE_RATE}:cl=stereo",
        "-t", str(duration),
        "-acodec", "pcm_s16le",
        wav_path,
    ]
    _run_ffmpeg(cmd, "silent audio placeholder", cwd=temp_dir)
    return wav_path


def _build_dialogue_bus(
    dialogue_segments: List[tuple[AudioTrack, str]],
    temp_dir: str,
) -> str:
    """Mix per-slot dialogue extracts into one timed, gated, compressed bus.

    Each segment is delayed to its timeline position so silent padding keeps the
    music sidechain from reacting when no one is speaking. The resulting WAV is
    a single input that can be used directly as the sidechain key.
    """
    if len(dialogue_segments) == 1:
        return dialogue_segments[0][1]

    output_path = os.path.join(temp_dir, "dialogue_bus.wav")
    inputs: List[str] = []
    for _, path in dialogue_segments:
        inputs.extend(["-i", path])

    parts: List[str] = []
    labels: List[str] = []
    for i, (track, _) in enumerate(dialogue_segments):
        label = f"dlg{i}"
        delay_ms = max(0, int(round(track.start_s * 1000)))
        filters = [f"volume={track.gain_db}dB"]
        if delay_ms > 0:
            filters.append(f"adelay=delays={delay_ms}|{delay_ms}:all=1")
        parts.append(f"[{i}:a]{','.join(filters)}[{label}]")
        labels.append(f"[{label}]")

    parts.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0[dlgbus]"
    )
    parts.append(
        f"[dlgbus]"
        f"agate=threshold={COMPILER.DIALOGUE_BUS_GATE_THRESHOLD_DB}dB:ratio={COMPILER.DIALOGUE_BUS_GATE_RATIO}:"
        f"attack={COMPILER.DIALOGUE_BUS_GATE_ATTACK_MS}:release={COMPILER.DIALOGUE_BUS_GATE_RELEASE_MS},"
        f"acompressor=threshold={COMPILER.DIALOGUE_BUS_COMP_THRESHOLD_DB}dB:ratio={COMPILER.DIALOGUE_BUS_COMP_RATIO}:"
        f"attack={COMPILER.DIALOGUE_BUS_COMP_ATTACK_MS}:release={COMPILER.DIALOGUE_BUS_COMP_RELEASE_MS}"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(parts),
        "-ar", str(COMPILER.SILENCE_SAMPLE_RATE), "-ac", "2",
        output_path,
    ]
    _run_ffmpeg(cmd, "dialogue bus mix", cwd=temp_dir)
    return output_path


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
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        log_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".log", prefix="ave_ffmpeg_", delete=False, encoding="utf-8"
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
    """Read an effect parameter whether params is a dict or a pydantic model.

    Supports both snake_case (legacy/Python) and camelCase (schema/TS) keys.
    """
    camel_key = "".join([key.split("_")[0]] + [w.capitalize() for w in key.split("_")[1:]])
    if isinstance(params, dict):
        if key in params:
            return params[key]
        if camel_key in params:
            return params[camel_key]
        return default
    if hasattr(params, key):
        return getattr(params, key)
    if hasattr(params, camel_key):
        return getattr(params, camel_key)
    return default


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


class SlotAudioMix(NamedTuple):
    """Per-slot audio mix decision used by the two-pass audio renderer."""

    song_level_db: float
    clip_audio_enabled: bool


def _duck_ratio(duck_gain_db: float) -> float:
    """Convert a negative duck gain to a sidechaincompress ratio >= 1."""
    return max(1.0, round(10 ** (abs(duck_gain_db) / 20.0), 2))


def _fade_filters(track: AudioTrack) -> List[str]:
    """Return afade filters for a music track based on its declared window."""
    filters: List[str] = []
    if track.fade_in_s and track.fade_in_s > 0:
        filters.append(f"afade=t=in:ss=0:d={track.fade_in_s}")
    fade_out = track.fade_out_s or 0.0
    if fade_out > 0:
        clip_dur = max(0.0, track.end_s - track.start_s)
        out_start = max(0.0, clip_dur - fade_out)
        if out_start > 0:
            filters.append(f"afade=t=out:st={out_start}:d={fade_out}")
    return filters


def _build_audio_filter(
    audio_tracks: List[AudioTrack],
    audio_paths: List[str],
    base_input_count: int,
    song_path: Optional[str],
    temp_dir: Optional[str] = None,
) -> tuple[str, int, List[str]]:
    """Build audio filter graph with adaptive ducking.

    Dialogue/voiceover tracks are expected to be a single pre-mixed bus file
    (produced by ``_build_dialogue_bus``) when ducking is required. This avoids
    an FFmpeg limitation where ``sidechaincompress`` cannot use a filter-output
    sidechain stream in graphs that also contain video filters.

    Returns the filter string, the next input index, and a list of extra audio
    files that must be appended as additional inputs to the FFmpeg command.
    """
    if not audio_tracks and not song_path:
        return "", -1, []

    music_tracks: List[tuple[int, AudioTrack]] = []
    dialogue_tracks: List[tuple[int, AudioTrack]] = []
    other_tracks: List[tuple[int, AudioTrack]] = []
    for offset, track in enumerate(audio_tracks):
        idx = base_input_count + offset
        if track.role == "music":
            music_tracks.append((idx, track))
        elif track.role in ("dialogue", "voiceover"):
            dialogue_tracks.append((idx, track))
        else:
            other_tracks.append((idx, track))

    parts: List[str] = []
    next_idx = base_input_count + len(audio_tracks)
    extra_inputs: List[str] = []

    # No ducking needed when there is no dialogue or no music.
    if not dialogue_tracks or not music_tracks:
        all_tracks = music_tracks + dialogue_tracks + other_tracks
        labels: List[str] = []
        for idx, track in all_tracks:
            label = f"trk{idx}"
            filters = [f"volume={track.gain_db}dB", *_fade_filters(track)]
            parts.append(f"[{idx}:a]{','.join(filters)}[{label}]")
            labels.append(label)
        if len(labels) > 1:
            parts.append(
                f"{''.join(f'[{l}]' for l in labels)}"
                f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
                f"acompressor=threshold=-12dB:ratio=4:attack=5:release=50[amixed]"
            )
        elif labels:
            parts.append(f"[{labels[0]}]anull[amixed]")
        return ";".join(parts), next_idx, extra_inputs

    # Multiple dialogues are pre-mixed by the caller. If we still receive more
    # than one, fall back to a plain amix without sidechain ducking.
    if len(dialogue_tracks) > 1:
        labels = []
        for idx, track in dialogue_tracks:
            label = f"dlg{idx}"
            delay_ms = max(0, int(round(track.start_s * 1000)))
            filters = [f"volume={track.gain_db}dB"]
            if delay_ms > 0:
                filters.append(f"adelay=delays={delay_ms}|{delay_ms}:all=1")
            parts.append(f"[{idx}:a]{','.join(filters)}[{label}]")
            labels.append(label)
        parts.append(
            f"{''.join(f'[{l}]' for l in labels)}"
            f"amix=inputs={len(labels)}:duration=longest:normalize=0[dlg_mix]"
        )
        dialogue_label = "dlg_mix"
    else:
        d_idx, d_track = dialogue_tracks[0]
        # The sidechain key must be the RAW input stream (FFmpeg limitation when
        # video filters are also in the graph). Mix gets a gain-adjusted copy.
        dialogue_label = f"dlg{d_idx}_mix"
        parts.append(f"[{d_idx}:a]volume={d_track.gain_db}dB[{dialogue_label}]")

    # Duck each music track against the raw dialogue bus input.
    music_labels: List[str] = []
    for idx, track in music_tracks:
        label = f"trk{idx}"
        filters = [f"volume={track.gain_db}dB", *_fade_filters(track)]

        if track.duck_disabled or len(dialogue_tracks) > 1:
            parts.append(f"[{idx}:a]{','.join(filters)}[{label}]")
        else:
            ratio = _duck_ratio(track.duck_gain_db)
            raw_label = f"{label}_raw"
            parts.append(f"[{idx}:a]{','.join(filters)}[{raw_label}]")
            parts.append(
                f"[{raw_label}][{d_idx}:a]"
                f"sidechaincompress=threshold={track.duck_threshold}:ratio={ratio}:"
                f"attack={track.duck_attack_ms}:release={track.duck_release_ms}:"
                f"level_sc=1[{label}]"
            )
        music_labels.append(label)

    # SFX / ambience straight through.
    other_labels: List[str] = []
    for idx, track in other_tracks:
        label = f"trk{idx}"
        parts.append(f"[{idx}:a]volume={track.gain_db}dB[{label}]")
        other_labels.append(label)

    # Final mix with a safety limiter.
    final_inputs = (
        [f"[{dialogue_label}]"]
        + [f"[{l}]" for l in music_labels]
        + [f"[{l}]" for l in other_labels]
    )
    if len(final_inputs) > 1:
        parts.append(
            f"{''.join(final_inputs)}"
            f"amix=inputs={len(final_inputs)}:duration=longest:normalize=0,"
            f"acompressor=threshold=-12dB:ratio=4:attack=5:release=50[amixed]"
        )
    elif final_inputs:
        parts.append(f"{final_inputs[0]}anull[amixed]")
    return ";".join(parts), next_idx, extra_inputs


def _build_music_volume_filter(
    slots: List[Slot],
    mix_decisions: List[SlotAudioMix],
    song_input_idx: int,
    temp_dir: str,
) -> str:
    """Build music volume filtering using asendcmd.

    Writes a sendcmd file to ``temp_dir`` and returns a filter graph fragment
    that turns the song input into the ``[music]`` labelled stream.  This avoids
    the deeply-nested ``if(between(t,...))`` expression that FFmpeg's audio
    evaluator rejects for long songs.
    """
    default_db = COMPILER.DEFAULT_MUSIC_GAIN_DB
    total_duration = slots[-1].start_s + slots[-1].duration_s if slots else 0.0

    raw_segments: List[tuple[float, float, float]] = []
    for slot, dec in zip(slots, mix_decisions):
        start = float(slot.start_s)
        end = float(slot.start_s + slot.duration_s)
        raw_segments.append((start, end, float(dec.song_level_db)))

    # Merge adjacent segments with identical gain.
    merged: List[tuple[float, float, float]] = []
    for start, end, db in raw_segments:
        if (
            merged
            and abs(merged[-1][2] - db) < 0.001
            and abs(merged[-1][1] - start) < 0.001
        ):
            merged[-1] = (merged[-1][0], end, db)
        else:
            merged.append((start, end, db))

    # Fill gaps before the first slot and after the last slot with default level.
    segments: List[tuple[float, float, float]] = []
    if not merged:
        segments.append((0.0, total_duration, default_db))
    else:
        if merged[0][0] > 0.001:
            segments.append((0.0, merged[0][0], default_db))
        segments.extend(merged)
        if merged[-1][1] < total_duration - 0.001:
            segments.append((merged[-1][1], total_duration, default_db))

    initial_linear = 10 ** (segments[0][2] / 20)
    cmd_lines: List[str] = []
    for start_s, _end_s, db in segments[1:]:
        linear = 10 ** (db / 20)
        cmd_lines.append(f"{start_s:.3f} volume volume {linear:.4f};")

    if cmd_lines:
        cmd_path = os.path.join(temp_dir, "volume_sendcmd.txt")
        with open(cmd_path, "w", encoding="utf-8") as f:
            f.write("\n".join(cmd_lines) + "\n")
        cmd_file = os.path.basename(cmd_path)
        return (
            f"[{song_input_idx}:a]"
            f"volume='{initial_linear:.4f}':eval=frame,"
            f"asendcmd=f={cmd_file},"
            f"aresample={COMPILER.SILENCE_SAMPLE_RATE}"
            f"[music]"
        )

    return (
        f"[{song_input_idx}:a]"
        f"volume='{initial_linear:.4f}':eval=frame,"
        f"aresample={COMPILER.SILENCE_SAMPLE_RATE}"
        f"[music]"
    )


def _build_audio_filter_v2(
    slots: List[Slot],
    song_input_idx: int,
    dialogue_specs: List[tuple[int, int, int, float]],
    mix_decisions: List[SlotAudioMix],
    temp_dir: str,
    dialogue_bus_idx: Optional[int] = None,
) -> str:
    """Build a two-pass FFmpeg audio filter graph with correct ducking.

    Video is rendered in a separate pass, so this graph contains only audio
    filters. That lets ``sidechaincompress`` use the gated dialogue bus as its
    sidechain input without hitting FFmpeg's limitation with mixed video/audio
    filter graphs.

    Improvements over the original v2:
      - Each dialogue track is gated *before* mixing so room tone / silence
        from other tracks cannot open the sidechain.
      - Dialogue buses are summed without normalization (preserve levels).
      - A safety limiter prevents clipping on the final output.

    When ``dialogue_bus_idx`` is provided, the dialogue tracks have already been
    mixed into a single bus (with per-track delays/gating) and are referenced
    directly. This keeps the final FFmpeg command line short when many clips
    contain dialogue.
    """
    parts: List[str] = []

    # 1. Music: per-section volume curve + resample to 48k.
    parts.append(
        _build_music_volume_filter(slots, mix_decisions, song_input_idx, temp_dir)
    )

    # Pad sidechain inputs to the full output duration so sidechaincompress does
    # not truncate the music bed to the length of the dialogue.
    total_duration_s = slots[-1].start_s + slots[-1].duration_s if slots else 0.0
    total_samples = int(total_duration_s * COMPILER.SILENCE_SAMPLE_RATE)

    if dialogue_bus_idx is not None:
        # Pre-built dialogue bus is already delayed, gated, and compressed.
        # Split it so the sidechain input can be consumed separately from the
        # dialogue stream used in the final mix.
        parts.append(
            f"[{dialogue_bus_idx}:a]"
            f"alimiter=level_in=1:level_out=1:limit=0.95,"
            f"asplit=2[dlg_sc][dlg_mix]"
        )
        if total_samples > 0:
            parts.append(f"[dlg_sc]apad=whole_len={total_samples}[dlg_sc_padded]")
        else:
            parts.append("[dlg_sc]anull[dlg_sc_padded]")
        parts.append(
            "[music][dlg_sc_padded]sidechaincompress="
            "threshold=0.12:"
            "ratio=4:"
            "attack=150:"
            "release=350"
            "[music_ducked]"
        )
        parts.append(
            "[music_ducked][dlg_mix]"
            "amix=inputs=2:duration=longest:weights='1.0 1.3':normalize=0"
            ",alimiter=level_in=1:level_out=1:limit=0.95"
            "[a_out]"
        )
        return ";".join(parts)

    # 2. Dialogue tracks: fade, gate, resample, delay to timeline position.
    #    asplit gives one stream for the sidechain key bus and one for the
    #    final dialogue mix bus.
    sc_labels: List[str] = []
    mix_labels: List[str] = []
    for slot_idx, input_idx, t_start_ms, dur_s in dialogue_specs:
        sc_label = f"dlg_sc_{slot_idx}"
        mix_label = f"dlg_mix_{slot_idx}"
        fade_out_start = max(0.0, dur_s - 0.03)
        parts.append(
            f"[{input_idx}:a]"
            f"afade=t=in:st=0:d=0.03,"
            f"afade=t=out:st={fade_out_start:.3f}:d=0.03,"
            f"agate=threshold=-45dB:ratio=10:attack=10:release=100,"
            f"aresample={COMPILER.SILENCE_SAMPLE_RATE},"
            f"adelay={t_start_ms}|{t_start_ms},"
            f"asplit=2[{sc_label}][{mix_label}]"
        )
        sc_labels.append(sc_label)
        mix_labels.append(mix_label)

    if not mix_labels:
        parts.append("[music]anull[a_out]")
        return ";".join(parts)

    # 3. Sum gated dialogue streams for the sidechain key (no normalization).
    sc_inputs = "".join(f"[{l}]" for l in sc_labels)
    parts.append(
        f"{sc_inputs}"
        f"amix=inputs={len(sc_labels)}:duration=longest:normalize=0"
        f",alimiter=level_in=1:level_out=1:limit=0.95"
        f"[dlg_sc]"
    )

    # 4. Sum gated dialogue streams for the final mix (no normalization).
    mix_inputs = "".join(f"[{l}]" for l in mix_labels)
    parts.append(
        f"{mix_inputs}"
        f"amix=inputs={len(mix_labels)}:duration=longest:normalize=0"
        f",alimiter=level_in=1:level_out=1:limit=0.95"
        f"[dlg_mix]"
    )

    # 5. Sidechain duck music using the gated-only dialogue bus.
    if total_samples > 0:
        parts.append(f"[dlg_sc]apad=whole_len={total_samples}[dlg_sc_padded]")
    else:
        parts.append("[dlg_sc]anull[dlg_sc_padded]")
    parts.append(
        "[music][dlg_sc_padded]sidechaincompress="
        "threshold=0.12:"
        "ratio=4:"
        "attack=150:"
        "release=350"
        "[music_ducked]"
    )

    # 6. Final mix with dialogue slightly boosted over the ducked bed.
    parts.append(
        "[music_ducked][dlg_mix]"
        "amix=inputs=2:duration=longest:weights='1.0 1.3':normalize=0"
        ",alimiter=level_in=1:level_out=1:limit=0.95"
        "[a_out]"
    )

    return ";".join(parts)


def _has_nvenc() -> bool:
    """Return True if FFmpeg was built with h264_nvenc."""
    try:
        out = subprocess.check_output(["ffmpeg", "-encoders"], stderr=subprocess.DEVNULL, text=True)
        return "h264_nvenc" in out
    except Exception:
        return False


def _extract_segment(args) -> Optional[dict]:
    """Extract and optionally mask/layer a single slot segment."""
    slot, clip_path, scaled_duration, config, temp_dir, relative_font, style_tier, kinetic_overlays = args
    segment_path = os.path.join(temp_dir, f"slot_{slot.index:03d}.mp4")

    # If the ranker did not pick a source window, deterministically rotate the
    # seek point across the clip so repeated clips show different moments instead
    # of replaying the same opening seconds.
    if slot.source_window_start_s is not None:
        base_start = float(slot.source_window_start_s)
    else:
        clip_duration = _probe_duration(clip_path)
        safe_max_start = max(0.0, clip_duration - scaled_duration - 0.5)
        if safe_max_start > 0:
            # 1.7 is an arbitrary irrational-ish step that spreads slots evenly.
            base_start = (slot.index * 1.7) % safe_max_start
        else:
            base_start = 0.0
    anticipation = float(getattr(slot, "anticipation_offset_s", 0.0) or 0.0)
    start = max(0.0, base_start + anticipation)
    clip_duration = _probe_duration(clip_path)
    duration = min(scaled_duration, max(0.0, clip_duration - start))
    if duration < 0.1:
        start = max(0.0, clip_duration - scaled_duration)
        duration = min(scaled_duration, max(0.0, clip_duration - start))
    if duration < 0.1:
        return None

    base_vf = (
        f"fps={config.fps},"
        f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
        f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2"
    )
    vf = _apply_video_effects(slot, base_vf, temp_dir, relative_font, config, style_tier=style_tier)

    encode_args = _segment_video_args(config)
    input_prefix = ["-hwaccel", "cuda"] if config.use_hwaccel else []
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        *input_prefix,
        "-i", clip_path,
        "-vf", vf,
        *encode_args,
        segment_path,
    ]
    try:
        _run_ffmpeg(cmd, f"segment extraction for slot {slot.index}", cwd=temp_dir)
    except RuntimeError:
        if config.use_hwaccel:
            warnings.warn(
                f"Hardware decode failed for slot {slot.index}; retrying with software decode.",
                stacklevel=2,
            )
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-t", str(duration),
                "-i", clip_path,
                "-vf", vf,
                *encode_args,
                segment_path,
            ]
            _run_ffmpeg(cmd, f"segment extraction for slot {slot.index}", cwd=temp_dir)
        else:
            raise

    raw_mask_path = None
    if getattr(slot, "mask_enabled", True):
        if config.slot_mask_paths and slot.index in config.slot_mask_paths:
            raw_mask_path = config.slot_mask_paths[slot.index]
        elif config.mask_paths and slot.selected_clip_id in config.mask_paths:
            raw_mask_path = config.mask_paths[slot.selected_clip_id]
    mask_path = raw_mask_path and _safe_path(raw_mask_path, must_exist=True)
    mask_exists = bool(mask_path and os.path.exists(mask_path))
    if mask_exists:
        masked_segment_path = os.path.join(temp_dir, f"slot_{slot.index:03d}_masked.mp4")
        _apply_subject_mask(segment_path, mask_path, masked_segment_path, config, temp_dir)
        segment_path = masked_segment_path

    # Kinetic text compositing: behind the subject when a mask exists, otherwise
    # fall back to a global overlay so the render does not fail without SAM3.
    if slot.enable_kinetic_text and slot.kinetic_text:
        if slot.text_z_layer == "behind_subject" and mask_exists:
            layered_path = os.path.join(temp_dir, f"slot_{slot.index:03d}_layered.mp4")
            _render_layered_text(
                segment_path,
                mask_path,
                layered_path,
                slot,
                config,
                temp_dir,
                relative_font,
                animation="bold_bounce",
            )
            segment_path = layered_path
        elif kinetic_overlays is not None:
            kinetic_overlays.append(Overlay(
                text=slot.kinetic_text,
                start_s=slot.start_s,
                end_s=slot.start_s + slot.duration_s,
                position="center",
                font="Inter",
                font_size_px=64,
                color="#FFFFFF",
                stroke="#000000",
                animation="pop",
            ))

    return {
        "path": segment_path,
        "slot": slot,
        "actual_duration": _probe_duration(segment_path),
    }


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
        *_video_encode_args(config),
        "-an",
        output_path,
    ]
    _run_ffmpeg(cmd, "subject mask composite", cwd=temp_dir)


def _render_layered_text(
    segment_path: str,
    mask_path: str,
    output_path: str,
    slot: Slot,
    config: RenderConfig,
    temp_dir: str,
    relative_font: str,
    animation: str = "bold_bounce",
) -> None:
    """Composite kinetic text behind a masked subject.

    The segment is treated as the foreground subject (via the mask alpha matte)
    and drawn over a text-filled background so the text appears behind the
    protagonist.
    """
    width = config.width
    height = config.height
    fps = config.fps or 30.0
    duration = _probe_duration(segment_path) or slot.duration_s or 1.0

    if animation == "bold_bounce":
        fontsize_expr = "48 + 24 * sin(t * 8)"
    else:
        fontsize_expr = "64"

    font_clause = f"fontfile={relative_font}:" if relative_font else ""
    enable = _enable_expr(0.0, duration)
    text = _esc_text(slot.kinetic_text or "")

    filter_complex = (
        f"[1:v]format=gray,"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"setsar=1[mask];"
        f"[0:v][mask]alphamerge[fg];"
        f"color=c=black:s={width}x{height}:r={fps}[bg];"
        f"[bg]drawtext=text='{text}':"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"fontsize={fontsize_expr}:"
        f"fontcolor=white:"
        f"{font_clause}"
        f"borderw=2:bordercolor=black:"
        f"enable='{enable}'[textbg];"
        f"[textbg][fg]overlay=0:0:shortest=1:format=auto[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", segment_path,
        "-i", mask_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        *_video_encode_args(config),
        "-an",
        output_path,
    ]
    _run_ffmpeg(cmd, f"layered kinetic text for slot {slot.index}", cwd=temp_dir)


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
    # Audio is a base feature: if a song or audio track is provided, render it.
    enable_audio = bool(cutlist.audio_tracks or config.song_path)

    if config.lut_path and not enable_color_grade:
        _warn_if_below(style_tier, "color_grade", "LUT / color grade")
    if cutlist.overlays and not enable_text:
        _warn_if_below(style_tier, "with_text", "text overlays")
    if cutlist.subtitles and not enable_text:
        _warn_if_below(style_tier, "with_text", "subtitles")
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

    # Scale slot durations to compensate for xfade transition overlap. The
    # compiler overlaps adjacent slots by ~0.3s per transition, so we need
    # extra source content to end up at the target duration.
    target_duration = cutlist.globals.total_duration_s
    raw_slot_sum = sum(s.duration_s for s in cutlist.slots)
    estimated_overlap = (len(cutlist.slots) - 1) * 0.3
    desired_slot_sum = target_duration + estimated_overlap
    duration_scale = desired_slot_sum / raw_slot_sum if raw_slot_sum > 0 else 1.0
    scaled_durations = {
        s.index: s.duration_s * duration_scale for s in cutlist.slots
    }

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

        # Extract slot segments in parallel.  Each slot is an independent FFmpeg
        # subprocess, so we saturate CPU/GPU by running several at once.
        # Kinetic text that cannot be composited behind the subject is collected
        # here and appended to the global overlay list after extraction.
        kinetic_overlays: List[Overlay] = []
        extract_args = []
        for slot in cutlist.slots:
            clip_id = slot.selected_clip_id
            if not clip_id or clip_id not in sanitized_clip_paths:
                continue
            if slot.start_s < 0:
                raise ValueError(f"Slot {slot.index} has negative start_s: {slot.start_s}")
            clip_path = sanitized_clip_paths[clip_id]
            scaled_duration = scaled_durations.get(slot.index, slot.duration_s)
            extract_args.append((slot, clip_path, scaled_duration, config, temp_dir, relative_font, style_tier, kinetic_overlays))

        workers = max(1, (os.cpu_count() or 1))
        # Do not oversubscribe the GPU if NVENC is used downstream; cap workers.
        workers = min(workers, 8)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for seg in pool.map(_extract_segment, extract_args):
                if seg is not None:
                    slot_segments.append(seg)

        if not slot_segments:
            raise ValueError("No valid segments could be extracted")

        # Append kinetic-text fallbacks collected during segment extraction.
        if kinetic_overlays:
            cutlist.overlays = list(cutlist.overlays) + kinetic_overlays

        # Stage 2: Build filter_complex for concatenation + transitions
        filter_parts = []

        for i, _ in enumerate(slot_segments):
            filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")

        current_label = "v0"
        current_duration = slot_segments[0]["actual_duration"]
        for i in range(len(slot_segments) - 1):
            slot = slot_segments[i]["slot"]
            next_slot = slot_segments[i + 1]["slot"]
            transition = XFADE_MAP.get(slot.transition_out if enable_effects else "hard_cut", "fade")
            slot_dur = slot_segments[i]["actual_duration"]
            next_dur = slot_segments[i + 1]["actual_duration"]
            xfade_duration = min(0.3, slot_dur * 0.5, next_dur * 0.5)
            offset = max(0.0, current_duration - xfade_duration)

            out_label = f"vx{i}"
            filter_parts.append(
                f"[{current_label}][v{i+1}]xfade=transition={transition}:duration={xfade_duration}:offset={offset}[{out_label}]"
            )
            current_label = out_label
            current_duration = current_duration + next_dur - xfade_duration

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

        # Cap output at the cutlist's declared duration.
        duration_cap = cutlist.globals.total_duration_s

        # Build video-only intermediate. Audio is rendered in a separate pass so
        # the sidechain ducking graph can reference filter outputs without the
        # FFmpeg limitation that forbids sidechaincompress from using a filtered
        # stream when video filters are also present in the graph.
        video_input_args = []
        for seg in slot_segments:
            video_input_args.extend(["-i", seg["path"]])

        video_filter_complex = ";".join(filter_parts)
        video_only_path = os.path.join(temp_dir, "video_only.mp4")
        video_cmd = [
            "ffmpeg", "-y",
            *video_input_args,
            "-filter_complex", video_filter_complex,
            "-map", f"[{final_label}]",
            "-an",
            *_video_encode_args(config),
            "-movflags", "+faststart",
        ]
        if duration_cap and duration_cap > 0:
            video_cmd.extend(["-t", str(duration_cap)])
        video_cmd.append(video_only_path)

        try:
            debug_fc_path = os.path.join(os.getcwd(), "filter_complex_video_debug.txt")
            with open(debug_fc_path, "w", encoding="utf-8") as f:
                f.write(video_filter_complex)
        except Exception:
            pass

        _run_ffmpeg(video_cmd, "video pass", cwd=temp_dir)

        # Collect audio tracks.
        audio_tracks: List[AudioTrack] = []
        if enable_audio:
            audio_tracks = list(cutlist.audio_tracks) if hasattr(cutlist, "audio_tracks") else []
            if not audio_tracks and config.song_path and os.path.exists(config.song_path or ""):
                audio_tracks = [AudioTrack(asset_id="song", role="music", start_s=0.0, end_s=current_duration, gain_db=0.0)]

        slot_by_index = {seg["slot"].index: seg["slot"] for seg in slot_segments}
        music_tracks: List[AudioTrack] = []
        dialogue_segments: List[tuple[AudioTrack, str]] = []

        for track in audio_tracks:
            if track.role in ("dialogue", "voiceover"):
                clip_path = config.audio_paths.get(track.asset_id)
                if not clip_path:
                    clip_path = sanitized_clip_paths.get(track.asset_id)
                if not clip_path or not os.path.exists(clip_path):
                    continue

                src_start = track.source_start_s
                src_end = track.source_end_s
                if src_start is None:
                    slot = slot_by_index.get(track.slot_index) if track.slot_index is not None else None
                    if slot is None:
                        for seg in slot_segments:
                            s = seg["slot"]
                            if s.selected_clip_id == track.asset_id and abs(s.start_s - track.start_s) < 0.5:
                                slot = s
                                break
                    if slot is not None:
                        window_start = slot.source_window_start_s if slot.source_window_start_s is not None else slot.start_s
                        src_start = window_start + max(0.0, track.start_s - slot.start_s)
                        src_end = src_start + max(0.0, track.end_s - track.start_s)
                    else:
                        src_start = 0.0
                        src_end = max(0.0, track.end_s - track.start_s)
                clip_dur = _probe_duration(clip_path)
                src_start = max(0.0, min(src_start or 0.0, clip_dur - 0.05))
                src_end = max(src_start + 0.05, min(src_end or clip_dur, clip_dur))

                wav_path = _extract_dialogue_audio(clip_path, src_start, src_end, temp_dir)
                if wav_path:
                    dialogue_segments.append((track, wav_path))
                continue

            if track.role == "music":
                music_tracks.append(track)

        # Final mux: video-only intermediate + self-contained audio graph.
        if enable_audio and config.song_path and os.path.exists(config.song_path):
            song_input_idx = 1
            audio_input_args = ["-i", video_only_path, "-i", config.song_path]

            # Build a single pre-mixed dialogue bus.  This avoids a huge final
            # FFmpeg command line when many clips contain dialogue and keeps the
            # sidechain key + final dialogue mix perfectly aligned.
            dialogue_bus_idx: Optional[int] = None
            if dialogue_segments:
                dialogue_bus_path = _build_dialogue_bus(dialogue_segments, temp_dir)
                if dialogue_bus_path:
                    dialogue_bus_idx = 2
                    audio_input_args.extend(["-i", dialogue_bus_path])

            dialogue_specs: List[tuple[int, int, int, float]] = []

            mix_decisions: List[SlotAudioMix] = []
            for slot in cutlist.slots:
                song_level_db = 0.0
                for mt in music_tracks:
                    if mt.start_s <= slot.start_s < mt.end_s:
                        song_level_db = mt.gain_db
                        break
                has_dialogue = any(
                    t.slot_index == slot.index
                    for t, _ in dialogue_segments
                    if t.slot_index is not None
                )
                mix_decisions.append(SlotAudioMix(song_level_db=song_level_db, clip_audio_enabled=has_dialogue))

            audio_filter = _build_audio_filter_v2(
                cutlist.slots,
                song_input_idx,
                dialogue_specs,
                mix_decisions,
                temp_dir,
                dialogue_bus_idx=dialogue_bus_idx,
            )

            try:
                debug_fc_path = os.path.join(os.getcwd(), "filter_complex_audio_debug.txt")
                with open(debug_fc_path, "w", encoding="utf-8") as f:
                    f.write(audio_filter)
            except Exception:
                pass

            final_cmd = [
                "ffmpeg", "-y",
                *audio_input_args,
                "-filter_complex", audio_filter,
                "-map", "0:v",
                "-map", "[a_out]",
                "-c:v", "copy",
                "-c:a", config.audio_codec,
                "-b:a", config.audio_bitrate,
                "-movflags", "+faststart",
            ]
            if duration_cap and duration_cap > 0:
                final_cmd.extend(["-t", str(duration_cap)])
            final_cmd.append(output_path)

            _run_ffmpeg(final_cmd, "audio/mux pass", cwd=temp_dir)
        else:
            copy_cmd = [
                "ffmpeg", "-y",
                "-i", video_only_path,
                "-c", "copy",
                "-an",
                "-movflags", "+faststart",
            ]
            if duration_cap and duration_cap > 0:
                copy_cmd.extend(["-t", str(duration_cap)])
            copy_cmd.append(output_path)
            _run_ffmpeg(copy_cmd, "copy video pass", cwd=temp_dir)

        shutil.rmtree(temp_dir, ignore_errors=True)
        return output_path
    except Exception:
        # Keep the scratch directory for debugging on failure.
        import logging
        logging.error("Render failed; temp dir preserved: %s", temp_dir)
        raise


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
    profile = QUALITY_PROFILES["preview"]
    config = RenderConfig(
        output_path=output_path,
        width=width,
        height=height,
        video_preset=profile["preset"],
        video_crf=profile["crf"],
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