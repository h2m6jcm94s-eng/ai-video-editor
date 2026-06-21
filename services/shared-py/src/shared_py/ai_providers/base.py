# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Base AIProvider interface. All prompts are provider-agnostic."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from shared_py.models import CutList, ShotAnalysis, StyleAnalysis


class AIProvider(ABC):
    """Abstract base for all AI providers.

    Prompts, schemas, and analysis context are identical across providers.
    Only the transport layer (HTTP client / SDK) and response parsing differ.
    """

    name: str = "base"

    # ------------------------------------------------------------------
    # Prompt templates (shared across all providers)
    # ------------------------------------------------------------------

    SYSTEM_PROMPT_CUTLIST = (
        "You are an expert video editor AI for a beat-synced social video editor. "
        "Always return valid JSON matching the provided schema exactly. "
        "Every cut must snap to the nearest beat. Every 4-8 cuts, force a longer shot at the nearest downbeat. "
        "Dramatic transitions (flash, whip, dissolve) only at section boundaries. "
        "Match energy_curve: low energy = wide/establishing shots, high energy = close-ups/action. "
        "Do not request shot types the user doesn't have. Keep total duration under 60 seconds for the MVP. "
        "Populate slot.effects[] and overlays[] to make the edit feel alive, not like a slideshow. "
        "Effects: zoom_punch_in on high-energy downbeats, vignette on the highest-energy slot, "
        "film_grain at section boundaries, focus_pull on long low-energy slots. "
        "Overlays: add 1-3 short text overlays (hook, section labels, call-to-action) timed to energy peaks. "
        "Do not stack more than 2 effects per slot."
    )

    SYSTEM_PROMPT_SHOT = (
        "You are a cinematography expert AI. Analyze the provided video frames and return "
        "a structured classification of the shot type, motion, subject, lighting, and camera movement."
    )

    SYSTEM_PROMPT_STYLE = (
        "You are a film colorist and editor AI. Analyze the reference video description and "
        "extract the color palette, contrast, saturation, brightness, pacing, mood, and detected camera motions."
    )

    @abstractmethod
    def generate_cutlist(
        self,
        context: str,
        schema: Dict[str, Any],
        max_tokens: int = 4096,
    ) -> CutList:
        """Generate a cut-list from analysis context using the provider's native tool/schema enforcement."""
        ...

    @abstractmethod
    def classify_shot(
        self,
        keyframes: List[Any],
        schema: Dict[str, Any],
    ) -> ShotAnalysis:
        """Classify a single shot from keyframe images."""
        ...

    @abstractmethod
    def analyze_style(
        self,
        reference_desc: str,
    ) -> StyleAnalysis:
        """Analyze overall style from a text description of the reference video."""
        ...

    def _build_cutlist_context(
        self,
        beat_grid: Any,
        shot_boundaries: List[Any],
        style_analysis: Dict[str, Any],
        energy_curve: List[float],
        available_shot_types: List[str],
        total_duration: float = 30.0,
    ) -> str:
        """Build the rich text context used by ALL providers."""
        lines = [
            "# Reference Video Analysis",
            "",
            "## Beat Grid",
            f"- BPM: {beat_grid.bpm if hasattr(beat_grid, 'bpm') else 'unknown'}",
            f"- Time Signature: 4/4",
            f"- Total Beats: {len(beat_grid.beats) if hasattr(beat_grid, 'beats') else 0}",
            f"- Downbeats at: {[round(b, 2) for b in (beat_grid.downbeats if hasattr(beat_grid, 'downbeats') else [])[:8]]}...",
            "",
            "## Song Sections",
        ]

        segments = beat_grid.segments if hasattr(beat_grid, "segments") else []
        for seg in segments:
            lines.append(f"- {seg.label}: {seg.start:.2f}s - {seg.end:.2f}s")

        lines.extend(["", "## Reference Shot Sequence"])
        for i, shot in enumerate(shot_boundaries[:20]):
            t_in = getattr(shot, "transition_in", "unknown")
            lines.append(
                f"- Shot {i+1}: {shot.start_s:.2f}s - {shot.end_s:.2f}s "
                f"({'gradual' if getattr(shot, 'is_gradual', False) else 'cut'}, transition: {t_in})"
            )

        lines.extend([
            "",
            "## Style Analysis",
            f"- Color Palette: {style_analysis.get('color_palette', [])}",
            f"- Contrast: {style_analysis.get('contrast_level', 1.0):.2f}",
            f"- Saturation: {style_analysis.get('saturation_level', 1.0):.2f}",
            f"- Brightness: {style_analysis.get('brightness_level', 1.0):.2f}",
            f"- Pacing: {style_analysis.get('pacing', 'medium')}",
            f"- Mood: {style_analysis.get('mood', 'neutral')}",
            f"- Detected Motions: {style_analysis.get('camera_motions', [])}",
            "",
            "## Energy Curve (10-point)",
            str([round(e, 2) for e in energy_curve]),
            "",
            "## Available User Clip Shot Types",
            str(available_shot_types),
            "",
            "## Instructions",
            f"Generate a cut-list that matches the reference video's editing rhythm, pacing, and energy.",
            f"- Total target duration: {total_duration}s",
            "- Every cut must snap to the nearest beat",
            "- Every 4-8 cuts, force a longer shot at the nearest downbeat",
            "- Dramatic transitions (flash, whip, dissolve) only at section boundaries",
            "- Match energy_curve: low energy = wide/establishing shots, high energy = close-ups/action",
            "- Do not request shot types the user doesn't have",
            "",
            "## Effects and Overlays (MANDATORY — do not leave empty)",
            "For each slot, decide if it needs effects in slot.effects[]:",
            "- zoom_punch_in: on downbeats where energyLevel > 0.7 (targetScale 1.15-1.3, durationMs 200-300, easing easeOut).",
            "- focus_pull: on slots where energyLevel < 0.4 and durationS > 1.5 (targetBlur 0→6, durationMs 600-1000).",
            "- film_grain: on the first slot after a section boundary (intensity 0.15).",
            "- vignette: on the single highest-energy slot in the song (intensity 0.3-0.5).",
            "- Do not add more than 2 effects per slot.",
            "",
            "Add 1-3 text overlays in overlays[]:",
            "- Hook: big text in the first 2 seconds if the song starts high-energy.",
            "- Section label: small text when a section changes (e.g., 'DROP', 'VERSE').",
            "- Outro CTA: final 2 seconds, e.g., 'FOLLOW FOR MORE'.",
            "- Use position 'center', 'top', or 'bottom'. fontSizePx 36-72. animation 'fade', 'scale', or 'pop'.",
        ])

        return "\n".join(lines)
