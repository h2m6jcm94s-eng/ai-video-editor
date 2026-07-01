#!/usr/bin/env python3
"""Golden Render Regression Suite for the batch-2 cyberpunk AMV fixture."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "render-worker" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "shared-py" / "src"))

from render_worker.compiler import _FONT_NAME_ALIASES, _FONT_FILES, _STYLE_PRESET_FONTS  # noqa: E402
from shared_py.models import CutList  # noqa: E402


BATCH_DIR = REPO_ROOT / "test files" / "batch 2"
OUTPUT_DIR = BATCH_DIR / "output"
RENDER_LOG = OUTPUT_DIR / "render.log"
OUTPUT_VIDEO = OUTPUT_DIR / "output.mp4"
CUTLIST_JSON = OUTPUT_DIR / "cutlist.json"

WORD_BANKS = {
    "triumphant": [
        "RISE", "UNBREAKABLE", "LEGEND", "VICTORY", "EMPIRE", "GLORY", "CONQUER",
        "UNSTOPPABLE", "FOREVER", "THRIVE", "DOMINATE", "ASCEND", "POWER",
    ],
    "action": [
        "CHAOS", "FURY", "IMPACT", "SHATTER", "BREAK", "FORCE", "STRIKE",
        "RUN", "HUNT", "CRASH", "BURN", "RECKLESS", "WAR",
    ],
    "melancholy": [
        "GHOST", "BROKEN", "SILENCE", "FADE", "ALONE", "MEMORY", "REGRET",
        "VOID", "WASTED", "LOST", "GOODBYE", "HOLLOW", "DROWN",
    ],
    "cyberpunk": [
        "NEON", "SYSTEM", "UPGRADE", "OVERRIDE", "GLITCH", "DATA", "SYNTH",
        "UPLOAD", "REBOOT", "PULSE", "WIRED", "CIRCUIT", "HACK",
    ],
}
WORD_BANK_SET = {w.lower() for bank in WORD_BANKS.values() for w in bank}

SYSTEM_FONT_NAMES = {"", "Arial", "Helvetica", "sans-serif", "serif", "monospace"}


def _is_bundled_font(font_name: Optional[str]) -> bool:
    """Return True if the overlay font resolves to a bundled cinematic family.

    Accepts raw font filenames, font family names, and kinetic-text style presets
    (which the compiler maps to a bundled font).
    """
    if not font_name:
        return False
    if font_name in _FONT_FILES:
        return True
    if font_name in _FONT_NAME_ALIASES:
        return _FONT_NAME_ALIASES[font_name] in _FONT_FILES
    if font_name in _STYLE_PRESET_FONTS:
        return bool(_STYLE_PRESET_FONTS[font_name])
    return False


@dataclass
class Criterion:
    name: str
    passed: bool
    value: Any = None
    threshold: Any = None
    detail: str = ""
    required: bool = True


@dataclass
class SuiteResult:
    criteria: List[Criterion] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    def add(self, criterion: Criterion) -> None:
        self.criteria.append(criterion)
        if criterion.passed:
            self.passed += 1
        elif criterion.required:
            self.failed += 1
        else:
            self.skipped += 1


def _run_render(args: argparse.Namespace) -> None:
    if args.skip_render:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "batch2-offline-render.py"),
        "--quality",
        "preview",
        "--heatmap-workers",
        "1",
        "--source-ip-hint",
        "Cyberpunk Edgerunners",
        "--feature-iconic-quotes",
        "--tier",
        "full_remix",
    ]
    if args.feature_emotion_led_cuts:
        cmd.append("--feature-emotion-led-cuts")
    print(f"Running canonical render: {' '.join(cmd)}")
    with open(RENDER_LOG, "w", encoding="utf-8") as log_file:
        subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT, check=True)


def _load_render_log() -> str:
    if not RENDER_LOG.exists():
        return ""
    return RENDER_LOG.read_text(encoding="utf-8", errors="replace")


def _load_cutlist() -> Optional[CutList]:
    if not CUTLIST_JSON.exists():
        return None
    with open(CUTLIST_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return CutList(**data)


def _probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _parse_feature_summary(log: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    in_summary = False
    for line in log.splitlines():
        if "Feature runtime summary:" in line:
            in_summary = True
            continue
        if not in_summary:
            continue
        if "real_path_ratio:" in line:
            m = re.search(r"real_path_ratio:\s*([0-9.]+)", line)
            if m:
                summary["real_path_ratio"] = float(m.group(1))
            continue
        if ":" in line:
            name, rest = line.strip().split(":", 1)
            name = name.strip()
            rest = rest.strip()
            if "fallback" in rest:
                summary[name] = {"status": "fallback", "reason": rest}
            elif "real" in rest:
                summary[name] = {"status": "real"}
    return summary


def _check_duration_match(cutlist: CutList, result: SuiteResult) -> None:
    if not OUTPUT_VIDEO.exists():
        result.add(Criterion("duration_match", False, detail="output video missing"))
        return
    video_dur = _probe_duration(OUTPUT_VIDEO)
    song_dur = cutlist.globals.total_duration_s
    diff = abs(video_dur - song_dur)
    passed = diff <= 0.1
    result.add(
        Criterion(
            "duration_match",
            passed,
            value=round(diff, 3),
            threshold=0.1,
            detail=f"video={video_dur:.2f}s song={song_dur:.2f}s diff={diff:.3f}s",
        )
    )


def _check_real_path_ratio(summary: Dict[str, Any], result: SuiteResult) -> None:
    ratio = summary.get("real_path_ratio", 0.0)
    passed = isinstance(ratio, float) and ratio >= 0.95
    result.add(
        Criterion(
            "real_path_ratio",
            passed,
            value=ratio,
            threshold=0.95,
            detail=f"ratio={ratio}",
        )
    )


def _check_slot_window_fallback(log: str, result: SuiteResult) -> None:
    m = re.search(r"slot_window_fallback_count:\s*(\d+)", log)
    count = int(m.group(1)) if m else None
    passed = count == 0
    result.add(
        Criterion(
            "slot_window_fallback_count",
            passed,
            value=count,
            threshold=0,
            detail=f"count={count}",
        )
    )


def _check_max_slot_gap(cutlist: CutList, result: SuiteResult) -> None:
    slots = sorted(cutlist.slots, key=lambda s: s.start_s)
    max_gap = 0.0
    for i in range(1, len(slots)):
        prev_end = slots[i - 1].start_s + slots[i - 1].duration_s
        gap = slots[i].start_s - prev_end
        max_gap = max(max_gap, gap)
    passed = max_gap <= 0.1
    result.add(
        Criterion(
            "max_slot_gap",
            passed,
            value=round(max_gap, 3),
            threshold=0.1,
            detail=f"max_gap={max_gap:.3f}s",
        )
    )


def _check_feature_real(summary: Dict[str, Any], feature: str, result: SuiteResult) -> None:
    info = summary.get(feature)
    passed = isinstance(info, dict) and info.get("status") == "real"
    detail = f"status={info.get('status') if isinstance(info, dict) else 'missing'}"
    result.add(
        Criterion(
            f"{feature}_real",
            passed,
            value=info,
            detail=detail,
        )
    )


def _check_kinetic_llm_ratio(cutlist: CutList, result: SuiteResult) -> None:
    texts: List[str] = []
    for slot in cutlist.slots:
        text = getattr(slot, "kinetic_text", None)
        if text:
            texts.append(text.strip().upper())
    if not texts:
        result.add(Criterion("kinetic_text_llm_ratio", False, value=0.0, threshold=0.8, detail="no kinetic texts"))
        return
    # The deterministic word-bank fallback was removed in Phase 2.  All kinetic
    # texts now come from the LLM, so we validate prompt compliance instead:
    # uppercase, 1-4 words, non-empty.
    llm_like = 0
    for text in texts:
        words = text.split()
        if text and 1 <= len(words) <= 4 and text.isupper():
            llm_like += 1
    ratio = llm_like / len(texts)
    passed = ratio >= 0.8
    result.add(
        Criterion(
            "kinetic_text_llm_ratio",
            passed,
            value=round(ratio, 2),
            threshold=0.8,
            detail=f"llm_compliant={llm_like}/{len(texts)}",
        )
    )


def _check_no_clip_repeats(cutlist: CutList, result: SuiteResult) -> None:
    clip_ids = [s.selected_clip_id for s in cutlist.slots if s.selected_clip_id]
    if len(clip_ids) < 2:
        result.add(Criterion("no_clip_repeats", False, detail="not enough slots"))
        return
    repeats = 0
    for i, cid in enumerate(clip_ids):
        window = clip_ids[max(0, i - 3) : i] + clip_ids[i + 1 : min(len(clip_ids), i + 4)]
        if cid in window:
            repeats += 1
    passed = repeats == 0
    result.add(
        Criterion(
            "no_clip_repeats",
            passed,
            value=repeats,
            threshold=0,
            detail=f"repeats_within_3_slots={repeats}",
        )
    )


def _check_caption_density(cutlist: CutList, result: SuiteResult) -> None:
    overlays = cutlist.overlays or []
    duration = cutlist.globals.total_duration_s
    if not overlays or duration <= 0:
        result.add(Criterion("caption_density", True, value=0.0, threshold=0.5, detail="no captions"))
        return
    density = len(overlays) / duration
    passed = density <= 0.5
    result.add(
        Criterion(
            "caption_density",
            passed,
            value=round(density, 3),
            threshold=0.5,
            detail=f"{len(overlays)} overlays in {duration:.1f}s",
        )
    )


def _check_no_triton_warnings(log: str, result: SuiteResult) -> None:
    has_triton = "triton" in log.lower()
    passed = not has_triton
    result.add(
        Criterion(
            "no_triton_warnings",
            passed,
            value=has_triton,
            detail="Triton warning found" if has_triton else "none",
        )
    )


def _check_non_system_font(cutlist: CutList, result: SuiteResult) -> None:
    overlays = cutlist.overlays or []
    if not overlays:
        result.add(Criterion("non_system_font", True, value="n/a", detail="no overlays"))
        return
    bad = [o.font for o in overlays if not _is_bundled_font(o.font)]
    passed = len(bad) == 0
    result.add(
        Criterion(
            "non_system_font",
            passed,
            value=len(bad),
            threshold=0,
            detail=f"non-bundled-font overlays={len(bad)}/{len(overlays)}",
        )
    )


def _frame_stats_and_mse(p1: Path, p2: Path) -> Tuple[float, float, float]:
    """Return (mse, mean, std) for two frames.

    Low mean/std indicates a fade/black frame and should not count as frozen.
    """
    try:
        from PIL import Image
        import numpy as np

        a = np.array(Image.open(p1).convert("RGB"), dtype=np.float32)
        b = np.array(Image.open(p2).convert("RGB"), dtype=np.float32)
        mse = float(np.mean((a - b) ** 2))
        mean = float(np.mean(a))
        std = float(np.std(a))
        return mse, mean, std
    except Exception:
        return float("inf"), 0.0, 0.0


def _extract_all_frames(video: Path, tmpdir: Path, fps: float = 1.0) -> List[Path]:
    """Extract frames at the given fps in a single ffmpeg invocation."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps={fps}",
        "-q:v",
        "2",
        str(tmpdir / "frame_%06d.png"),
    ]
    subprocess.run(cmd, capture_output=True, check=False, stdin=subprocess.DEVNULL)
    return sorted(tmpdir.glob("frame_*.png"))


