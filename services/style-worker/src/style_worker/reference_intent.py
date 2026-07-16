# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Extract an intent pattern profile from a reference video.

A real editor doesn't pick techniques from a menu; they decide what the viewer
should feel at each moment. This module watches the reference video's structure
(shot boundaries, transitions, timing, audio events) and extracts the editor's
intent pattern: which intents deploy, when, and with what rhythm.

Downstream intent composer uses this profile to bias its own per-slot intent
assignments.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    from scenedetect import ContentDetector, SceneManager, open_video
except Exception:  # pragma: no cover
    ContentDetector = None  # type: ignore[assignment,misc]
    SceneManager = None  # type: ignore[assignment,misc]
    open_video = None  # type: ignore[assignment,misc]

from shared_py.llm_client import LLMClient, LLMTask
from shared_py.logging_config import StructuredLogger
from shared_py.models import MusicEventGrid, ShotBoundary, StyleAnalysis

logger = StructuredLogger("style_worker.reference_intent")

# The 15 editor intents. See T.11 intent-first architecture.
INTENT_LABELS = [
    "BREATHE",
    "PUNCTUATE",
    "RAMP_UP",
    "RELEASE",
    "REVEAL",
    "WITHHOLD",
    "CONNECT",
    "ISOLATE",
    "SHOCK",
    "CARRY",
    "LINGER",
    "JAB",
    "LAYER",
    "STRIP_DOWN",
    "AMPLIFY",
]


@dataclass
class ShotIntent:
    """Intent assigned to one shot in the reference."""

    start_s: float
    end_s: float
    intent: str
    confidence: float
    rationale: str


@dataclass
class ReferenceIntentProfile:
    """Aggregate intent pattern extracted from a reference video."""

    version: str = "1.0"
    shot_intents: List[ShotIntent] = field(default_factory=list)
    intent_histogram: Dict[str, float] = field(default_factory=dict)
    intent_trajectory: List[Tuple[str, float, float]] = field(
        default_factory=list
    )  # (intent, start_s, end_s)
    avg_shot_duration_s: float = 0.0
    std_shot_duration_s: float = 0.0
    cut_density_per_min: float = 0.0
    reasoning: str = ""

    def model_dump(self) -> dict:
        return {
            "version": self.version,
            "shotIntents": [
                {
                    "start_s": s.start_s,
                    "end_s": s.end_s,
                    "intent": s.intent,
                    "confidence": s.confidence,
                    "rationale": s.rationale,
                }
                for s in self.shot_intents
            ],
            "intentHistogram": self.intent_histogram,
            "intentTrajectory": [
                {"intent": i, "start_s": s, "end_s": e}
                for i, s, e in self.intent_trajectory
            ],
            "avgShotDurationS": self.avg_shot_duration_s,
            "stdShotDurationS": self.std_shot_duration_s,
            "cutDensityPerMin": self.cut_density_per_min,
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_cache_dict(cls, data: dict) -> "ReferenceIntentProfile":
        return cls(
            version=data.get("version", "1.0"),
            shot_intents=[
                ShotIntent(
                    start_s=s.get("start_s", 0.0),
                    end_s=s.get("end_s", 0.0),
                    intent=s.get("intent", "CARRY"),
                    confidence=s.get("confidence", 0.0),
                    rationale=s.get("rationale", ""),
                )
                for s in data.get("shotIntents", [])
            ],
            intent_histogram=data.get("intentHistogram", {}),
            intent_trajectory=[
                (t.get("intent", ""), t.get("start_s", 0.0), t.get("end_s", 0.0))
                for t in data.get("intentTrajectory", [])
            ],
            avg_shot_duration_s=data.get("avgShotDurationS", 0.0),
            std_shot_duration_s=data.get("stdShotDurationS", 0.0),
            cut_density_per_min=data.get("cutDensityPerMin", 0.0),
            reasoning=data.get("reasoning", ""),
        )


def _cache_key(video_path: str) -> str:
    """Stable cache key from file size + mtime + version."""
    stat = os.stat(video_path)
    raw = f"{video_path}|{stat.st_size}|{stat.st_mtime}|reference_intent_v1"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_path(video_path: str, cache_root: Path) -> Path:
    key = _cache_key(video_path)
    return cache_root / f"{key}.json"


def _load_cached_profile(video_path: str, cache_root: Path) -> Optional[ReferenceIntentProfile]:
    path = _cache_path(video_path, cache_root)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ReferenceIntentProfile.from_cache_dict(data)
        except Exception as e:
            logger.warning("failed_to_load_cached_intent_profile", error=str(e))
    return None


def _save_cached_profile(profile: ReferenceIntentProfile, video_path: str, cache_root: Path) -> None:
    path = _cache_path(video_path, cache_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def detect_shot_boundaries(video_path: str) -> List[Tuple[float, float]]:
    """Return list of (start_s, end_s) shot windows using PySceneDetect."""
    if ContentDetector is None or SceneManager is None or open_video is None:
        logger.warning("scenedetect_not_available")
        return []

    try:
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=27.0))
        scene_manager.detect_scenes(video)
        scenes = scene_manager.get_scene_list()
        return [(s[0].get_seconds(), s[1].get_seconds()) for s in scenes]
    except Exception as e:
        logger.warning("shot_detection_failed", error=str(e))
        return []


