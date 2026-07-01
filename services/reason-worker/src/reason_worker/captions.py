# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Auto-caption generator (AC1 tier).

Burns word-by-word captions into the final render using Whisper word-level
timestamps. AC1 is single-speaker, no diarization, one style preset
(``tiktok_white_pop``). Speaker names and color-coding come in AC2.

Captions are gated by face visibility so voiceover-over-action moments do not
burn disconnected dialogue onto the screen.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from shared_py.feature_tracer import FeatureTracer
from shared_py.logging_config import StructuredLogger
from shared_py.models import CutList, Overlay

from reason_worker.audio_scoring import DialogueSegment

logger = StructuredLogger("reason_worker.captions")

# AC1 single-speaker default style: TikTok-style white pop.
DEFAULT_CAPTION_STYLE = {
    "position": "bottom",
    "font": "Inter",
    "font_size_px": 72,
    "color": "#FFFFFF",
    "stroke": "#000000",
    "animation": "pop",
}

# Minimum face area (as a fraction of the frame) to count as "visible speaker".
_MIN_FACE_AREA_RATIO = 0.02


@dataclass
class CaptionWord:
    text: str
    start_s: float
    end_s: float
    slot_index: int
    slot_start_s: float


def _load_face_detections(clip_path: str) -> List[dict]:
    """Load cached InsightFace detections for a clip without heavy imports."""
    cache_path = f"{clip_path}.faces.json"
    if not os.path.exists(cache_path):
        return []
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("failed_to_load_face_cache", path=cache_path, error=str(exc))
        return []


def _face_visible_in_window(
    clip_path: str,
    window_start_s: float,
    start_s: float,
    end_s: float,
    min_area_ratio: float = _MIN_FACE_AREA_RATIO,
    min_coverage: float = 0.30,
) -> bool:
    """Return True if a sufficiently large face covers most of the window.

    All times are in clip-relative seconds. Coverage is the fraction of the
    phrase window that has at least one qualifying face detection. If no face
    cache exists, the gate fails open so captions still render, but a warning is
    logged.
    """
    detections = _load_face_detections(clip_path)
    if not detections:
        logger.warning("face_cache_missing_for_caption_gate", clip_path=clip_path)
        return True

    abs_start = window_start_s + start_s
    abs_end = window_start_s + end_s
    window_duration = max(0.001, abs_end - abs_start)

    qualifying_times = {
        float(det.get("t_s", -1.0))
        for det in detections
        if abs_start <= float(det.get("t_s", -1.0)) <= abs_end
        and float(det.get("face_area_ratio", 0.0)) >= min_area_ratio
    }
    if not qualifying_times:
        return False

    # Coverage estimate: sampled at 2 fps (the same rate used during extraction).
    sample_interval = 0.5
    samples = max(1, int(window_duration / sample_interval))
    covered_samples = sum(
        1
        for i in range(samples)
        if any(
            abs((abs_start + i * sample_interval) - t) <= sample_interval
            for t in qualifying_times
        )
    )
    coverage = covered_samples / samples
    return coverage >= min_coverage


def _segments_to_caption_words(
    segments: List[DialogueSegment],
    slot_index: int,
    slot_start_s: float,
) -> List[CaptionWord]:
    """Convert dialogue segments (with word timestamps) into caption words."""
    words: List[CaptionWord] = []
    for seg in segments:
        for word in getattr(seg, "words", []):
            text = word.text.strip()
            if not text:
                continue
            words.append(
                CaptionWord(
                    text=text,
                    start_s=slot_start_s + word.start_s,
                    end_s=slot_start_s + word.end_s,
                    slot_index=slot_index,
                    slot_start_s=slot_start_s,
                )
            )
    return words


