# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""FFmpeg-based timeline compiler for beat-synced video rendering."""

import json
import os
import shutil
import tempfile
import subprocess
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, NamedTuple
from shared_py.models import CutList, Slot, RenderConfig, AudioTrack, Overlay, WordTiming
from shared_py.tuning import COMPILER
from shared_py.logging_config import StructuredLogger
from render_worker.edits.flash_frame import flash_frame_filter
from render_worker.kinetic_animations import default_for_style, preset as _kinetic_preset
from render_worker.reframe import reframe_filter
from render_worker.stabilize import stabilization_filter

logger = StructuredLogger("render_worker.compiler")


# Ordered from least to most capability. Used for tier-gating warnings only in M1.
STYLE_TIERS = ("cuts_only", "color_grade", "with_text", "with_effects", "full_remix")

# Re-export dimension/quality tables from the centralized tuning module so
# existing imports continue to work.
PRESET_DIMENSIONS = COMPILER.PRESET_DIMENSIONS
QUALITY_PROFILES = COMPILER.QUALITY_PROFILES
ASPECT_RATIO_DIMENSIONS = COMPILER.ASPECT_RATIO_DIMENSIONS

# Telemetry counter for slots that fall back to deterministic rotation because the
# ranker did not provide a source_window_start_s.
_slot_window_fallback_count = 0
_slot_window_fallback_lock = threading.Lock()

# Bundled cinematic font directory. Fonts are downloaded by the setup script or
# manually by the operator. The compiler prefers these over system fonts so text
# renders consistently across machines.
_BUNDLED_FONT_DIR = os.environ.get(
    "AVE_FONT_DIR", "E:/ai-video-editor-storage/fonts/display"
)

# Canonical display font filenames (all SIL Open Font License or freely usable).
_FONT_FILES = {
    "Anton": "Anton-Regular.ttf",
    "Bebas Neue": "BebasNeue-Regular.ttf",
    "Cinzel": "Cinzel-Black.ttf",
    "Oswald": "Oswald-Bold.ttf",
    "Rajdhani": "Rajdhani-Bold.ttf",
    "Russo One": "RussoOne-Regular.ttf",
    "Teko": "Teko-Bold.ttf",
    "Montserrat": "Montserrat-Black.ttf",
    "Playfair Display": "PlayfairDisplay-Black.ttf",
    "League Spartan": "LeagueSpartan-Black.ttf",
}

# Map kinetic-text style presets to preferred font families.
_STYLE_PRESET_FONTS = {
    "anime_impact": ["Anton", "Bebas Neue", "Russo One"],
    "trailer_block": ["Bebas Neue", "Anton", "Oswald"],
    "stamp_white": ["Anton", "Bebas Neue"],
    "cinematic_serif": ["Cinzel", "Playfair Display"],
    "lowercase_intimate": ["Playfair Display", "Cinzel"],
    "neon_glitch": ["Rajdhani", "Teko", "League Spartan"],
    "handwritten_pen": ["League Spartan", "Rajdhani"],
    "shake_emphasis": ["Anton", "Bebas Neue", "Russo One"],
}

# Map common Overlay.font names to bundled families.
_FONT_NAME_ALIASES = {
    "Inter": "Montserrat",
    "Arial": "Anton",
    "Helvetica": "Oswald",
    "serif": "Cinzel",
    "sans-serif": "Montserrat",
    "display": "Anton",
}


def get_slot_window_fallback_count() -> int:
    """Return the number of slot window fallbacks since the last reset."""
    with _slot_window_fallback_lock:
        return _slot_window_fallback_count


def reset_slot_window_fallback_count() -> None:
    """Reset the slot window fallback counter."""
    global _slot_window_fallback_count
    with _slot_window_fallback_lock:
        _slot_window_fallback_count = 0


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
    """Return the first video stream duration in seconds, with caching.

    Uses the video stream duration rather than the container ``format`` duration
    so that clips whose audio track outlasts their video stream are not treated
    as longer than they really are.
    """
    if video_path in _ffprobe_duration_cache:
        return _ffprobe_duration_cache[video_path]

    duration = 0.0
    for entries in ("stream=duration", "format=duration"):
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", entries,
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
            if out and out.lower() != "n/a":
                duration = float(out)
                break
        except Exception:
            continue

    _ffprobe_duration_cache[video_path] = duration
    return duration


def _validate_output_tracks(output_path: str, expected_duration: Optional[float] = None) -> None:
    """Raise if the output file's video and audio tracks have mismatched durations.

    This catches the container-level bug where the video track dies mid-render
    (e.g. xfade/timebase failure) while the audio track completes.
    """
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_type,duration",
                "-of", "json",
                output_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        data = json.loads(out)
    except Exception as e:
        raise RuntimeError(f"Could not probe output tracks for {output_path}: {e}") from e

    durations: Dict[str, float] = {}
    for stream in data.get("streams", []):
        ctype = stream.get("codec_type")
        dur = stream.get("duration")
        if ctype in ("video", "audio") and dur is not None:
            try:
                durations[ctype] = float(dur)
            except (TypeError, ValueError):
                pass

    video_dur = durations.get("video")
    audio_dur = durations.get("audio")
    if video_dur is None:
        raise RuntimeError(f"Output {output_path} has no video stream")
    if audio_dur is None:
        # Silent outputs are allowed in some paths.
        return

    diff = abs(video_dur - audio_dur)
    tolerance = 0.5
    if diff > tolerance:
        raise RuntimeError(
            f"Output track duration mismatch: video={video_dur:.3f}s, "
            f"audio={audio_dur:.3f}s, diff={diff:.3f}s (tolerance {tolerance}s). "
            "The video track died before the audio track."
        )

    if expected_duration and expected_duration > 0:
        if abs(video_dur - expected_duration) > tolerance:
            raise RuntimeError(
                f"Output video duration mismatch: expected={expected_duration:.3f}s, "
                f"actual={video_dur:.3f}s, diff={abs(video_dur - expected_duration):.3f}s"
            )


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


