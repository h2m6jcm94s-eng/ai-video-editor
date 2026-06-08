# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Upscale video using Real-ESRGAN ncnn-vulkan wrapper."""

import os
import subprocess
import tempfile
from typing import Optional


def upscale_with_realesrgan(
    input_path: str,
    output_path: str,
    scale: int = 2,
    model: str = "realesr-animevideov3",
    tile_size: int = 200,
) -> str:
    """Upscale video using Real-ESRGAN ncnn-vulkan.

    Requires realesrgan-ncnn-vulkan binary in PATH.
    """
    binary = os.environ.get("REALESRGAN_BINARY", "realesrgan-ncnn-vulkan")

    # Real-ESRGAN processes images, so we extract frames, upscale, then re-encode
    temp_dir = tempfile.mkdtemp(prefix="ave_upscale_")
    frames_dir = os.path.join(temp_dir, "frames")
    upscaled_dir = os.path.join(temp_dir, "upscaled")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(upscaled_dir, exist_ok=True)

    try:
        # Extract frames
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", input_path,
                "-vf", "fps=30",
                os.path.join(frames_dir, "frame_%06d.png"),
            ],
            check=True, capture_output=True,
        )

        # Upscale frames
        frames = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
        for frame in frames:
            in_frame = os.path.join(frames_dir, frame)
            out_frame = os.path.join(upscaled_dir, frame)
            subprocess.run(
                [
                    binary,
                    "-i", in_frame,
                    "-o", out_frame,
                    "-s", str(scale),
                    "-n", model,
                    "-t", str(tile_size),
                ],
                check=True, capture_output=True,
            )

        # Re-encode
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", os.path.join(upscaled_dir, "frame_%06d.png"),
                "-i", input_path,  # Use original audio
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                output_path,
            ],
            check=True, capture_output=True,
        )

    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path
