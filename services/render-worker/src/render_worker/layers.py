# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Per-slot layer compositing (color, image, video overlays)."""

import os
import re
import subprocess
import tempfile
import warnings
from typing import Any, Dict, List, Tuple

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


def _transform_filters(layer: Layer, width: int, height: int, duration_s: float) -> str:
    """Return filters that apply a layer's transform keyframes / static values."""
    transform: Dict[str, Any] = layer.transform or {}
    scale = float(transform.get("scale", 1.0))
    rotate = float(transform.get("rotate", 0.0))
    x = float(transform.get("x", 0.0))
    y = float(transform.get("y", 0.0))

    # Animated opacity uses the dedicated "opacity" keyframe track if present.
    opacity_kf = layer.keyframes.get("opacity") if layer.keyframes else None
    if opacity_kf:
        opacity_kf = normalize_track(opacity_kf, duration_s)
        alpha_expr = f"clamp(geq=a='{ffmpeg_expression(opacity_kf)}*255',0,255)"
    else:
        opacity = max(0.0, min(1.0, layer.opacity))
        alpha_expr = f"geq=a='{opacity}*255'"

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


def _build_layer_filter_complex(
    layers: List[Layer],
    duration_s: float,
    width: int,
    height: int,
    fps: float,
) -> Tuple[List[str], List[str], str]:
    """Return (extra_inputs, filter_complex_lines, output_label).

    Input 0 is the base segment.  Extra inputs are appended for image/video
    layers.  Color layers are generated inside the filter graph with the
    ``color`` source filter.
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

        layer_label: str
        if layer.type == "color":
            r, g, b = _parse_color(layer.source or "")
            layer_label = f"col_{color_count}"
            color_count += 1
            transform = _transform_filters(layer, width, height, duration_s)
            lines.append(
                f"[{layer_label}]color=c=0x{r:02X}{g:02X}{b:02X}:"
                f"s={width}x{height}:d={duration_s:.3f}:r={fps},{transform}"
            )
        elif layer.type == "image":
            src = _safe_path(layer.source or "")
            extra_inputs.extend(["-loop", "1", "-t", f"{duration_s:.3f}", "-i", src])
            layer_label = f"img_{i}"
            transform = _transform_filters(layer, width, height, duration_s)
            lines.append(f"[{image_input_idx}:v]{transform}[{layer_label}]")
            image_input_idx += 1
        elif layer.type == "video":
            src = _safe_path(layer.source or "")
            extra_inputs.extend(["-t", f"{duration_s:.3f}", "-i", src])
            layer_label = f"vid_{i}"
            transform = _transform_filters(layer, width, height, duration_s)
            lines.append(f"[{image_input_idx}:v]{transform}[{layer_label}]")
            image_input_idx += 1
        else:
            warnings.warn(f"Unsupported layer type '{layer.type}' on layer {layer.id}")
            continue

        transform_dict = layer.transform or {}
        x_expr = str(float(transform_dict.get("x", 0.0)))
        y_expr = str(float(transform_dict.get("y", 0.0)))
        x_kf = layer.keyframes.get("x") if layer.keyframes else None
        y_kf = layer.keyframes.get("y") if layer.keyframes else None
        if x_kf:
            x_expr = ffmpeg_expression(normalize_track(x_kf, duration_s))
        if y_kf:
            y_expr = ffmpeg_expression(normalize_track(y_kf, duration_s))

        enable = _enable_expr(in_s, out_s)
        out_label = f"comp_{i}" if i < len(sorted_layers) - 1 else "outv"
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