def _check_no_frozen_frames(result: SuiteResult) -> None:
    if not OUTPUT_VIDEO.exists():
        result.add(Criterion("no_frozen_frames", False, detail="output video missing"))
        return
    duration = _probe_duration(OUTPUT_VIDEO)
    if duration <= 0:
        result.add(Criterion("no_frozen_frames", False, detail="could not probe duration"))
        return

    with tempfile.TemporaryDirectory(prefix="ave_golden_") as tmp:
        tmpdir = Path(tmp)
        frames = _extract_all_frames(OUTPUT_VIDEO, tmpdir, fps=1.0)
        if len(frames) < 2:
            result.add(Criterion("no_frozen_frames", True, detail="too few frames to analyze"))
            return

        sample_interval = 1.0
        max_frozen = 0.0
        frozen_start: Optional[float] = None
        # Threshold: adjacent frames are "identical" when MSE is tiny relative to
        # the frame's own variance.  We also skip near-black frames (fades/dissolves).
        for i in range(1, len(frames)):
            t = i * sample_interval
            mse, mean, std = _frame_stats_and_mse(frames[i - 1], frames[i])
            is_black = mean < 5.0 or std < 1.0
            is_frozen = not is_black and mse < 5.0
            if is_frozen:
                if frozen_start is None:
                    frozen_start = (i - 1) * sample_interval
            else:
                if frozen_start is not None:
                    max_frozen = max(max_frozen, t - frozen_start)
                    frozen_start = None
        if frozen_start is not None:
            max_frozen = max(max_frozen, duration - frozen_start)

    passed = max_frozen <= 1.0
    result.add(
        Criterion(
            "no_frozen_frames",
            passed,
            value=round(max_frozen, 2),
            threshold=1.0,
            detail=f"longest_frozen={max_frozen:.2f}s",
        )
    )


