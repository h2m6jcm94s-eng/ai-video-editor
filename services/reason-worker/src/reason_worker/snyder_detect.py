# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Real Save-the-Cat beat detection from audio, motion and dialogue signals.

``detect_snyder_beats`` returns anchor times for Blake Snyder's 15 story beats.
When real signals are missing it falls back to the canonical percentage anchors,
so the assembler can still label slots even for sparse inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Literal, Optional, Sequence, Tuple

import numpy as np

# Optional signal-processing libraries. We import them lazily and degrade to
# percentage anchors when they are unavailable.
try:
    from scipy.signal import find_peaks
except Exception:  # pragma: no cover - optional dependency
    find_peaks = None  # type: ignore[assignment,misc]

try:
    import librosa
except Exception:  # pragma: no cover - optional dependency
    librosa = None  # type: ignore[assignment]

try:
    import autochord
except Exception:  # pragma: no cover - optional dependency
    autochord = None  # type: ignore[assignment]


BeatName = Literal[
    "opening_image",
    "theme_stated",
    "setup",
    "catalyst",
    "debate",
    "break_into_two",
    "b_story",
    "fun_and_games",
    "midpoint",
    "bad_guys_close_in",
    "all_is_lost",
    "dark_night",
    "break_into_three",
    "finale",
    "final_image",
]


# Canonical Snyder percentage anchors.
SNYDER_PERCENTAGE_ANCHORS: dict[BeatName, float] = {
    "opening_image": 0.00,
    "theme_stated": 0.05,
    "setup": 0.045,
    "catalyst": 0.10,
    "debate": 0.15,
    "break_into_two": 0.20,
    "b_story": 0.225,
    "fun_and_games": 0.36,
    "midpoint": 0.50,
    "bad_guys_close_in": 0.63,
    "all_is_lost": 0.75,
    "dark_night": 0.775,
    "break_into_three": 0.80,
    "finale": 0.90,
    "final_image": 0.995,
}


@dataclass(frozen=True)
class DetectedBeat:
    """A single Save-the-Cat story-beat anchor."""

    name: BeatName
    t: float
    confidence: float


@dataclass(frozen=True)
class _DialogueSegment:
    start: float
    end: float
    text: str = ""


def _parse_dialogue_segments(
    dialogue_segments: Optional[Sequence[Any]],
) -> List[_DialogueSegment]:
    """Normalize dialogue segments from dict/list/tuple inputs."""
    segments: List[_DialogueSegment] = []
    if dialogue_segments is None:
        return segments
    for seg in dialogue_segments:
        if seg is None:
            continue
        if isinstance(seg, _DialogueSegment):
            segments.append(seg)
        elif isinstance(seg, (list, tuple)) and len(seg) >= 2:
            start, end = float(seg[0]), float(seg[1])
            text = str(seg[2]) if len(seg) > 2 else ""
            segments.append(_DialogueSegment(start=start, end=end, text=text))
        elif isinstance(seg, dict):
            start = float(seg.get("start", seg.get("start_s", 0.0)))
            end = float(seg.get("end", seg.get("end_s", 0.0)))
            text = str(seg.get("text", ""))
            segments.append(_DialogueSegment(start=start, end=end, text=text))
    return sorted(segments, key=lambda s: s.start)


def _to_numpy(audio: Any) -> Optional[np.ndarray]:
    """Normalize an audio object to a 1-D numpy float array."""
    if audio is None:
        return None
    if isinstance(audio, np.ndarray):
        arr = audio
    elif isinstance(audio, (list, tuple)):
        arr = np.asarray(audio, dtype=float)
    else:
        return None
    if arr.size == 0:
        return None
    if arr.ndim > 1:
        # Mix down multi-channel audio.
        arr = arr.mean(axis=tuple(range(1, arr.ndim)))
    return np.asarray(arr, dtype=float).ravel()


def _rms_curve(audio: np.ndarray, sr: int, hop_ms: float = 100.0) -> Tuple[np.ndarray, float]:
    """Return a simple per-frame RMS energy curve and its hop length in seconds."""
    hop = max(1, int(sr * hop_ms / 1000.0))
    frames = []
    for i in range(0, len(audio) - hop + 1, hop):
        frame = audio[i : i + hop]
        val = float(np.sqrt(np.mean(frame * frame))) if len(frame) else 0.0
        frames.append(val)
    if not frames:
        return np.zeros(1), hop / sr
    return np.asarray(frames, dtype=float), hop / sr


