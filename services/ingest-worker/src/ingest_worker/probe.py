# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
try:
    import av
except ImportError:
    av = None  # type: ignore[assignment]

from shared_py.logging_config import StructuredLogger
from typing import Dict, Any

logger = StructuredLogger("ingest_worker.probe")


def probe_video(video_path: str) -> Dict[str, Any]:
    """Probe video metadata using PyAV."""
    if av is None:
        logger.warning("av not available, cannot probe video")
        return {"duration_sec": 0.0, "format": None, "streams": []}
    try:
        container = av.open(video_path)
    except Exception as e:
        raise RuntimeError(f"Cannot open video '{video_path}': {e}") from e
    info = {
        "duration_sec": float(container.duration) / av.time_base if container.duration else 0.0,
        "format": container.format.name if container.format else None,
        "streams": [],
    }

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
        info["streams"].append(stream_info)

    container.close()
    return info
