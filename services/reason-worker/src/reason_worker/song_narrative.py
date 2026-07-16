# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Gemma-based song narrative labeling for arc anchoring."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional, Tuple

from shared_py.llm_client import LLMClient, LLMTask
from shared_py.logging_config import StructuredLogger
from shared_py.models import SectionMoodTags, SongMoodProfile, SongNarrative, SongSectionSemantics, VocalEmotionCurve, VocalEmotionSample

# Import the ingest-side dataclass directly; it is lightweight and stable.
from ingest_worker.song_lyrics import LyricWord

logger = StructuredLogger("reason_worker.song_narrative")

_ALLOWED_ARC_HINTS = {
    "HOOK",
    "WORLD",
    "CONFLICT",
    "CRISIS",
    "VICTORY",
    "PEACE",
    "CRACK",
    "LOSS",
    "DARKNESS",
    "ACCEPTANCE",
}

_ALLOWED_ROLES = {"setup", "reveal", "climax", "resolution", "reprise"}

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "lyric_sentiment": {"type": "string"},
        "story_role": {"type": "string"},
        "emotional_intensity": {"type": "number"},
        "arc_beat_hint": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
    },
    "required": [
        "lyric_sentiment",
        "story_role",
        "emotional_intensity",
        "arc_beat_hint",
        "rationale",
    ],
}


def _lyrics_in_section(
    lyric_words: List[LyricWord],
    start_s: float,
    end_s: float,
) -> str:
    """Return the lyrics text overlapping a section, or an instrumental marker."""
    words = [
        w.text
        for w in lyric_words
        if w.start_s < end_s and w.end_s > start_s
    ]
    text = " ".join(words).strip()
    return text if text else "[instrumental]"


def _vocal_emotion_in_section(
    vocal_curve: VocalEmotionCurve,
    start_s: float,
    end_s: float,
) -> Tuple[str, dict]:
    """Return the dominant vocal emotion and an averaged distribution for a section."""
    samples = [
        s
        for s in vocal_curve.samples
        if start_s - 0.5 <= s.t_center_s <= end_s + 0.5
    ]
    if not samples:
        # Fallback: nearest sample to section midpoint.
        mid = (start_s + end_s) / 2
        nearest = min(
            vocal_curve.samples,
            key=lambda s: abs(s.t_center_s - mid),
            default=None,
        )
        if nearest is None:
            return "neutral", {}
        return nearest.dominant_emotion, dict(nearest.distribution)

    aggregated: dict = {}
    for s in samples:
        for k, v in s.distribution.items():
            aggregated[k] = aggregated.get(k, 0.0) + float(v)
    total = sum(aggregated.values())
    if total > 0:
        aggregated = {k: v / total for k, v in aggregated.items()}
    dominant = max(aggregated, key=aggregated.get, default="neutral")
    return dominant, aggregated


def _build_prompt(
    section_label: str,
    start_s: float,
    end_s: float,
    lyrics_text: str,
    clap_moods: List[Tuple[str, float]],
    dominant_emotion: str,
    distribution: dict,
    genre_tags: List[Tuple[str, float]],
) -> str:
    """Assemble the exact prompt required by the Gemma narrative labeler."""
    mood_lines = "\n".join(
        f"- {mood}: {confidence:.3f}" for mood, confidence in clap_moods[:3]
    )
    dist_lines = "\n".join(
        f"  - {emotion}: {score:.3f}"
        for emotion, score in sorted(distribution.items(), key=lambda x: -x[1])[:5]
    )
    genre_lines = ", ".join(f"{tag}" for tag, _ in genre_tags[:3])

    return (
        "You are a music-aware editor's assistant. Read the following data about ONE section\n"
        "of a song and return a JSON object describing its narrative role.\n\n"
        f"SONG SECTION LABEL: {section_label}\n"
        f"TIME RANGE: {start_s:.1f}s - {end_s:.1f}s\n"
        f"LYRICS (Whisper transcription, may be empty for instrumental):\n{lyrics_text}\n\n"
        "CLAP mood tags for this section (top-3 with confidence):\n"
        f"{mood_lines}\n\n"
        "Vocal emotion trajectory (Wav2Vec2 on vocals stem):\n"
        f"- Dominant emotion: {dominant_emotion}\n"
        "- Distribution:\n"
        f"{dist_lines}\n\n"
        f"Global song genre tags (top-3): {genre_lines}\n\n"
        "Return a JSON object with EXACTLY these keys:\n"
        "{\n"
        '  "lyric_sentiment": "one phrase describing what the lyrics convey emotionally (e.g. \'loss and self-doubt\', \'defiant hope\', \'nostalgic longing\', \'instrumental_no_lyrics\')",\n'
        '  "story_role": "one of: setup, reveal, climax, resolution, reprise",\n'
        '  "emotional_intensity": <float 0.0-1.0>,\n'
        '  "arc_beat_hint": "one of: HOOK, WORLD, CONFLICT, CRISIS, VICTORY, PEACE, CRACK, LOSS, DARKNESS, ACCEPTANCE, or null if no strong signal",\n'
        '  "rationale": "one sentence justifying the arc_beat_hint given lyrics + mood"\n'
        "}\n\n"
        "Return ONLY the JSON object. No prose before or after. No markdown fences."
    )


