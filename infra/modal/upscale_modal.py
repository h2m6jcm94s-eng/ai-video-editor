# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Modal deployment for upscale worker with Real-ESRGAN."""

import modal

app = modal.App("ave-upscale")

image = (
    modal.Image.debian_slim()
    .apt_install("ffmpeg", "libgl1-mesa-glx", "wget", "unzip")
    .run_commands(
        "wget -q https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip -O /tmp/realesrgan.zip",
        "echo 'a69410e1b1c8e74ec3e8ed4c3e94206f3a2c65c30f42b71a6d369ab4d72b7b2c  /tmp/realesrgan.zip' | sha256sum -c - || exit 1",
        "unzip /tmp/realesrgan.zip -d /opt/realesrgan",
        "chmod +x /opt/realesrgan/realesrgan-ncnn-vulkan",
    )
    .pip_install("numpy", "pillow", "opencv-python")
    .add_local_dir("services/shared-py/src", remote_path="/app")
    .add_local_dir("services/upscale-worker/src", remote_path="/app")
)

volume = modal.Volume.from_name("ave-data", create_if_missing=True)


@app.function(image=image, gpu="L4", volumes={"/data": volume}, timeout=1800)
def upscale_video(input_path: str, output_path: str, scale: int = 2) -> str:
    """Upscale video using Real-ESRGAN on Modal L4."""
    import os
    os.environ["REALESRGAN_BINARY"] = "/opt/realesrgan/realesrgan-ncnn-vulkan"

    from upscale_worker.realesrgan import upscale_with_realesrgan
    return upscale_with_realesrgan(input_path, output_path, scale=scale)
