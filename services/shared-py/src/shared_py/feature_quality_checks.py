# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Quality checks for demo-critical features.

Each checker receives the feature's output (or ``None`` when the feature did
not run) and returns ``(ok, reason)``.  Most checks are intentionally lenient
placeholders; only a few have real thresholds so the framework can catch the
most obvious regressions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def _as_list(value: Any) -> Optional[List[float]]:
    """Coerce numeric sequence-like inputs to a list of floats."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    if hasattr(value, "tolist"):
        return [float(v) for v in value.tolist()]
    return None


def check_heatmap(windows: Optional[List[Any]]) -> Tuple[bool, str]:
    """Coverage >= 0.95 windows scored > 0 and score std > 0.1."""
    if not windows:
        return False, "heatmap: no windows produced"

    scores: List[float] = []
    for w in windows:
        if hasattr(w, "score"):
            scores.append(float(w.score))
        elif isinstance(w, dict):
            scores.append(float(w.get("score", 0.0)))
        else:
            try:
                scores.append(float(w))
            except Exception:
                continue

    if not scores:
        return False, "heatmap: no scoreable windows"

    coverage = sum(1.0 for s in scores if s > 0.0) / len(scores)
    if coverage < 0.95:
        return False, f"heatmap: coverage {coverage:.2f} < 0.95"

    std = float(np.std(scores))
    if std <= 0.1:
        return False, f"heatmap: score std {std:.3f} <= 0.1"

    return True, ""


def check_aesthetic(scores: Optional[Any]) -> Tuple[bool, str]:
    """Mean aesthetic score is in a sane range and shows some variance."""
    values = _as_list(scores)
    if values is None or len(values) == 0:
        return False, "aesthetic: no scores"

    mean = float(np.mean(values))
    std = float(np.std(values))
    if mean < 0.1:
        return False, f"aesthetic: mean {mean:.3f} < 0.1"
    if mean > 0.95:
        return False, f"aesthetic: mean {mean:.3f} > 0.95"
    if std < 0.02:
        return False, f"aesthetic: std {std:.3f} < 0.02"
    return True, ""


def check_iconic_quotes(quotes: Optional[List[Any]]) -> Tuple[bool, str]:
    """At least one quote crossed the iconic threshold."""
    if not quotes:
        return False, "iconic_quotes: no quotes produced"
    return True, ""


def check_identity_matte(output: Optional[Any]) -> Tuple[bool, str]:
    """Identity-aware matting produced non-empty detections or mask paths."""
    if output is None:
        return False, "identity_matte: no output"
    if isinstance(output, dict):
        if not output:
            return False, "identity_matte: empty mask map"
        if any(output.values()):
            return True, ""
        return False, "identity_matte: mask paths are empty"
    if isinstance(output, (list, tuple)):
        if not output:
            return False, "identity_matte: no detections"
        return True, ""
    return True, ""


def check_dialogue(tracks: Optional[List[Any]]) -> Tuple[bool, str]:
    """At least one dialogue audio track was produced."""
    if not tracks:
        return False, "dialogue: no tracks produced"
    dialogue_count = 0
    for t in tracks:
        role = None
        if hasattr(t, "role"):
            role = t.role
        elif isinstance(t, dict):
            role = t.get("role")
        if role == "dialogue":
            dialogue_count += 1
    if dialogue_count == 0:
        return False, "dialogue: no dialogue-role tracks"
    return True, ""


def check_save_the_cat(cutlist: Optional[Any]) -> Tuple[bool, str]:
    """Save-the-Cat annotated at least one slot."""
    if cutlist is None:
        return False, "save_the_cat: no cutlist"
    slots = None
    if hasattr(cutlist, "slots"):
        slots = cutlist.slots
    elif isinstance(cutlist, dict):
        slots = cutlist.get("slots")
    if not slots:
        return False, "save_the_cat: no slots"
    for slot in slots:
        story_beat = None
        if hasattr(slot, "story_beat"):
            story_beat = slot.story_beat
        elif isinstance(slot, dict):
            story_beat = slot.get("story_beat")
        if story_beat is not None:
            return True, ""
    return False, "save_the_cat: no slot has a story beat"


def check_auto_lut(style_analysis: Optional[Any]) -> Tuple[bool, str]:
    """Auto-LUT transfer produced an extracted LUT when a reference exists."""
    if style_analysis is None:
        return False, "auto_lut: no style analysis"

    data: Dict[str, Any]
    if hasattr(style_analysis, "model_dump"):
        data = style_analysis.model_dump()
    elif hasattr(style_analysis, "__dict__"):
        data = vars(style_analysis)
    else:
        data = dict(style_analysis) if isinstance(style_analysis, dict) else {}

    if not data.get("reference_present") and not data.get("lut_extracted"):
        return True, ""
    if data.get("lut_extracted") and data.get("lut_storage_key"):
        return True, ""
    return False, "auto_lut: reference present but LUT not extracted"


def check_style_genome(genome: Optional[Any]) -> Tuple[bool, str]:
    """Style genome contains populated families."""
    if genome is None:
        return False, "style_genome: no genome"

    data: Dict[str, Any]
    if hasattr(genome, "model_dump"):
        data = genome.model_dump()
    elif hasattr(genome, "__dict__"):
        data = vars(genome)
    else:
        data = dict(genome) if isinstance(genome, dict) else {}

    families = data.get("families")
    if not families:
        return False, "style_genome: empty families"
    return True, ""


def check_demucs(stems: Optional[Any]) -> Tuple[bool, str]:
    """Demucs produced at least one stem."""
    if stems is None:
        return False, "demucs: no stems"
    if isinstance(stems, dict) and not stems:
        return False, "demucs: empty stem map"
    if isinstance(stems, (list, tuple)) and not stems:
        return False, "demucs: empty stem list"
    return True, ""


def check_momentum(coherence_scores: Optional[Any]) -> Tuple[bool, str]:
    """Momentum coherence scores exist and show variance."""
    values = _as_list(coherence_scores)
    if values is None or len(values) == 0:
        return False, "momentum: no coherence scores"
    std = float(np.std(values))
    if std < 0.01:
        return False, f"momentum: coherence std {std:.3f} < 0.01"
    return True, ""