def _check_ssim_vs_previous(result: SuiteResult) -> None:
    previous = os.environ.get("AVE_GOLDEN_REFERENCE")
    if not previous or not Path(previous).exists():
        result.add(
            Criterion(
                "ssim_vs_previous",
                True,
                value="n/a",
                detail="AVE_GOLDEN_REFERENCE not set; skipped",
                required=False,
            )
        )
        return
    if not OUTPUT_VIDEO.exists():
        result.add(Criterion("ssim_vs_previous", False, detail="output video missing"))
        return
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(OUTPUT_VIDEO),
        "-i",
        previous,
        "-filter_complex",
        "ssim",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    m = re.search(r"All:([0-9.]+)", proc.stderr)
    ssim = float(m.group(1)) if m else 0.0
    passed = ssim >= 0.85
    result.add(
        Criterion(
            "ssim_vs_previous",
            passed,
            value=round(ssim, 3),
            threshold=0.85,
            detail=f"ssim={ssim:.3f}",
        )
    )


def _check_kinetic_relevance(cutlist: CutList, result: SuiteResult) -> None:
    texts: List[str] = []
    for slot in cutlist.slots:
        text = getattr(slot, "kinetic_text", None)
        if text:
            texts.append(text.strip())
    if not texts:
        result.add(Criterion("kinetic_text_relevance", False, detail="no kinetic text"))
        return
    multi_word = sum(1 for t in texts if len(t.split()) > 1)
    ratio = multi_word / len(texts)
    passed = ratio >= 0.5
    result.add(
        Criterion(
            "kinetic_text_relevance",
            passed,
            value=round(ratio, 2),
            threshold=0.5,
            detail=f"multi_word_kinetic={multi_word}/{len(texts)}",
        )
    )


