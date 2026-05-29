import av
from typing import Dict, Any


def probe_video(video_path: str) -> Dict[str, Any]:
    """Probe video metadata using PyAV."""
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
