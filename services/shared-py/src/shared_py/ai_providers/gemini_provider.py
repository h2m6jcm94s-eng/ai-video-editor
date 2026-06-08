# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Google Gemini provider with responseSchema / JSON mode."""

import os
import json
import base64
from typing import Dict, Any, List
from io import BytesIO

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from shared_py.ai_providers.base import AIProvider
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, ShotAnalysis, StyleAnalysis


class GeminiProvider(AIProvider):
    """Gemini 2.5 Pro / Flash with structured JSON output."""

    name = "gemini"

    def __init__(self, api_key: str = None, model: str = "gemini-2.5-flash-preview-05-20"):
        if genai is None:
            raise ImportError("google-generativeai not installed. Run: pip install google-generativeai")
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set")
        genai.configure(api_key=self.api_key)
        self.model = model
        self._client = genai.GenerativeModel(model)

    def generate_cutlist(self, context: str, schema: Dict[str, Any], max_tokens: int = 4096) -> CutList:
        prompt = (
            f"{self.SYSTEM_PROMPT_CUTLIST}\n\n"
            f"{context}\n\n"
            "Return ONLY valid JSON matching this schema exactly. No markdown, no explanation.\n"
            f"{json.dumps(schema, indent=2)}"
        )

        for attempt in range(3):
            try:
                response = self._client.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        max_output_tokens=max_tokens,
                    ),
                )
                text = response.text
                data = json.loads(text)
                return CutList(
                    globals=CutListGlobals(**data["globals"]),
                    slots=[Slot(**s) for s in data["slots"]],
                    overlays=[Overlay(**o) for o in data.get("overlays", [])],
                )
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"Gemini cut-list generation failed after 3 attempts: {e}")

        raise RuntimeError("Gemini returned invalid JSON")

    def classify_shot(self, keyframes: List[Any], schema: Dict[str, Any]) -> ShotAnalysis:
        # keyframes can be PIL Images, numpy arrays, or file paths
        parts = [self.SYSTEM_PROMPT_SHOT + "\n\nClassify these keyframes:"]
        for frame in keyframes[:16]:  # Gemini handles up to 16 images
            img = self._to_pil(frame)
            parts.append(img)

        parts.append(
            "Return ONLY valid JSON with keys: shot_size, motion, subject_type, lighting, dominant_color, camera_move"
        )

        response = self._client.generate_content(
            parts,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
            ),
        )

        text = response.text
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
            f"{self.SYSTEM_PROMPT_STYLE}\n\n"
            f"Analyze this reference video description:\n\n{reference_desc}\n\n"
            "Return ONLY valid JSON with keys: color_palette, contrast_level, saturation_level, "
            "brightness_level, pacing, mood, detected_transitions, camera_motions"
        )

        response = self._client.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
            ),
        )

        text = response.text
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

    @staticmethod
    def _to_pil(frame):
        """Convert various image types to PIL Image."""
        from PIL import Image
        if isinstance(frame, Image.Image):
            return frame
        if isinstance(frame, str):
            return Image.open(frame)
        if hasattr(frame, "shape"):  # numpy
            import numpy as np
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                return Image.fromarray(frame.astype(np.uint8))
        raise ValueError(f"Cannot convert frame of type {type(frame)} to PIL Image")