def _safe_parse_json(text: str) -> Optional[dict]:
    """Parse the LLM response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _validate_label(raw: dict, section_index: int) -> Optional[SongSectionSemantics]:
    """Validate and coerce a raw LLM label into a SongSectionSemantics."""
    try:
        story_role = raw.get("story_role", "setup")
        if story_role not in _ALLOWED_ROLES:
            story_role = "setup"
        arc_hint = raw.get("arc_beat_hint")
        if arc_hint is not None and arc_hint not in _ALLOWED_ARC_HINTS:
            arc_hint = None
        intensity = float(raw.get("emotional_intensity", 0.5))
        intensity = max(0.0, min(1.0, intensity))
        return SongSectionSemantics(
            start_s=float(raw["start_s"]),
            end_s=float(raw["end_s"]),
            section_label=str(raw["section_label"]),
            lyric_sentiment=str(raw.get("lyric_sentiment", "")),
            story_role=story_role,  # type: ignore[arg-type]
            emotional_intensity=intensity,
            arc_beat_hint=arc_hint,
            rationale=str(raw.get("rationale", "")),
        )
    except Exception as exc:
        logger.warning("song_narrative_label_validation_failed", section_index=section_index, error=str(exc))
        return None


def _samples_to_distribution(
    samples: List[VocalEmotionSample],
) -> Tuple[str, dict]:
    """Aggregate a list of vocal emotion samples into a dominant emotion + distribution."""
    if not samples:
        return "neutral", {}
    aggregated: dict = {}
    for s in samples:
        for k, v in s.distribution.items():
            aggregated[k] = aggregated.get(k, 0.0) + float(v)
    total = sum(aggregated.values())
    if total > 0:
        aggregated = {k: v / total for k, v in aggregated.items()}
    dominant = max(aggregated, key=aggregated.get, default="neutral")
    return dominant, aggregated


async def label_song_section(
    section: SectionMoodTags,
    lyrics_in_section: List[LyricWord],
    vocal_emotion_in_section: List[VocalEmotionSample],
    global_genres: List[Tuple[str, float]],
    llm_client: LLMClient,
) -> Optional[SongSectionSemantics]:
    """Label a single song section using Gemma via the unified LLM client."""
    lyrics_text = " ".join(w.text for w in lyrics_in_section).strip() or "[instrumental]"
    dominant_emotion, distribution = _samples_to_distribution(vocal_emotion_in_section)
    prompt = _build_prompt(
        section_label=section.section_label,
        start_s=section.start_s,
        end_s=section.end_s,
        lyrics_text=lyrics_text,
        clap_moods=section.top_moods,
        dominant_emotion=dominant_emotion,
        distribution=distribution,
        genre_tags=global_genres,
    )

    start_t = time.monotonic()
    try:
        raw_response = await llm_client.complete(
            task=LLMTask.NARRATIVE_SECTION_LABEL,
            prompt=prompt,
            max_tokens=256,
            temperature=0.0,
            json_schema=_JSON_SCHEMA,
            fallback_response=None,
        )
    except Exception as exc:
        elapsed = time.monotonic() - start_t
        if elapsed > 20:
            logger.warning("song_narrative_section_slow", section_index=-1, elapsed_s=round(elapsed, 1))
        return None

    elapsed = time.monotonic() - start_t
    if elapsed > 20:
        logger.warning("song_narrative_section_slow", section_index=-1, elapsed_s=round(elapsed, 1))

    if isinstance(raw_response, dict):
        raw_response = json.dumps(raw_response)

    parsed = _safe_parse_json(raw_response)
    if parsed is not None:
        parsed["start_s"] = section.start_s
        parsed["end_s"] = section.end_s
        parsed["section_label"] = section.section_label
        return _validate_label(parsed, -1)

    # One retry with feedback.
    retry_prompt = (
        f"{prompt}\n\n"
        f"You returned invalid JSON. Here is your last response: {raw_response}. "
        "Fix it and return ONLY valid JSON with the keys named above."
    )
    try:
        raw_response = await llm_client.complete(
            task=LLMTask.NARRATIVE_SECTION_LABEL,
            prompt=retry_prompt,
            max_tokens=256,
            temperature=0.0,
            json_schema=_JSON_SCHEMA,
            fallback_response=None,
        )
    except Exception:
        return None

    if isinstance(raw_response, dict):
        raw_response = json.dumps(raw_response)

    parsed = _safe_parse_json(raw_response)
    if parsed is not None:
        parsed["start_s"] = section.start_s
        parsed["end_s"] = section.end_s
        parsed["section_label"] = section.section_label
        return _validate_label(parsed, -1)

    return None


async def _label_section(
    section: SectionMoodTags,
    lyric_words: List[LyricWord],
    vocal_curve: VocalEmotionCurve,
    global_genres: List[Tuple[str, float]],
    llm_client: LLMClient,
    section_index: int,
) -> Tuple[Optional[SongSectionSemantics], Optional[dict]]:
    """Label one section and return (label, skip_record)."""
    lyrics_text = _lyrics_in_section(lyric_words, section.start_s, section.end_s)
    dominant_emotion, distribution = _vocal_emotion_in_section(
        vocal_curve, section.start_s, section.end_s
    )
    prompt = _build_prompt(
        section_label=section.section_label,
        start_s=section.start_s,
        end_s=section.end_s,
        lyrics_text=lyrics_text,
        clap_moods=section.top_moods,
        dominant_emotion=dominant_emotion,
        distribution=distribution,
        genre_tags=global_genres,
    )

    start_t = time.monotonic()
    try:
        raw_response = await llm_client.complete(
            task=LLMTask.NARRATIVE_SECTION_LABEL,
            prompt=prompt,
            max_tokens=256,
            temperature=0.0,
            json_schema=_JSON_SCHEMA,
            fallback_response=None,
        )
    except Exception as exc:
        elapsed = time.monotonic() - start_t
        if elapsed > 20:
            logger.warning("song_narrative_section_slow", section_index=section_index, elapsed_s=round(elapsed, 1))
        return None, {
            "section_index": section_index,
            "reason": "ollama_exception",
            "raw_response": str(exc),
        }

    elapsed = time.monotonic() - start_t
    if elapsed > 20:
        logger.warning("song_narrative_section_slow", section_index=section_index, elapsed_s=round(elapsed, 1))

    if isinstance(raw_response, dict):
        raw_response = json.dumps(raw_response)

    parsed = _safe_parse_json(raw_response)
    if parsed is not None:
        parsed["start_s"] = section.start_s
        parsed["end_s"] = section.end_s
        parsed["section_label"] = section.section_label
        label = _validate_label(parsed, section_index)
        if label is not None:
            return label, None

    # First retry with explicit feedback.
    retry_prompt = (
        f"{prompt}\n\n"
        f"You returned invalid JSON. Here is your last response: {raw_response}. "
        "Fix it and return ONLY valid JSON with the keys named above."
    )
    try:
        raw_response = await llm_client.complete(
            task=LLMTask.NARRATIVE_SECTION_LABEL,
            prompt=retry_prompt,
            max_tokens=256,
            temperature=0.0,
            json_schema=_JSON_SCHEMA,
            fallback_response=None,
        )
    except Exception as exc:
        return None, {
            "section_index": section_index,
            "reason": "ollama_exception_on_retry",
            "raw_response": str(exc),
        }

    if isinstance(raw_response, dict):
        raw_response = json.dumps(raw_response)

    parsed = _safe_parse_json(raw_response)
    if parsed is not None:
        parsed["start_s"] = section.start_s
        parsed["end_s"] = section.end_s
        parsed["section_label"] = section.section_label
        label = _validate_label(parsed, section_index)
        if label is not None:
            return label, None

    return None, {
        "section_index": section_index,
        "reason": "gemma_json_failure",
        "raw_response": raw_response,
    }


async def analyze_song_narrative(
    song_hash: str,
    mood_profile: SongMoodProfile,
    lyric_words: List[LyricWord],
    vocal_curve: VocalEmotionCurve,
    llm_client: LLMClient,
    cache_dir: Path = Path(r"E:\ai-video-editor-storage\song_meaning"),
) -> SongNarrative:
    """Label each song section with narrative semantics.

    Results are cached under ``<cache_dir>/<song_hash>/narrative.json``.
    """
    cache_dir = Path(cache_dir)
    cache_file = cache_dir / song_hash / "narrative.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return SongNarrative(**data)
        except Exception as exc:
            logger.warning("song_narrative_cache_corrupt", song_hash=song_hash, error=str(exc))

    sections: List[SongSectionSemantics] = []
    skipped: List[dict] = []

    for idx, section in enumerate(mood_profile.section_moods):
        label, skip = await _label_section(
            section=section,
            lyric_words=lyric_words,
            vocal_curve=vocal_curve,
            global_genres=mood_profile.genre_tags,
            llm_client=llm_client,
            section_index=idx,
        )
        if label is not None:
            sections.append(label)
        elif skip is not None:
            skipped.append(skip)
        else:
            skipped.append({"section_index": idx, "reason": "unknown", "raw_response": ""})

    narrative = SongNarrative(
        song_hash=song_hash,
        sections=sections,
        skipped_sections=skipped,
    )

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(narrative.model_dump_json(), encoding="utf-8")
        tmp.replace(cache_file)
        logger.info(
            "song_narrative_cached",
            song_hash=song_hash,
            labeled=len(sections),
            skipped=len(skipped),
        )
    except Exception as exc:
        logger.warning("song_narrative_cache_write_failed", song_hash=song_hash, error=str(exc))

    return narrative


# ---------------------------------------------------------------------------
# Synchronous helpers for callers that are not running an asyncio event loop
# (e.g. the ingest worker's song-meaning aggregation).
# ---------------------------------------------------------------------------

import httpx


def _ollama_generate_sync(
    prompt: str,
    base_url: str = "http://localhost:11434",
    model: str = "gemma4:12b",
    max_tokens: int = 256,
    temperature: float = 0.0,
) -> str:
    """Synchronous Ollama /api/chat call with keep_alive=-1."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "keep_alive": -1,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    resp = httpx.post(f"{base_url}/api/chat", json=payload, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    message = data.get("message") or {}
    text = message.get("content", "") if isinstance(message, dict) else ""
    return text if isinstance(text, str) else json.dumps(text)