def _copy_font_to_temp(temp_dir: str, family_or_preset: str) -> str:
    """Copy a resolved font into the render temp dir and return its basename."""
    path = _find_font(family_or_preset)
    if not path:
        return ""
    base = os.path.basename(path)
    local = os.path.join(temp_dir, base)
    if not os.path.exists(local):
        try:
            shutil.copy2(path, local)
        except Exception as exc:
            logger.warning("failed_to_copy_font", path=path, error=str(exc))
            return ""
    return base


def _build_font_map(temp_dir: str, cutlist: CutList) -> Dict[str, str]:
    """Copy all fonts referenced by the cutlist into temp_dir and map keys.

    Keys are Overlay.font values, kinetic-text style presets, and the empty
    string for the default font. Values are relative font filenames safe for
    FFmpeg on Windows (no colons, no backslashes).
    """
    font_map: Dict[str, str] = {}

    # Default font.
    default = _copy_font_to_temp(temp_dir, "")
    if default:
        font_map[""] = default

    # Kinetic text styles and in-slot text effects.
    for slot in cutlist.slots:
        style = getattr(slot, "kinetic_text_style", None) or ""
        if style and style not in font_map:
            copied = _copy_font_to_temp(temp_dir, style)
            if copied:
                font_map[style] = copied
        for effect in slot.effects or []:
            if effect.type in ("text_kinetic", "lower_third", "callout_arrow"):
                font = _get_param(effect.params or {}, "font", "")
                if font and font not in font_map:
                    copied = _copy_font_to_temp(temp_dir, font)
                    if copied:
                        font_map[font] = copied

    # Existing overlays.
    for overlay in (cutlist.overlays or []):
        font = overlay.font or ""
        if font and font not in font_map:
            copied = _copy_font_to_temp(temp_dir, font)
            if copied:
                font_map[font] = copied

    return font_map


def _find_font(family_or_preset: str = "") -> str:
    """Find a font file for the given family or style preset.

    Prefer bundled cinematic fonts, then fall back to system fonts. Returns an
    empty string if nothing usable is found.
    """
    family_or_preset = (family_or_preset or "").strip()

    # Resolve aliases like "Inter" -> bundled family.
    aliased = _FONT_NAME_ALIASES.get(family_or_preset)
    if aliased:
        family_or_preset = aliased

    candidates: List[str] = []
    if family_or_preset in _STYLE_PRESET_FONTS:
        candidates = _STYLE_PRESET_FONTS[family_or_preset]
    elif family_or_preset in _FONT_FILES:
        candidates = [family_or_preset]

    # Try bundled fonts first.
    if os.path.isdir(_BUNDLED_FONT_DIR):
        for name in candidates:
            path = os.path.join(_BUNDLED_FONT_DIR, _FONT_FILES[name])
            if os.path.exists(path):
                return path
        # If no specific mapping matched, return any available bundled font.
        for name in ("Anton", "Bebas Neue", "Montserrat", "Oswald"):
            path = os.path.join(_BUNDLED_FONT_DIR, _FONT_FILES[name])
            if os.path.exists(path):
                return path

    # System fallback.
    system_candidates = [
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
    for f in system_candidates:
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
XFADE_OVERLAP = 0.3  # seconds of overlap material needed per xfade boundary
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
    "zoomblur": "zoomin",
    "radial": "radial",
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
    animation: str = "none",
    fps: float = 30.0,
) -> str:
    """Build a drawtext filter string with cinematic font + animation support.

    Returns the drawtext clause (without input/output labels) so it can be
    inserted into filter_complex chains for in-slot effects, overlays, or the
    layered text background.
    """
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

    # Cinematic outline + soft drop shadow.
    style_clause = (
        f"borderw=8:bordercolor={stroke}:"
        f"shadowcolor=black@0.5:shadowx=4:shadowy=4"
    )

    animation = (animation or "none").lower()
    fontsize_expr = str(font_size_px)
    alpha_expr = ""
    x_anim_expr = x_expr
    y_anim_expr = y_expr

    # T.7 H4: cinematic kinetic-text animations.  We avoid fontsize expressions
    # because they crash the Windows FFmpeg build when spawned from Python, so
    # scale is approximated with fast alpha + position offsets.
    if animation in ("pop", "scale", "punch_in", "punch_in_3f"):
        # Punch-in: fast alpha ramp + slight vertical settle over 3 frames.
        frames = 3 if animation in ("pop", "punch_in", "punch_in_3f") else 6
        dur = max(0.001, frames / fps)
        alpha_expr = f"if(lt(t\\,{start_s})\\,0\\,if(lt(t\\,{start_s}+{dur})\\,(t-{start_s})/{dur}\\,1))"
        y_offset = int(font_size_px * 0.15)
        y_anim_expr = (
            f"{y_expr}-if(lt(t\\,{start_s}+{dur})\\,{y_offset}*(1-(t-{start_s})/{dur})\\,0)"
        )
    elif animation == "fade":
        dur = max(0.001, 10 / fps)
        alpha_expr = f"if(lt(t\\,{start_s})\\,0\\,if(lt(t\\,{start_s}+{dur})\\,(t-{start_s})/{dur}\\,1))"
    elif animation in ("typewriter", "type_on"):
        # Progressive reveal approximated as an alpha sweep over 12 frames.
        dur = max(0.001, 12 / fps)
        alpha_expr = f"if(lt(t\\,{start_s})\\,0\\,if(lt(t\\,{start_s}+{dur})\\,(t-{start_s})/{dur}\\,1))"
    elif animation in ("smash", "smash_cut", "smash_cut_2f"):
        # Smash-cut out: fade out + jitter over the last 2 frames.
        fade_dur = max(0.001, 2 / fps)
        alpha_expr = f"if(lt(t\\,{end_s}-{fade_dur})\\,1\\,({end_s}-t)/{fade_dur})"
        x_anim_expr = (
            f"{x_expr}+if(between(t\\,{end_s}-{fade_dur}\\,{end_s})\\,random(1)*10-5\\,0)"
        )
    elif animation in ("glitch", "glitch_in"):
        # Random x offset bursts every 200ms.
        x_anim_expr = f"{x_expr}+if(between(mod(t*1000\\,200)\\,0\\,100)\\,random(1)*20-10\\,0)"
    elif animation in ("shake", "shake_3f"):
        # Shake: random +/-5px translate for the first 3 frames, then hold.
        shake_dur = max(0.001, 3 / fps)
        x_anim_expr = (
            f"{x_expr}+if(lt(t\\,{start_s}+{shake_dur})\\,random(1)*10-5\\,0)"
        )
    elif animation == "bold_bounce":
        # Fontsize expression is unstable from Python subprocess; use alpha pulse.
        alpha_expr = f"0.75+0.25*sin(t*8)"

    alpha_clause = f"alpha='{alpha_expr}':" if alpha_expr else ""

    return (
        f"drawtext=text='{_esc_text(text)}':"
        f"x={x_anim_expr}:y={y_anim_expr}:"
        f"fontsize={fontsize_expr}:"
        f"fontcolor={color}:"
        f"{alpha_clause}"
        f"{font_clause}"
        f"{style_clause}:"
        f"enable='{enable}'"
    )


