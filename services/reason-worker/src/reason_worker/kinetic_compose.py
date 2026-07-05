# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Cinematic kinetic text composer for music-video moments.

Three tiers:
  KT1 — Lyric stamp from Whisper'd song lyrics (placeholder; requires lyrics).
  KT2 — Iconic dialogue line surfaced by iconic_quotes.
  KT3 — LLM-composed 1-4 word punch phrase for peak narrative beats.

Density is strictly capped so text stays cinematic, not spammy.

Anti-decoration rule: there is no deterministic word-bank fallback. If the LLM
fails to produce valid structured output, the slot receives no kinetic text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

from shared_py.feature_tracer import FeatureTracer
from shared_py.llm_client import LLMClient, LLMTask
from shared_py.logging_config import StructuredLogger
from shared_py.models import Slot, ClipScore

from reason_worker.animation_select import choose_kinetic_animation
from reason_worker.face_safe import face_region_in_window

logger = StructuredLogger("reason_worker.kinetic_compose")

# Style presets mapped to a simple visual bundle.
STYLE_PRESETS = {
    "anime_impact": {"color": "#FFE600", "outline": True, "size_pct": 0.45, "animation": "punch_in_3f"},
    "cinematic_serif": {"color": "#F5F0E8", "outline": False, "size_pct": 0.35, "animation": "fade"},
    "trailer_block": {"color": "#FFFFFF", "outline": True, "size_pct": 0.50, "animation": "type_on"},
    "lowercase_intimate": {"color": "#C7C0B5", "outline": False, "size_pct": 0.30, "animation": "fade"},
    "neon_glitch": {"color": "#00F0FF", "outline": True, "size_pct": 0.40, "animation": "glitch"},
    "stamp_white": {"color": "#FFFFFF", "outline": True, "size_pct": 0.55, "animation": "smash_cut_2f"},
    "handwritten_pen": {"color": "#000000", "outline": False, "size_pct": 0.35, "animation": "type_on"},
    "shake_emphasis": {"color": "#FFFFFF", "outline": True, "size_pct": 0.50, "animation": "shake_3f"},
}

KT3_PEAK_BEATS = {
    "HOOK", "VICTORY", "CLIMAX", "RESOLUTION",
    "CRISIS", "FALL", "GRIEF",
    "catalyst", "midpoint", "all_is_lost", "finale", "break_into_three",
}


@dataclass
class KineticText:
    text: str
    tier: str  # "KT1" | "KT2" | "KT3"
    style_preset: str
    color_hex: str
    outline: bool
    size_pct: float
    animation: str
    rationale: str = ""
    animation_in: str = ""
    animation_out: str = ""
    hold_duration_s: float = 0.0


def _style_for_preset(preset_key: str, energy: float) -> Dict[str, Any]:
    """Return the style bundle for a preset, falling back to energy-aware default."""
    if preset_key in STYLE_PRESETS:
        return STYLE_PRESETS[preset_key]
    if energy > 0.8:
        return STYLE_PRESETS["anime_impact"]
    if energy > 0.55:
        return STYLE_PRESETS["trailer_block"]
    return STYLE_PRESETS["cinematic_serif"]


def _clean_llm_json(raw: str) -> Optional[dict]:
    """Extract a JSON object from raw LLM output, stripping fences and prose."""
    raw = raw.strip()
    # Strip markdown fences.
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    # Find the first JSON object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def _build_kt3_prompt(
    slot: Slot,
    source_ip_hint: Optional[str],
    previous_texts: List[str],
) -> str:
    """Build the arc-beat-aware KT3 prompt."""
    beat_context = ""
    if slot.story_beat:
        emotion = slot.arc_beat_emotion_target or "intense"
        beat_context = (
            f"Narrative beat: {slot.story_beat}\n"
            f"Required emotion: {emotion}\n"
        )

    emotion_target = slot.arc_beat_emotion_target or "intense"
    archetype_hint = f"- Archetype / IP: {source_ip_hint or 'generic'}\n"

    return (
        "You compose short on-screen text for music-video moments.\n\n"
        "Rules:\n"
        "- 1 to 4 words, UPPERCASE\n"
        "- The text must name the moment, not decorate it. Avoid generic hype words like EPIC, AWESOME, WOW.\n"
        "- Match the required emotion of the narrative beat.\n"
        "- Avoid IP-specific named characters or places.\n\n"
        "Respond ONLY with this exact JSON format (no markdown fences, no explanation):\n"
        '{"text": "YOUR WORDS", "style_preset": "anime_impact", "rationale": "one sentence"}\n\n'
        "Pick style_preset from: anime_impact, cinematic_serif, trailer_block, "
        "lowercase_intimate, neon_glitch, stamp_white, handwritten_pen.\n\n"
        f"Context:\n"
        f"- Section: {slot.section}\n"
        f"- Energy: {slot.energy_level:.2f} (0.0 calm — 1.0 climax)\n"
        f"- Required emotion: {emotion_target}\n"
        f"{beat_context}"
        f"{archetype_hint}"
        f"- Previous texts (avoid repeating): {', '.join(previous_texts[-5:]) or 'none'}"
    )


