#!/usr/bin/env python3
"""API-driven end-to-end smoke test.

Mimics a user who:
1. Creates a new project
2. Uploads a reference video, 3 clips, and a song
3. Waits for ingest/style analysis
4. Hits "Generate" (reference-driven)
5. Waits for cutlist generation
6. Hits "Render"
7. Waits for the render and validates the output MP4
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load the same env the API uses
load_dotenv("apps/api/.env.local")

API_BASE = f"http://localhost:{os.environ.get('API_PORT', '4000')}"
FIXTURES = Path("e2e/fixtures")
OUTPUT_DIR = Path("e2e")
OUTPUT_DIR.mkdir(exist_ok=True)


def log(msg, **kwargs):
    payload = {"event": msg}
    payload.update(kwargs)
    print(json.dumps(payload, default=str), flush=True)


def api(method, path, **kwargs):
    url = f"{API_BASE}{path}"
    r = httpx.request(method, url, timeout=60, **kwargs)
    log("api_request", method=method, path=path, status=r.status_code)
    return r


def upload_file_to_presigned(file_path: Path, asset_type: str, project_id: str):
    filename = file_path.name
    mime_type = {
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
    }.get(file_path.suffix.lower(), "application/octet-stream")

    r = api(
        "POST",
        "/api/uploads/presigned",
        json={
            "projectId": project_id,
            "filename": filename,
            "mimeType": mime_type,
            "type": asset_type,
        },
    )
    r.raise_for_status()
    data = r.json()
    asset_id = data["assetId"]
    upload_url = data["url"]
    fields = data.get("fields") or {}

    with open(file_path, "rb") as f:
        upload_resp = httpx.put(
            upload_url,
            content=f.read(),
            headers={"Content-Type": mime_type},
            timeout=120,
        )
    upload_resp.raise_for_status()
    etag = upload_resp.headers.get("etag", "").strip('"')
    if not etag:
        # Fallback for MinIO sometimes returning ETag in body for errors
        log("upload_response_headers", headers=dict(upload_resp.headers))
        raise RuntimeError("No ETag returned from storage upload")

    complete_r = api(
        "POST",
        f"/api/uploads/{asset_id}/complete",
        json={
            "sizeBytes": file_path.stat().st_size,
            "etag": etag,
        },
    )
    complete_r.raise_for_status()
    return asset_id


def wait_for_asset_ingested(project_id: str, asset_id: str, timeout: float = 180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = api("GET", f"/api/projects/{project_id}")
        r.raise_for_status()
        assets = r.json()["project"].get("assets", [])
        for a in assets:
            if a["id"] == asset_id and a.get("durationSec") is not None:
                return a
        time.sleep(2)
    raise TimeoutError(f"Asset {asset_id} not ingested within {timeout}s")


def wait_for_style_analysis(project_id: str, timeout: float = 180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = api("GET", f"/api/projects/{project_id}/style")
        if r.status_code == 200:
            return r.json().get("styleAnalysis")
        time.sleep(2)
    raise TimeoutError("Style analysis not available")


def wait_for_generation(project_id: str, timeout: float = 300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = api("GET", f"/api/projects/{project_id}/generation")
        if r.status_code != 200:
            time.sleep(2)
            continue
        job = r.json().get("job", {})
        status = job.get("status")
        stage = job.get("stage")
        log("generation_poll", status=status, stage=stage, error=job.get("errorMessage"))
        if status == "complete":
            return job
        if status == "failed":
            raise RuntimeError(f"Generation failed: {job.get('errorMessage')}")
        time.sleep(2)
    raise TimeoutError("Generation did not complete")


def wait_for_render(project_id: str, timeout: float = 600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = api("GET", f"/api/renders/project/{project_id}")
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
        if not jobs:
            time.sleep(2)
            continue
        job = jobs[0]
        status = job.get("status")
        log("render_poll", status=status, error=job.get("errorMessage"))
        if status == "complete":
            return job
        if status == "failed":
            raise RuntimeError(f"Render failed: {job.get('errorMessage')}")
        time.sleep(2)
    raise TimeoutError("Render did not complete")


def ffprobe(path: Path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    return json.loads(out)


def main():
    log("smoke_start")

    # 1. Create project
    r = api("POST", "/api/projects", json={"name": "E2E-Smoke-Reference-3Clips-Song"})
    r.raise_for_status()
    project = r.json()["project"]
    project_id = project["id"]
    log("project_created", project_id=project_id)

    # 2. Upload assets
    reference_id = upload_file_to_presigned(FIXTURES / "reference.mp4", "reference_video", project_id)
    song_id = upload_file_to_presigned(FIXTURES / "song.mp3", "song", project_id)
    clip_ids = [
        upload_file_to_presigned(FIXTURES / f"clip-{i}.mp4", "clip", project_id)
        for i in (1, 2, 3)
    ]
    log("assets_uploaded", reference_id=reference_id, song_id=song_id, clip_ids=clip_ids)

    # 3. Wait for ingest + style analysis
    for asset_id in [reference_id, song_id, *clip_ids]:
        wait_for_asset_ingested(project_id, asset_id)
    log("assets_ingested")

    style_analysis = wait_for_style_analysis(project_id)
    log("style_analysis_ready", keys=list(style_analysis.keys()) if style_analysis else [])

    # 4. Generate reference-driven cutlist
    r = api(
        "POST",
        f"/api/projects/{project_id}/generate",
        json={"prompt": "Make a punchy vertical reel that cuts on beats."},
    )
    log("generate_response", status=r.status_code, body=r.text[:500])
    r.raise_for_status()

    job = wait_for_generation(project_id)
    log("generation_complete", job_id=job.get("id"))

    # 5. Render
    r = api("POST", "/api/renders", json={"projectId": project_id})
    log("render_response", status=r.status_code, body=r.text[:500])
    r.raise_for_status()

    render_job = wait_for_render(project_id)
    log("render_complete", render_id=render_job.get("id"), output_asset_id=render_job.get("outputAssetId"))

    # 6. Download output
    output_asset_id = render_job.get("outputAssetId")
    if not output_asset_id:
        raise RuntimeError("No output asset ID")

    r = api("GET", f"/api/uploads/{output_asset_id}")
    r.raise_for_status()
    asset_data = r.json()
    storage_url = asset_data["asset"]["storageUrl"]
    log("download_url_ready", url=storage_url[:120])

    output_path = OUTPUT_DIR / "smoke-output.mp4"
    video_r = httpx.get(storage_url, timeout=120)
    video_r.raise_for_status()
    output_path.write_bytes(video_r.content)
    log("output_downloaded", path=str(output_path), bytes=len(video_r.content))

    # 7. Validate
    probe = ffprobe(output_path)
    video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    duration = float(probe["format"]["duration"])
    size = int(probe["format"]["size"])

    log(
        "probe_result",
        duration=duration,
        width=video_stream["width"] if video_stream else None,
        height=video_stream["height"] if video_stream else None,
        video_codec=video_stream["codec_name"] if video_stream else None,
        audio_codec=audio_stream["codec_name"] if audio_stream else None,
        size=size,
    )

    assert video_stream and video_stream["codec_name"] == "h264", "Expected h264 video"
    assert audio_stream and audio_stream["codec_name"] == "aac", "Expected aac audio"
    # Reference is 10s; the edit should use most of it, not collapse to a couple seconds.
    assert 5 <= duration <= 15, f"Expected 5-15s output, got {duration}s"
    assert size > 500_000, "Expected non-trivial file size"
    aspect = video_stream["width"] / video_stream["height"]
    assert abs(aspect - 9 / 16) < 0.1, f"Expected 9:16 aspect ratio, got {aspect}"

    log("smoke_passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("smoke_failed", error=str(exc))
        sys.exit(1)
