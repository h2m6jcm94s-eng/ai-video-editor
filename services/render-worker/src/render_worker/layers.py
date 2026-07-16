# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Per-slot layer compositing (color, image, video, text overlays)."""

import os
import re
import subprocess
import tempfile
import warnings
from typing import Any, Dict, List, Optional, Tuple

from shared_py.models import Layer
from render_worker.keyframes import ffmpeg_expression, normalize_track


# Map common CSS color names to hex for the color layer source.
_CSS_COLORS = {
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#FF0000",
    "green": "#00FF00",
    "blue": "#0000FF",
    "yellow": "#FFFF00",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
}


# Blend modes supported by FFmpeg's blend filter.
_BLEND_MODES = {
    "normal": None,  # handled by overlay
    "screen": "screen",
    "multiply": "multiply",
    "overlay": "overlay",
    "addition": "addition",
    "lighten": "lighten",
    "darken": "darken",
}


def _parse_color(source: str) -> Tuple[int, int, int]:
    """Return (r, g, b) integers from a hex color string."""
    raw = source or "#000000"
    raw = _CSS_COLORS.get(raw.lower(), raw)
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", raw)
    if not m:
        return (0, 0, 0)
    hex_color = m.group(1)
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def _safe_path(path: str) -> str:
    """Return an absolute path that exists, or raise."""
    full = os.path.abspath(path)
    if not os.path.exists(full):
        raise FileNotFoundError(f"Layer source not found: {path}")
    return full


def _enable_expr(start_s: float, end_s: float) -> str:
    return rf"between(t\,{start_s:.3f}\,{end_s:.3f})"


def _escape_expr(expr: str) -> str:
    """Escape commas inside an FFmpeg expression so it can be nested in options."""
    return expr.replace(",", r"\,")


def _escape_drawtext(text: str) -> str:
    """Escape single quotes and colons in drawtext text."""
    return text.replace("'", "'\\\\\\''").replace(":", "\\:")


def _find_font_file(preferred: Optional[str]) -> Optional[str]:
    """Best-effort font file resolver for drawtext."""
    if preferred:
        if os.path.isfile(preferred):
            return os.path.abspath(preferred)
        # Try common Windows font names.
        win_fonts = os.path.expandvars(r"C:\Windows\Fonts")
        candidates = [
            f"{preferred}.ttf",
            f"{preferred}.otf",
            f"{preferred}-Regular.ttf",
            f"{preferred}-Regular.otf",
        ]
        for cand in candidates:
            path = os.path.join(win_fonts, cand)
            if os.path.isfile(path):
                return path
    # Fallback to Arial if available.
    arial = os.path.expandvars(r"C:\Windows\Fonts\arial.ttf")
    if os.path.isfile(arial):
        return arial
    return None


def _default_easing(layer: Layer) -> str:
    """Text and graphic layers default to spring entrance easing."""
    if layer.type == "text":
        return "spring"
    return "linear"


def _transform_filters(
    layer: Layer, width: int, height: int, duration_s: float, default_easing: str = "linear"
) -> str:
    """Return filters that apply a layer's transform keyframes / static values."""
    transform: Dict[str, Any] = layer.transform or {}
    scale = float(transform.get("scale", 1.0))
    rotate = float(transform.get("rotate", 0.0))
    x = float(transform.get("x", 0.0))
    y = float(transform.get("y", 0.0))

    # Animated opacity uses the dedicated "opacity" keyframe track if present.
    opacity_kf = layer.keyframes.get("opacity") if layer.keyframes else None
    if opacity_kf:
        opacity_kf = normalize_track(opacity_kf, duration_s, default_easing=default_easing)
        alpha_expr = f"clamp(geq(a='{ffmpeg_expression(opacity_kf)}*255'),0,255)"
    else:
        opacity = max(0.0, min(1.0, layer.opacity))
        alpha_expr = f"geq(a='{opacity}*255')"

    parts: List[str] = []
    if scale != 1.0:
        parts.append(f"scale=iw*{scale}:ih*{scale}")
    if rotate != 0.0:
        # FFmpeg rotate uses radians.
        parts.append(f"rotate=angle={rotate}*PI/180:fillcolor=0x00000000")
    parts.append("format=yuva420p")
    parts.append(alpha_expr)
    # Position is handled by the overlay filter using x/y expressions.
    return ",".join(parts)