def _audio_context_at(
    start_s: float,
    end_s: float,
    music_event_grid: Optional[MusicEventGrid],
) -> str:
    """Build a short text description of what the audio is doing at this shot."""
    if music_event_grid is None:
        return "no audio context"
    events = []
    midpoint = (start_s + end_s) / 2.0
    for t in getattr(music_event_grid, "kick_times", []) or []:
        if start_s <= t <= end_s:
            events.append("kick")
    for t in getattr(music_event_grid, "snare_times", []) or []:
        if start_s <= t <= end_s:
            events.append("snare")
    downbeats = getattr(music_event_grid, "downbeats", []) or []
    near_downbeat = any(abs(t - midpoint) < 0.1 for t in downbeats)
    parts = []
    if events:
        parts.append(f"contains {', '.join(events)}")
    if near_downbeat:
        parts.append("lands on downbeat")
    if not parts:
        return "no strong music events"
    return "; ".join(parts)


def _shot_description(
    index: int,
    start_s: float,
    end_s: float,
    duration_s: float,
    shot_boundary: Optional[ShotBoundary],
    audio_context: str,
    prev_duration_s: Optional[float],
) -> str:
    """Build a text description of one shot for the intent classifier."""
    lines = [
        f"Shot {index + 1}: {start_s:.2f}s - {end_s:.2f}s, duration {duration_s:.2f}s",
        f"  audio context: {audio_context}",
    ]
    if shot_boundary:
        lines.append(f"  transition in: {shot_boundary.transition_in}")
        lines.append(f"  transition out: {shot_boundary.transition_out}")
        if getattr(shot_boundary, "is_gradual", False):
            lines.append("  gradual transition")
        if getattr(shot_boundary, "confidence", 1.0) < 0.5:
            lines.append("  low-confidence boundary")
    if prev_duration_s is not None:
        ratio = duration_s / max(prev_duration_s, 0.1)
        if ratio > 1.8:
            lines.append("  much longer than previous shot")
        elif ratio < 0.5:
            lines.append("  much shorter than previous shot")
    return "\n".join(lines)


def _parse_intent_json(content: str) -> Tuple[str, float, str]:
    """Parse intent JSON from model response."""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*?\}", content, re.DOTALL)
        parsed = json.loads(match.group()) if match else {}

    if not parsed:
        return "CARRY", 0.0, "parse failed"

    intent = str(parsed.get("intent", "CARRY")).upper()
    if intent not in INTENT_LABELS:
        intent = "CARRY"
    confidence = float(parsed.get("confidence", 0.5))
    rationale = str(parsed.get("rationale", ""))
    return intent, max(0.0, min(1.0, confidence)), rationale


def _classify_intents_with_llm(
    shot_descriptions: List[str],
    style_analysis: Optional[StyleAnalysis],
    llm_client: Optional[LLMClient] = None,
) -> List[Tuple[str, float, str]]:
    """Ask Gemma text model to classify intents for all shots at once."""
    if not shot_descriptions:
        return []

    system = (
        "You are a film editor analyzing a reference video. For each shot below, "
        "choose the single best intent that describes what the editor is making "
        "the viewer feel at that moment."
    )
    labels_str = ", ".join(INTENT_LABELS)
    style_hint = ""
    if style_analysis:
        style_hint = (
            f"\nReference style: pacing={style_analysis.pacing}, "
            f"mood={style_analysis.mood}, transitions={style_analysis.detected_transitions}, "
            f"camera_motions={style_analysis.camera_motions}\n"
        )

    user = (
        f"{style_hint}"
        f"Available intents: {labels_str}\n\n"
        "Return ONLY a JSON array (no markdown fences):\n"
        '[{"intent": "<LABEL>", "confidence": 0.0-1.0, "rationale": "<one sentence>"}, ...]\n\n'
        "Shots:\n" + "\n\n".join(shot_descriptions)
    )

    try:
        client = llm_client or LLMClient(local_model="gemma4:12b")
        response = client.complete(
            task=LLMTask.REFERENCE_INTENT,
            prompt=f"SYSTEM: {system}\nUSER: {user}",
            max_tokens=512,
            temperature=0.0,
        )
        content = response if isinstance(response, str) else json.dumps(response)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Look for JSON array in prose.
            match = re.search(r"\[.*\]", content, re.DOTALL)
            parsed = json.loads(match.group()) if match else []

        if not isinstance(parsed, list):
            parsed = []

        results = []
        for item in parsed:
            intent = str(item.get("intent", "CARRY")).upper()
            if intent not in INTENT_LABELS:
                intent = "CARRY"
            confidence = float(item.get("confidence", 0.5))
            rationale = str(item.get("rationale", ""))
            results.append((intent, max(0.0, min(1.0, confidence)), rationale))

        # Pad if model returned fewer entries.
        while len(results) < len(shot_descriptions):
            results.append(("CARRY", 0.0, "model returned fewer entries"))
        return results[: len(shot_descriptions)]
    except Exception as e:
        logger.warning("gemma_intent_failed", error=str(e))
        return [("CARRY", 0.0, "llm failed") for _ in shot_descriptions]