def _group_words_into_phrases(
    words: List[CaptionWord], max_words: int = 4, max_gap_s: float = 0.35
) -> List[CaptionWord]:
    """Group rapid consecutive words into short phrases for readability."""
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: w.start_s)
    phrases: List[CaptionWord] = []
    current: List[CaptionWord] = [sorted_words[0]]

    for w in sorted_words[1:]:
        last = current[-1]
        same_slot = w.slot_index == last.slot_index
        gap_ok = w.start_s - last.end_s <= max_gap_s
        len_ok = len(current) < max_words
        if same_slot and gap_ok and len_ok:
            current.append(w)
        else:
            phrases.append(
                CaptionWord(
                    text=" ".join(cw.text for cw in current),
                    start_s=current[0].start_s,
                    end_s=current[-1].end_s,
                    slot_index=current[0].slot_index,
                    slot_start_s=current[0].slot_start_s,
                )
            )
            current = [w]

    if current:
        phrases.append(
            CaptionWord(
                text=" ".join(cw.text for cw in current),
                start_s=current[0].start_s,
                end_s=current[-1].end_s,
                slot_index=current[0].slot_index,
                slot_start_s=current[0].slot_start_s,
            )
        )

    return phrases


def generate_caption_overlays_from_segments(
    slot_segments: List[tuple[int, str, float, float, List[DialogueSegment]]],
    style: str = "tiktok_white_pop",
    max_captions: Optional[int] = None,
    clip_paths: Optional[Dict[str, str]] = None,
) -> List[Overlay]:
    """Generate caption Overlay objects from per-slot dialogue segments.

    Each ``slot_segments`` tuple is ``(slot_index, clip_id, source_window_start_s,
    slot_start_s, segments)``. AC1 is single-speaker, tiktok_white_pop style,
    phrase-grouped for readability. Phrases are dropped when no speaker face is
    visible in the source window.
    """
    with FeatureTracer("captions", gated_in=True) as ft:
        all_words: List[CaptionWord] = []
        for slot_index, _clip_id, _window_start, slot_start_s, segments in slot_segments:
            all_words.extend(
                _segments_to_caption_words(segments, slot_index, slot_start_s)
            )

        if not all_words:
            ft.fallback("no_words_available")
            return []

        phrases = _group_words_into_phrases(all_words)

        # Filter phrases to those where a face is visible in the source window.
        filtered_phrases: List[CaptionWord] = []
        dropped_for_no_face = 0
        if clip_paths:
            # Build a map from slot_index -> (clip_id, source_window_start_s).
            slot_info = {
                idx: (cid, wstart)
                for idx, cid, wstart, _start, _segs in slot_segments
            }
            for phrase in phrases:
                info = slot_info.get(phrase.slot_index)
                if not info:
                    filtered_phrases.append(phrase)
                    continue
                clip_id, window_start = info
                clip_path = clip_paths.get(clip_id)
                if not clip_path:
                    filtered_phrases.append(phrase)
                    continue
                phrase_start_in_slot = phrase.start_s - phrase.slot_start_s
                phrase_end_in_slot = phrase.end_s - phrase.slot_start_s
                if _face_visible_in_window(
                    clip_path,
                    window_start,
                    phrase_start_in_slot,
                    phrase_end_in_slot,
                ):
                    filtered_phrases.append(phrase)
                else:
                    dropped_for_no_face += 1
        else:
            filtered_phrases = phrases

        if max_captions:
            filtered_phrases = filtered_phrases[:max_captions]

        style_cfg = DEFAULT_CAPTION_STYLE
        overlays: List[Overlay] = []
        for phrase in filtered_phrases:
            overlays.append(
                Overlay(
                    text=phrase.text.upper(),
                    start_s=phrase.start_s,
                    end_s=phrase.end_s,
                    position=style_cfg["position"],
                    font=style_cfg["font"],
                    font_size_px=style_cfg["font_size_px"],
                    color=style_cfg["color"],
                    stroke=style_cfg["stroke"],
                    animation=style_cfg["animation"],
                )
            )

        ft.signature(
            f"style={style},n_captions={len(overlays)},n_words={len(all_words)},"
            f"dropped_for_no_face={dropped_for_no_face}"
        )
        ft.real()
        return overlays


def generate_caption_overlays(
    cutlist: CutList,
    style: str = "tiktok_white_pop",
    max_captions: Optional[int] = None,
) -> List[Overlay]:
    """Backward-compatible entry point from a cutlist."""
    return generate_caption_overlays_from_segments([], style=style, max_captions=max_captions)