def _canonical_font_family(font_name: str) -> str:
    """Return the bundled font family name for ASS styles."""
    return _FONT_NAME_ALIASES.get(font_name or "", font_name or "Montserrat")


def _ass_color(hex_color: str) -> str:
    """Convert #RRGGBB to ASS BGR format ``&HBBGGRR&``."""
    hex_color = (hex_color or "#FFFFFF").lstrip("#")
    if len(hex_color) != 6:
        hex_color = "FFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b}{g}{r}&"


def _ass_alpha_color(hex_color: str, alpha_hex: str = "00") -> str:
    """Convert #RRGGBB with alpha to ASS ABGR format ``&HBBGGRRAA&``."""
    hex_color = (hex_color or "#FFFFFF").lstrip("#")
    if len(hex_color) != 6:
        hex_color = "FFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b}{g}{r}{alpha_hex}&"


def _ass_alignment(position: str) -> int:
    """Map Overlay.position to ASS Alignment value."""
    return {
        "bottom_left": 1,
        "bottom": 2,
        "bottom_right": 3,
        "left": 4,
        "center": 5,
        "right": 6,
        "top_left": 7,
        "top": 8,
        "top_right": 9,
    }.get((position or "center").lower(), 5)


def _ass_escape(text: str) -> str:
    """Escape literal characters that are special in ASS Dialogue text."""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace(",", "\\,")
    return text


def _ass_time(seconds: float) -> str:
    """Format seconds as ASS ``H:MM:SS.cc``."""
    seconds = max(0.0, seconds)
    cs = int(round((seconds % 1) * 100))
    if cs >= 100:
        cs = 99
    total_s = int(seconds)
    mm, ss = divmod(total_s, 60)
    h, mm = divmod(mm, 60)
    return f"{h}:{mm:02d}:{ss:02d}.{cs:02d}"


