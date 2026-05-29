# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Alibaba Qwen provider via DashScope OpenAI-compatible API."""

import os
import json
from typing import Dict, Any, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from shared_py.ai_providers.base import AIProvider
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, ShotAnalysis, StyleAnalysis


class QwenProvider(AIProvider):
    """Qwen (qwen-max / qwen-plus / qwen-turbo) via DashScope OpenAI-compatible API.
    Models: qwen-max, qwen-plus, qwen-turbo, qwen2.5-72b-instruct, etc.
    """

    name = "qwen"
    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(self, api_key: str = None, model: str = "qwen-max"):
        if OpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")
        key = api_key or os.environ.get("QWEN_API_KEY", "")
        if not key:
            raise ValueError("QWEN_API_KEY environment variable is required")
        self.client = OpenAI(
            api_key=key,
            base_url=self.BASE_URL,
        )
        self.model = model

    def _strip_markdown(self, text: str) -> str:
        """Qwen models sometimes wrap JSON in markdown code blocks."""
        return (
            text.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )

    def generate_cutlist(self, context: str, schema: Dict[str, Any], max_tokens: int = 4096) -> CutList:
        prompt = (
            f"{self.SYSTEM_PROMPT_CUTLIST}\n\n"
            f"{context}\n\n"
            "Return ONLY valid JSON matching this schema exactly. No markdown, no explanation.\n"
            f"{json.dumps(schema, indent=2)}"
        )

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT_CUTLIST},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=max_tokens,
                )
                text = self._strip_markdown(response.choices[0].message.content)
                data = json.loads(text)
                return CutList(
                    globals=CutListGlobals(**data["globals"]),
                    slots=[Slot(**s) for s in data["slots"]],
                    overlays=[Overlay(**o) for o in data.get("overlays", [])],
                )
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"Qwen cut-list generation failed after 3 attempts: {e}")

        raise RuntimeError("Qwen returned invalid JSON")

    def classify_shot(self, keyframes: List[Any], schema: Dict[str, Any]) -> ShotAnalysis:
        prompt = (
            "Classify this video shot. Describe the keyframes: "
            f"{len(keyframes)} frames provided.\n\n"
            "Return ONLY valid JSON with keys: shot_size, motion, subject_type, lighting, dominant_color, camera_move"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT_SHOT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=512,
        )

        text = self._strip_markdown(response.choices[0].message.content)
        data = json.loads(text)
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
            f"Analyze this reference video description:\n\n{reference_desc}\n\n"
            "Return ONLY valid JSON with keys: color_palette, contrast_level, saturation_level, "
            "brightness_level, pacing, mood, detected_transitions, camera_motions"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT_STYLE},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=1024,
        )

        text = self._strip_markdown(response.choices[0].message.content)
        data = json.loads(text)
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
