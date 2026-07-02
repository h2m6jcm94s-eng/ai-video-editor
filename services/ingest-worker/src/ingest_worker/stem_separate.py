# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
r"""Demucs stem separation for songs.

Produces four stems (drums, bass, vocals, other) and caches them under
``E:\ai-video-editor-storage\stems\<song_hash>\``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("ingest_worker.stem_separate")

EXPECTED_STEMS = ["drums", "bass", "vocals", "other"]


def _song_hash(audio_path: str) -> str:
    path = Path(audio_path).resolve()
    stat = path.stat()
    raw = f"{path}|{stat.st_mtime}|{stat.st_size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _default_cache_dir() -> Path:
    root = os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")
    return Path(root) / "stems"


def _run_demucs(audio_path: str, out_dir: Path, model: str) -> bool:
    """Run Demucs in a subprocess. Returns True on success.

    Demucs on Windows can crash with ``UnicodeEncodeError`` when printing a
    non-ASCII track name, so the caller should pass an ASCII-safe temporary
    copy of the input file.
    """
    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--name",
        model,
        "--out",
        str(out_dir),
        "--device",
        "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES", "") != "-1" else "cpu",
        audio_path,
    ]
    logger.info("running demucs", model=model, path=audio_path)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode != 0:
            logger.warning(
                "demucs failed",
                model=model,
                returncode=result.returncode,
                stderr=result.stderr[-2000:],
            )
            return False
        return True
    except Exception as e:
        logger.warning("demucs subprocess error", model=model, error=str(e))
        return False


def separate_song_stems(
    audio_path: str,
    cache_dir: Optional[Path] = None,
    model: str = "htdemucs_ft",
) -> Dict[str, Optional[Path]]:
    """Separate a song into drums/bass/vocals/other and cache the WAVs.

    Returns a mapping from stem name to cached file path, or ``None`` if that
    stem is missing. On ``htdemucs_ft`` OOM/failure, falls back to the lighter
    ``htdemucs`` model once.
    """
    cache_dir = cache_dir or _default_cache_dir()
    song_hash = _song_hash(audio_path)
    target_dir = cache_dir / song_hash

    # Fast path: all stems already cached.
    result: Dict[str, Optional[Path]] = {}
    all_present = True
    for stem in EXPECTED_STEMS:
        path = target_dir / f"{stem}.wav"
        result[stem] = path if path.exists() else None
        if not path.exists():
            all_present = False
    if all_present:
        logger.info("stems loaded from cache", song_hash=song_hash)
        return result

    # Copy the input to an ASCII-only temporary path.  Demucs prints the track
    # name to the Windows console using the active code page and will fail with
    # ``UnicodeEncodeError`` when the original filename contains characters
    # outside that code page (e.g. Polish ``Ł``).
    audio_path_obj = Path(audio_path)
    suffix = audio_path_obj.suffix or ".wav"
    tmp_dir = Path(tempfile.mkdtemp(prefix="demucs_"))
    try:
        safe_audio = tmp_dir / f"input{suffix}"
        shutil.copy2(audio_path, safe_audio)

        demucs_out = tmp_dir / model / "input"
        success = _run_demucs(str(safe_audio), tmp_dir, model)
        if not success and model == "htdemucs_ft":
            logger.warning("htdemucs_ft failed; falling back to htdemucs")
            model = "htdemucs"
            demucs_out = tmp_dir / model / "input"
            success = _run_demucs(str(safe_audio), tmp_dir, model)

        if not success:
            logger.warning("stem separation failed for both models", song_hash=song_hash)
            return result

        # Move/copy Demucs outputs into the canonical cache location.
        target_dir.mkdir(parents=True, exist_ok=True)
        for stem in EXPECTED_STEMS:
            src = demucs_out / f"{stem}.wav"
            dst = target_dir / f"{stem}.wav"
            if src.exists():
                shutil.copy2(src, dst)
                result[stem] = dst
            else:
                result[stem] = None
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    logger.info(
        "stems cached",
        song_hash=song_hash,
        model=model,
        present=[s for s, p in result.items() if p],
    )
    return result


def get_stem_cache_paths(audio_path: str, cache_dir: Optional[Path] = None) -> Dict[str, Path]:
    cache_dir = cache_dir or _default_cache_dir()
    target_dir = cache_dir / _song_hash(audio_path)
    return {stem: target_dir / f"{stem}.wav" for stem in EXPECTED_STEMS}
