# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Modal deployment for ingest worker with GPU acceleration."""

import modal

app = modal.App("ave-ingest")

image = (
    modal.Image.debian_slim()
    .apt_install("ffmpeg", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch", "torchvision",
        "opencv-python", "pillow", "numpy",
        "librosa", "soundfile",
        "scenedetect", "scipy",
        "av", "ffmpeg-python",
    )
    .add_local_dir("services/shared-py/src", remote_path="/app")
    .add_local_dir("services/ingest-worker/src", remote_path="/app")
)

volume = modal.Volume.from_name("ave-data", create_if_missing=True)


@app.function(image=image, gpu="L4", volumes={"/data": volume})
def process_video_upload(video_path: str) -> dict:
    """Process uploaded video: probe, shot detect, keyframes."""
    from ingest_worker.probe import probe_video
    from ingest_worker.shot_detect import detect_shot_boundaries

    info = probe_video(video_path)
    shots = detect_shot_boundaries(video_path, use_transnet=True, device="cuda")

    return {
        "probe": info,
        "shots": [s.model_dump() for s in shots],
    }


@app.function(image=image, gpu="L4", volumes={"/data": volume})
def process_audio_upload(audio_path: str) -> dict:
    """Process uploaded audio: beat detection."""
    from ingest_worker.beat_detect import detect_beats, compute_energy_curve

    beats = detect_beats(audio_path)
    energy = compute_energy_curve(audio_path)

    return {
        "beats": beats.model_dump(),
        "energy": energy,
    }