def _parse_kt3_result(raw: dict, slot: Slot) -> Optional[KineticText]:
    """Validate and normalize an LLM result dict into a KineticText."""
    text = str(raw.get("text", "")).strip().upper()
    if not text:
        return None

    preset_key = str(raw.get("style_preset", "anime_impact")).strip()
    if preset_key not in STYLE_PRESETS:
        preset_key = "anime_impact"
    style = STYLE_PRESETS[preset_key]

    size_pct = float(raw.get("size_pct", style["size_pct"]))
    size_pct = max(0.20, min(0.60, size_pct))

    color_hex = str(raw.get("color_hex", style["color"])).strip()
    if not _HEX_COLOR_RE.match(color_hex):
        color_hex = style["color"]

    return KineticText(
        text=text,
        tier="KT3",
        style_preset=preset_key,
        color_hex=color_hex,
        outline=bool(raw.get("outline", style["outline"])),
        size_pct=size_pct,
        animation=str(raw.get("animation", style["animation"])).strip() or style["animation"],
        rationale=str(raw.get("rationale", "")).strip(),
        animation_in=str(raw.get("animation_in", "")).strip(),
        animation_out=str(raw.get("animation_out", "")).strip(),
        hold_duration_s=float(raw.get("hold_duration_s", 0.0) or 0.0),
    )


def _compose_kt3_with_llm(
    slot: Slot,
    source_ip_hint: Optional[str],
    previous_texts: List[str],
) -> Optional[KineticText]:
    """Ask the local LLM to compose an arc-beat-aware cinematic phrase.

    Returns ``None`` if the LLM fails or returns invalid JSON after one retry.
    """
    prompt = _build_kt3_prompt(slot, source_ip_hint, previous_texts)
    client = LLMClient(local_model="gemma4:12b")

    for attempt in range(2):
        try:
            result = client.complete(
                task=LLMTask.KINETIC_TEXT_COMPOSE,
                prompt=prompt,
                max_tokens=128,
                temperature=0.7,
                json_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "style_preset": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["text", "style_preset", "rationale"],
                },
            )
            if not isinstance(result, dict):
                raw_dict = _clean_llm_json(str(result))
                if raw_dict is None:
                    continue
                result = raw_dict
            kt = _parse_kt3_result(result, slot)
            if kt is not None:
                return kt
        except Exception as e:
            logger.warning("kinetic_text_llm_failed", attempt=attempt, error=str(e))

    slot.enable_kinetic_text = False
    logger.info("kinetic_text_llm_parse_failed", slot_index=slot.index, fallback_reason="llm_parse_failed")
    return None