def _build_ass_for_overlay(
    overlay: Overlay,
    width: int,
    height: int,
    font_family: str,
) -> str:
    """Build an ASS subtitle file for word-by-word/typewriter text overlays.

    The output can be burned with FFmpeg's ``subtitles`` filter using the render
    temp directory as ``fontsdir`` so bundled fonts are found without installing
    them on the host OS.
    """
    font_family = _canonical_font_family(font_family)
    primary = _ass_color(overlay.color)
    secondary = _ass_color(overlay.highlight_color or overlay.color)
    outline = _ass_color(overlay.stroke or "#000000")
    back = "&H000000&"
    alignment = _ass_alignment(overlay.position)

    style_line = (
        f"Style: Default,{font_family},{overlay.font_size_px},"
        f"{primary},{secondary},{outline},{back},"
        f"0,0,0,0,100,100,0,0,1,3,2,{alignment},0,0,0,1"
    )

    header = (
        "[Script Info]\n"
        "Title: AVE Overlay\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_line}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    animation = (overlay.animation or "none").lower()
    words = overlay.words or []

    if animation == "word_by_word" and words:
        # Karaoke: highlight each word as it is spoken.
        line_text_parts = []
        for i, word in enumerate(words):
            next_start = words[i + 1].start_s if i + 1 < len(words) else overlay.end_s
            duration_s = max(0.0, next_start - word.start_s)
            cs = max(1, int(round(duration_s * 100)))
            line_text_parts.append(f"{{\\k{cs}}}{_ass_escape(word.text)}")
        line_text = " ".join(line_text_parts)
    elif animation == "karaoke_reveal" and words:
        # Stylized karaoke: ghost line with active words scaling up and swapping
        # to the highlight colour during their timing window.
        line_text_parts = []
        base_ms = int(round(overlay.start_s * 1000))
        end_ms = int(round(overlay.end_s * 1000))
        ghost_alpha = "99"
        active_color = _ass_color(overlay.highlight_color or overlay.color or "#FFFFFF")
        ghost_color = _ass_color(overlay.color or "#FFFFFF")
        for word in words:
            t1 = max(0, int(round(word.start_s * 1000)) - base_ms)
            t2 = max(t1 + 30, int(round(word.end_s * 1000)) - base_ms)
            t3 = min(t2 + 80, end_ms)
            tags = (
                f"{{\\alpha&H{ghost_alpha}&\\c{ghost_color}"
                f"\\t({t1},{t2},\\alpha&H00&\\c{active_color}\\fscx120\\fscy120)"
                f"\\t({t2},{t3},\\alpha&H{ghost_alpha}&\\c{ghost_color}\\fscx100\\fscy100)}}"
            )
            line_text_parts.append(tags + _ass_escape(word.text))
        line_text = " ".join(line_text_parts)
    elif animation == "typewriter":
        # Per-character reveal over the overlay duration.
        text = overlay.text or ""
        duration_s = max(0.001, overlay.end_s - overlay.start_s)
        n_chars = max(1, len(text))
        stagger_ms = max(30, int(round((duration_s / n_chars) * 1000)))
        parts = []
        for i, ch in enumerate(text):
            start_ms = i * stagger_ms
            end_ms = (i + 1) * stagger_ms
            parts.append(
                f"{{\\alpha&HFF\\t({start_ms},{end_ms},\\alpha&H0)}}{_ass_escape(ch)}"
            )
        line_text = "".join(parts)
    else:
        # Fallback to a simple fade-in if animation is not recognised.
        line_text = (
            f"{{\\fad(300,300)}}{_ass_escape(overlay.text or '')}"
        )

    dialogue = (
        f"Dialogue: 0,{_ass_time(overlay.start_s)},{_ass_time(overlay.end_s)},"
        f"Default,,0,0,0,,{line_text}"
    )
    return header + dialogue + "\n"


def _write_ass_for_overlay(
    overlay: Overlay,
    temp_dir: str,
    width: int,
    height: int,
    font_map: Dict[str, str],
) -> str:
    """Write an ASS file for ``overlay`` and return its basename."""
    font_key = overlay.font or ""
    font_family = font_map.get(font_key, font_map.get("", ""))
    if not font_family:
        # Last-resort copy the requested font into the temp dir.
        font_family = _copy_font_to_temp(temp_dir, font_key) or ""
    ass_content = _build_ass_for_overlay(overlay, width, height, font_key)
    basename = f"overlay_{int(round(overlay.start_s * 1000))}.ass"
    path = os.path.join(temp_dir, basename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    return basename


def _ass_filter_clause(
    overlay: Overlay,
    temp_dir: str,
    width: int,
    height: int,
    font_map: Dict[str, str],
) -> str:
    """Return an unlabeled FFmpeg filter clause that burns an ASS overlay.

    Useful inside per-slot filter chains where labels are implicit.
    """
    basename = _write_ass_for_overlay(overlay, temp_dir, width, height, font_map)
    return f"subtitles=filename={basename}"


def _speed_ramp_factor(slot: Slot) -> float:
    """Return average playback speed factor from a speed_ramp effect, or 1.0."""
    for effect in slot.effects or []:
        if effect.type == "speed_ramp":
            params = effect.params or {}
            start = float(_get_param(params, "start_speed", 1.0))
            end = float(_get_param(params, "end_speed", 1.0))
            return max(0.25, min(4.0, (start + end) / 2.0))
    return 1.0


def _apply_video_effects(
    slot: Slot,
    base_vf: str,
    temp_dir: str,
    font_map: Dict[str, str],
    config: RenderConfig,
    style_tier: str = "full_remix",
    speed_factor: float = 1.0,
    clip_path: Optional[str] = None,
) -> str:
    """Apply video effects to a slot's filter chain.

    Effects are applied during segment extraction, so ``t`` is relative to the
    start of the slot.  ``effect.start_s`` is absolute timeline time; we compute
    a relative window for timeline-enabled filters.
    """
    # Optional reframe / stabilization pre-filters applied to the source
    # resolution before scaling/padding.
    prefilters: List[str] = []
    for effect in slot.effects or []:
        if effect.type == "reframe" and clip_path:
            target_aspect = effect.params.get("target_aspect") if effect.params else None
            if target_aspect:
                prefilters.append(reframe_filter(clip_path, target_aspect))
        elif effect.type == "stabilize":
            method = effect.params.get("method", "deshake") if effect.params else "deshake"
            prefilters.append(stabilization_filter(method))

    filters = prefilters + ([base_vf] if base_vf else [])

    # Apply uniform speed scaling immediately after scaling/padding so that all
    # subsequent effect timings are relative to the final (scaled) slot timeline.
    if speed_factor != 1.0:
        filters.append(f"setpts=PTS/{speed_factor}")

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

        if etype == "flash_frame":
            filters.append(
                flash_frame_filter(rel_start, rel_end - rel_start, fps=config.fps or 30.0)
            )

        elif etype == "zoom_punch_in":
            scale = _get_param(params, "target_scale", 1.3)
            dur = min(_get_param(params, "duration_ms", 300) / 1000.0, rel_end - rel_start)
            center_x = _get_param(params, "center_x", 0.5)
            center_y = _get_param(params, "center_y", 0.5)
            # Use a time-varying crop window to simulate a zoom/punch-in.
            # ``n`` is the frame index relative to the start of the segment.
            fps = config.fps or 30
            start_frame = int(rel_start * fps)
            end_frame = start_frame + max(1, int(dur * fps))
            ramp_expr = f"max(0\\,min(1\\,(n-{start_frame})/({end_frame}-{start_frame})))"
            filters.append(
                f"crop='iw/(1+({scale}-1)*{ramp_expr})':"
                f"'ih/(1+({scale}-1)*{ramp_expr})':"
                f"(iw-ow)*{center_x}:(ih-oh)*{center_y}"
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
            if not text:
                continue
            position = "bottom" if etype == "lower_third" else _get_param(params, "position", "center")
            font_size_px = _get_param(params, "font_size_px", 42)
            color = _get_param(params, "color", "#FFFFFF")
            stroke = _get_param(params, "stroke", "#000000")
            animation = _get_param(params, "animation", "pop")
            font_key = _get_param(params, "font", "")
            animation_l = (animation or "pop").lower()

            if animation_l in ("word_by_word", "typewriter"):
                # Use ASS for true per-character / per-word reveals inside a slot.
                text_overlay = Overlay(
                    text=text,
                    start_s=rel_start,
                    end_s=rel_end,
                    position=position,
                    font=font_key or "Montserrat",
                    font_size_px=font_size_px,
                    color=color,
                    stroke=stroke,
                    animation=animation_l,
                )
                filters.append(
                    _ass_filter_clause(
                        text_overlay,
                        temp_dir,
                        config.width,
                        config.height,
                        font_map,
                    )
                )
                continue

            fontfile = font_map.get(font_key, font_map.get("", ""))
            if not fontfile:
                # Last-resort fallback to any available bundled/system font.
                fallback = _find_font(font_key or "")
                if fallback:
                    fontfile = _copy_font_to_temp(temp_dir, font_key or "")
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
                    fontfile=fontfile,
                    animation=animation,
                    fps=config.fps or 30.0,
                )
            )

        elif etype == "freeze_frame":
            warnings.warn(
                f"freeze_frame effect on slot {slot.index} is not yet rendered; "
                "it changes clip timing and requires time-remapping support.",
                stacklevel=3,
            )

        elif etype == "speed_ramp":
            # Time-remapping was already applied to the base stream above.
            pass

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
            f"acompressor=threshold=-14dB:ratio=3:attack=5:release=50,"
            f"alimiter=level_in=1:level_out=1:limit=0.95[amixed]"
        )
    elif final_inputs:
        parts.append(
            f"{final_inputs[0]}"
            f"acompressor=threshold=-14dB:ratio=3:attack=5:release=50,"
            f"alimiter=level_in=1:level_out=1:limit=0.95[amixed]"
        )
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
            ",acompressor=threshold=-14dB:ratio=3:attack=5:release=50"
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
        parts.append(
            "[music]"
            "acompressor=threshold=-14dB:ratio=3:attack=5:release=50,"
            "alimiter=level_in=1:level_out=1:limit=0.95"
            "[a_out]"
        )
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

    # 6. Final mix with dialogue slightly boosted over the ducked bed,
    #    followed by a master compressor + brick-wall limiter.
    parts.append(
        "[music_ducked][dlg_mix]"
        "amix=inputs=2:duration=longest:weights='1.0 1.3':normalize=0"
        ",acompressor=threshold=-14dB:ratio=3:attack=5:release=50"
        ",alimiter=level_in=1:level_out=1:limit=0.95"
        "[a_out]"
    )

    return ";".join(parts)