def _build_text_filter(layer: Layer, width: int, height: int, duration_s: float) -> str:
    """Return filters that render a text layer onto a transparent canvas."""
    text = (layer.source or "").strip()
    if not text:
        text = " "
    fontfile = layer.font_file or _find_font_file(layer.transform.get("font"))
    font_size = int(layer.font_size)
    font_color = layer.font_color or "#FFFFFF"
    stroke_color = layer.stroke_color or "#000000"
    transform = layer.transform or {}
    x_expr = str(transform.get("x", "(w-text_w)/2"))
    y_expr = str(transform.get("y", "(h-text_h)/2"))
    enable = _enable_expr(layer.in_s, min(duration_s, layer.out_s))
    drawtext = (
        f"drawtext=text='{_escape_drawtext(text)}':"
        f"fontfile={fontfile or 'default'}:fontsize={font_size}:"
        f"fontcolor={font_color}:borderw=2:bordercolor={stroke_color}:"
        f"x={x_expr}:y={y_expr}:enable='{enable}'"
    )
    if not fontfile:
        # drawtext will likely fail; the caller should warn, but we still emit a
        # transparent placeholder so the filter graph is structurally valid.
        warnings.warn(f"No font file found for text layer {layer.id}; drawtext may fail")
    return drawtext


def _position_expressions(layer: Layer, duration_s: float, default_easing: str) -> Tuple[str, str]:
    """Return (x_expr, y_expr) for the overlay filter, honoring keyframes."""
    transform_dict = layer.transform or {}
    x_expr = str(float(transform_dict.get("x", 0.0)))
    y_expr = str(float(transform_dict.get("y", 0.0)))
    x_kf = layer.keyframes.get("x") if layer.keyframes else None
    y_kf = layer.keyframes.get("y") if layer.keyframes else None
    if x_kf:
        x_expr = ffmpeg_expression(normalize_track(x_kf, duration_s, default_easing=default_easing))
    if y_kf:
        y_expr = ffmpeg_expression(normalize_track(y_kf, duration_s, default_easing=default_easing))
    return x_expr, y_expr


def _blend_filter(mode: str) -> Optional[str]:
    return _BLEND_MODES.get(mode)