def _local_peak(
    curve: np.ndarray,
    t_min: float,
    t_max: float,
    time_step: float,
    total_duration: float,
    prefer: Literal["max", "min"] = "max",
) -> Optional[float]:
    """Return the time of a local extremum in ``[t_min, t_max]``."""
    if total_duration <= 0 or curve.size == 0:
        return None
    i_min = max(0, int(t_min / time_step))
    i_max = min(len(curve), int(math.ceil(t_max / time_step)) + 1)
    if i_min >= i_max:
        return None
    window = curve[i_min:i_max]
    if prefer == "max":
        idx = int(np.argmax(window))
    else:
        idx = int(np.argmin(window))
    return (i_min + idx) * time_step


def _nearest_downbeat(
    target: float,
    beats: Sequence[float],
    tolerance: float = float("inf"),
) -> Optional[float]:
    """Return the nearest beat time to ``target`` within ``tolerance``."""
    if not beats:
        return None
    best = min(beats, key=lambda b: abs(b - target))
    if abs(best - target) <= tolerance:
        return best
    return None


def _detect_chord_changes(
    chord_seq: Optional[Sequence[Any]], total_duration: float
) -> List[Tuple[float, float]]:
    """Extract chord change times from a chord sequence.

    ``chord_seq`` is expected to be an iterable of ``(start, end, label)`` tuples
    or dictionaries with ``start``/``end``/``label`` keys.
    """
    changes: List[Tuple[float, float]] = []
    if chord_seq is None or total_duration <= 0:
        return changes
    prev: Optional[str] = None
    for item in chord_seq:
        if item is None:
            continue
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            start, end, label = float(item[0]), float(item[1]), str(item[2])
        elif isinstance(item, dict):
            start = float(item.get("start", item.get("start_s", 0.0)))
            end = float(item.get("end", item.get("end_s", 0.0)))
            label = str(item.get("label", item.get("chord", "N")))
        else:
            continue
        if prev is not None and label != prev:
            changes.append((start, end))
        prev = label
    return changes


def _detect_downbeats_from_audio(
    audio: np.ndarray, sr: int, total_duration: float
) -> List[float]:
    """Return a list of estimated downbeat times from audio.

    Uses librosa when available, otherwise returns an empty list.
    """
    if librosa is None:
        return []
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        # Estimate downbeats as every 4th beat, anchored to the strongest onset.
        if len(beat_times) < 4:
            return list(beat_times)
        # Find the beat with the highest onset strength in the first 4 beats.
        onset_env = librosa.onset.onset_strength(y=audio, sr=sr)
        onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)
        best_idx = 0
        best_val = -1.0
        for i in range(min(4, len(beat_times))):
            t = beat_times[i]
            idx = np.searchsorted(onset_times, t)
            if idx < len(onset_env) and onset_env[idx] > best_val:
                best_val = onset_env[idx]
                best_idx = i
        downbeats = [b for i, b in enumerate(beat_times) if (i - best_idx) % 4 == 0]
        return [float(b) for b in downbeats if 0 <= b <= total_duration]
    except Exception:
        return []


def _detect_energy_rises(
    rms: np.ndarray, time_step: float, total_duration: float
) -> List[Tuple[float, float]]:
    """Return times where RMS energy rises sharply.

    Returns a list of ``(time, rise_magnitude)`` tuples, sorted by magnitude.
    """
    if rms.size < 2:
        return []
    # Smooth lightly.
    kernel = np.ones(3) / 3.0
    smoothed = np.convolve(rms, kernel, mode="same")
    diff = np.diff(smoothed)
    peaks: List[Tuple[float, float]] = []
    if find_peaks is not None:
        height = max(float(np.mean(diff) + 0.5 * np.std(diff)), 1e-9)
        idxs, _ = find_peaks(diff, height=height)
        for idx in idxs:
            t = (idx + 1) * time_step
            if 0 <= t <= total_duration:
                peaks.append((t, float(diff[idx])))
    else:
        # Simple local-max detector.
        for i in range(1, len(diff) - 1):
            if diff[i] > diff[i - 1] and diff[i] > diff[i + 1] and diff[i] > 0:
                t = (i + 1) * time_step
                if 0 <= t <= total_duration:
                    peaks.append((t, float(diff[i])))
    peaks.sort(key=lambda x: x[1], reverse=True)
    return peaks


