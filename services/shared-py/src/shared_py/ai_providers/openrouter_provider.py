"""OpenRouter universal gateway provider. Access 100+ models with one key."""

import os
import json
from typing import Dict, Any, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from shared_py.ai_providers.base import AIProvider
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, ShotAnalysis, StyleAnalysis


class OpenRouterProvider(AIProvider):
    """OpenRouter gateway — use any model (Claude, GPT, Llama, etc) with one API key."""

    name = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str = None, model: str = "anthropic/claude-sonnet-4"):
        if OpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")
        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not resolved_key:
            raise ValueError("OPENROUTER_API_KEY is not set — set it or remove 'openrouter' from AI_PROVIDER")
        self.client = OpenAI(
            api_key=resolved_key,
            base_url=self.BASE_URL,
        )
        self.model = model

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
                    extra_headers={"HTTP-Referer": "https://ai-video-editor.local", "X-Title": "AI Video Editor"},
                    max_tokens=max_tokens,
                )
                text = response.choices[0].message.content
                # OpenRouter may return markdown-wrapped JSON
                text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                data = json.loads(text)
                return CutList(
                    globals=CutListGlobals(**data["globals"]),
                    slots=[Slot(**s) for s in data["slots"]],
                    overlays=[Overlay(**o) for o in data.get("overlays", [])],
                )
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"OpenRouter cut-list generation failed after 3 attempts: {e}")

        raise RuntimeError("OpenRouter returned invalid JSON")

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
            extra_headers={"HTTP-Referer": "https://ai-video-editor.local", "X-Title": "AI Video Editor"},
            max_tokens=512,
        )

        text = response.choices[0].message.content
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
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
            extra_headers={"HTTP-Referer": "https://ai-video-editor.local", "X-Title": "AI Video Editor"},
            max_tokens=1024,
        )

        text = response.choices[0].message.content
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
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
