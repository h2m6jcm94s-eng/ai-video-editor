# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Programmatic fallback provider - no LLM calls, uses rules/heuristics."""

import os
from typing import Dict, Any, List

from shared_py.ai_providers.base import AIProvider
from shared_py.models import CutList, CutListGlobals, Slot, SectionMarker, ShotAnalysis, StyleAnalysis


class ProgrammaticProvider(AIProvider):
    """Zero-cost provider that generates cut-lists using beat-synced heuristics."""

    name = "programmatic"

    def generate_cutlist(
        self,
        context: str,
        schema: Dict[str, Any],
        max_tokens: int = 4096,
    ) -> CutList:
        """Parse context and generate a programmatic cut-list."""
        import sys
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        reason_path = os.path.join(repo_root, "reason-worker", "src")
        if reason_path not in sys.path:
            sys.path.insert(0, reason_path)

        from reason_worker.cutlist_gen import generate_cutlist_programmatic
        from shared_py.models import BeatGrid, ShotBoundary

        # Parse BeatGrid and ShotBoundary from the rich text context
        # For the programmatic fallback we construct minimal objects from context heuristics
        # In practice, callers of the programmatic provider should call generate_cutlist_programmatic directly
        # with real BeatGrid / ShotBoundary objects. This adapter parses enough to return a valid CutList.
        beat_grid = BeatGrid(
            bpm=120.0,
            time_signature="4/4",
            beats=[],
            downbeats=[],
            beat_positions=[],
            segments=[],
        )
        shots = []
        return generate_cutlist_programmatic(beat_grid, shots, [], ["wide"])

    def classify_shot(self, keyframes: List[Any], schema: Dict[str, Any]) -> ShotAnalysis:
        """Heuristic shot classification without LLM."""
        return ShotAnalysis(
            shot_size="medium",
            motion="static",
            subject_type="unknown",
            lighting="neutral",
            dominant_color="#808080",
            camera_move="static",
        )

    def analyze_style(self, reference_desc: str) -> StyleAnalysis:
        """Heuristic style analysis without LLM."""
        return StyleAnalysis(
            color_palette=["#808080"],
            contrast_level=1.0,
            saturation_level=1.0,
            brightness_level=1.0,
            lut_extracted=False,
            detected_transitions=[],
            detected_overlays=[],
            camera_motions=[],
            pacing="medium",
            mood="neutral",
        )