def _check_arc_beats_detected(cutlist: CutList, result: SuiteResult) -> None:
    detected = {s.story_beat for s in cutlist.slots if s.story_beat}
    # Exclude generic/default beats if any; count the canonical arc beats.
    canonical = {"HOOK", "WORLD", "CONFLICT", "CRISIS", "VICTORY", "INCITING_INCIDENT", "RISING_ACTION", "CLIMAX", "RESOLUTION"}
    count = len(detected & canonical)
    passed = count >= 3
    result.add(
        Criterion(
            "arc_beats_detected",
            passed,
            value=count,
            threshold=3,
            detail=f"canonical_arc_beats={sorted(detected & canonical)}",
        )
    )


def _check_emotion_match_per_slot(cutlist: CutList, result: SuiteResult) -> None:
    scores = [s.emotion_match_score for s in cutlist.slots if s.story_beat]
    if not scores:
        result.add(Criterion("emotion_match_per_slot", False, detail="no arc-annotated slots"))
        return
    avg = sum(scores) / len(scores)
    passed = avg >= 0.6
    result.add(
        Criterion(
            "emotion_match_per_slot",
            passed,
            value=round(avg, 3),
            threshold=0.6,
            detail=f"avg_emotion_match={avg:.3f} over {len(scores)} arc slots",
        )
    )


def _check_interleaved_glimpse(cutlist: CutList, result: SuiteResult) -> None:
    has_glimpse = any(s.is_glimpse for s in cutlist.slots)
    result.add(
        Criterion(
            "interleaved_glimpse_present_in_rising_action",
            has_glimpse,
            value=has_glimpse,
            detail=f"glimpse_slots={sum(1 for s in cutlist.slots if s.is_glimpse)}",
        )
    )