def _motion_curve_array(motion_curve: Any, total_duration: float) -> np.ndarray:
    """Normalize a motion curve to a 1-D numpy array of at least two samples."""
    arr = _to_numpy(motion_curve)
    if arr is None or arr.size == 0:
        return np.zeros(max(2, int(total_duration * 10)))
    return arr


def detect_snyder_beats(
    song_audio: Any = None,
    sr: int = 22050,
    motion_curve: Any = None,
    dialogue_segments: Optional[Sequence[Any]] = None,
    chord_seq: Optional[Sequence[Any]] = None,
    total_duration_s: float = 0.0,
) -> List[DetectedBeat]:
    """Detect Save-the-Cat beat anchors from available signals.

    Parameters
    ----------
    song_audio:
        Raw audio waveform as a numpy array, list, or similar 1-D sequence.
    sr:
        Sample rate of ``song_audio``.
    motion_curve:
        Per-frame or per-beat motion magnitude as a numpy array or list.
    dialogue_segments:
        Iterable of ``(start, end, text)`` tuples or dicts describing speech.
    chord_seq:
        Iterable of ``(start, end, chord_label)`` tuples or dicts. If missing,
        ``break_into_three`` falls back to its percentage anchor.
    total_duration_s:
        Total duration of the output edit in seconds.

    Returns
    -------
    List of ``DetectedBeat`` objects, one for each of the 15 Save-the-Cat beats.
    Confidence is ``1.0`` when real signals drive the estimate and decreases as
    more fallbacks are used.
    """
    if total_duration_s <= 0:
        return [
            DetectedBeat(name=name, t=0.0, confidence=0.0)
            for name in SNYDER_PERCENTAGE_ANCHORS
        ]

    audio = _to_numpy(song_audio)
    motion = _motion_curve_array(motion_curve, total_duration_s)
    dialogue = _parse_dialogue_segments(dialogue_segments)
    chord_changes = _detect_chord_changes(chord_seq, total_duration_s)
    downbeats: List[float] = []
    rms = np.zeros(1)
    time_step = 1.0
    energy_rises: List[Tuple[float, float]] = []

    if audio is not None and audio.size > 0:
        rms, time_step = _rms_curve(audio, sr)
        downbeats = _detect_downbeats_from_audio(audio, sr, total_duration_s)
        energy_rises = _detect_energy_rises(rms, time_step, total_duration_s)

    def pct(anchor: float) -> float:
        return anchor * total_duration_s

    def anchor(
        name: BeatName,
        target: float,
        real: Optional[float],
        confidence: float,
        window: float = 0.05,
    ) -> DetectedBeat:
        """Pick a real estimate within ``window`` of ``target`` or the fallback."""
        if real is not None and abs(real - target) <= window * total_duration_s:
            return DetectedBeat(name=name, t=max(0.0, min(total_duration_s, real)), confidence=confidence)
        return DetectedBeat(name=name, t=max(0.0, min(total_duration_s, target)), confidence=max(0.0, confidence - 0.4))

    def first_dialogue_after(t: float) -> Optional[float]:
        for seg in dialogue:
            if seg.start >= t:
                return seg.start
        return None

    def last_dialogue_before(t: float) -> Optional[float]:
        best: Optional[float] = None
        for seg in dialogue:
            if seg.end <= t:
                best = seg.end
        return best

    def nearest_chord_change(target: float, window: float = 0.05) -> Optional[float]:
        for start, end in chord_changes:
            if abs(start - target) <= window * total_duration_s:
                return start
        return None

    def nearest_downbeat(target: float, window: float = 0.03) -> Optional[float]:
        return _nearest_downbeat(target, downbeats, window * total_duration_s)

    def motion_peak(t_min: float, t_max: float, prefer: Literal["max", "min"] = "max") -> Optional[float]:
        if motion.size == 0:
            return None
        step = total_duration_s / max(1, len(motion) - 1)
        return _local_peak(motion, t_min, t_max, step, total_duration_s, prefer=prefer)

    def energy_peak(t_min: float, t_max: float, prefer: Literal["max", "min"] = "max") -> Optional[float]:
        if rms.size == 0:
            return None
        return _local_peak(rms, t_min, t_max, time_step, total_duration_s, prefer=prefer)

    # --- Detect individual beats --------------------------------------------

    # 1. Opening Image: first real beat or silence break at the start.
    opening_target = pct(SNYDER_PERCENTAGE_ANCHORS["opening_image"])
    opening = opening_target
    opening_conf = 0.6
    if audio is not None and rms.size > 1:
        # Find first frame with energy above threshold.
        threshold = float(np.max(rms)) * 0.1 + float(np.mean(rms)) * 0.1
        for i, val in enumerate(rms):
            if val > threshold:
                opening = min(i * time_step, total_duration_s)
                opening_conf = 1.0
                break
    beat_opening = DetectedBeat(name="opening_image", t=opening, confidence=opening_conf)

    # 2. Theme Stated: first dialogue line or canonical 5%.
    theme_target = pct(SNYDER_PERCENTAGE_ANCHORS["theme_stated"])
    theme = first_dialogue_after(0.0)
    theme_conf = 1.0 if theme is not None else 0.6
    beat_theme = anchor("theme_stated", theme_target, theme, theme_conf)

    # 3. Set-Up: spans opening to catalyst; pick its center.
    setup_target = pct(SNYDER_PERCENTAGE_ANCHORS["setup"])
    beat_setup = DetectedBeat(name="setup", t=setup_target, confidence=0.6)

    # 4. Catalyst: first big energy rise in the first act.
    catalyst_target = pct(SNYDER_PERCENTAGE_ANCHORS["catalyst"])
    catalyst: Optional[float] = None
    catalyst_conf = 0.6
    for t, _ in energy_rises:
        if 0.02 * total_duration_s <= t <= 0.18 * total_duration_s:
            catalyst = t
            catalyst_conf = 1.0
            break
    if catalyst is None:
        catalyst = first_dialogue_after(catalyst_target - 0.05 * total_duration_s)
        if catalyst is not None:
            catalyst_conf = 0.8
    beat_catalyst = anchor("catalyst", catalyst_target, catalyst, catalyst_conf)

    # 5. Debate: dialogue following catalyst.
    debate_target = pct(SNYDER_PERCENTAGE_ANCHORS["debate"])
    debate = first_dialogue_after(max(beat_catalyst.t, debate_target - 0.05 * total_duration_s))
    debate_conf = 1.0 if debate is not None else 0.6
    beat_debate = anchor("debate", debate_target, debate, debate_conf)

    # 6. Break into Two: downbeat near 20%.
    break2_target = pct(SNYDER_PERCENTAGE_ANCHORS["break_into_two"])
    break2 = nearest_downbeat(break2_target)
    beat_break2 = anchor("break_into_two", break2_target, break2, 1.0 if break2 is not None else 0.6)

    # 7. B Story: chord change or dialogue near 22.5%.
    bstory_target = pct(SNYDER_PERCENTAGE_ANCHORS["b_story"])
    bstory = nearest_chord_change(bstory_target) or first_dialogue_after(bstory_target - 0.03 * total_duration_s)
    beat_bstory = anchor("b_story", bstory_target, bstory, 1.0 if bstory is not None else 0.6)

    # 8. Fun and Games: high-energy / high-motion region in act 2A.
    fun_target = pct(SNYDER_PERCENTAGE_ANCHORS["fun_and_games"])
    fun = motion_peak(0.24 * total_duration_s, 0.49 * total_duration_s, prefer="max")
    if fun is None:
        fun = energy_peak(0.24 * total_duration_s, 0.49 * total_duration_s, prefer="max")
    beat_fun = anchor("fun_and_games", fun_target, fun, 1.0 if fun is not None else 0.6)

    # 9. Midpoint: downbeat or energy peak near 50%.
    midpoint_target = pct(SNYDER_PERCENTAGE_ANCHORS["midpoint"])
    midpoint = nearest_downbeat(midpoint_target) or energy_peak(
        0.45 * total_duration_s, 0.55 * total_duration_s, prefer="max"
    )
    beat_midpoint = anchor("midpoint", midpoint_target, midpoint, 1.0 if midpoint is not None else 0.6)

    # 10. Bad Guys Close In: high-energy span in act 2B.
    bgci_target = pct(SNYDER_PERCENTAGE_ANCHORS["bad_guys_close_in"])
    bgci = motion_peak(0.51 * total_duration_s, 0.74 * total_duration_s, prefer="max")
    if bgci is None:
        bgci = energy_peak(0.51 * total_duration_s, 0.74 * total_duration_s, prefer="max")
    beat_bgci = anchor("bad_guys_close_in", bgci_target, bgci, 1.0 if bgci is not None else 0.6)

    # 11. All Is Lost: energy dip near 75%.
    ail_target = pct(SNYDER_PERCENTAGE_ANCHORS["all_is_lost"])
    ail = energy_peak(0.72 * total_duration_s, 0.78 * total_duration_s, prefer="min")
    beat_ail = anchor("all_is_lost", ail_target, ail, 1.0 if ail is not None else 0.6)

    # 12. Dark Night of the Soul: low energy after All Is Lost.
    dark_target = pct(SNYDER_PERCENTAGE_ANCHORS["dark_night"])
    dark = energy_peak(0.75 * total_duration_s, 0.80 * total_duration_s, prefer="min")
    beat_dark = anchor("dark_night", dark_target, dark, 1.0 if dark is not None else 0.6)

    # 13. Break into Three: chord change near 80%, fallback to position %.
    break3_target = pct(SNYDER_PERCENTAGE_ANCHORS["break_into_three"])
    break3 = nearest_chord_change(break3_target, window=0.08)
    if break3 is None and chord_changes:
        # Pick the first chord change after 75% if none is near 80%.
        for start, _ in chord_changes:
            if start >= 0.75 * total_duration_s:
                break3 = start
                break
    beat_break3 = anchor("break_into_three", break3_target, break3, 1.0 if break3 is not None else 0.6)

    # 14. Finale: highest energy / motion in the last act.
    finale_target = pct(SNYDER_PERCENTAGE_ANCHORS["finale"])
    finale = motion_peak(0.81 * total_duration_s, 0.99 * total_duration_s, prefer="max")
    if finale is None:
        finale = energy_peak(0.81 * total_duration_s, 0.99 * total_duration_s, prefer="max")
    beat_finale = anchor("finale", finale_target, finale, 1.0 if finale is not None else 0.6)

    # 15. Final Image: last audible moment or final downbeat.
    final_target = pct(SNYDER_PERCENTAGE_ANCHORS["final_image"])
    final_image: Optional[float] = None
    final_conf = 0.6
    if audio is not None and rms.size > 1:
        threshold = float(np.max(rms)) * 0.05 + float(np.mean(rms)) * 0.05
        for i in range(len(rms) - 1, -1, -1):
            if rms[i] > threshold:
                final_image = min(i * time_step, total_duration_s)
                final_conf = 1.0
                break
    if final_image is None:
        final_image = last_dialogue_before(total_duration_s)
        if final_image is not None:
            final_conf = 0.8
    beat_final = anchor("final_image", final_target, final_image, final_conf)

    return [
        beat_opening,
        beat_theme,
        beat_setup,
        beat_catalyst,
        beat_debate,
        beat_break2,
        beat_bstory,
        beat_fun,
        beat_midpoint,
        beat_bgci,
        beat_ail,
        beat_dark,
        beat_break3,
        beat_finale,
        beat_final,
    ]


