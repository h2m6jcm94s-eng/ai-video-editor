# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Anthropic Claude provider with forced tool-use JSON schema."""

import os
import json
from typing import Dict, Any, List

try:
    import anthropic
except ImportError:
    anthropic = None

from shared_py.ai_providers.base import AIProvider
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, ShotAnalysis, StyleAnalysis


class ClaudeProvider(AIProvider):
    """Claude Sonnet 4.6 with forced tool-use for reliable structured output."""

    name = "claude"

    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-6-20251001"):
        if anthropic is None:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not resolved_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self.client = anthropic.Anthropic(api_key=resolved_key)
        self.model = model

    def generate_cutlist(self, context: str, schema: Dict[str, Any], max_tokens: int = 4096) -> CutList:
        tools = [
            {
                "name": "emit_cutlist",
                "description": "Emit the final cut-list as structured JSON",
                "input_schema": schema,
            }
        ]

        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=self.SYSTEM_PROMPT_CUTLIST,
                    messages=[{"role": "user", "content": context}],
                    tools=tools,
                    tool_choice={"type": "tool", "name": "emit_cutlist"},
                )

                for block in response.content:
                    if block.type == "tool_use" and block.name == "emit_cutlist":
                        data = block.input
                        return CutList(
                            globals=CutListGlobals(**data["globals"]),
                            slots=[Slot(**s) for s in data["slots"]],
                            overlays=[Overlay(**o) for o in data.get("overlays", [])],
                        )

            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"Claude cut-list generation failed after 3 attempts: {e}")

        raise RuntimeError("Claude returned no tool_use block")

    def classify_shot(self, keyframes: List[Any], schema: Dict[str, Any]) -> ShotAnalysis:
        # For shot classification, we describe the keyframes textually
        # since Claude doesn't natively accept video (only images)
        frame_desc = f"Analyzing {len(keyframes)} keyframes for shot classification."
        prompt = (
            f"{frame_desc}\n\n"
            "Return a JSON object with these exact keys: "
            "shot_size, motion, subject_type, lighting, dominant_color, camera_move"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=self.SYSTEM_PROMPT_SHOT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else "{}"
        # Extract JSON from markdown code blocks if present
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Claude returned invalid JSON: {e}\nRaw response: {text[:500]}") from e

        return ShotAnalysis(
            shot_size=data.get("shot_size", "medium"),
            motion=data.get("motion", "static"),
            subject_type=data.get("subject_type", "unknown"),
            lighting=data.get("lighting", "neutral"),
            dominant_color=data.get("dominant_color", "#808080"),
            camera_move=data.get("camera_move", "static"),
        )

    def analyze_style(self, reference_desc: str) -> StyleAnalysis:
        prompt = (
            f"Analyze this reference video:\n\n{reference_desc}\n\n"
            "Return JSON with: color_palette (list of hex strings), contrast_level (float), "
            "saturation_level (float), brightness_level (float), pacing (string), mood (string), "
            "detected_transitions (list), camera_motions (list)"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.SYSTEM_PROMPT_STYLE,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else "{}"
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Claude returned invalid JSON: {e}\nRaw response: {text[:500]}") from e

        return StyleAnalysis(
            color_palette=data.get("color_palette", ["#808080"]),
            contrast_level=data.get("contrast_level", 1.0),
            saturation_level=data.get("saturation_level", 1.0),
            brightness_level=data.get("brightness_level", 1.0),
            pacing=data.get("pacing", "medium"),
            mood=data.get("mood", "neutral"),
            detected_transitions=data.get("detected_transitions", []),
            camera_motions=data.get("camera_motions", []),
        )
