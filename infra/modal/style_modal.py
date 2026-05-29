"""Modal deployment for style analysis worker."""

import modal

app = modal.App("ave-style")

image = (
    modal.Image.debian_slim()
    .apt_install("ffmpeg", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "opencv-python", "pillow", "numpy", "scipy", "scikit-image",
        "color-matcher", "colour-science",
        "paddlepaddle", "paddleocr",
    )
    .add_local_dir("services/shared-py/src", remote_path="/app")
    .add_local_dir("services/style-worker/src", remote_path="/app")
    .add_local_dir("services/ingest-worker/src", remote_path="/app")
)

volume = modal.Volume.from_name("ave-data", create_if_missing=True)


@app.function(image=image, cpu=4, memory=8192, volumes={"/data": volume}, timeout=300)
def analyze_style(reference_path: str, tier: str = "full_style") -> dict:
    """Analyze reference video style: LUT, transitions, text, motion."""
    from style_worker.lut_extract import extract_lut_from_reference
    from style_worker.transition_type import classify_transitions
    from style_worker.text_extract import extract_text_overlays
    from style_worker.camera_motion import analyze_camera_motion
    from ingest_worker.shot_detect import detect_shot_boundaries

    result = {}

    if tier in ("with_color", "full_style"):
        lut_path, style = extract_lut_from_reference(reference_path, "/data/luts")
        result["lut"] = lut_path
        result["style"] = style.model_dump()

    shots = detect_shot_boundaries(reference_path)
    shots = classify_transitions(reference_path, shots)
    result["transitions"] = [s.transition_in for s in shots if hasattr(s, "transition_in")]

    if tier in ("with_text", "full_style"):
        overlays = extract_text_overlays(reference_path)
        result["overlays"] = [o.model_dump() for o in overlays]

    if tier == "full_style":
        motions = analyze_camera_motion(reference_path, shots)
        result["motions"] = motions

    return result