def _build_layer_filter_complex(
    layers: List[Layer],
    duration_s: float,
    width: int,
    height: int,
    fps: float,
) -> Tuple[List[str], List[str], str]:
    """Return (extra_inputs, filter_complex_lines, output_label).

    Input 0 is the base segment.  Extra inputs are appended for image/video/text
    layers that need an external source.  Color layers are generated inside the
    filter graph with the ``color`` source filter.
    """
    if not layers:
        return [], [], "[0:v]"

    sorted_layers = sorted(layers, key=lambda l: l.z_index)
    extra_inputs: List[str] = []
    lines: List[str] = []
    current_label = "0:v"
    color_count = 0
    image_input_idx = 1  # input 0 is base

    for i, layer in enumerate(sorted_layers):
        in_s = max(0.0, layer.in_s)
        out_s = min(duration_s, layer.out_s)
        if out_s <= in_s:
            continue

        default_easing = _default_easing(layer)
        layer_label: str
        if layer.type == "color":
            r, g, b = _parse_color(layer.source or "")
            layer_label = f"col_{color_count}"
            color_count += 1
            transform = _transform_filters(layer, width, height, duration_s, default_easing)
            lines.append(
                f"color=c=0x{r:02X}{g:02X}{b:02X}:"
                f"s={width}x{height}:d={duration_s:.3f}:r={fps}[{layer_label}];"
                f"[{layer_label}]{transform}[{layer_label}_t]"
            )
            layer_label = f"{layer_label}_t"
        elif layer.type == "image":
            src = _safe_path(layer.source or "")
            extra_inputs.extend(["-loop", "1", "-t", f"{duration_s:.3f}", "-i", src])
            layer_label = f"img_{i}"
            transform = _transform_filters(layer, width, height, duration_s, default_easing)
            lines.append(f"[{image_input_idx}:v]{transform}[{layer_label}]")
            image_input_idx += 1
        elif layer.type == "video":
            src = _safe_path(layer.source or "")
            extra_inputs.extend(["-t", f"{duration_s:.3f}", "-i", src])
            layer_label = f"vid_{i}"
            transform = _transform_filters(layer, width, height, duration_s, default_easing)
            lines.append(f"[{image_input_idx}:v]{transform}[{layer_label}]")
            image_input_idx += 1
        elif layer.type == "text":
            layer_label = f"txt_{i}"
            text_filter = _build_text_filter(layer, width, height, duration_s)
            transform = _transform_filters(layer, width, height, duration_s, default_easing)
            lines.append(
                f"color=c=0x00000000:s={width}x{height}:"
                f"d={duration_s:.3f}:r={fps}[{layer_label}];"
                f"[{layer_label}]format=yuva420p,{text_filter},{transform}[{layer_label}_t]"
            )
            layer_label = f"{layer_label}_t"
        else:
            warnings.warn(f"Unsupported layer type '{layer.type}' on layer {layer.id}")
            continue

        x_expr, y_expr = _position_expressions(layer, duration_s, default_easing)
        enable = _enable_expr(in_s, out_s)
        out_label = f"comp_{i}" if i < len(sorted_layers) - 1 else "outv"

        blend_mode = _blend_filter(layer.blend_mode)
        if blend_mode and layer.type != "text":
            # Position the layer on a transparent canvas first, then blend.
            positioned_label = f"pos_{i}"
            lines.append(
                f"color=c=0x00000000:s={width}x{height}:d={duration_s:.3f}[canvas_{i}];"
                f"[canvas_{i}][{layer_label}]overlay={_escape_expr(x_expr)}:{_escape_expr(y_expr)}:"
                f"enable='{enable}':format=auto[{positioned_label}];"
                f"[{current_label}][{positioned_label}]blend=all_mode={blend_mode}:shortest=1[{out_label}]"
            )
        else:
            lines.append(
                f"[{current_label}][{layer_label}]"
                f"overlay={_escape_expr(x_expr)}:{_escape_expr(y_expr)}:enable='{enable}':format=auto"
                f"[{out_label}]"
            )
        current_label = out_label

    return extra_inputs, lines, f"[{current_label}]"


def composite_layers(
    base_path: str,
    layers: List[Layer],
    duration_s: float,
    width: int,
    height: int,
    fps: float,
    encode_args: List[str],
    run_ffmpeg,
    temp_dir: str,
) -> str:
    """Composite ``layers`` on top of ``base_path`` and return the output path.

    ``run_ffmpeg`` is a callable that accepts (cmd, description) and executes
    FFmpeg, raising on failure.  This avoids a circular import with the
    compiler module.
    """
    if not layers:
        return base_path

    extra_inputs, filter_lines, out_label = _build_layer_filter_complex(
        layers, duration_s, width, height, fps
    )
    if not filter_lines:
        return base_path

    output_path = os.path.join(temp_dir, f"layered_{os.path.basename(base_path)}")
    filter_complex = ";".join(filter_lines)
    cmd = [
        "ffmpeg", "-y",
        "-i", base_path,
        *extra_inputs,
        "-filter_complex", filter_complex,
        "-map", out_label,
        *encode_args,
        output_path,
    ]
    run_ffmpeg(cmd, f"layer compositing for {os.path.basename(base_path)}")
    return output_path
