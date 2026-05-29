"""Modal deployment for render worker."""

import modal

app = modal.App("ave-render")

image = (
    modal.Image.debian_slim()
    .apt_install("ffmpeg", "libgl1-mesa-glx", "fonts-dejavu")
    .pip_install(
        "opencv-python", "pillow", "numpy", "scipy",
        "av", "ffmpeg-python", "httpx",
    )
    .add_local_dir("services/shared-py/src", remote_path="/app")
    .add_local_dir("services/render-worker/src", remote_path="/app")
)

volume = modal.Volume.from_name("ave-data", create_if_missing=True)


@app.function(image=image, cpu=8, memory=16384, volumes={"/data": volume}, timeout=600)
def render_video_job(
    cutlist_json: dict,
    clip_paths: dict,
    output_key: str,
    lut_path: str = None,
    song_path: str = None,
) -> str:
    """Render a video job on Modal."""
    from shared_py.models import CutList, RenderConfig
    from render_worker.compiler import compile_timeline

    cutlist = CutList(**cutlist_json)
    config = RenderConfig(
        output_path=f"/data/{output_key}",
        width=1280,
        height=720,
        lut_path=lut_path,
        song_path=song_path,
    )

    result = compile_timeline(cutlist, clip_paths, config.output_path, config)
    return result
