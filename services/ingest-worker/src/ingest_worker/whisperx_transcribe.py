"""WhisperX-backed lyric transcription wrapper.

Used when ``USE_WHISPERX=1`` is set. If ``whisperx`` is not installed the
module degrades gracefully and ``transcribe_song_lyrics`` falls back to
faster-whisper.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


def whisperx_available() -> bool:
    try:
        import whisperx  # noqa: F401

        return True
    except Exception:
        return False


def _load_whisperx_model(model_size: str, device: str, compute_type: str, cache_dir: Path):
    import whisperx

    # WhisperX model names are base/en etc.; map faster-whisper sizes.
    wx_size = {
        "tiny": "tiny",
        "base": "base",
        "small": "small",
        "medium": "medium",
        "large-v1": "large-v1",
        "large-v2": "large-v2",
        "large-v3": "large-v3",
    }.get(model_size, "large-v3")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return whisperx.load_model(
        wx_size,
        device,
        compute_type=compute_type,
        download_root=str(cache_dir),
    )


def _align_with_whisperx(audio_path: str, transcript: Dict[str, Any], model, device: str, language: Optional[str]):
    import whisperx

    # WhisperX alignment models require a known language; if none provided, try
    # the detected language.
    align_lang = language or transcript.get("language")
    if not align_lang:
        logger.warning("whisperx_alignment_skipped_no_language")
        return transcript
    try:
        model_a, metadata = whisperx.load_align_model(language_code=align_lang, device=device)
        return whisperx.align(
            transcript["segments"],
            model_a,
            metadata,
            audio_path,
            device,
            return_char_alignments=False,
        )
    except Exception as e:
        logger.warning("whisperx_alignment_failed", error=str(e))
        return transcript


def _diarize(audio_path: str, transcript: Dict[str, Any], device: str) -> Optional[Dict[str, Any]]:
    """Optional speaker diarization for later use (e.g. separating vocals from speech)."""
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        return None
    try:
        import whisperx

        diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
        diarize_segments = diarize_model(audio_path)
        return whisperx.assign_word_speakers(diarize_segments, transcript)
    except Exception as e:
        logger.warning("whisperx_diarization_failed", error=str(e))
        return None


def transcribe_with_whisperx(
    audio_path: str,
    model_size: str = "large-v3",
    language: Optional[str] = None,
    min_word_probability: float = 0.4,
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    cache_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return word-level lyrics using WhisperX.

    The return list contains dictionaries with ``text``, ``start``, ``end``,
    ``probability`` keys suitable for conversion to ``LyricWord``.
    """
    import torch
    import whisperx

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if compute_type is None:
        compute_type = "float16" if device == "cuda" else "int8"
    cache_dir = cache_dir or _default_cache_dir()

    logger.info("whisperx_loading_model", model=model_size, device=device, compute_type=compute_type)
    model = _load_whisperx_model(model_size, device, compute_type, cache_dir)

    audio = whisperx.load_audio(audio_path)
    logger.info("whisperx_transcribing", path=audio_path, language=language)
    result = model.transcribe(audio, batch_size=16, language=language)

    result = _align_with_whisperx(audio_path, result, model, device, language)
    words = result.get("word_segments") or []

    # Flatten whisperx word segments into our normalized shape.
    output: List[Dict[str, Any]] = []
    for w in words:
        text = (w.get("word") or "").strip()
        if not text:
            continue
        prob = float(w.get("score") or w.get("probability") or 1.0)
        if prob < min_word_probability:
            continue
        output.append(
            {
                "text": text,
                "start": float(w["start"]),
                "end": float(w["end"]),
                "probability": prob,
            }
        )

    # Diarize only when token provided; not required for lyrics.
    if os.environ.get("HF_TOKEN"):
        _diarize(audio_path, result, device)

    logger.info("whisperx_transcription_complete", words=len(output))
    return output


def _default_cache_dir() -> Path:
    return Path(os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")) / "models" / "whisperx"
