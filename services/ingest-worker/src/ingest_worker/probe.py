# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
try:
    import av
except ImportError:
    av = None  # type: ignore[assignment]

import os
import tempfile
from shared_py.logging_config import StructuredLogger
from shared_py.storage import download_asset
from shared_py.config import settings
from typing import Dict, Any
from types import SimpleNamespace

logger = StructuredLogger("ingest_worker.probe")


class ProbeInfo(SimpleNamespace):
    """Dict-like namespace for video probe results.

    Supports both attribute access (info.width) and dict-like access
    (info['width']) for backward compatibility.
    """

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


VideoProbeResult = ProbeInfo  # alias for clarity


def probe_video(video_path: str) -> VideoProbeResult:
    """Probe video metadata using PyAV."""
    if av is None:
        logger.warning("av not available, cannot probe video")
        return ProbeInfo(duration_sec=0.0, format=None, streams=[])
    try:
        with av.open(video_path) as container:
            if not container.duration:
                raise RuntimeError(f"Video has no duration metadata: {video_path}")

            info = ProbeInfo(
                duration_sec=float(container.duration) / av.time_base,
                format=container.format.name if container.format else None,
                streams=[],
            )

            for stream in container.streams:
                stream_info = {
                    "index": stream.index,
                    "type": stream.type,
                }
                if stream.type == "video":
                    stream_info.update({
                        "codec": stream.codec.name if stream.codec else None,
                        "width": stream.width,
                        "height": stream.height,
                        "fps": float(stream.average_rate) if stream.average_rate else None,
                        "frames": stream.frames if stream.frames else None,
                        "pix_fmt": stream.pix_fmt,
                    })
                elif stream.type == "audio":
                    stream_info.update({
                        "codec": stream.codec.name if stream.codec else None,
                        "sample_rate": stream.sample_rate,
                        "channels": stream.channels if hasattr(stream, "channels") else None,
                    })
                info.streams.append(stream_info)

            # Convenience attributes from first video stream
            video_stream = next((s for s in info.streams if s.get("type") == "video"), None)
            if video_stream:
                info.width = video_stream.get("width")
                info.height = video_stream.get("height")
                info.fps = video_stream.get("fps")

            return info
    except av.error.FFmpegError as e:
        raise RuntimeError(f"Cannot open video '{video_path}': {e}") from e


async def probe_asset_remote(asset_id: str, storage_key: str) -> Dict[str, Any]:
    """Download from R2, probe, and PATCH metadata back to API."""
    import httpx

    local_path = download_asset(storage_key)
    try:
        info = probe_video(local_path)
    except RuntimeError as e:
        logger.error(f"Probe failed for {asset_id}: {e}")
        raise
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass

    video_stream = next((s for s in info.streams if s.get("type") == "video"), None)
    payload = {
        "durationSec": info.duration_sec,
        "width": video_stream["width"] if video_stream else None,
        "height": video_stream["height"] if video_stream else None,
        "fps": video_stream["fps"] if video_stream else None,
    }

    # Filter out None values
    payload = {k: v for k, v in payload.items() if v is not None}

    internal_token = os.environ.get("INTERNAL_WORKER_TOKEN")
    headers = {"x-internal-token": internal_token} if internal_token else {}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{settings.api_base}/internal/assets/{asset_id}/probe",
                json=payload,
                headers=headers,
                timeout=30,
            )
        if resp.status_code >= 400:
            logger.error(f"Probe report failed body: {resp.text}")
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"Failed to report probe for {asset_id}: {e}")
        raise

    return payload
