# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Save-the-Cat beat-sheet assembler.

Maps a continuous video duration to Blake Snyder's 15-beat story structure and
assigns each cut-list slot a story beat + a corresponding audio section. The
trailer-style path uses real signal-driven beat anchors from
``snyder_detect.detect_snyder_beats``; speech-coherent mode uses a topic-based
thirds assembler; ``off`` leaves the cutlist untouched.
"""

from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from shared_py.feature_tracer import FeatureTracer
from shared_py.models import CutList, Slot

from reason_worker.snyder_detect import (
    BeatName,
    DetectedBeat,
    assign_slot_beat,
    detect_snyder_beats,
)


NarrativeMode = Literal["speech_coherent", "trailer_style", "off"]


# Multipliers applied to a slot's energy/motion/density hints when a beat is
# detected. Values > 1.0 boost the hint, values < 1.0 dampen it. These are
# intentionally conservative so the underlying energy curve remains dominant.
SNYDER_BEAT_PROFILES: Dict[BeatName, Dict[str, float]] = {
    "opening_image": {"energy": 0.7, "motion": 0.6, "density": 0.5},
    "theme_stated": {"energy": 0.8, "motion": 0.7, "density": 0.6},
    "setup": {"energy": 0.75, "motion": 0.6, "density": 0.6},
    "catalyst": {"energy": 1.1, "motion": 1.0, "density": 0.9},
    "debate": {"energy": 0.85, "motion": 0.75, "density": 0.8},
    "break_into_two": {"energy": 1.0, "motion": 1.0, "density": 1.0},
    "b_story": {"energy": 0.9, "motion": 0.85, "density": 0.85},
    "fun_and_games": {"energy": 1.15, "motion": 1.1, "density": 1.1},
    "midpoint": {"energy": 1.2, "motion": 1.15, "density": 1.05},
    "bad_guys_close_in": {"energy": 1.1, "motion": 1.1, "density": 1.05},
    "all_is_lost": {"energy": 0.6, "motion": 0.5, "density": 0.7},
    "dark_night": {"energy": 0.5, "motion": 0.4, "density": 0.6},
    "break_into_three": {"energy": 1.05, "motion": 1.0, "density": 1.0},
    "finale": {"energy": 1.25, "motion": 1.2, "density": 1.1},
    "final_image": {"energy": 0.7, "motion": 0.5, "density": 0.4},
}


def _percentage_beats(total_duration: float) -> List[DetectedBeat]:
    """Return pure percentage-anchor beats for backward compatibility."""
    return detect_snyder_beats(total_duration_s=total_duration)


def _apply_beat_profile(slot: Slot, beat_name: BeatName) -> None:
    """Optionally adjust slot energy/motion hints using the beat profile."""
    profile = SNYDER_BEAT_PROFILES.get(beat_name)
    if profile is None:
        return
    if "energy" in profile and slot.energy_level is not None:
        slot.energy_level = max(0.0, min(1.0, slot.energy_level * profile["energy"]))
    if "motion" in profile:
        # Motion is encoded in the subject hint as a scale factor; we do not
        # overwrite the discrete motion_hint, but we append a soft multiplier
        # so downstream renderers can intensify camera work if they support it.
        slot.subject_hint = f"{slot.subject_hint} motion_scale={profile['motion']:.2f}"


def _trailer_style_assembler(
    cutlist: CutList,
    total_duration: float,
    beats: Optional[Sequence[DetectedBeat]],
) -> CutList:
    """Assign each slot its nearest Save-the-Cat beat and section."""
    if beats is None:
        beats = _percentage_beats(total_duration)

    for slot in cutlist.slots:
        beat_name, section = assign_slot_beat(slot.start_s, total_duration, beats)
        slot.story_beat = beat_name
        slot.section = section
        _apply_beat_profile(slot, beat_name)

    return cutlist


def _speech_coherent_assembler(cutlist: CutList, total_duration: float) -> CutList:
    """Group slots by thirds and label intro/body/climax/outro."""
    if total_duration <= 0 or not cutlist.slots:
        return cutlist

    slots = sorted(cutlist.slots, key=lambda s: s.start_s)
    n = len(slots)
    # Divide into four narrative blocks.
    intro_end = max(1, n // 4)
    body_end = max(intro_end + 1, n // 2)
    climax_end = max(body_end + 1, 3 * n // 4)

    labels: List[Tuple[str, str]] = []
    for i, slot in enumerate(slots):
        if i < intro_end:
            labels.append(("intro", "intro"))
        elif i < body_end:
            labels.append(("body", "verse"))
        elif i < climax_end:
            labels.append(("climax", "chorus"))
        else:
            labels.append(("outro", "outro"))

    for slot, (beat, section) in zip(slots, labels):
        slot.story_beat = beat
        slot.section = section

    return cutlist


def apply_save_the_cat_beats(
    cutlist: CutList,
    total_duration: float,
    beats: Optional[Sequence[DetectedBeat]] = None,
    mode: NarrativeMode = "trailer_style",
    song_audio: Any = None,
    sr: int = 22050,
    motion_curve: Any = None,
    dialogue_segments: Optional[Sequence[Any]] = None,
    chord_seq: Optional[Sequence[Any]] = None,
) -> CutList:
    """Apply a Save-the-Cat narrative structure to ``cutlist``.

    Parameters
    ----------
    cutlist:
        The generated cutlist whose slots will be annotated.
    total_duration:
        Total duration of the rendered output in seconds.
    beats:
        Pre-computed Snyder beat anchors. If ``None`` and ``mode`` is
        ``"trailer_style"``, beats are detected from the supplied signals
        (falling back to percentage anchors when signals are absent).
    mode:
        ``"trailer_style"`` maps slots to the 15 Save-the-Cat beats,
        ``"speech_coherent"`` groups slots into intro/body/climax/outro, and
        ``"off"`` returns ``cutlist`` unchanged.
    song_audio, sr, motion_curve, dialogue_segments, chord_seq:
        Optional signals for real beat detection in trailer style.

    Returns
    -------
    The same ``CutList`` instance with ``story_beat`` and ``section`` updated on
    every slot.
    """
    gated_in = mode != "off"
    with FeatureTracer("save_the_cat", gated_in=gated_in) as ft:
        if total_duration <= 0 or not cutlist.slots:
            ft.fallback("empty_cutlist")
            return cutlist

        if mode == "off":
            ft.fallback("mode_off")
            return cutlist

        if mode == "speech_coherent":
            result = _speech_coherent_assembler(cutlist, total_duration)
            ft.signature(f"mode=speech_coherent,slots={len(result.slots)}")
            ft.real()
            return result

        # trailer_style
        if beats is None:
            beats = detect_snyder_beats(
                song_audio=song_audio,
                sr=sr,
                motion_curve=motion_curve,
                dialogue_segments=dialogue_segments,
                chord_seq=chord_seq,
                total_duration_s=total_duration,
            )
        result = _trailer_style_assembler(cutlist, total_duration, beats)
        beat_names = {slot.story_beat for slot in result.slots if slot.story_beat}
        ft.signature(f"mode=trailer_style,beats={len(beat_names)},slots={len(result.slots)}")
        ft.real()
        return result