def extract_reference_intent_profile(
    video_path: str,
    shot_boundaries: Optional[List[ShotBoundary]] = None,
    style_analysis: Optional[StyleAnalysis] = None,
    music_event_grid: Optional[MusicEventGrid] = None,
    cache_root: Optional[Path] = None,
    llm_client: Optional[LLMClient] = None,
    max_shots: int = 40,
) -> ReferenceIntentProfile:
    """Extract an intent pattern profile from a reference video.

    Caches results in ``cache_root`` (defaults to ``E:\ai-video-editor-storage\reference_intent``).
    """
    if cache_root is None:
        cache_root = Path(os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage")) / "reference_intent"

    cached = _load_cached_profile(video_path, cache_root)
    if cached is not None:
        return cached

    if shot_boundaries:
        shots = [(s.start_s, s.end_s) for s in shot_boundaries]
    else:
        shots = detect_shot_boundaries(video_path)

    if not shots:
        logger.warning("no_shots_detected", video_path=video_path)
        return ReferenceIntentProfile(reasoning="shot detection failed")

    if len(shots) > max_shots:
        step = len(shots) / max_shots
        shots = [shots[int(i * step)] for i in range(max_shots)]

    shot_descriptions: List[str] = []
    prev_duration: Optional[float] = None
    for i, (start_s, end_s) in enumerate(shots):
        duration_s = end_s - start_s
        boundary = shot_boundaries[i] if shot_boundaries and i < len(shot_boundaries) else None
        audio_context = _audio_context_at(start_s, end_s, music_event_grid)
        desc = _shot_description(i, start_s, end_s, duration_s, boundary, audio_context, prev_duration)
        shot_descriptions.append(desc)
        prev_duration = duration_s

    intent_results = _classify_intents_with_llm(shot_descriptions, style_analysis, llm_client)

    shot_intents: List[ShotIntent] = []
    for (start_s, end_s), (intent, confidence, rationale) in zip(shots, intent_results):
        shot_intents.append(
            ShotIntent(
                start_s=start_s,
                end_s=end_s,
                intent=intent,
                confidence=confidence,
                rationale=rationale,
            )
        )

    durations = [s.end_s - s.start_s for s in shot_intents]
    avg_dur = sum(durations) / len(durations) if durations else 0.0
    std_dur = float(np.std(durations)) if (durations and len(durations) > 1 and np is not None) else 0.0
    total_s = sum(durations)
    cut_density = (len(shot_intents) / max(total_s, 1.0)) * 60.0

    hist: Dict[str, float] = {label: 0.0 for label in INTENT_LABELS}
    for si in shot_intents:
        hist[si.intent] += 1.0
    total = sum(hist.values()) or 1.0
    hist = {k: v / total for k, v in hist.items()}

    trajectory = [(si.intent, si.start_s, si.end_s) for si in shot_intents]

    top3 = sorted(hist.items(), key=lambda x: x[1], reverse=True)[:3]
    reasoning = (
        f"Reference editor favors {top3[0][0]} ({top3[0][1]:.0%}), followed by "
        f"{', '.join(f'{i} ({p:.0%})' for i, p in top3[1:])}. "
        f"Average shot length {avg_dur:.1f}s, density {cut_density:.1f} cuts/min."
    )

    profile = ReferenceIntentProfile(
        shot_intents=shot_intents,
        intent_histogram=hist,
        intent_trajectory=trajectory,
        avg_shot_duration_s=avg_dur,
        std_shot_duration_s=std_dur,
        cut_density_per_min=cut_density,
        reasoning=reasoning,
    )
    _save_cached_profile(profile, video_path, cache_root)
    return profile