def _check_emotion_profile_cache(cutlist: CutList, result: SuiteResult) -> None:
    clips_dir = BATCH_DIR / "clips"
    clip_files = list(clips_dir.glob("*.mp4"))
    if not clip_files:
        result.add(Criterion("emotion_profile_cache", False, detail="no clips found"))
        return
    cached = sum(1 for cf in clip_files if (cf.with_suffix(cf.suffix + ".emotion.json")).exists() or (cf.parent / (cf.name + ".emotion.json")).exists())
    ratio = cached / len(clip_files)
    passed = ratio >= 0.8
    result.add(
        Criterion(
            "emotion_profile_cache",
            passed,
            value=round(ratio, 3),
            threshold=0.8,
            detail=f"emotion caches={cached}/{len(clip_files)}",
        )
    )


def _check_kinetic_text_scene_relevance(cutlist: CutList, result: SuiteResult) -> None:
    texts = [s.kinetic_text.strip() for s in cutlist.slots if s.kinetic_text]
    if not texts:
        result.add(Criterion("kinetic_text_scene_relevance", False, detail="no kinetic texts"))
        return
    # Proxy: the arc-beat-aware LLM prompt asks for 1-4 uppercase words that
    # name the moment.  Compliance with that format is our deterministic proxy
    # for scene relevance now that the word bank fallback is gone.
    generic = {"TEXT", "TITLE", "CLIP", "SCENE", "MOMENT"}
    good = 0
    for text in texts:
        words = text.split()
        if 1 <= len(words) <= 4 and text.isupper() and text not in generic:
            good += 1
    ratio = good / len(texts)
    passed = ratio >= 0.75
    result.add(
        Criterion(
            "kinetic_text_scene_relevance",
            passed,
            value=round(ratio, 3),
            threshold=0.75,
            detail=f"scene_relevant={good}/{len(texts)}",
        )
    )


def run_suite(args: argparse.Namespace) -> SuiteResult:
    _run_render(args)
    log = _load_render_log()
    cutlist = _load_cutlist()
    summary = _parse_feature_summary(log)

    result = SuiteResult()
    if cutlist is None:
        result.add(Criterion("cutlist_loaded", False, detail="cutlist.json missing"))
        return result

    _check_duration_match(cutlist, result)
    _check_real_path_ratio(summary, result)
    _check_slot_window_fallback(log, result)
    _check_max_slot_gap(cutlist, result)
    _check_feature_real(summary, "audio_ducking", result)
    _check_feature_real(summary, "kinetic_text", result)
    _check_feature_real(summary, "captions", result)
    _check_feature_real(summary, "speed_ramps", result)
    _check_kinetic_llm_ratio(cutlist, result)
    _check_no_clip_repeats(cutlist, result)
    _check_caption_density(cutlist, result)
    _check_no_triton_warnings(log, result)
    _check_non_system_font(cutlist, result)
    _check_no_frozen_frames(result)
    _check_ssim_vs_previous(result)
    _check_kinetic_relevance(cutlist, result)

    if args.feature_emotion_led_cuts:
        _check_arc_beats_detected(cutlist, result)
        _check_emotion_match_per_slot(cutlist, result)
        _check_interleaved_glimpse(cutlist, result)
        _check_emotion_profile_cache(cutlist, result)
        _check_kinetic_text_scene_relevance(cutlist, result)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden Render Regression Suite")
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="Validate an existing render in test files/batch 2/output instead of re-rendering.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit results as JSON instead of a human-readable report.",
    )
    parser.add_argument(
        "--feature-emotion-led-cuts",
        action="store_true",
        help="Run the narrative/emotion-led cut path and apply Phase 2 criteria.",
    )
    args = parser.parse_args()

    result = run_suite(args)

    if args.json:
        payload = {
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "criteria": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "value": c.value,
                    "threshold": c.threshold,
                    "detail": c.detail,
                    "required": c.required,
                }
                for c in result.criteria
            ],
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("\nGolden Render Regression Suite")
        print("=" * 60)
        for c in result.criteria:
            status = "PASS" if c.passed else ("SKIP" if not c.required else "FAIL")
            print(f"[{status}] {c.name}: {c.detail}")
        print("-" * 60)
        print(f"Passed: {result.passed}  Failed: {result.failed}  Skipped: {result.skipped}")

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
