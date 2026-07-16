#!/usr/bin/env python3
"""Targeted verification for the P0.2 fade-through-black compiler fix.

Renders a two-slot timeline that reproduces the failing boundary pattern:
left slot ends in a hard cut; right slot asks for a fade-in. Before the fix
the compiler treated the pair as a hard cut and the right slot faded up from
black. After the fix the compiler collapses the pair into a dissolve
crossfade, so the boundary frame is a direct blend and must not be black.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "render-worker" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "shared-py" / "src"))

from render_worker.compiler import compile_timeline  # noqa: E402
from shared_py.models import CutList, CutListGlobals, RenderConfig, Slot  # noqa: E402

BATCH_DIR = REPO_ROOT / "test files" / "batch 2" / "clips"
OUTPUT_PATH = REPO_ROOT / ".tmp" / "t15_black_frame_check.mp4"


def _frame_mean(path: Path, t: float) -> float:
    tmp = REPO_ROOT / ".tmp" / f"t15_frame_{t:.3f}.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", str(path), "-frames:v", "1", "-q:v", "2", str(tmp)],
        check=True,
        capture_output=True,
    )
    img = np.array(Image.open(tmp).convert("L"))
    return float(img.mean())


def main() -> int:
    # Choose source windows that are well inside the clips so this test isolates
    # the transition logic rather than source fade-outs at clip boundaries.
    left_clip = "Cyberpunk Edgerunners - S01E06 (72).mp4"
    right_clip = "Cyberpunk Edgerunners - S01E07 (20).mp4"
    left_path = BATCH_DIR / left_clip
    right_path = BATCH_DIR / right_clip
    if not left_path.exists() or not right_path.exists():
        print(f"Missing clips: {left_path.exists()=} {right_path.exists()=}")
        return 1

    left_duration = 2.0
    slots = [
        Slot(
            index=0,
            start_s=0.0,
            duration_s=left_duration,
            beat_index=0,
            section="verse",
            target_shot_type="medium",
            subject_hint="character",
            motion_hint="static",
            energy_level=0.5,
            transition_out="hard_cut",
            transition_in="hard_cut",
            selected_clip_id="left",
            source_window_start_s=0.0,
        ),
        Slot(
            index=1,
            start_s=left_duration,
            duration_s=2.0,
            beat_index=1,
            section="verse",
            target_shot_type="medium",
            subject_hint="character",
            motion_hint="static",
            energy_level=0.5,
            transition_out="hard_cut",
            transition_in="fade",
            selected_clip_id="right",
            source_window_start_s=0.0,
        ),
    ]
    cutlist = CutList(
        globals=CutListGlobals(total_duration_s=left_duration + 2.0, tempo_bpm=110.0),
        slots=slots,
    )
    clip_path_map = {"left": str(left_path), "right": str(right_path)}
    config = RenderConfig(
        output_path=str(OUTPUT_PATH),
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="libx264",
        video_preset="ultrafast",
        video_crf=28,
        use_nvenc=False,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = compile_timeline(cutlist, clip_path_map, str(OUTPUT_PATH), config, style_tier="full_remix")
    print(f"Rendered: {result}")

    boundary = left_duration
    samples = [boundary - 0.15, boundary - 0.05, boundary, boundary + 0.05, boundary + 0.15]
    print(f"Boundary at t={boundary:.3f}s")
    ok = True
    for t in samples:
        mean = _frame_mean(Path(result), max(0.0, t))
        status = "OK" if mean > 10.0 else "DARK"
        if mean <= 10.0:
            ok = False
        print(f"  t={t:+.2f}s mean={mean:7.3f} {status}")
    if not ok:
        print("FAIL: boundary frame is black (fade-through-black still present)")
        return 1
    print("PASS: boundary is a direct dissolve, no fade-through-black")
    return 0


if __name__ == "__main__":
    sys.exit(main())