def _label_section_sync(
    section: SectionMoodTags,
    lyric_words: List[LyricWord],
    vocal_curve: VocalEmotionCurve,
    global_genres: List[Tuple[str, float]],
    section_index: int,
    base_url: str = "http://localhost:11434",
    model: str = "gemma4:12b",
) -> Tuple[Optional[SongSectionSemantics], Optional[dict]]:
    """Synchronous label of one section with one retry on JSON failure."""
    lyrics_text = _lyrics_in_section(lyric_words, section.start_s, section.end_s)
    dominant_emotion, distribution = _vocal_emotion_in_section(
        vocal_curve, section.start_s, section.end_s
    )
    prompt = _build_prompt(
        section_label=section.section_label,
        start_s=section.start_s,
        end_s=section.end_s,
        lyrics_text=lyrics_text,
        clap_moods=section.top_moods,
        dominant_emotion=dominant_emotion,
        distribution=distribution,
        genre_tags=global_genres,
    )

    start_t = time.monotonic()
    try:
        raw_response = _ollama_generate_sync(prompt, base_url=base_url, model=model)
    except Exception as exc:
        elapsed = time.monotonic() - start_t
        if elapsed > 20:
            logger.warning("song_narrative_section_slow", section_index=section_index, elapsed_s=round(elapsed, 1))
        return None, {
            "section_index": section_index,
            "reason": "ollama_exception",
            "raw_response": str(exc),
        }

    elapsed = time.monotonic() - start_t
    if elapsed > 20:
        logger.warning("song_narrative_section_slow", section_index=section_index, elapsed_s=round(elapsed, 1))

    parsed = _safe_parse_json(raw_response)
    if parsed is not None:
        parsed["start_s"] = section.start_s
        parsed["end_s"] = section.end_s
        parsed["section_label"] = section.section_label
        label = _validate_label(parsed, section_index)
        if label is not None:
            return label, None

    retry_prompt = (
        f"{prompt}\n\n"
        f"You returned invalid JSON. Here is your last response: {raw_response}. "
        "Fix it and return ONLY valid JSON with the keys named above."
    )
    try:
        raw_response = _ollama_generate_sync(retry_prompt, base_url=base_url, model=model)
    except Exception as exc:
        return None, {
            "section_index": section_index,
            "reason": "ollama_exception_on_retry",
            "raw_response": str(exc),
        }

    parsed = _safe_parse_json(raw_response)
    if parsed is not None:
        parsed["start_s"] = section.start_s
        parsed["end_s"] = section.end_s
        parsed["section_label"] = section.section_label
        label = _validate_label(parsed, section_index)
        if label is not None:
            return label, None

    return None, {
        "section_index": section_index,
        "reason": "gemma_json_failure",
        "raw_response": raw_response,
    }