def _beat_section(name: BeatName) -> str:
    """Map a Save-the-Cat beat to a canonical audio section label."""
    section_map: dict[BeatName, str] = {
        "opening_image": "intro",
        "theme_stated": "intro",
        "setup": "intro",
        "catalyst": "verse",
        "debate": "verse",
        "break_into_two": "verse",
        "b_story": "chorus",
        "fun_and_games": "chorus",
        "midpoint": "chorus",
        "bad_guys_close_in": "drop",
        "all_is_lost": "drop",
        "dark_night": "drop",
        "break_into_three": "outro",
        "finale": "outro",
        "final_image": "outro",
    }
    return section_map.get(name, "verse")


def assign_slot_beat(
    slot_start: float,
    total_duration: float,
    beats: Optional[Sequence[DetectedBeat]] = None,
) -> Tuple[str, str]:
    """Return the (story_beat, section) for a slot based on nearest beat anchor.

    This helper is exposed so other modules can test beat assignment without
    building a full ``CutList``.
    """
    if total_duration <= 0 or not beats:
        return "Finale", "outro"

    ratio = max(0.0, min(1.0, slot_start / total_duration))
    beat_list = list(beats)
    # Nearest-neighbor in time; tie-break toward earlier beats.
    best = min(
        beat_list,
        key=lambda b: (abs(b.t / total_duration - ratio), b.t),
    )
    return best.name, _beat_section(best.name)