def _has_nvenc() -> bool:
    """Return True if FFmpeg can actually encode with h264_nvenc.

    Some builds list the encoder but fail at runtime because no NVIDIA
    hardware is present. A short test encode avoids selecting NVENC in
    those environments.
    """
    try:
        out = subprocess.check_output(["ffmpeg", "-encoders"], stderr=subprocess.DEVNULL, text=True)
        if "h264_nvenc" not in out:
            return False
    except Exception:
        return False

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f", "lavfi",
                "-i", "color=c=black:s=64x64:d=0.1",
                "-c:v", "h264_nvenc",
                "-f", "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        return False


def _extract_segment(args) -> Optional[dict]:
    """Extract and optionally mask/layer a single slot segment."""
    slot, clip_path, scaled_duration, config, temp_dir, font_map, style_tier, kinetic_overlays = args
    segment_path = os.path.join(temp_dir, f"slot_{slot.index:03d}.mp4")

    # If the ranker did not pick a source window, deterministically rotate the
    # seek point across the clip so repeated clips show different moments instead
    # of replaying the same opening seconds.
    if slot.source_window_start_s is not None:
        base_start = float(slot.source_window_start_s)
    else:
        global _slot_window_fallback_count
        with _slot_window_fallback_lock:
            _slot_window_fallback_count += 1
        logger.warning(
            "slot_window_fallback",
            slot_index=slot.index,
            clip_id=getattr(slot, "selected_clip_id", None),
            reason="source_window_start_s is None; rotating seek point",
        )
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

    # Ensure the chosen source window actually contains enough footage for this
    # slot. If the heatmap window or anticipation offset pushes the start too
    # late, rewind to the latest feasible start. This is the H2 residual fix:
    # never ask FFmpeg to read past the end of the source clip.
    speed_factor = _speed_ramp_factor(slot)
    source_duration = scaled_duration * speed_factor
    max_feasible_start = max(0.0, clip_duration - source_duration - 0.05)
    if start > max_feasible_start:
        logger.warning(
            "source_window_rewound_for_feasibility",
            slot_index=slot.index,
            requested_start=start,
            rewound_start=max_feasible_start,
            clip_duration=clip_duration,
            source_duration=source_duration,
        )
        start = max_feasible_start

    # Speed ramps consume more source time when speeding up and less when slowing
    # down, but the rendered slot duration stays fixed to the beat grid. Clamp the
    # speed factor to the amount of source footage actually available so we never
    # produce a freeze-frame tail.
    speed_factor = _speed_ramp_factor(slot)
    if scaled_duration > 0:
        max_available_speed = max(0.25, (clip_duration - start) / scaled_duration)
        if speed_factor > max_available_speed:
            logger.warning(
                "speed_ramp_clamped",
                slot_index=slot.index,
                requested_speed=speed_factor,
                available_speed=max_available_speed,
                clip_duration=clip_duration,
                start=start,
                scaled_duration=scaled_duration,
            )
            speed_factor = max(1.0, max_available_speed * 0.95)
    source_duration = scaled_duration * speed_factor

    duration = min(source_duration, max(0.0, clip_duration - start))
    if duration < 0.1:
        start = max(0.0, clip_duration - source_duration)
        duration = min(source_duration, max(0.0, clip_duration - start))
    if duration < 0.1:
        return None

    base_vf = (
        f"fps={config.fps},"
        f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
        f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2"
    )
    vf = _apply_video_effects(
        slot, base_vf, temp_dir, font_map, config,
        style_tier=style_tier, speed_factor=speed_factor,
        clip_path=clip_path,
    )

    # If the available source footage is shorter than the slot's timeline
    # duration (after speed ramps and window clamping), extend the segment to
    # the full slot duration so the container video track never underflows
    # during xfade/concat. Long extensions loop the available footage to avoid
    # a frozen-frame artefact; short gaps clone the last frame.
    rendered_output_duration = duration / speed_factor if speed_factor else duration
    pad_duration = max(0.0, scaled_duration - rendered_output_duration)
    if pad_duration > 0.05:
        logger.warning(
            "segment_extended_to_timeline",
            slot_index=slot.index,
            rendered_duration=rendered_output_duration,
            target_duration=scaled_duration,
            pad_duration=pad_duration,
            clip_id=getattr(slot, "selected_clip_id", None),
        )
        if pad_duration > 1.0:
            # Loop the existing footage. size is the number of frames in the
            # source window (after fps conversion), capped at the filter max.
            fps = config.fps or 30.0
            loop_size = min(32767, max(1, int(round(duration * fps))))
            vf = (
                f"{vf},"
                f"loop=loop=-1:size={loop_size}:start=0,"
                f"trim=duration={scaled_duration:.3f}"
            )
        else:
            vf = f"{vf},tpad=stop_mode=clone:stop_duration={pad_duration:.3f}"

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
    except RuntimeError as exc:
        err_text = str(exc)
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
        elif config.use_nvenc and ("Cannot allocate memory" in err_text or "4294967284" in err_text):
            warnings.warn(
                f"NVENC segment extraction failed for slot {slot.index} with memory error; "
                "retrying with software encoder.",
                stacklevel=2,
            )
            software_encode_args = [
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", str(config.video_crf),
                "-pix_fmt", config.pix_fmt,
                "-an",
            ]
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-t", str(duration),
                "-i", clip_path,
                "-vf", vf,
                *software_encode_args,
                segment_path,
            ]
            _run_ffmpeg(cmd, f"segment extraction for slot {slot.index} (software fallback)", cwd=temp_dir)
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
    # Validate that the rendered segment is roughly the requested length. A
    # severe underflow means the source window was too short; we keep the
    # segment but surface it in the runtime report so the Golden Render gate
    # can catch the freeze class rather than silently shipping it.
    rendered_duration = _probe_duration(segment_path)
    expected_duration = scaled_duration
    if rendered_duration > 0 and abs(rendered_duration - expected_duration) > 0.2:
        logger.warning(
            "segment_duration_mismatch",
            slot_index=slot.index,
            expected=expected_duration,
            actual=rendered_duration,
            clip_id=getattr(slot, "selected_clip_id", None),
        )

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
                font_map,
                animation="bold_bounce",
            )
            segment_path = layered_path
        elif kinetic_overlays is not None:
            color = getattr(slot, "kinetic_text_color", None) or "#FFFFFF"
            style = getattr(slot, "kinetic_text_style", None) or "anime_impact"
            animation = getattr(slot, "kinetic_text_animation", None)
            if not animation:
                animation = default_for_style(style, energy=float(getattr(slot, "energy_level", 0.5) or 0.5))
            kinetic_overlays.append(Overlay(
                text=slot.kinetic_text,
                start_s=slot.start_s,
                end_s=slot.start_s + slot.duration_s,
                position="center",
                font=style,
                font_size_px=64,
                color=color,
                stroke="#000000",
                animation=animation,
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
    font_map: Dict[str, str],
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

    style = getattr(slot, "kinetic_text_style", None) or "anime_impact"
    fontfile = font_map.get(style, font_map.get("", ""))
    color = getattr(slot, "kinetic_text_color", None) or "#FFFFFF"

    # Prefer the animation chosen by the reason worker, but keep the default
    # behind-subject animation if the selected one jumps too much.
    chosen = getattr(slot, "kinetic_text_animation", None)
    if chosen:
        p = _kinetic_preset(chosen)
        if p and p.safe_behind_subject:
            animation = chosen
    text_filter = _drawtext_filter(
        text=slot.kinetic_text or "",
        start_s=0.0,
        end_s=duration,
        position="center",
        font_size_px=64,
        color=color,
        stroke="#000000",
        fontfile=fontfile,
        animation=animation,
        fps=fps,
    )

    filter_complex = (
        f"[1:v]format=gray,"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"setsar=1[mask];"
        f"[0:v][mask]alphamerge[fg];"
        f"color=c=black:s={width}x{height}:r={fps}[bg];"
        f"[bg]{text_filter}[textbg];"
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


class _MergeNode(NamedTuple):
    """A node in the binary video-merge tree.

    ``timeline_duration`` is the intended raw content length of the node (sum of
    the underlying slot durations). ``media_duration`` is the actual video file
    length, which may be longer because it carries overlap tails needed by
    downstream xfade transitions.
    """

    path: str
    timeline_duration: float
    media_duration: float
    first_slot: Slot
    last_slot: Slot


def _transition_name_for_pair(left_slot: Slot, right_slot: Slot, enable_effects: bool) -> str:
    """Return the xfade transition name, or 'hard_cut' for no transition."""
    if not enable_effects:
        return "hard_cut"
    if getattr(left_slot, "transition_out", None) == "hard_cut":
        return "hard_cut"
    return XFADE_MAP.get(getattr(left_slot, "transition_out", None), "fade")


def _merge_two_video_nodes(
    left: _MergeNode,
    right: _MergeNode,
    actual_durations: Dict[int, float],
    temp_dir: str,
    config: RenderConfig,
    merge_index: int,
    enable_effects: bool,
) -> _MergeNode:
    """Concatenate or xfade two intermediate videos using only two inputs.

    Keeping each merge to two inputs prevents FFmpeg from opening dozens of
    decoder contexts at once, which exhausts memory on Windows when 100+ slots
    are chained in a single filter graph.
    """
    requested_transition = _transition_name_for_pair(left.last_slot, right.first_slot, enable_effects)
    out_path = os.path.join(temp_dir, f"merge_{merge_index:04d}.mp4")
    out_path_rel = os.path.basename(out_path)

    # Normalize inputs before concat/xfade: identical fps, pixel format, SAR,
    # timebase, and resolution. This prevents container-level video track death
    # when heterogeneous source clips (different fps/timebase/SAR) meet in xfade.
    norm = (
        f"fps={config.fps or 30.0}:round=near,"
        f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
        f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2,"
        "format=yuv420p,"
        "setsar=1,"
        "settb=1/30000"
    )

    def _build_filter_complex(transition: str) -> str:
        if transition == "hard_cut":
            # Trim the left input to its intended timeline so overlap tails
            # from the previous xfade are not shown again at a hard cut. The
            # right input is kept full so its own trailing overlaps remain
            # available for subsequent xfades.
            return (
                f"[0:v]{norm},setpts=PTS-STARTPTS,trim=start=0:duration={left.timeline_duration:.3f}[a];"
                f"[1:v]{norm},setpts=PTS-STARTPTS[b];"
                "[a][b]concat=n=2:v=1:a=0[outv]"
            )
        # xfade duration is limited by the actual media lengths of the two
        # inputs. Anchor the transition to the end of the left *media* so the
        # overlap tail carried by the left node is consumed by the blend.
        offset = max(0.0, left.media_duration - xfade_duration)
        return (
            f"[0:v]{norm},setpts=PTS-STARTPTS[a];"
            f"[1:v]{norm},setpts=PTS-STARTPTS[b];"
            f"[a][b]xfade=transition={transition}:duration={xfade_duration:.3f}:offset={offset:.3f}[outv]"
        )

    # Compute the actual xfade duration up front so the rest of the merge
    # (offset, underflow checks, and duration estimates) stays consistent.
    if requested_transition == "hard_cut":
        xfade_duration = 0.0
    else:
        xfade_duration = min(
            XFADE_OVERLAP,
            left.media_duration * 0.5,
            right.media_duration * 0.5,
        )

    # If either input is too short to provide the required overlap, fall back
    # to a hard cut for this boundary.
    if requested_transition != "hard_cut" and (
        left.media_duration < xfade_duration + 0.05
        or right.media_duration < xfade_duration + 0.05
    ):
        logger.warning(
            "merge_underflow_hard_cut",
            merge_index=merge_index,
            transition=requested_transition,
            left_slot=left.last_slot.index,
            left_timeline=left.timeline_duration,
            left_media=left.media_duration,
            right_slot=right.first_slot.index,
            right_timeline=right.timeline_duration,
            right_media=right.media_duration,
        )
        transition = "hard_cut"
        xfade_duration = 0.0
    else:
        transition = requested_transition

    filter_complex = _build_filter_complex(transition)

    cmd = [
        "ffmpeg", "-y",
        "-i", left.path,
        "-i", right.path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-an",
        *_video_encode_args(config),
        "-movflags", "+faststart",
        out_path_rel,
    ]
    try:
        _run_ffmpeg(cmd, f"video merge {merge_index}", cwd=temp_dir)
    except RuntimeError:
        if transition != "hard_cut":
            logger.warning(
                "merge_xfade_failed_fallback_to_hard_cut",
                merge_index=merge_index,
                transition=transition,
            )
            transition = "hard_cut"
            filter_complex = _build_filter_complex("hard_cut")
            cmd = [
                "ffmpeg", "-y",
                "-i", left.path,
                "-i", right.path,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-an",
                *_video_encode_args(config),
                "-movflags", "+faststart",
                out_path_rel,
            ]
            _run_ffmpeg(cmd, f"video merge {merge_index} (hard cut fallback)", cwd=temp_dir)
        else:
            raise

    # The merged output's actual length is what matters for downstream merges.
    # When probing fails, estimate from the inputs and the transition.
    if transition == "hard_cut":
        merged_media_duration = _probe_duration(out_path) or (
            left.timeline_duration + right.media_duration
        )
    else:
        merged_media_duration = _probe_duration(out_path) or (
            left.media_duration - xfade_duration + right.media_duration
        )
    # Timeline is the intended raw content length; overlaps are not double counted.
    merged_timeline_duration = left.timeline_duration + right.timeline_duration
    return _MergeNode(
        path=out_path_rel,
        timeline_duration=merged_timeline_duration,
        media_duration=merged_media_duration,
        first_slot=left.first_slot,
        last_slot=right.last_slot,
    )


def _build_overlay_filter_parts(
    current_label: str,
    current_duration: float,
    cutlist: CutList,
    font_map: Dict[str, str],
    relative_lut: str,
    enable_text: bool,
    enable_color_grade: bool,
    fps: float = 30.0,
    width: int = 1080,
    height: int = 1920,
    temp_dir: str = "",
) -> tuple[List[str], str]:
    """Build drawtext/ASS/LUT filter strings on a single input label."""
    filter_parts: List[str] = []

    if relative_lut and enable_color_grade:
        lut_label = f"{current_label}_lut"
        filter_parts.append(
            f"[{current_label}]format=rgb24,lut3d=file={relative_lut}:interp=tetrahedral[{lut_label}]"
        )
        current_label = lut_label

    for overlay in (cutlist.overlays if enable_text else []):
        start_s = round(max(0.0, overlay.start_s), 3)
        end_s = round(min(overlay.end_s, current_duration - 0.05), 3)
        if start_s >= current_duration or end_s <= start_s:
            continue

        text_label = f"text_{start_s}"
        relative_font = font_map.get(overlay.font or "")
        animation = (overlay.animation or "none").lower()
        use_ass = (
            animation in ("word_by_word", "typewriter", "karaoke_reveal")
            or overlay.words
        )

        if use_ass:
            ass_basename = _write_ass_for_overlay(
                overlay, temp_dir, width, height, font_map
            )
            filter_parts.append(
                f"[{current_label}]subtitles=filename={ass_basename}[{text_label}]"
            )
        else:
            drawtext = _drawtext_filter(
                text=overlay.text,
                start_s=start_s,
                end_s=end_s,
                position=overlay.position or "center",
                font_size_px=overlay.font_size_px or 48,
                color=overlay.color or "#FFFFFF",
                stroke=overlay.stroke or "#000000",
                fontfile=relative_font or "",
                animation=overlay.animation or "none",
                fps=fps,
            )
            filter_parts.append(f"[{current_label}]{drawtext}[{text_label}]")
        current_label = text_label

    for subtitle in (cutlist.subtitles if enable_text else []):
        start_s = round(max(0.0, subtitle.start_s), 3)
        end_s = round(min(subtitle.end_s, current_duration - 0.05), 3)
        if start_s >= current_duration or end_s <= start_s or not subtitle.text.strip():
            continue

        sub_label = f"sub_{subtitle.id}_{start_s:.0f}"
        relative_font = font_map.get("")
        drawtext = _drawtext_filter(
            text=subtitle.text,
            start_s=start_s,
            end_s=end_s,
            position="bottom",
            font_size_px=48,
            color="#FFFFFF",
            stroke="#000000",
            fontfile=relative_font or "",
            animation="none",
            fps=fps,
        )
        filter_parts.append(f"[{current_label}]{drawtext}[{sub_label}]")
        current_label = sub_label

    return filter_parts, current_label


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

    # Per-slot extraction durations. A slot that is the left side of a
    # non-hardcut transition needs extra tail material (overlap) so the xfade
    # has frames to blend without shortening the video track. Hard-cut
    # boundaries do not consume overlap, so they receive none.
    target_duration = cutlist.globals.total_duration_s
    scaled_durations: Dict[int, float] = {}
    for idx, slot in enumerate(cutlist.slots):
        overlap = 0.0
        if idx + 1 < len(cutlist.slots):
            next_slot = cutlist.slots[idx + 1]
            if _transition_name_for_pair(slot, next_slot, enable_effects) != "hard_cut":
                overlap = XFADE_OVERLAP
        scaled_durations[slot.index] = slot.duration_s + overlap

    try:
        # Copy all referenced fonts into the render temp dir up-front so both
        # per-slot text effects (Stage 1) and global overlays/LUT (Stage 2) can
        # reference them with relative, colon-free paths on Windows.
        font_map = _build_font_map(temp_dir, cutlist)

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
            extract_args.append((slot, clip_path, scaled_duration, config, temp_dir, font_map, style_tier, kinetic_overlays))

        workers = max(1, (os.cpu_count() or 1))
        # Keep peak decoder/encoder memory low. With NVENC we open multiple
        # hardware contexts; on memory-constrained Windows boxes this can fail
        # with "Cannot allocate memory" during segment extraction.
        # On this Windows workstation RAM is tight (Ollama + other services
        # often consume >20 GB). Sequential extraction avoids malloc failures.
        workers = min(workers, 1 if config.use_nvenc else 2)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for seg in pool.map(_extract_segment, extract_args):
                if seg is not None:
                    slot_segments.append(seg)

        if not slot_segments:
            raise ValueError("No valid segments could be extracted")

        # Append kinetic-text fallbacks collected during segment extraction.
        if kinetic_overlays:
            cutlist.overlays = list(cutlist.overlays) + kinetic_overlays

        # Stage 2: merge extracted slot segments into one continuous video.
        # A single FFmpeg filter graph with 100+ open inputs exhausts memory on
        # Windows, so we build a binary merge tree: each invocation concatenates
        # (or xfades) exactly two inputs. This caps peak decoder count at 2 and
        # limits re-encode generations to ~log2(N).
        actual_durations = {seg["slot"].index: seg["actual_duration"] for seg in slot_segments}

        nodes: List[_MergeNode] = [
            _MergeNode(
                path=os.path.basename(seg["path"]),
                timeline_duration=seg["slot"].duration_s,
                media_duration=seg["actual_duration"],
                first_slot=seg["slot"],
                last_slot=seg["slot"],
            )
            for seg in slot_segments
        ]

        merge_counter = 0
        while len(nodes) > 1:
            next_nodes: List[_MergeNode] = []
            for i in range(0, len(nodes), 2):
                if i + 1 >= len(nodes):
                    next_nodes.append(nodes[i])
                    continue
                merged = _merge_two_video_nodes(
                    nodes[i],
                    nodes[i + 1],
                    actual_durations,
                    temp_dir,
                    config,
                    merge_counter,
                    enable_effects,
                )
                next_nodes.append(merged)
                merge_counter += 1
            nodes = next_nodes

        merged_video_path_rel = nodes[0].path
        current_duration = nodes[0].timeline_duration

        # Stage 3: apply global LUT, text overlays, and subtitles on a single input.
        duration_cap = cutlist.globals.total_duration_s
        video_only_path = os.path.join(temp_dir, "video_only.mp4")
        video_only_path_rel = os.path.basename(video_only_path)

        filter_parts, final_label = _build_overlay_filter_parts(
            "v0",
            current_duration,
            cutlist,
            font_map,
            relative_lut,
            enable_text,
            enable_color_grade,
            fps=config.fps or 30.0,
            width=config.width,
            height=config.height,
            temp_dir=temp_dir,
        )

        if filter_parts:
            filter_parts.append(f"[{final_label}]format=yuv420p[outv]")
            final_label = "outv"
            video_filter_complex = ";".join(filter_parts)
            video_cmd = [
                "ffmpeg", "-y",
                "-i", merged_video_path_rel,
                "-filter_complex", video_filter_complex,
                "-map", f"[{final_label}]",
                "-an",
                *_video_encode_args(config),
                "-movflags", "+faststart",
            ]
            if duration_cap and duration_cap > 0:
                video_cmd.extend(["-t", str(duration_cap)])
            video_cmd.append(video_only_path_rel)

            try:
                debug_fc_path = os.path.join(os.getcwd(), "filter_complex_video_debug.txt")
                with open(debug_fc_path, "w", encoding="utf-8") as f:
                    f.write(video_filter_complex)
            except Exception:
                pass

            _run_ffmpeg(video_cmd, "video pass", cwd=temp_dir)
        else:
            # No overlays or LUT: copy the merged result, capping to the
            # target duration in case a trailing unmerged node is slightly long.
            if duration_cap and duration_cap > 0 and nodes[0].media_duration > duration_cap + 0.05:
                trim_cmd = [
                    "ffmpeg", "-y",
                    "-i", merged_video_path_rel,
                    "-t", str(duration_cap),
                    "-c", "copy",
                    video_only_path_rel,
                ]
                _run_ffmpeg(trim_cmd, "cap video duration", cwd=temp_dir)
            else:
                shutil.copy2(
                    os.path.join(temp_dir, merged_video_path_rel),
                    video_only_path,
                )

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

            # Apply EBU R128 loudness normalization if the cutlist carries a
            # loudness measurement. This is a true second-pass loudnorm using
            # measured input values from the ingest worker.
            audio_out_label = "[a_out]"
            loudness = getattr(cutlist.globals, "loudness", None)
            if loudness is not None:
                loudnorm_filter = (
                    f"loudnorm=I={loudness.target_i}:TP={loudness.target_tp}:LRA={loudness.target_lra}:"
                    f"measured_I={loudness.input_i}:measured_TP={loudness.input_tp}:"
                    f"measured_LRA={loudness.input_lra}:measured_thresh={loudness.input_thresh}:"
                    f"offset={loudness.target_offset}"
                )
                audio_filter += f";[a_out]{loudnorm_filter}[a_out_norm]"
                audio_out_label = "[a_out_norm]"

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
                "-map", audio_out_label,
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

        # Container-level integrity gate: the rendered video stream must span the
        # same duration as the audio stream (within 0.5 s). A mismatch here means
        # the video track died mid-render while audio continued — the exact
        # symptom of the slot 4→5 xfade/timebase bug.
        _validate_output_tracks(output_path, duration_cap)

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