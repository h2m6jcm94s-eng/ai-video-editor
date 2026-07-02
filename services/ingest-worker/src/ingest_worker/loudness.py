# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""EBU R128 loudness measurement via FFmpeg loudnorm."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from shared_py.logging_config import StructuredLogger
from shared_py.models import LoudnessMeasurement

logger = StructuredLogger("ingest_worker.loudness")

# Default loudnorm targets (EBU R128 / streaming standard).
TARGET_I = -14.0
TARGET_TP = -1.5
TARGET_LRA = 11.0


def _song_hash(audio_path: str) -> str:
    path = Path(audio_path).resolve()
    try:
        stat = path.stat()
        raw = f"{path}|{stat.st_mtime}|{stat.st_size}"
    except FileNotFoundError:
        raw = str(path)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "audio_master"


def _parse_loudnorm_json(stderr_text: str) -> Optional[dict]:
    """Find and parse the loudnorm JSON block in FFmpeg stderr."""
    match = re.search(r"\[Parsed_loudnorm_\d+ @ [^\]]+\]\s*\n(\{.*?\})\s*\n", stderr_text, re.DOTALL)
    if not match:
        # Some FFmpeg builds print the JSON without the Parsed_loudnorm prefix.
        match = re.search(r"\{\s*\"input_i\".*?\"target_offset\".*?\}", stderr_text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def analyze_loudness(
    audio_path: str,
    cache_dir: Optional[Path] = None,
    target_i: float = TARGET_I,
    target_tp: float = TARGET_TP,
    target_lra: float = TARGET_LRA,
) -> LoudnessMeasurement:
    """Measure integrated loudness using FFmpeg's loudnorm filter.

    The measurement is cached under ``<cache_dir>/<song_hash>/loudness.json``.
    """
    cache_dir = cache_dir or _default_cache_dir()
    song_hash = _song_hash(audio_path)
    cache_file = cache_dir / song_hash / "loudness.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            measurement = LoudnessMeasurement(**data)
            logger.info("loudness loaded from cache", song_hash=song_hash)
            return measurement
        except Exception as e:
            logger.warning("loudness cache corrupt; recomputing", error=str(e))

    logger.info("analyzing loudness", path=audio_path)
    filter_str = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json"
    )
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i", audio_path,
        "-af", filter_str,
        "-f", "null",
        "-",
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        logger.warning("loudness analysis failed", error=str(e))
        return LoudnessMeasurement(target_i=target_i, target_tp=target_tp, target_lra=target_lra)

    data = _parse_loudnorm_json(result.stderr) or _parse_loudnorm_json(result.stdout)
    if data is None:
        logger.warning("loudnorm JSON not found in FFmpeg output")
        return LoudnessMeasurement(target_i=target_i, target_tp=target_tp, target_lra=target_lra)

    measurement = LoudnessMeasurement(
        input_i=float(data.get("input_i", 0.0)),
        input_tp=float(data.get("input_tp", 0.0)),
        input_lra=float(data.get("input_lra", 0.0)),
        input_thresh=float(data.get("input_thresh", 0.0)),
        target_offset=float(data.get("target_offset", 0.0)),
        target_i=target_i,
        target_tp=target_tp,
        target_lra=target_lra,
    )

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(measurement.model_dump_json(), encoding="utf-8")
        tmp.replace(cache_file)
        logger.info(
            "loudness cached",
            song_hash=song_hash,
            input_i=measurement.input_i,
            input_tp=measurement.input_tp,
            target_offset=measurement.target_offset,
        )
    except Exception as e:
        logger.warning("failed to write loudness cache", error=str(e))

    return measurement