def analyze_song_narrative_sync(
    song_hash: str,
    mood_profile: SongMoodProfile,
    lyric_words: List[LyricWord],
    vocal_curve: VocalEmotionCurve,
    cache_dir: Path = Path(r"E:\ai-video-editor-storage\song_meaning"),
    base_url: str = "http://localhost:11434",
    model: str = "gemma4:12b",
) -> SongNarrative:
    """Synchronous variant of ``analyze_song_narrative`` for sync callers."""
    cache_dir = Path(cache_dir)
    cache_file = cache_dir / song_hash / "narrative.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return SongNarrative(**data)
        except Exception as exc:
            logger.warning("song_narrative_cache_corrupt", song_hash=song_hash, error=str(exc))

    sections: List[SongSectionSemantics] = []
    skipped: List[dict] = []
    for idx, section in enumerate(mood_profile.section_moods):
        label, skip = _label_section_sync(
            section=section,
            lyric_words=lyric_words,
            vocal_curve=vocal_curve,
            global_genres=mood_profile.genre_tags,
            section_index=idx,
            base_url=base_url,
            model=model,
        )
        if label is not None:
            sections.append(label)
        elif skip is not None:
            skipped.append(skip)
        else:
            skipped.append({"section_index": idx, "reason": "unknown", "raw_response": ""})

    narrative = SongNarrative(
        song_hash=song_hash,
        sections=sections,
        skipped_sections=skipped,
    )

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(narrative.model_dump_json(), encoding="utf-8")
        tmp.replace(cache_file)
        logger.info(
            "song_narrative_cached",
            song_hash=song_hash,
            labeled=len(sections),
            skipped=len(skipped),
        )
    except Exception as exc:
        logger.warning("song_narrative_cache_write_failed", song_hash=song_hash, error=str(exc))

    return narrative