def compose_kinetic_text_for_slot(
    slot: Slot,
    source_ip_hint: Optional[str] = None,
    previous_texts: Optional[List[str]] = None,
    iconic_text: Optional[str] = None,
    use_llm: bool = True,
) -> Optional[KineticText]:
    """Compose a single kinetic text moment for ``slot``.

    Prefers KT2 (iconic quote) when available, otherwise KT3 for peak beats.
    Returns ``None`` when no text should appear on this slot or the LLM fails.
    """
    previous_texts = previous_texts or []

    # KT2 — iconic dialogue line surfaced by iconic_quotes.
    if iconic_text:
        text = iconic_text.strip().upper()
        if text and text not in previous_texts:
            style = _style_for_preset("trailer_block", 0.8)
            return KineticText(
                text=text,
                tier="KT2",
                style_preset="trailer_block",
                color_hex=style["color"],
                outline=style["outline"],
                size_pct=style["size_pct"],
                animation=style["animation"],
                rationale="iconic_quote_surface",
            )

    # KT3 — generated phrase for peak narrative beats.
    story_beat = getattr(slot, "story_beat", None)
    is_peak = story_beat in KT3_PEAK_BEATS
    is_high_energy = slot.energy_level >= 0.75 and slot.section in ("chorus", "drop", "bridge")
    if not (is_peak or is_high_energy):
        return None

    if not use_llm:
        slot.enable_kinetic_text = False
        logger.info("kinetic_text_skipped", slot_index=slot.index, fallback_reason="llm_disabled")
        return None

    return _compose_kt3_with_llm(slot, source_ip_hint, previous_texts)


def assign_kinetic_text_to_slots(
    slots: List[Slot],
    source_ip_hint: Optional[str] = None,
    use_llm: bool = True,
    max_text_count: Optional[int] = None,
    iconic_texts: Optional[Dict[str, str]] = None,
    rankings: Optional[Dict[int, List[ClipScore]]] = None,
    clip_paths: Optional[Dict[str, str]] = None,
) -> List[Slot]:
    """Assign kinetic text to a subset of slots, respecting density caps.

    Mutates ``slot.kinetic_text`` and ``slot.enable_kinetic_text`` in place.
    Returns the mutated list for chaining.
    """
    with FeatureTracer("kinetic_text", gated_in=True) as ft:
        if max_text_count is None:
            max_text_count = max(3, int(0.1 * len(slots)))

        previous_texts: List[str] = []
        last_text_index = -10
        text_count = 0
        produced_tiers: List[str] = []
        failed_count = 0

        for slot in slots:
            if text_count >= max_text_count:
                break
            if slot.index - last_text_index < 3:
                continue

            # Semantic relevance gate: skip slots whose best clip is a poor match.
            if rankings is not None:
                scores = rankings.get(slot.index, [])
                if not scores or scores[0].semantic_score < 0.45:
                    continue

            iconic_text = None
            if iconic_texts and slot.selected_clip_id:
                iconic_text = iconic_texts.get(slot.selected_clip_id)

            kt = compose_kinetic_text_for_slot(
                slot,
                source_ip_hint=source_ip_hint,
                previous_texts=previous_texts,
                iconic_text=iconic_text,
                use_llm=use_llm,
            )
            if kt is None:
                if slot.story_beat and not slot.enable_kinetic_text:
                    failed_count += 1
                continue

            # Wave 8: pick a context-aware animation for the style and placement.
            face_present = False
            if clip_paths and slot.selected_clip_id:
                clip_path = clip_paths.get(slot.selected_clip_id)
                if clip_path:
                    window_start = slot.source_window_start_s or 0.0
                    window_end = window_start + max(0.1, slot.duration_s)
                    region = face_region_in_window(clip_path, window_start, window_end)
                    face_present = region["area_ratio"] >= 0.02

            animation = choose_kinetic_animation(slot, kt.style_preset, face_present=face_present)
            kt.animation = animation
            slot.kinetic_text = kt.text
            slot.enable_kinetic_text = True
            slot.kinetic_text_style = kt.style_preset  # type: ignore[attr-defined]
            slot.kinetic_text_color = kt.color_hex  # type: ignore[attr-defined]
            slot.kinetic_text_animation = animation  # type: ignore[attr-defined]
            previous_texts.append(kt.text)
            last_text_index = slot.index
            produced_tiers.append(kt.tier)
            text_count += 1

        if text_count == 0:
            ft.fallback("no_high_energy_slots")
            return slots

        tier_counts = {}
        for t in produced_tiers:
            tier_counts[t] = tier_counts.get(t, 0) + 1
        tier_sig = ",".join(f"{k}={v}" for k, v in sorted(tier_counts.items()))
        ft.signature(
            f"n_texts={text_count},failed={failed_count},tiers={tier_sig},"
            f"texts={'|'.join(previous_texts)}"
        )
        ft.real()
        return slots
